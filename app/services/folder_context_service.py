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

import asyncio
import logging
from uuid import UUID

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.http_client import get_client
from app.models.models import Conversation, Folder, Interaction, MessageEmbedding

logger = logging.getLogger(__name__)
settings = get_settings()

# Mesmo modelo do cache semântico — vetores de espaços diferentes não são
# comparáveis, e usar dois modelos criaria dois índices incompatíveis.
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536

# Piso de similaridade — porta contra lixo, NÃO critério de relevância.
#
# A relevância aqui é dada pela PASTA, não pelo vetor: uma pasta é o projeto de
# um paciente ou de um tema, e quase tudo dentro dela é potencialmente
# pertinente. A similaridade serve para RANQUEAR o que entra no orçamento
# limitado, não para decidir se algo é do assunto.
#
# O piso é baixo de propósito. A primeira versão usava 0.72, ancorado no 0.88 do
# cache semântico — comparação errada, e medida em produção: a pergunta
# "existe alguma contraindicação para o paciente Jorge?" contra a evolução que
# diz "Jorge, 58 anos, HAS em acompanhamento" pontuou 0.516, e nada passava.
#
# Os dois números medem regimes diferentes: o cache compara dois prompts CURTOS
# quase idênticos (0.88 é apropriado ali); aqui compara uma pergunta curta com
# um documento clínico longo, onde 0.5 já é forte. Cosseno absoluto não é
# comparável entre esses dois usos.
SIMILARITY_FLOOR = 0.25

# Nome antigo mantido para não quebrar import de fora — ver o comentário acima
# sobre por que a semântica mudou de "limiar" para "piso".
SIMILARITY_THRESHOLD = SIMILARITY_FLOOR

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

    Preguiçosa, mas NÃO no caminho da resposta: quem chama é
    `agendar_indexacao`, em background. Rodando inline, uma pasta ativa fazia o
    médico esperar o embedding de todos os turnos acumulados antes do primeiro
    token — e o custo crescia com o uso da pasta, que é o oposto do desejado.

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


# Referência forte às tarefas em voo. `asyncio` só guarda referência fraca para
# a task, então sem este conjunto o coletor de lixo pode recolher a indexação no
# meio do caminho — e a falha seria silenciosa, que é o pior modo possível aqui.
# Serve também de trava: duas perguntas seguidas na mesma pasta não devem
# disparar duas indexações concorrentes do mesmo conjunto pendente.
_indexacoes_em_voo: dict[UUID, asyncio.Task] = {}


async def _indexar_com_sessao_propria(user_id: UUID, folder_id: UUID) -> None:
    """
    Roda a indexação fora da requisição, com sessão própria.

    A sessão da requisição NÃO pode ser reaproveitada: `AsyncSession` não é
    segura para uso concorrente, e a requisição vai dar commit no meio — a
    indexação entraria por carona numa transação que não controla.
    """
    async with async_session_factory() as db:
        try:
            quantos = await indexar_pasta(db, user_id, folder_id)
            if quantos:
                await db.commit()
                logger.info(
                    "[PastaContexto] Pasta %s indexada em background: %d turnos",
                    folder_id, quantos,
                )
        except Exception:
            await db.rollback()
            raise


