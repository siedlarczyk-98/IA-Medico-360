"""
Montagem do contexto enviado ao modelo (Fase 4).

Substituiu o achatamento em texto — últimas 10 mensagens, 800 caracteres cada,
tudo numa única mensagem `user` com rótulos "Médico:"/"Assistente:" dentro do
texto — por turnos de verdade cortados por orçamento de tokens e lidos do banco.

Três garantias, nesta ordem de importância:
1. O histórico vem do BANCO, não do corpo da requisição (era forjável).
2. Um usuário nunca recebe contexto da conversa de outro.
3. O corte por tokens preserva o que é recente.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.models.models import Interaction, InteractionResponse
from app.services.context_budget import (
    Turn,
    estimate_tokens,
    fit_turns_to_budget,
    truncate_to_tokens,
    turns_to_messages,
)
from app.services.conversation_history import load_history
from app.services.orquestrador_shared import load_context_messages

# ── Orçamento de tokens (funções puras) ──────────────────────────────────────

def test_estimativa_cresce_com_o_texto():
    assert estimate_tokens("a" * 100) < estimate_tokens("a" * 1000)


def test_texto_vazio_ainda_custa_algo():
    # Mesmo uma mensagem vazia carrega marcação de papel no payload.
    assert estimate_tokens("") > 0


def test_orcamento_mantem_os_turnos_mais_recentes():
    turnos = [Turn("user", f"pergunta {i} " * 50) for i in range(20)]
    cabem = fit_turns_to_budget(turnos, budget_tokens=500)

    assert cabem, "o orçamento deveria caber pelo menos um turno"
    assert cabem[-1] is turnos[-1], "o turno mais recente não pode ser descartado"
    assert len(cabem) < len(turnos), "com orçamento apertado, algo tem de sair"


def test_turno_gigante_sozinho_e_truncado_e_nao_descartado():
    # Perder a última fala esvaziaria o contexto justo do que mais importa.
    turnos = [Turn("user", "x" * 100_000)]
    cabem = fit_turns_to_budget(turnos, budget_tokens=200)

    assert len(cabem) == 1
    assert estimate_tokens(cabem[0].content) <= 200
    assert len(cabem[0].content) < 100_000


def test_truncamento_avisa_que_houve_corte():
    # Sem a marca, o modelo lê um caso interrompido como se fosse o caso todo.
    cortado = truncate_to_tokens("y" * 10_000, 100)
    assert "omitido" in cortado


def test_truncamento_preserva_o_fim_da_mensagem():
    # Numa evolução clínica, o fim costuma ser conduta e desfecho.
    texto = "começo irrelevante " * 500 + "CONDUTA FINAL"
    assert "CONDUTA FINAL" in truncate_to_tokens(texto, 100)


def test_contexto_nunca_comeca_com_fala_do_assistente():
    # Perplexity exige alternância começando por `user`; e um histórico que
    # abre com a resposta a uma pergunta ausente confunde qualquer modelo.
    turnos = [Turn("assistant", "resposta órfã"), Turn("user", "pergunta"), Turn("assistant", "ok")]
    cabem = fit_turns_to_budget(turnos, budget_tokens=10_000)
    assert cabem[0].role == "user"


def test_orcamento_apertado_prefere_a_pergunta_a_resposta_solta():
    """
    Se só cabe um turno e o mais recente é do assistente, o orçamento vai para
    a última PERGUNTA: uma resposta sem a pergunta correspondente não se
    sustenta, e ainda quebra a alternância exigida por alguns provedores.
    """
    turnos = [
        Turn("user", "PERGUNTA IMPORTANTE " * 40),
        Turn("assistant", "resposta " * 40),
    ]
    cabem = fit_turns_to_budget(turnos, budget_tokens=120)

    assert len(cabem) == 1
    assert cabem[0].role == "user"
    assert "PERGUNTA IMPORTANTE" in cabem[0].content


def test_orcamento_zero_devolve_nada():
    assert fit_turns_to_budget([Turn("user", "oi")], budget_tokens=0) == []


def test_conversao_para_mensagens_usa_papeis_de_verdade():
    # A diferença central da fase: papel estrutural, não rótulo dentro do texto.
    msgs = turns_to_messages([Turn("user", "a"), Turn("assistant", "b")])
    assert msgs == [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
    ]


# ── Leitura do banco ─────────────────────────────────────────────────────────

pytestmark_async = pytest.mark.asyncio


async def _gravar_troca(db, conv, dono, pergunta, resposta, *, minutos=0, status="completed"):
    interaction = Interaction(
        conversation_id=conv.id,
        user_id=dono.id,
        feature="ORQUESTRADOR",
        mode="CLINICAL_REASONING",
        prompt_text=pergunta,
        status=status,
        started_at=datetime.now(UTC) + timedelta(minutes=minutos),
        completed_at=datetime.now(UTC) + timedelta(minutes=minutos),
    )
    db.add(interaction)
    await db.flush()
    if resposta is not None:
        db.add(InteractionResponse(
            interaction_id=interaction.id,
            model_used="claude-sonnet-4-6",
            response_text=resposta,
        ))
    await db.flush()
    return interaction


@pytest.mark.asyncio
async def test_historico_vem_do_banco_em_ordem_cronologica(db, user, conversation_factory):
    conv = await conversation_factory(user)
    await _gravar_troca(db, conv, user, "primeira pergunta", "primeira resposta", minutos=0)
    await _gravar_troca(db, conv, user, "segunda pergunta", "segunda resposta", minutos=1)

    turnos = await load_history(db, user.id, conv.id)

    assert [t.role for t in turnos] == ["user", "assistant", "user", "assistant"]
    assert [t.content for t in turnos] == [
        "primeira pergunta", "primeira resposta",
        "segunda pergunta", "segunda resposta",
    ]


@pytest.mark.asyncio
async def test_conversa_de_outro_usuario_nao_vaza_para_o_contexto(
    db, user, user_factory, conversation_factory
):
    """A garantia que mais importa: contexto é por dono, não por id."""
    outro = await user_factory()
    conv_alheia = await conversation_factory(outro)
    await _gravar_troca(db, conv_alheia, outro, "caso sigiloso do outro", "resposta sigilosa")

    turnos = await load_history(db, user.id, conv_alheia.id)

    assert turnos == []


@pytest.mark.asyncio
async def test_primeira_mensagem_da_conversa_nao_tem_historico(db, user):
    assert await load_history(db, user.id, None) == []


@pytest.mark.asyncio
async def test_conversa_inexistente_devolve_vazio_sem_erro(db, user):
    import uuid
    assert await load_history(db, user.id, uuid.uuid4()) == []


@pytest.mark.asyncio
async def test_interacao_aguardando_clarificacao_fica_fora(db, user, conversation_factory):
    # Ela ainda não tem resposta, e a versão consolidada já entra pelo prompt —
    # incluí-la duplicaria a pergunta no contexto.
    conv = await conversation_factory(user)
    await _gravar_troca(db, conv, user, "caso incompleto", None, status="pending_clarification")

    assert await load_history(db, user.id, conv.id) == []


@pytest.mark.asyncio
async def test_resposta_com_erro_nao_entra_no_contexto(db, user, conversation_factory):
    """Devolver o registro de falha faria o modelo crer que já respondeu aquilo."""
    conv = await conversation_factory(user)
    interaction = await _gravar_troca(db, conv, user, "pergunta", None)
    db.add(InteractionResponse(
        interaction_id=interaction.id,
        model_used="claude-sonnet-4-6",
        response_text="",
        error_message="timeout do provider",
    ))
    await db.flush()

    turnos = await load_history(db, user.id, conv.id)

    assert [t.role for t in turnos] == ["user"]


@pytest.mark.asyncio
async def test_contexto_montado_respeita_o_orcamento(db, user, conversation_factory):
    conv = await conversation_factory(user)
    for i in range(30):
        await _gravar_troca(db, conv, user, f"pergunta longa {i} " * 100, f"resposta longa {i} " * 100, minutos=i)

    mensagens = await load_context_messages(db, user.id, conv.id, budget_tokens=800)

    assert mensagens, "deveria sobrar algo dentro do orçamento"
    total = sum(estimate_tokens(m["content"]) for m in mensagens)
    assert total <= 800
    # E o que sobrou tem de ser o fim da conversa, não o começo.
    assert "29" in mensagens[-1]["content"]


@pytest.mark.asyncio
async def test_contexto_montado_sai_no_formato_dos_providers(db, user, conversation_factory):
    conv = await conversation_factory(user)
    await _gravar_troca(db, conv, user, "oi doutor", "olá")

    mensagens = await load_context_messages(db, user.id, conv.id)

    assert all(set(m) == {"role", "content"} for m in mensagens)
    assert all(m["role"] in {"user", "assistant"} for m in mensagens)


# ── Calibração da estimativa contra dados reais ──────────────────────────────
# Medida em 2026-08-27 sobre 54 interações com `tokens_in` gravado, isolando as
# que não tinham histórico, anexo nem busca web somados à contagem.

def test_razao_esta_dentro_do_intervalo_medido():
    """
    A razão precisa ficar entre o pior caso observado e a mediana global.

    Abaixo de 2.55 (pior caso real) a estimativa vira pessimismo sem base —
    corta contexto que caberia. Acima de 3.55 (mediana global) ela passa a
    subestimar sistematicamente até no texto mais leve.
    """
    from app.services.context_budget import CHARS_PER_TOKEN

    assert 2.55 <= CHARS_PER_TOKEN <= 3.55, (
        "valor fora do intervalo medido em produção — se a medição foi refeita, "
        "atualize os limites junto com o número e a fonte em docs/debitos.md"
    )


def test_estimativa_bate_com_caso_real_de_texto_clinico_denso():
    """
    Caso real da amostra: 2928 caracteres de evolução clínica custaram 1112
    tokens no claude-sonnet-4-6 (razão 2.63). A estimativa não pode errar feio
    justamente no tipo de texto que o produto mais processa.
    """
    from app.services.context_budget import estimate_tokens

    estimado = estimate_tokens("x" * 2928)
    real = 1112

    assert 0.7 <= estimado / real <= 1.5, (
        f"estimou {estimado} para um texto que custou {real} tokens de verdade"
    )
