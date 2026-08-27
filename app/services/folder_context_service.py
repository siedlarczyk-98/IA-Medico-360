"""
Pastas como projetos: contexto entre conversas da mesma pasta.

Uma conversa iniciada dentro de uma pasta pode usar as OUTRAS conversas daquela
pasta como contexto. A recuperação é sob demanda e por similaridade — só os
trechos relevantes à pergunta atual entram no prompt.

Por que não injetar a pasta inteira: uma pasta de acompanhamento acumula dezenas
de conversas. Injetar tudo estoura a janela de contexto, sobe o custo por
mensagem sem teto, e afoga o caso atual em ruído de casos parecidos.

**A garantia que mais importa aqui é o isolamento.** A busca cruza conversas, o
que é exatamente o tipo de recurso que vaza dado de um paciente para a discussão
de outro se o filtro estiver frouxo. Todo caminho de leitura filtra por
`user_id` E `folder_id`, e há teste dedicado em `tests/test_folder_context.py`.
"""

import logging
from uuid import UUID

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.http_client import get_client
from app.models.models import Conversation, Interaction, MessageEmbedding

logger = logging.getLogger(__name__)
settings = get_settings()

# Mesmo modelo do cache semântico — vetores de espaços diferentes não são
# comparáveis, e usar dois modelos criaria dois índices incompatíveis.
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536

# Similaridade mínima para um trecho entrar no contexto.
#
# Deliberadamente MAIS FROUXO que o 0.88 do cache semântico, porque a pergunta é
# outra: o cache precisa de quase-identidade (servir a resposta errada é grave),
# a recuperação precisa de relevância (um trecho meio relacionado ainda ajuda, e
# vem rotulado como vindo de outra conversa). Número escolhido, não medido —
# ver docs/debitos.md.
SIMILARITY_THRESHOLD = 0.72

# Teto de trechos injetados. Cada trecho consome orçamento de contexto que
# poderia ser da própria conversa.
MAX_TRECHOS = 4

# Caracteres por trecho indexado. Trechos muito longos diluem o embedding —
# o vetor médio de um texto grande não representa bem nenhuma parte dele.
MAX_CHARS_POR_TRECHO = 2000

# Teto de trechos indexados numa passada. Limita o custo da primeira pergunta
# feita numa pasta que já tinha conversas.
MAX_INDEXAR_POR_VEZ = 60


async def _embed_batch(client: httpx.AsyncClient, textos: list[str]) -> list[list[float]]:
    """
    Embute vários textos numa chamada só.

    A API aceita lista em `input` e cobra por token, não por requisição —
    indexar 40 trechos um a um seria 40 viagens de rede pelo mesmo preço.
    """
    if not textos:
        return []
    resp = await client.post(
        "https://api.openai.com/v1/embeddings",
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        json={"model": EMBEDDING_MODEL, "input": [t[:8000] for t in textos]},
        timeout=30,
    )
    resp.raise_for_status()
    dados = resp.json()["data"]
    # A API devolve `index` em cada item; ordenar por ele evita depender da
    # ordem de chegada para casar embedding com texto.
    return [item["embedding"] for item in sorted(dados, key=lambda d: d["index"])]


async def _turnos_nao_indexados(db: AsyncSession, user_id: UUID, folder_id: UUID) -> list[dict]:
    """
    Trechos das conversas da pasta que ainda não estão no índice.

    Filtra por dono e por pasta já aqui: o que não é do usuário nunca chega a
    ser candidato a indexação, muito menos a recuperação.
    """
    resultado = await db.execute(
        select(Interaction)
        .join(Conversation, Interaction.conversation_id == Conversation.id)
        .where(
            Conversation.user_id == user_id,
            Conversation.folder_id == folder_id,
            Conversation.status.is_(True),
            Interaction.status == "completed",
        )
        .order_by(Interaction.started_at.desc())
        .limit(MAX_INDEXAR_POR_VEZ)
        # As respostas são lidas logo abaixo; sem o eager load isso viraria uma
        # consulta por interação dentro do laço.
        .options(selectinload(Interaction.responses))
    )
    interacoes = list(resultado.scalars().all())
    if not interacoes:
        return []

    ja_indexados = await db.execute(
        select(MessageEmbedding.interaction_id, MessageEmbedding.role).where(
            MessageEmbedding.interaction_id.in_([i.id for i in interacoes])
        )
    )
    existentes = set(ja_indexados.all())

    pendentes: list[dict] = []
    for interaction in interacoes:
        if interaction.prompt_text and (interaction.id, "user") not in existentes:
            pendentes.append({
                "interaction": interaction,
                "role": "user",
                "content": interaction.prompt_text[:MAX_CHARS_POR_TRECHO],
            })

        if (interaction.id, "assistant") in existentes:
            continue
        for resp in sorted(interaction.responses, key=lambda r: r.created_at):
            if resp.error_message or not resp.response_text:
                continue
            pendentes.append({
                "interaction": interaction,
                "role": "assistant",
                "content": resp.response_text[:MAX_CHARS_POR_TRECHO],
            })
            break

    return pendentes


