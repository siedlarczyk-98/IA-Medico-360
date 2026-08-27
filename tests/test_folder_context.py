"""
Pastas como projetos: contexto entre conversas da mesma pasta (Fase 6 / item 8).

Uma conversa dentro de uma pasta pode usar as OUTRAS conversas daquela pasta
como contexto, por similaridade com a pergunta atual.

**O bloco de isolamento é o mais importante deste arquivo.** A recuperação cruza
conversas — é exatamente o tipo de recurso que vaza dado de um paciente para a
discussão de outro se o filtro estiver frouxo. Um teste fraco aqui vale menos
que teste nenhum, porque dá falsa confiança.

Os embeddings são fabricados nos testes em vez de chamados na API: o guard de
rede bloqueia chamada externa, e o que se quer verificar é o FILTRO, não a
qualidade do modelo de embedding.

**Não apague `test_recupera_trecho_de_conversa_irma_na_mesma_pasta`.** Ele é o
canário deste arquivo. `recuperar_trechos` engole exceções e devolve lista vazia
por decisão de produto (sem contexto da pasta a resposta sai pior; sem resposta
o médico fica sem nada), o que significa que TODO teste de isolamento passa se a
consulta estiver quebrada. Só o teste positivo distingue "filtrou certo" de "não
buscou nada". Isso não é hipótese: a primeira versão desta consulta tinha um
erro de sintaxe e os dezesseis testes de isolamento passaram alegremente.
"""

from datetime import UTC, datetime

import pytest

from app.models.models import Interaction, InteractionResponse, MessageEmbedding
from app.services import folder_context_service
from app.services.folder_context_service import (
    EMBEDDING_DIMS,
    SIMILARITY_FLOOR,
    contexto_da_pasta,
    formatar_bloco,
    recuperar_trechos,
)

# asyncio_mode=auto no pytest.ini — os testes async não precisam de marca de
# módulo, e uma marca aqui pegaria também os síncronos de formatação.


def vetor(valor: float = 1.0) -> list[float]:
    """Vetor unitário no primeiro eixo, escalado — similaridade previsível."""
    v = [0.0] * EMBEDDING_DIMS
    v[0] = valor
    return v


def vetor_ortogonal() -> list[float]:
    """Similaridade cosseno ~0 contra `vetor()` — serve de 'nada a ver'."""
    v = [0.0] * EMBEDDING_DIMS
    v[1] = 1.0
    return v


async def _conversa_indexada(db, dono, folder, titulo, texto, embedding=None):
    """Cria conversa + interação + trecho indexado, tudo coerente."""
    from app.models.models import Conversation

    conv = Conversation(
        user_id=dono.id, title=titulo, feature="ORQUESTRADOR",
        status=True, folder_id=folder.id if folder else None,
    )
    db.add(conv)
    await db.flush()

    interaction = Interaction(
        conversation_id=conv.id, user_id=dono.id, feature="ORQUESTRADOR",
        mode="CLINICAL_REASONING", prompt_text=texto, status="completed",
        started_at=datetime.now(UTC), completed_at=datetime.now(UTC),
    )
    db.add(interaction)
    await db.flush()
    db.add(InteractionResponse(
        interaction_id=interaction.id, model_used="claude-sonnet-4-6",
        response_text=f"resposta sobre {texto}",
    ))
    db.add(MessageEmbedding(
        interaction_id=interaction.id,
        conversation_id=conv.id,
        user_id=dono.id,
        role="user",
        content=texto,
        embedding=embedding if embedding is not None else vetor(),
    ))
    await db.flush()
    return conv


@pytest.fixture(autouse=True)
def embedding_previsivel(monkeypatch):
    """A pergunta atual sempre vira o mesmo vetor — o alvo do teste é o filtro."""
    async def _embed(_client, textos):
        return [vetor() for _ in textos]

    monkeypatch.setattr(folder_context_service, "_embed_batch", _embed)


# ── ISOLAMENTO ───────────────────────────────────────────────────────────────

