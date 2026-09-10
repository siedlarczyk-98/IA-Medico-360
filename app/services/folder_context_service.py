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
import re
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

# ── Perguntas agregadoras ────────────────────────────────────────────────────
#
# "Monte um roteiro de aula com as informações que constam nesta pasta."
#
# Esta pergunta pede o CONJUNTO, e a busca por similaridade é a ferramenta
# errada para ela. O texto não fala de tema nenhum — é uma instrução sobre o
# que fazer — então o vetor dela não se parece com o de nenhuma conversa da
# pasta, por mais pertinente que a conversa seja.
#
# Medido na pasta "Aulas" do caso que motivou isto, com três conversas dentro:
#
#   0.359  resposta sobre complicações cardiovasculares do diabetes
#   0.240  resposta sobre PCR extra-hospitalar (Data Ocean)
#   0.216  pergunta sobre PCR extra-hospitalar
#   0.159  pergunta sobre complicações do diabetes
#
# Com o piso em 0.25, entrou UM trecho e a conversa inteira do Data Ocean
# ficou de fora por um centésimo. O médico pediu para juntar duas conversas e
# recebeu uma resposta construída sobre metade do material, sem nada na tela
# que indicasse a falta.
#
# Baixar o piso não é a correção: ele existe para as pastas CLÍNICAS, onde
# trazer o trecho errado significa material de outro paciente na discussão
# atual. O que muda aqui é o CRITÉRIO — quando a pergunta é agregadora, a
# relevância é dada pela pasta (o médico já disse "desta pasta"), e o piso sai
# do caminho. O teto de trechos continua valendo, e o orçamento de contexto
# em `context_budget` continua sendo o limite real.
_PADRAO_AGREGADOR = re.compile(
    r"""
    (?:
        # Referência explícita ao continente: "nesta pasta", "deste projeto".
        \b(?:nesta|nessa|desta|dessa|na|da)\s+pasta\b
      | \b(?:neste|nesse|deste|desse|no|do)\s+projeto\b
        # Referência ao trabalho conjunto: "o que discutimos aqui".
      | \b(?:discutimos|conversamos|falamos|vimos|levantamos)\b
        # Quantificador sobre as conversas: "todas as conversas", "tudo que".
      | \btodas?\s+as\s+(?:conversas|discuss(?:ão|ões)|pesquisas)\b
      | \btudo\s+(?:que|o\s+que)\b
        # Verbo de consolidação seguido do material: "junte o material".
      | \b(?:junt(?:e|ar|ando)|consolid(?:e|ar|ando)|compil(?:e|ar|ando)
           |unifi(?:que|car|cando)|re[uú]n(?:a|ir|indo))\b
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Teto de trechos numa pergunta agregadora. Mais alto que `MAX_TRECHOS` porque
# o objetivo aqui é COBRIR a pasta, não escolher o mais parecido — mas ainda um
# teto: uma pasta com trinta conversas não cabe num prompt, e o corte por
# orçamento em `fit_turns_with_attachment_budget` é quem dá a palavra final.
MAX_TRECHOS_AGREGADOR = 12


def e_pergunta_agregadora(pergunta: str) -> bool:
    """
    Diz se a pergunta pede o CONJUNTO da pasta em vez de um tema dela.

    Serve para escolher o critério de recuperação, e por isso erra para o lado
    de NÃO agregar: um falso positivo injeta mais contexto do que o necessário
    (custo e ruído), enquanto um falso negativo devolve ao médico uma resposta
    que ignora silenciosamente parte do material — que é o defeito original.

    Deliberadamente uma regex, e não uma chamada de modelo: isto roda no
    caminho da resposta, antes do primeiro token, e um classificador aqui
    somaria latência a um fluxo que já mede p50 de 33s em raciocínio clínico.
    """
    return bool(pergunta and _PADRAO_AGREGADOR.search(pergunta))


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
    limite: int | None = None,
) -> list[dict]:
    """
    Trechos relevantes das OUTRAS conversas da pasta.

    Exclui a conversa atual: o que foi dito nela já entra pelo histórico
    próprio, e recuperá-lo de novo duplicaria contexto e gastaria orçamento.

    Dois regimes, escolhidos por `e_pergunta_agregadora`:

    - **Tema** (o normal): ranqueia por similaridade e corta no piso. "Qual
      anti-hipertensivo escolher?" deve trazer o que se parece com isso, e o
      piso é a proteção contra material de outro paciente entrar de carona.
    - **Agregador**: "monte um roteiro com o que está nesta pasta". O médico já
      declarou o escopo; a similaridade não sabe medir isso e cortaria as
      conversas cuja redação não se parece com a instrução. Aqui o piso sai do
      caminho e o teto sobe — ver `_PADRAO_AGREGADOR`.

    Em AMBOS os regimes a seleção é distribuída entre as conversas da pasta:
    um trecho de cada uma antes do segundo trecho de qualquer uma. Sem isso,
    uma conversa longa ocupava os quatro lugares e as outras sumiam — que é o
    oposto do que "contexto da pasta" promete.
    """
    agregador = e_pergunta_agregadora(pergunta)
    if limite is None:
        limite = MAX_TRECHOS_AGREGADOR if agregador else MAX_TRECHOS
    piso = 0.0 if agregador else SIMILARITY_FLOOR

    try:
        client = get_client()
        vetores = await _embed_batch(client, [pergunta])
        if not vetores:
            return []
        vetor_str = "[" + ",".join(str(x) for x in vetores[0]) + "]"

        # SQL cru pelo operador de distância do pgvector. Os filtros de dono e
        # pasta ficam DENTRO da consulta, nunca aplicados depois em Python.
        #
        # `rank` numera os trechos DENTRO de cada conversa por similaridade, e
        # a ordenação externa põe todos os primeiros colocados na frente. O
        # efeito é rodízio: cada conversa da pasta é representada antes que
        # qualquer uma repita. O piso continua sendo aplicado antes disso, na
        # cláusula WHERE — cobrir a pasta não é motivo para injetar lixo.
        resultado = await db.execute(
            text("""
                WITH candidatos AS (
                    SELECT me.content,
                           me.role,
                           me.conversation_id,
                           c.title AS conversa,
                           1 - (me.embedding <=> CAST(:emb AS vector)) AS sim,
                           ROW_NUMBER() OVER (
                               PARTITION BY me.conversation_id
                               ORDER BY me.embedding <=> CAST(:emb AS vector)
                           ) AS rank
                      FROM message_embeddings me
                      JOIN conversations c ON c.id = me.conversation_id
                     WHERE me.user_id = :user_id
                       AND c.user_id = :user_id
                       AND c.folder_id = :folder_id
                       AND c.status IS TRUE
                       -- CAST(... AS uuid) e não `::uuid`: os dois-pontos
                       -- duplos colidem com a sintaxe de parâmetro nomeado
                       -- do SQLAlchemy.
                       AND (CAST(:conversation_id AS uuid) IS NULL
                            OR me.conversation_id <> CAST(:conversation_id AS uuid))
                       AND 1 - (me.embedding <=> CAST(:emb AS vector)) >= :piso
                )
                SELECT content, role, conversa, sim
                  FROM candidatos
                 ORDER BY rank, sim DESC
                 LIMIT :limite
            """),
            {
                "emb": vetor_str,
                "user_id": str(user_id),
                "folder_id": str(folder_id),
                "conversation_id": str(conversation_id) if conversation_id else None,
                "piso": piso,
                "limite": limite,
            },
        )
        selecionados = [
            {"content": linha.content, "role": linha.role, "conversa": linha.conversa, "sim": linha.sim}
            for linha in resultado.fetchall()
        ]
        # Observabilidade: sem isto, "não veio contexto" e "veio contexto ruim"
        # são indistinguíveis de fora, e foi essa cegueira que fez o limiar
        # errado passar despercebido até a homologação. O regime entra no log
        # porque ele muda o piso: sem ele, uma similaridade de 0.16 na linha
        # pareceria um piso quebrado.
        regime = "agregador" if agregador else "tema"
        if selecionados:
            logger.info(
                "[PastaContexto] pasta=%s regime=%s trechos=%d conversas=%d similaridades=%s",
                folder_id, regime, len(selecionados),
                len({t["conversa"] for t in selecionados}),
                [round(t["sim"], 3) for t in selecionados],
            )
        else:
            logger.info(
                "[PastaContexto] pasta=%s regime=%s nenhum trecho acima do piso",
                folder_id, regime,
            )
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


# Teto do texto de evolução injetado no prompt, em caracteres.
#
# Ele é enviado em TODA mensagem da pasta — é essa a decisão de produto: o
# médico escreveu, ele espera que o modelo saiba. O custo disso é linear no
# tamanho do campo, então o teto existe.
#
# 8000 caracteres ≈ 2500 tokens pela razão medida em `context_budget`, o que
# cabe folgado ao lado do histórico (6000) e dos anexos (12000) sem que a soma
# se aproxime da janela de qualquer modelo em uso. É também mais espaço do que
# uma evolução clínica costuma ocupar — o limite é rede de segurança contra um
# prontuário inteiro colado no campo, não um orçamento a ser disputado.
#
# A API recusa acima disto com 422 (`MAX_CHARS_EVOLUCAO` em `folders.py`), então
# um texto maior só chega aqui vindo de dado gravado antes do limite existir.
MAX_CHARS_EVOLUCAO_NO_PROMPT = 8000


FOLDER_KIND_CLINICAL = "clinical"
FOLDER_KIND_GENERAL = "general"
FOLDER_KINDS: frozenset[str] = frozenset({FOLDER_KIND_CLINICAL, FOLDER_KIND_GENERAL})

# Cabeçalho do bloco por tipo de pasta.
#
# Isto não é cosmético. A primeira versão injetava SEMPRE "Evolução do paciente
# ... Vale como parte do caso atual", porque o campo nasceu supondo que toda
# pasta é de um paciente. Numa pasta "Artigos para ler", esse cabeçalho faz o
# modelo tratar um plano de leitura como a evolução de alguém — e responder
# clinicamente sobre o que não é um caso.
#
# O texto de `general` evita de propósito qualquer palavra que sugira paciente,
# e diz o que aquilo É: escopo declarado pelo médico para o trabalho da pasta.
_CABECALHO_POR_TIPO: dict[str, str] = {
    FOLDER_KIND_CLINICAL: (
        "[Evolução do paciente / contexto do caso — informada pelo médico nesta "
        "pasta. Vale como parte do caso atual.]"
    ),
    FOLDER_KIND_GENERAL: (
        "[Contexto desta pasta — objetivo e escopo declarados pelo médico. "
        "NÃO é um caso clínico nem descreve um paciente.]"
    ),
}


def formatar_bloco_evolucao(
    clinical_context: str | None,
    folder_kind: str = FOLDER_KIND_CLINICAL,
) -> str:
    """
    Formata a evolução declarada pelo médico como bloco de contexto.

    A marcação é o ponto, e é DELIBERADAMENTE diferente da de
    `formatar_bloco`. Aquele bloco avisa "pode ser de outro paciente, não trate
    como parte do caso atual", porque traz trechos recuperados por similaridade
    de outras conversas. Este é o contrário: foi o médico que escreveu, sobre o
    paciente desta pasta, e vale como parte do caso.

    Reaproveitar a marcação de apoio entregaria ao modelo um texto autoritativo
    com um aviso dizendo para não confiar nele — e o modelo obedeceria.

    O cabeçalho segue `folder_kind`: numa pasta não clínica, anunciar o texto
    como "evolução do paciente" faria o modelo inventar um paciente que não
    existe. Um tipo desconhecido cai no cabeçalho clínico — é o default da
    coluna e o mais conservador: descreve o texto como contexto do caso em vez
    de negar que ele seja clínico.
    """
    if not clinical_context or not clinical_context.strip():
        return ""

    texto = clinical_context.strip()
    if len(texto) > MAX_CHARS_EVOLUCAO_NO_PROMPT:
        texto = (
            texto[:MAX_CHARS_EVOLUCAO_NO_PROMPT]
            + "\n[...evolução truncada por limite de tamanho]"
        )

    cabecalho = _CABECALHO_POR_TIPO.get(folder_kind, _CABECALHO_POR_TIPO[FOLDER_KIND_CLINICAL])
    return f"{cabecalho}\n{texto}"


async def evolucao_da_pasta(
    db: AsyncSession,
    user_id: UUID,
    conversation_id: UUID | None,
    folder_id: UUID | None = None,
) -> str:
    """
    Devolve o bloco de evolução da pasta em que a mensagem está, ou vazio.

    Usa o mesmo `_resolver_pasta` do contexto por similaridade — inclusive o
    caso da conversa NOVA, em que a pasta vem do corpo da requisição e ainda
    não há `conversation_id`. A checagem de posse mora lá.

    Vazio é o caminho normal: conversa fora de pasta, ou pasta sem evolução
    preenchida (que é o caso da maioria — uma pasta pode ser só organização
    por tema).
    """
    pasta = await _resolver_pasta(db, user_id, conversation_id, folder_id)
    if pasta is None:
        return ""

    # O filtro por `user_id` é redundante com `_resolver_pasta`, e fica: é uma
    # leitura de dado clínico de paciente, e uma segunda barreira aqui custa
    # nada e protege de um caminho futuro que resolva a pasta de outro jeito.
    resultado = await db.execute(
        select(Folder.clinical_context, Folder.folder_kind).where(
            Folder.id == pasta,
            Folder.user_id == user_id,
        )
    )
    linha = resultado.one_or_none()
    if linha is None:
        return ""
    return formatar_bloco_evolucao(linha.clinical_context, linha.folder_kind)