async def indexar_pasta(db: AsyncSession, user_id: UUID, folder_id: UUID) -> int:
    """
    Garante que as conversas da pasta estão indexadas. Devolve quantos entraram.

    Indexação preguiçosa, e não na escrita de cada mensagem, por dois motivos:
    uma conversa pode ser MOVIDA para dentro de uma pasta depois de pronta (e
    então nunca teria sido indexada), e conversas fora de pasta não custam
    embedding nenhum — só quem usa pasta como projeto paga por isso.

    Falha silenciosa: sem índice a resposta sai sem contexto da pasta, que é
    pior que o ideal mas melhor que não responder.
    """
    try:
        pendentes = await _turnos_nao_indexados(db, user_id, folder_id)
        if not pendentes:
            return 0

        client = get_client()
        vetores = await _embed_batch(client, [p["content"] for p in pendentes])

        for pendente, vetor in zip(pendentes, vetores, strict=True):
            db.add(MessageEmbedding(
                interaction_id=pendente["interaction"].id,
                conversation_id=pendente["interaction"].conversation_id,
                user_id=user_id,
                role=pendente["role"],
                content=pendente["content"],
                embedding=vetor,
            ))
        await db.flush()
        return len(pendentes)

    except Exception as exc:
        logger.warning("[PastaContexto] Falha ao indexar pasta %s: %s", folder_id, exc)
        return 0


async def recuperar_trechos(
    db: AsyncSession,
    user_id: UUID,
    folder_id: UUID,
    conversation_id: UUID | None,
    pergunta: str,
    limite: int = MAX_TRECHOS,
) -> list[dict]:
    """
    Trechos relevantes das OUTRAS conversas da pasta.

    Exclui a conversa atual: o que foi dito nela já entra pelo histórico
    próprio, e recuperá-lo de novo duplicaria contexto e gastaria orçamento.
    """
    try:
        client = get_client()
        vetores = await _embed_batch(client, [pergunta])
        if not vetores:
            return []
        vetor_str = "[" + ",".join(str(x) for x in vetores[0]) + "]"

        # SQL cru pelo operador de distância do pgvector. Os filtros de dono e
        # pasta ficam DENTRO da consulta, nunca aplicados depois em Python.
        resultado = await db.execute(
            text("""
                SELECT me.content,
                       me.role,
                       c.title AS conversa,
                       1 - (me.embedding <=> CAST(:emb AS vector)) AS sim
                  FROM message_embeddings me
                  JOIN conversations c ON c.id = me.conversation_id
                 WHERE me.user_id = :user_id
                   AND c.user_id = :user_id
                   AND c.folder_id = :folder_id
                   AND c.status IS TRUE
                   -- CAST(... AS uuid) e não `::uuid`: os dois-pontos duplos
                   -- colidem com a sintaxe de parâmetro nomeado do SQLAlchemy.
                   AND (CAST(:conversation_id AS uuid) IS NULL
                        OR me.conversation_id <> CAST(:conversation_id AS uuid))
                 ORDER BY me.embedding <=> CAST(:emb AS vector)
                 LIMIT :limite
            """),
            {
                "emb": vetor_str,
                "user_id": str(user_id),
                "folder_id": str(folder_id),
                "conversation_id": str(conversation_id) if conversation_id else None,
                "limite": limite,
            },
        )
        return [
            {"content": linha.content, "role": linha.role, "conversa": linha.conversa, "sim": linha.sim}
            for linha in resultado.fetchall()
            if linha.sim >= SIMILARITY_THRESHOLD
        ]

    except Exception as exc:
        logger.warning("[PastaContexto] Falha ao recuperar da pasta %s: %s", folder_id, exc)
        return []


def formatar_bloco(trechos: list[dict]) -> str:
    """
    Formata os trechos como um bloco identificado.

    A identificação por conversa de origem não é enfeite: sem ela o modelo
    apresenta como se fosse do caso atual algo que veio de outro paciente da
    mesma pasta, e o médico não tem como perceber.
    """
    if not trechos:
        return ""

    linhas = [
        "[Contexto de outras conversas desta pasta — material de APOIO, "
        "pode ser de outro paciente ou outro caso. Não trate como parte do caso atual.]"
    ]
    for trecho in trechos:
        quem = "Médico" if trecho["role"] == "user" else "Assistente"
        conversa = trecho.get("conversa") or "conversa sem título"
        linhas.append(f'- (da conversa "{conversa}", {quem}): {trecho["content"]}')
    return "\n".join(linhas)


async def contexto_da_pasta(
    db: AsyncSession,
    user_id: UUID,
    conversation_id: UUID | None,
    pergunta: str,
) -> str:
    """
    Ponto de entrada: devolve o bloco de contexto da pasta, ou string vazia.

    Vazio é o caminho normal e não é erro — conversa fora de pasta, pasta com
    uma conversa só, ou nada suficientemente parecido com a pergunta.
    """
    if not conversation_id:
        return ""

    conv = (await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )).scalar_one_or_none()

    if conv is None or conv.folder_id is None:
        return ""

    await indexar_pasta(db, user_id, conv.folder_id)
    trechos = await recuperar_trechos(db, user_id, conv.folder_id, conversation_id, pergunta)
    return formatar_bloco(trechos)