async def test_conversa_da_pasta_A_nao_recupera_trecho_da_pasta_B(
    db, user, folder_factory
):
    """Similaridade máxima e mesmo dono — só a pasta separa. Tem de bastar."""
    pasta_a = await folder_factory(user, "Pasta A")
    pasta_b = await folder_factory(user, "Pasta B")

    atual = await _conversa_indexada(db, user, pasta_a, "Caso atual", "caso em andamento")
    await _conversa_indexada(db, user, pasta_b, "Caso de outra pasta", "SEGREDO DA PASTA B")

    trechos = await recuperar_trechos(db, user.id, pasta_a.id, atual.id, "pergunta")

    assert all("SEGREDO DA PASTA B" not in t["content"] for t in trechos)


async def test_pasta_de_outro_usuario_nunca_e_alcancada(
    db, user, user_factory, folder_factory
):
    """Mesmo passando o id da pasta alheia explicitamente."""
    outro = await user_factory()
    pasta_alheia = await folder_factory(outro, "Pasta do outro")
    await _conversa_indexada(db, outro, pasta_alheia, "Caso alheio", "SEGREDO DO OUTRO MEDICO")

    trechos = await recuperar_trechos(db, user.id, pasta_alheia.id, None, "pergunta")

    assert trechos == []


async def test_trecho_de_outro_usuario_na_mesma_pasta_nao_vaza(
    db, user, user_factory, folder_factory
):
    """
    Defesa em profundidade: mesmo que um MessageEmbedding aponte para a pasta
    do usuário mas pertença a outro dono, o filtro por user_id o exclui.
    """
    outro = await user_factory()
    pasta = await folder_factory(user, "Minha pasta")
    atual = await _conversa_indexada(db, user, pasta, "Meu caso", "meu caso")

    # Registro forjado: pasta certa, dono errado.
    db.add(MessageEmbedding(
        interaction_id=(await db.execute(
            __import__("sqlalchemy").select(Interaction.id).limit(1)
        )).scalar_one(),
        conversation_id=atual.id,
        user_id=outro.id,
        role="user",
        content="SEGREDO INJETADO",
        embedding=vetor(),
    ))
    await db.flush()

    trechos = await recuperar_trechos(db, user.id, pasta.id, None, "pergunta")

    assert all("SEGREDO INJETADO" not in t["content"] for t in trechos)


async def test_conversa_apagada_sai_do_contexto(db, user, folder_factory):
    """Soft delete precisa valer aqui também, senão o apagar não apaga nada."""
    from sqlalchemy import update as sa_update

    from app.models.models import Conversation

    pasta = await folder_factory(user, "Pasta")
    atual = await _conversa_indexada(db, user, pasta, "Atual", "caso atual")
    apagada = await _conversa_indexada(db, user, pasta, "Apagada", "CONTEUDO APAGADO")

    await db.execute(
        sa_update(Conversation).where(Conversation.id == apagada.id).values(status=False)
    )
    await db.flush()

    trechos = await recuperar_trechos(db, user.id, pasta.id, atual.id, "pergunta")

    assert all("CONTEUDO APAGADO" not in t["content"] for t in trechos)


# ── Recuperação ──────────────────────────────────────────────────────────────

async def test_recupera_trecho_de_conversa_irma_na_mesma_pasta(db, user, folder_factory):
    pasta = await folder_factory(user, "Acompanhamento")
    atual = await _conversa_indexada(db, user, pasta, "Consulta de hoje", "consulta de hoje")
    await _conversa_indexada(db, user, pasta, "Consulta anterior", "EVOLUCAO ANTERIOR DO PACIENTE")

    trechos = await recuperar_trechos(db, user.id, pasta.id, atual.id, "como evoluiu?")

    assert any("EVOLUCAO ANTERIOR DO PACIENTE" in t["content"] for t in trechos)


async def test_a_propria_conversa_nao_e_recuperada(db, user, folder_factory):
    """O que foi dito nela já entra pelo histórico próprio — duplicaria contexto."""
    pasta = await folder_factory(user, "Pasta")
    atual = await _conversa_indexada(db, user, pasta, "Atual", "TEXTO DA CONVERSA ATUAL")

    trechos = await recuperar_trechos(db, user.id, pasta.id, atual.id, "pergunta")

    assert all("TEXTO DA CONVERSA ATUAL" not in t["content"] for t in trechos)


