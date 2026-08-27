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
    SIMILARITY_THRESHOLD,
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


async def test_limiar_e_mais_frouxo_que_o_do_cache():
    """
    O cache precisa de quase-identidade (servir a resposta errada é grave); a
    recuperação precisa de relevância. Usar o mesmo número nos dois seria
    confundir dois problemas diferentes.
    """
    from app.services.semantic_cache_service import SIMILARITY_THRESHOLD as CACHE_THRESHOLD

    assert SIMILARITY_THRESHOLD < CACHE_THRESHOLD


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
