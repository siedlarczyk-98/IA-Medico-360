from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import case, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AuditLog, User, UserWeeklyUsage, new_uuid

# Teto de gasto semanal por usuário beta, em USD.
#
# Era 1,00, calibrado quando a pergunta mais cara custava ~US$ 0,03 — trinta
# perguntas por semana, folgado para um piloto.
#
# O DATA_OCEAN mudou a escala. Medição da primeira consulta real em produção
# (2026-09-08): US$ 0,647945 — 22× uma pergunta clínica comum. Não é o modelo:
# são os 25,2 GB que a ferramenta processa e os 147 mil tokens que ela injeta
# no contexto do lado da Maritaca.
#
# Com o teto de 1,00, cabia UMA VEZ E MEIA por semana. Na segunda consulta o
# médico batia o limite e perdia TODOS os modos — inclusive a busca rápida, que
# custa centavos. Um limite que derruba a plataforma inteira por causa de duas
# perguntas não protege orçamento: impede o uso.
#
# 5,00 comporta ~7 consultas Data Ocean, ou ~170 perguntas clínicas comuns, ou
# qualquer mistura. Com 18 usuários, o pior caso absoluto é US$ 90/semana — e
# ninguém chega perto, porque o consumo real medido é de dezenas de interações
# por mês, não por semana.
#
# QUANDO REVISAR: se o custo médio por interação subir de novo (um modo novo
# mais caro, ou a Maritaca reajustar), ou quando a base sair da escala de
# piloto. `vigilancia_service.medir_custo` mostra o gasto por período.
BETA_WEEKLY_LIMIT = Decimal("5.00")
BETA_ROLE = "beta_user"


def add_interaction_audit(
    db: AsyncSession,
    *,
    user_id,
    interaction_id,
    action: str,
    metadata: dict,
) -> AuditLog:
    """
    Cria e enfileira um AuditLog padronizado para uma interação.
    Centraliza o wrapper repetido em Orquestrador e Agregador — o conteúdo
    de `metadata` continua específico de cada fluxo.
    """
    audit = AuditLog(
        user_id=user_id,
        interaction_id=interaction_id,
        action=action,
        entity_type="interaction",
        entity_id=interaction_id,
        metadata_=metadata,
    )
    db.add(audit)
    return audit


SEMANA = timedelta(days=7)


async def _gasto_vigente(db: AsyncSession, user_id) -> tuple[Decimal, datetime | None]:
    """Gasto da semana corrente e o início dela. SÓ LÊ.

    Semana vencida conta como zero aqui mesmo, sem gravar nada. É o ponto da
    correção: `check_limit` criava a linha (usuário novo) ou zerava a semana
    (virada) com `flush` e SEM commit, na sessão da requisição — que no
    `/orquestrador/stream` só fecha quando o stream termina. O `record_cost` do
    serviço de stream, em OUTRA sessão, esperava o bloqueio dessa linha, que só
    era solto no fim do mesmo stream: o texto aparecia inteiro e a resposta
    travava antes do `text_done`, segurando duas conexões.

    Quem zera a semana agora é `record_cost`, numa instrução só.
    """
    linha = (
        await db.execute(
            select(UserWeeklyUsage.total_cost_usd, UserWeeklyUsage.week_start).where(
                UserWeeklyUsage.user_id == user_id
            )
        )
    ).one_or_none()
    if linha is None:
        return Decimal("0"), None
    total, inicio = linha
    if datetime.now(UTC) >= inicio + SEMANA:
        return Decimal("0"), None
    return total, inicio


async def check_limit(db: AsyncSession, user: User) -> None:
    if user.role != BETA_ROLE:
        return
    gasto, _ = await _gasto_vigente(db, user.id)
    if gasto >= BETA_WEEKLY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite semanal de uso atingido. Seu limite será reiniciado em 7 dias a partir da sua primeira interação.",
        )


async def record_cost(db: AsyncSession, user_id, cost_usd: Decimal) -> None:
    """Soma o custo ao medidor semanal, de forma ATÔMICA.

    Era ler-somar-gravar em Python: duas respostas terminando juntas liam o
    mesmo total e uma das somas se perdia — custo subcontado, furando o teto
    beta. Agora é um `INSERT ... ON CONFLICT DO UPDATE` com a soma feita pelo
    banco, que também cria a linha (primeiro uso) e zera a semana vencida na
    mesma instrução. Não há intervalo entre ler e gravar para outra transação
    entrar.
    """
    if cost_usd <= Decimal("0"):
        return

    agora = datetime.now(UTC)
    vencida = UserWeeklyUsage.week_start <= agora - SEMANA
    instrucao = pg_insert(UserWeeklyUsage).values(
        id=new_uuid(), user_id=user_id, week_start=agora, total_cost_usd=cost_usd
    )
    instrucao = instrucao.on_conflict_do_update(
        index_elements=[UserWeeklyUsage.user_id],
        set_={
            "total_cost_usd": case(
                (vencida, cost_usd), else_=UserWeeklyUsage.total_cost_usd + cost_usd
            ),
            "week_start": case((vencida, agora), else_=UserWeeklyUsage.week_start),
            "updated_at": agora,
        },
    )
    await db.execute(instrucao)


async def get_usage_info(db: AsyncSession, user: User) -> dict:
    if user.role != BETA_ROLE:
        return {"has_limit": False, "usage_percentage": None, "week_reset_at": None}

    gasto, inicio = await _gasto_vigente(db, user.id)

    ratio = gasto / BETA_WEEKLY_LIMIT
    percentage = min(int(ratio * 100), 100)
    # Sem semana em curso (usuário novo, ou semana vencida) a próxima começa na
    # próxima interação: o reinício é daqui a sete dias.
    week_reset_at = (inicio or datetime.now(UTC)) + SEMANA

    return {
        "has_limit": True,
        "usage_percentage": percentage,
        "week_reset_at": week_reset_at,
    }