async def test_trecho_sem_relacao_fica_de_fora(db, user, folder_factory):
    """Abaixo do limiar, o trecho é ruído — e ruído afoga o caso atual."""
    pasta = await folder_factory(user, "Pasta")
    atual = await _conversa_indexada(db, user, pasta, "Atual", "atual")
    await _conversa_indexada(
        db, user, pasta, "Nada a ver", "ASSUNTO COMPLETAMENTE DIFERENTE",
        embedding=vetor_ortogonal(),
    )

    trechos = await recuperar_trechos(db, user.id, pasta.id, atual.id, "pergunta")

    assert all("ASSUNTO COMPLETAMENTE DIFERENTE" not in t["content"] for t in trechos)


async def test_respeita_o_teto_de_trechos(db, user, folder_factory):
    pasta = await folder_factory(user, "Pasta")
    atual = await _conversa_indexada(db, user, pasta, "Atual", "atual")
    for i in range(10):
        await _conversa_indexada(db, user, pasta, f"Irma {i}", f"conteudo {i}")

    trechos = await recuperar_trechos(db, user.id, pasta.id, atual.id, "pergunta", limite=3)

    assert len(trechos) <= 3


async def test_piso_e_muito_mais_baixo_que_o_limiar_do_cache():
    """
    Os dois números medem regimes diferentes e não devem convergir.

    O cache compara dois prompts CURTOS quase idênticos — 0.88 é apropriado
    ali. Aqui compara uma pergunta curta com um documento clínico longo, onde
    similaridade de 0.5 já é forte. Medido em produção: a pergunta sobre
    contraindicações do paciente pontuou 0.516 contra a evolução DELE MESMO, e
    o limiar original de 0.72 descartava tudo.
    """
    from app.services.semantic_cache_service import SIMILARITY_THRESHOLD as CACHE_THRESHOLD

    assert SIMILARITY_FLOOR < 0.5, (
        "piso acima de 0.5 descarta material claramente pertinente — "
        "ver a medição que motivou este teste"
    )
    assert SIMILARITY_FLOOR < CACHE_THRESHOLD


def test_similaridade_realista_entre_pergunta_e_documento_passa():
    """
    Trava o valor com um caso real: 0.516 foi a similaridade medida entre
    "existe alguma contraindicação para o paciente Jorge?" e a evolução que
    diz "Jorge, 58 anos, HAS em acompanhamento". Isso TEM de entrar.
    """
    assert 0.516 >= SIMILARITY_FLOOR


# ── Formatação do bloco ──────────────────────────────────────────────────────

def test_bloco_identifica_a_conversa_de_origem():
    """
    Sem identificação, o modelo apresenta como sendo do caso atual algo que veio
    de outro paciente da mesma pasta — e o médico não tem como perceber.
    """
    bloco = formatar_bloco([
        {"content": "paciente evoluiu bem", "role": "assistant", "conversa": "Consulta de março", "sim": 0.9},
    ])

    assert "Consulta de março" in bloco
    assert "pode ser de outro paciente" in bloco
    assert "paciente evoluiu bem" in bloco


def test_bloco_vazio_quando_nao_ha_trechos():
    assert formatar_bloco([]) == ""


def test_bloco_distingue_quem_falou():
    bloco = formatar_bloco([
        {"content": "pergunta do medico", "role": "user", "conversa": "C", "sim": 0.9},
        {"content": "resposta", "role": "assistant", "conversa": "C", "sim": 0.9},
    ])
    assert "Médico" in bloco
    assert "Assistente" in bloco


# ── Ponto de entrada ─────────────────────────────────────────────────────────

async def test_conversa_fora_de_pasta_nao_gera_contexto(db, user):
    """Sem pasta não há projeto — e não se paga embedding nenhum."""
    conv = await _conversa_indexada(db, user, None, "Solta", "conversa sem pasta")

    assert await contexto_da_pasta(db, user.id, conv.id, "pergunta") == ""


async def test_primeira_mensagem_sem_conversa_nao_gera_contexto(db, user):
    assert await contexto_da_pasta(db, user.id, None, "pergunta") == ""


async def test_conversa_de_outro_usuario_nao_gera_contexto(
    db, user, user_factory, folder_factory
):
    outro = await user_factory()
    pasta = await folder_factory(outro, "Pasta do outro")
    conv = await _conversa_indexada(db, outro, pasta, "Alheia", "SEGREDO")

    assert await contexto_da_pasta(db, user.id, conv.id, "pergunta") == ""