def agendar_indexacao(user_id: UUID, folder_id: UUID) -> asyncio.Task | None:
    """
    Dispara a indexação da pasta em background e devolve na hora.

    Devolve a task existente se já houver uma em voo para a mesma pasta, ou
    None se não houver event loop (chamada fora de contexto async).
    """
    em_voo = _indexacoes_em_voo.get(folder_id)
    if em_voo is not None and not em_voo.done():
        return em_voo

    try:
        tarefa = asyncio.create_task(
            _indexar_com_sessao_propria(user_id, folder_id),
            name=f"indexar-pasta-{folder_id}",
        )
    except RuntimeError:  # pragma: no cover — sem loop rodando
        return None

    _indexacoes_em_voo[folder_id] = tarefa

    def _encerrar(t: asyncio.Task) -> None:
        _indexacoes_em_voo.pop(folder_id, None)
        # Uma indexação que falha não pode derrubar nada nem virar
        # "Task exception was never retrieved" solto no log.
        if not t.cancelled() and t.exception() is not None:
            logger.warning(
                "[PastaContexto] Indexação em background da pasta %s falhou: %s",
                folder_id, t.exception(),
            )

    tarefa.add_done_callback(_encerrar)
    return tarefa


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
        selecionados = [
            {"content": linha.content, "role": linha.role, "conversa": linha.conversa, "sim": linha.sim}
            for linha in resultado.fetchall()
            if linha.sim >= SIMILARITY_FLOOR
        ]
        # Observabilidade: sem isto, "não veio contexto" e "veio contexto ruim"
        # são indistinguíveis de fora, e foi essa cegueira que fez o limiar
        # errado passar despercebido até a homologação.
        if selecionados:
            logger.info(
                "[PastaContexto] pasta=%s trechos=%d similaridades=%s",
                folder_id, len(selecionados), [round(t["sim"], 3) for t in selecionados],
            )
        else:
            logger.info("[PastaContexto] pasta=%s nenhum trecho acima do piso", folder_id)
        return selecionados

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


async def _resolver_pasta(
    db: AsyncSession,
    user_id: UUID,
    conversation_id: UUID | None,
    folder_id: UUID | None,
) -> UUID | None:
    """
    Descobre em que pasta a mensagem está sendo escrita.

    Dois caminhos, e ignorar o segundo era o bug: numa conversa JÁ EXISTENTE a
    pasta vem da conversa, mas numa conversa NOVA dentro de uma pasta a
    conversa ainda não existe — a primeira mensagem chega com
    `conversation_id=None` e a pasta vem separada, no corpo da requisição.

    Esse segundo caso é justamente o mais comum do recurso: o médico abre uma
    conversa dentro da pasta do paciente e pergunta sobre o material que já
    está ali. Antes, ele era exatamente o caso que saía sem contexto nenhum.
    """
    if conversation_id:
        conv = (await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )).scalar_one_or_none()
        return conv.folder_id if conv else None

    if not folder_id:
        return None

    # A pasta veio do cliente: confirmar a posse antes de usá-la. As consultas
    # seguintes já filtram por `user_id`, então isto é defesa em profundidade —
    # mas uma pasta alheia não deve nem chegar a ser indexada.
    dono = (await db.execute(
        select(Folder.id).where(Folder.id == folder_id, Folder.user_id == user_id)
    )).scalar_one_or_none()
    return dono


async def contexto_da_pasta(
    db: AsyncSession,
    user_id: UUID,
    conversation_id: UUID | None,
    pergunta: str,
    folder_id: UUID | None = None,
) -> str:
    """
    Ponto de entrada: devolve o bloco de contexto da pasta, ou string vazia.

    Vazio é o caminho normal e não é erro — conversa fora de pasta, pasta com
    uma conversa só, ou nada suficientemente parecido com a pergunta.

    A recuperação usa o índice COMO ELE ESTÁ e agenda a atualização para depois.
    O efeito visível é que os turnos ainda não indexados não entram no contexto
    desta pergunta — na prática, a primeira pergunta logo após mover uma
    conversa para a pasta não enxerga aquela conversa, e da segunda em diante
    sim. É uma troca deliberada: indexar antes de responder colocava um lote de
    embeddings no caminho do primeiro token, e a espera crescia junto com o
    tamanho da pasta, punindo justamente quem mais usa o recurso.
    """
    pasta = await _resolver_pasta(db, user_id, conversation_id, folder_id)
    if pasta is None:
        return ""

    trechos = await recuperar_trechos(db, user_id, pasta, conversation_id, pergunta)
    agendar_indexacao(user_id, pasta)
    return formatar_bloco(trechos)
