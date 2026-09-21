"""
Controle de custo e limite semanal (item 1.3 do plano de prontidão).

É o mecanismo que impede um usuário beta de consumir cota ilimitada de LLM.
Não tinha nenhum teste — e é dinheiro real saindo a cada chamada.

Regras exercitadas (de `app/services/usage_service.py`):
  - só `beta_user` tem teto; outros papéis passam livre
  - o teto é semanal, contado a partir da PRIMEIRA interação, não do domingo
  - ao vencer a janela, o contador zera e a nova janela começa naquele instante
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.models import UserWeeklyUsage
from app.services.usage_service import (
    BETA_WEEKLY_LIMIT,
    check_limit,
    get_usage_info,
    record_cost,
)


async def _usage_de(db, user) -> UserWeeklyUsage:
    from sqlalchemy import select

    # `populate_existing`: `record_cost` grava por SQL direto (upsert atômico), então
    # o objeto que a sessão já conhece está velho e precisa ser relido do banco.
    r = await db.execute(
        select(UserWeeklyUsage)
        .where(UserWeeklyUsage.user_id == user.id)
        .execution_options(populate_existing=True)
    )
    return r.scalar_one()


# ── Quem tem teto ────────────────────────────────────────────────────────

async def test_beta_dentro_do_limite_passa(db, user):
    await record_cost(db, user.id, Decimal("0.10"))
    await check_limit(db, user)  # não levanta


async def test_beta_no_limite_exato_e_bloqueado(db, user):
    """A comparação é `>=`: gastar exatamente o teto já bloqueia a próxima chamada."""
    await record_cost(db, user.id, BETA_WEEKLY_LIMIT)

    with pytest.raises(HTTPException) as exc:
        await check_limit(db, user)

    assert exc.value.status_code == 429


async def test_beta_acima_do_limite_e_bloqueado(db, user):
    await record_cost(db, user.id, BETA_WEEKLY_LIMIT + Decimal("0.01"))

    with pytest.raises(HTTPException) as exc:
        await check_limit(db, user)

    assert exc.value.status_code == 429


async def test_admin_nao_tem_teto(db, admin):
    """Papel diferente de beta_user passa mesmo tendo estourado o valor."""
    await record_cost(db, admin.id, BETA_WEEKLY_LIMIT * 10)
    await check_limit(db, admin)  # não levanta


# ── Acumulação ───────────────────────────────────────────────────────────

async def test_custos_somam_na_janela(db, user):
    for _ in range(4):
        await record_cost(db, user.id, Decimal("0.05"))

    usage = await _usage_de(db, user)
    assert usage.total_cost_usd == Decimal("0.20")


async def test_custo_zero_ou_negativo_e_ignorado(db, user):
    """Guarda contra provider que devolve custo vazio zerando/estragando o acumulado."""
    await record_cost(db, user.id, Decimal("0.30"))
    await record_cost(db, user.id, Decimal("0"))
    await record_cost(db, user.id, Decimal("-1.00"))

    usage = await _usage_de(db, user)
    assert usage.total_cost_usd == Decimal("0.30")


# ── Reset da janela ──────────────────────────────────────────────────────

async def test_janela_expirada_zera_o_contador(db, user):
    await record_cost(db, user.id, BETA_WEEKLY_LIMIT)
    usage = await _usage_de(db, user)

    # Empurra a janela para 8 dias atrás — já vencida.
    usage.week_start = datetime.now(UTC) - timedelta(days=8)
    await db.flush()

    await check_limit(db, user)  # não levanta: a janela virou

    # CONTRATO NOVO (2026-09-21): a checagem só LÊ. Ela gravava o reset com
    # `flush` e sem commit, na sessão da requisição — que no stream fica aberta
    # até o fim —, e o `record_cost` da outra sessão travava esperando essa linha.
    # Quem zera a semana vencida é o próximo `record_cost`, na mesma instrução
    # que soma: o total passa a ser SÓ o custo novo, não o antigo mais o novo.
    info = await get_usage_info(db, user)
    assert info["usage_percentage"] == 0

    await record_cost(db, user.id, Decimal("0.25"))
    usage = await _usage_de(db, user)
    assert usage.total_cost_usd == Decimal("0.25")


async def test_janela_de_seis_dias_ainda_bloqueia(db, user):
    """Fronteira: 6 dias não zera. Só a partir de 7 a janela vira."""
    await record_cost(db, user.id, BETA_WEEKLY_LIMIT)
    usage = await _usage_de(db, user)
    usage.week_start = datetime.now(UTC) - timedelta(days=6)
    await db.flush()

    with pytest.raises(HTTPException):
        await check_limit(db, user)


async def test_reset_reinicia_a_contagem_do_momento_atual(db, user):
    """A nova janela começa quando o reset acontece, não quando a antiga terminaria."""
    await record_cost(db, user.id, Decimal("0.50"))
    usage = await _usage_de(db, user)
    usage.week_start = datetime.now(UTC) - timedelta(days=30)
    await db.flush()

    await check_limit(db, user)
    await record_cost(db, user.id, Decimal("0.10"))  # é o uso que abre a janela nova

    usage = await _usage_de(db, user)
    assert (datetime.now(UTC) - usage.week_start).total_seconds() < 60
    assert usage.total_cost_usd == Decimal("0.10")


# ── Informação exposta ao usuário ────────────────────────────────────────

async def test_percentual_de_uso(db, user):
    await record_cost(db, user.id, BETA_WEEKLY_LIMIT / 4)

    info = await get_usage_info(db, user)

    assert info["has_limit"] is True
    assert info["usage_percentage"] == 25


async def test_percentual_nao_passa_de_cem(db, user):
    await record_cost(db, user.id, BETA_WEEKLY_LIMIT * 3)

    info = await get_usage_info(db, user)

    assert info["usage_percentage"] == 100


async def test_admin_nao_expoe_limite(db, admin):
    info = await get_usage_info(db, admin)
    assert info["has_limit"] is False
    assert info["usage_percentage"] is None


async def test_endpoint_de_uso_responde(client, user):
    from tests.conftest import auth_headers

    resp = await client.get("/api/v1/users/usage", headers=auth_headers(user))

    assert resp.status_code == 200
    assert resp.json()["has_limit"] is True


# ── O limite precisa comportar o modo mais caro ──────────────────────────────
# O teto era US$ 1,00, calibrado quando a pergunta mais cara custava ~US$ 0,03.
# O DATA_OCEAN custou US$ 0,647945 na primeira consulta real (medido em
# produção, 2026-09-08): cabia UMA VEZ E MEIA por semana, e na segunda o médico
# perdia todos os modos — inclusive os que custam centavos.


# Custo real medido da primeira consulta DATA_OCEAN em produção.
# Não é estimativa: 147.862 tokens de entrada, 2.773 de saída e 25,2 GB
# processados, com os preços da Maritaca de 2026-09.
CUSTO_MEDIDO_DATA_OCEAN = Decimal("0.647945")


def test_o_limite_comporta_mais_de_uma_consulta_do_modo_mais_caro():
    """Um limite que derruba a plataforma inteira por causa de duas perguntas
    não protege orçamento: impede o uso.

    O piso de 3 é o mínimo para o recurso ser utilizável — abaixo disso o
    médico gasta a semana inteira em duas perguntas.
    """
    cabem = BETA_WEEKLY_LIMIT / CUSTO_MEDIDO_DATA_OCEAN

    assert cabem >= 3, (
        f"o limite de US$ {BETA_WEEKLY_LIMIT} comporta só {cabem:.1f} consultas "
        f"do modo mais caro (US$ {CUSTO_MEDIDO_DATA_OCEAN}) — o médico bate o "
        "teto e perde TODOS os modos, inclusive os baratos"
    )


def test_o_limite_nao_e_alto_demais_para_um_piloto():
    """A contrapartida: o teto existe para que um bug de laço ou um uso
    inesperado não gerem fatura surpresa."""
    assert BETA_WEEKLY_LIMIT <= Decimal("20.00"), (
        "teto alto demais para a fase de piloto — 18 usuários no limite "
        f"gastariam US$ {BETA_WEEKLY_LIMIT * 18} por semana"
    )


# ── A checagem não escreve (era a causa do travamento do stream) ─────────

async def test_check_limit_nao_cria_linha_para_usuario_novo(db, user):
    from sqlalchemy import func, select

    await check_limit(db, user)
    await get_usage_info(db, user)

    linhas = await db.scalar(
        select(func.count()).select_from(UserWeeklyUsage).where(UserWeeklyUsage.user_id == user.id)
    )
    assert linhas == 0, "a checagem gravou — é o bloqueio que travava o stream antes do text_done"


async def test_semana_dentro_do_prazo_continua_somando(db, user):
    await record_cost(db, user.id, Decimal("1.00"))
    await record_cost(db, user.id, Decimal("0.50"))

    assert (await _usage_de(db, user)).total_cost_usd == Decimal("1.50")