async def test_pasta_com_uma_conversa_so_nao_recupera_a_si_mesma(db, user, folder_factory):
    pasta = await folder_factory(user, "Pasta")
    conv = await _conversa_indexada(db, user, pasta, "Unica", "unico caso")

    assert await contexto_da_pasta(db, user.id, conv.id, "pergunta") == ""


async def test_falha_de_embedding_nao_derruba_a_resposta(db, user, folder_factory, monkeypatch):
    """
    Sem contexto da pasta a resposta sai pior; sem resposta o médico fica sem
    nada. A degradação é deliberada.
    """
    async def _explode(*a, **k):
        raise RuntimeError("provedor de embedding fora do ar")

    monkeypatch.setattr(folder_context_service, "_embed_batch", _explode)

    pasta = await folder_factory(user, "Pasta")
    atual = await _conversa_indexada(db, user, pasta, "Atual", "atual")
    await _conversa_indexada(db, user, pasta, "Irma", "conteudo irmao")

    assert await contexto_da_pasta(db, user.id, atual.id, "pergunta") == ""


# ── Integração com a montagem de contexto ────────────────────────────────────

async def test_bloco_da_pasta_entra_no_contexto_enviado_ao_modelo(
    db, user, folder_factory
):
    """A ponta a ponta: da pasta até a lista de turnos que o provider recebe."""
    from app.services.orquestrador_shared import load_context_messages

    pasta = await folder_factory(user, "Acompanhamento")
    atual = await _conversa_indexada(db, user, pasta, "Hoje", "consulta de hoje")
    await _conversa_indexada(db, user, pasta, "Anterior", "EVOLUCAO ANTERIOR")

    mensagens = await load_context_messages(
        db, user.id, atual.id, pergunta_atual="como evoluiu?"
    )

    conteudo = " ".join(m["content"] for m in mensagens)
    assert "EVOLUCAO ANTERIOR" in conteudo
    assert "outras conversas desta pasta" in conteudo


async def test_bloco_da_pasta_vem_antes_do_historico_proprio(db, user, folder_factory):
    """É pano de fundo, não a última coisa dita."""
    from app.services.orquestrador_shared import load_context_messages

    pasta = await folder_factory(user, "Pasta")
    atual = await _conversa_indexada(db, user, pasta, "Hoje", "PERGUNTA DESTA CONVERSA")
    await _conversa_indexada(db, user, pasta, "Anterior", "TRECHO DA IRMA")

    mensagens = await load_context_messages(
        db, user.id, atual.id, pergunta_atual="pergunta"
    )
    conteudo = [m["content"] for m in mensagens]
    indice_bloco = next(i for i, c in enumerate(conteudo) if "TRECHO DA IRMA" in c)
    indice_proprio = next(i for i, c in enumerate(conteudo) if "PERGUNTA DESTA CONVERSA" in c)

    assert indice_bloco < indice_proprio


async def test_sem_pergunta_atual_nao_ha_busca_na_pasta(db, user, folder_factory):
    """
    Quem não passa `pergunta_atual` não paga embedding. Mantém o custo preso ao
    caminho que realmente usa o recurso.
    """
    from app.services.orquestrador_shared import load_context_messages

    pasta = await folder_factory(user, "Pasta")
    atual = await _conversa_indexada(db, user, pasta, "Hoje", "hoje")
    await _conversa_indexada(db, user, pasta, "Anterior", "TRECHO DA IRMA")

    mensagens = await load_context_messages(db, user.id, atual.id)

    assert all("TRECHO DA IRMA" not in m["content"] for m in mensagens)


# ── Conversa NOVA dentro de uma pasta ────────────────────────────────────────
# Regressão do bug encontrado na homologação: ao abrir uma conversa nova dentro
# de uma pasta, a primeira mensagem chega com `conversation_id=None` e a pasta
# vem separada, no corpo da requisição. A versão original saía na primeira linha
# e o caso mais comum do recurso — "discuta o caso com os arquivos desta pasta"
# — nunca recebia contexto nenhum.

