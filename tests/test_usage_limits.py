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

    r = await db.execute(select(UserWeeklyUsage).where(UserWeeklyUsage.user_id == user.id))
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

    usage = await _usage_de(db, user)
    assert usage.total_cost_usd == Decimal("0")


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

    usage = await _usage_de(db, user)
    assert (datetime.now(UTC) - usage.week_start).total_seconds() < 60


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