async def test_conversa_nova_na_pasta_recebe_contexto(db, user, folder_factory):
    pasta = await folder_factory(user, "Paciente Jorge")
    await _conversa_indexada(db, user, pasta, "Evolução", "EVOLUCAO DO PACIENTE JORGE")

    bloco = await contexto_da_pasta(
        db, user.id, None, "discuta o caso deste paciente", folder_id=pasta.id
    )

    assert "EVOLUCAO DO PACIENTE JORGE" in bloco


async def test_conversa_nova_indexa_a_pasta_na_primeira_pergunta(
    db, db_conn, user, folder_factory, monkeypatch
):
    """
    Sem conversa ainda, a indexação precisa acontecer pela pasta.

    Desde que ela saiu do caminho crítico, a indexação roda em background com
    sessão própria — o teste espera a tarefa antes de conferir o resultado.
    """
    from sqlalchemy import func
    from sqlalchemy import select as sa_select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    monkeypatch.setattr(
        folder_context_service, "async_session_factory",
        async_sessionmaker(bind=db_conn, expire_on_commit=False),
    )

    pasta = await folder_factory(user, "Pasta")
    conv = await _conversa_indexada(db, user, pasta, "Antiga", "conteudo antigo")

    # Remove o índice para forçar a indexação preguiçosa a agir.
    await db.execute(
        MessageEmbedding.__table__.delete().where(
            MessageEmbedding.conversation_id == conv.id
        )
    )
    await db.commit()

    await contexto_da_pasta(db, user.id, None, "pergunta", folder_id=pasta.id)
    tarefa = folder_context_service._indexacoes_em_voo.get(pasta.id)
    assert tarefa is not None, "a indexação deveria ter sido agendada"
    await tarefa

    total = (await db.execute(
        sa_select(func.count()).select_from(MessageEmbedding)
        .where(MessageEmbedding.conversation_id == conv.id)
    )).scalar_one()
    assert total > 0


# ── Indexação fora do caminho da resposta ────────────────────────────────────
# Rodando inline, o embedding de todos os turnos pendentes da pasta ficava entre
# a pergunta e o primeiro token — e a espera crescia conforme a pasta enchia.

async def test_contexto_da_pasta_nao_espera_o_embedding(
    db, db_conn, user, folder_factory, monkeypatch
):
    """
    Com a indexação travada, `contexto_da_pasta` ainda precisa retornar. Se ela
    voltasse a ser aguardada, este teste passaria a estourar por timeout.
    """
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    monkeypatch.setattr(
        folder_context_service, "async_session_factory",
        async_sessionmaker(bind=db_conn, expire_on_commit=False),
    )

    async def _embed_travado(_client, textos):
        # A recuperação usa o mesmo helper; só a indexação (lote > 1) trava.
        if len(textos) > 1:
            await asyncio.sleep(3600)
        return [vetor() for _ in textos]

    pasta = await folder_factory(user, "Pasta")
    conv_a = await _conversa_indexada(db, user, pasta, "Irma A", "conteudo A")
    await _conversa_indexada(db, user, pasta, "Irma B", "conteudo B")
    await db.execute(
        MessageEmbedding.__table__.delete().where(
            MessageEmbedding.conversation_id == conv_a.id
        )
    )
    await db.commit()

    monkeypatch.setattr(folder_context_service, "_embed_batch", _embed_travado)

    async with asyncio.timeout(5):
        await contexto_da_pasta(db, user.id, None, "pergunta", folder_id=pasta.id)

    tarefa = folder_context_service._indexacoes_em_voo.get(pasta.id)
    if tarefa is not None:
        tarefa.cancel()


async def test_indexacao_em_background_usa_sessao_propria(
    db, db_conn, user, folder_factory, monkeypatch
):
    """
    A sessão da requisição não pode ser reaproveitada: `AsyncSession` não é
    segura para uso concorrente e a requisição faz commit no meio.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    sessoes_abertas = []
    fabrica = async_sessionmaker(bind=db_conn, expire_on_commit=False)

    def _fabrica_espia():
        sessao = fabrica()
        sessoes_abertas.append(sessao)
        return sessao

    monkeypatch.setattr(folder_context_service, "async_session_factory", _fabrica_espia)

    pasta = await folder_factory(user, "Pasta")
    conv = await _conversa_indexada(db, user, pasta, "Antiga", "conteudo antigo")
    await db.execute(
        MessageEmbedding.__table__.delete().where(
            MessageEmbedding.conversation_id == conv.id
        )
    )
    await db.commit()

    await contexto_da_pasta(db, user.id, None, "pergunta", folder_id=pasta.id)
    await folder_context_service._indexacoes_em_voo[pasta.id]

    assert sessoes_abertas, "a indexação deveria ter aberto a própria sessão"
    assert all(s is not db for s in sessoes_abertas)


async def test_duas_perguntas_seguidas_nao_indexam_a_pasta_duas_vezes(
    db, db_conn, user, folder_factory, monkeypatch
):
    """Sem a trava, duas perguntas em sequência disparariam duas indexações
    concorrentes do MESMO conjunto pendente — trabalho e custo em dobro."""
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    monkeypatch.setattr(
        folder_context_service, "async_session_factory",
        async_sessionmaker(bind=db_conn, expire_on_commit=False),
    )

    lotes = []

    async def _embed_lento(_client, textos):
        lotes.append(len(textos))
        await asyncio.sleep(0.05)
        return [vetor() for _ in textos]

    pasta = await folder_factory(user, "Pasta")
    conv = await _conversa_indexada(db, user, pasta, "Antiga", "conteudo antigo")
    await db.execute(
        MessageEmbedding.__table__.delete().where(
            MessageEmbedding.conversation_id == conv.id
        )
    )
    await db.commit()

    monkeypatch.setattr(folder_context_service, "_embed_batch", _embed_lento)

    primeira = folder_context_service.agendar_indexacao(user.id, pasta.id)
    segunda = folder_context_service.agendar_indexacao(user.id, pasta.id)
    assert segunda is primeira, "a segunda chamada deveria reaproveitar a tarefa em voo"
    await primeira

    # Um único lote: o da indexação que estava em voo.
    assert len(lotes) == 1


async def test_pasta_alheia_no_corpo_da_requisicao_nao_vaza(
    db, user, user_factory, folder_factory
):
    """
    O `folder_id` vem do CLIENTE quando a conversa é nova. Forjar o id de uma
    pasta alheia não pode trazer o conteúdo dela.
    """
    outro = await user_factory()
    pasta_alheia = await folder_factory(outro, "Pasta do outro")
    await _conversa_indexada(db, outro, pasta_alheia, "Caso alheio", "SEGREDO DO OUTRO")

    bloco = await contexto_da_pasta(
        db, user.id, None, "pergunta", folder_id=pasta_alheia.id
    )

    assert bloco == ""


async def test_sem_conversa_e_sem_pasta_nao_ha_contexto(db, user):
    assert await contexto_da_pasta(db, user.id, None, "pergunta", folder_id=None) == ""


# ── Clarificação enxerga o contexto ──────────────────────────────────────────

def test_verificador_de_clarificacao_recebe_o_contexto():
    """
    Regressão do segundo bug da homologação: a etapa de clarificação recebia só
    o texto cru e pedia ao médico exatamente o que a pasta já continha.
    """
    from app.services.orquestrador_shared import _prompt_com_contexto

    montado = _prompt_com_contexto(
        "conseguimos discutir o caso do paciente?",
        [{"role": "user", "content": "EVOLUCAO E ELETRO DO PACIENTE JORGE"}],
    )

    assert "EVOLUCAO E ELETRO DO PACIENTE JORGE" in montado
    assert "[Contexto já disponível]" in montado
    # A mensagem a avaliar precisa continuar identificável dentro do bloco.
    assert "conseguimos discutir o caso do paciente?" in montado


def test_sem_contexto_o_prompt_de_clarificacao_passa_intacto():
    from app.services.orquestrador_shared import _prompt_com_contexto

    assert _prompt_com_contexto("pergunta", None) == "pergunta"
    assert _prompt_com_contexto("pergunta", []) == "pergunta"


def test_contexto_da_clarificacao_e_limitado():
    """O verificador roda num modelo pequeno — não pode receber a pasta inteira."""
    from app.services.orquestrador_shared import (
        MAX_CHARS_CONTEXTO_CLARIFICACAO,
        _prompt_com_contexto,
    )

    montado = _prompt_com_contexto(
        "pergunta",
        [{"role": "user", "content": "x" * 50_000} for _ in range(5)],
    )

    assert len(montado) < MAX_CHARS_CONTEXTO_CLARIFICACAO + 500
