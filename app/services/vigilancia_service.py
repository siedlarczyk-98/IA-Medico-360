"""
Vigilância — três perguntas sobre o sistema que ninguém estava fazendo.

POR QUE ISTO EXISTE
O cache semântico ficou meses sem gravar uma única linha. Um defeito engolido
por um `except` desligava toda escrita, e nada apontou. O detalhe que dói: o
dado para descobrir SEMPRE esteve lá — `interactions.cache_hit` é gravado em
toda interação, e um `SELECT avg(cache_hit::int)` teria devolvido zero a
qualquer momento.

Não faltou instrumentação. Faltou alguém perguntando. Este módulo é a pergunta,
feita de hora em hora pelo próprio backend.

Vale para a mesma classe de falha, não só para a instância: o expurgo LGPD
também parou por 39 dias sem avisar, e cada nova garantia silenciosa que o
sistema ganhar deve virar uma medição aqui.

DESENHO: MEDIR E DECIDIR SÃO COISAS SEPARADAS
`medir_*` só lê o banco e devolve números. `avaliar` é função pura que recebe os
números e decide o que vira alarme. A separação é o que permite testar os
limiares sem banco, e permite que `scripts/verificar_vigilancia.py` mostre as
MESMAS medições sem disparar alarme nenhum — pelo mesmo motivo que
`verificar_expurgo.py` reusa `medir_passivo`.

SOBRE OS LIMIARES
Todo número aqui é escolhido para errar do lado do silêncio. Um alarme que
dispara sem motivo é pior que alarme nenhum: ele treina o time a arquivar sem
ler, e aí a próxima falha silenciosa passa igual — só que agora com uma falsa
sensação de cobertura.
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AuditLog, Interaction, SemanticCache
from app.services.orquestrador_modes import MODOS_CACHEAVEIS

logger = logging.getLogger(__name__)

# Janela de observação. Sete dias absorve a sazonalidade da semana do médico —
# segunda-feira não se parece com domingo — sem diluir tanto a ponto de uma
# falha recente sumir na média.
JANELA_DIAS = 7

# Interações elegíveis mínimas antes de afirmar qualquer coisa sobre o cache.
# Com pouco volume, "zero linhas no cache" é indistinguível de "ninguém
# perguntou nada cacheável esta semana", e alarmar seria adivinhação.
MIN_AMOSTRA_CACHE = 50

# Multiplicador de custo semanal que caracteriza escalada. 3x é grosseiro de
# propósito: o objetivo é pegar laço infinito, retry descontrolado ou abuso —
# não flutuação de uso. Crescimento saudável de produto não triplica em 7 dias.
FATOR_ESCALADA_CUSTO = Decimal("3.0")

# Piso para a comparação de custo fazer sentido. Sem ele, US$ 0,10 virando
# US$ 0,40 dispara um alarme de "escalada de 4x" que não significa nada.
CUSTO_MINIMO_PARA_COMPARAR = Decimal("5.00")

# Dias sem uma rodada de expurgo registrada antes de alarmar. Mesma tolerância
# de `expurgo_agendado.ATRASO_TOLERADO_DIAS`, e pelo mesmo motivo: um dia é
# ruído normal de deploy e reinício.
ATRASO_TOLERADO_EXPURGO_DIAS = 2

# Ação gravada em `audit_logs` a cada rodada de expurgo bem-sucedida. É o rastro
# que permite responder "quando o expurgo rodou pela última vez?" olhando o
# banco, e não a memória de quem estava de plantão.
ACAO_EXPURGO = "expurgo.rodada"


def _desde(dias: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=dias)


# ── Medições ─────────────────────────────────────────────────────────────────

async def medir_cache_semantico(db: AsyncSession, janela_dias: int = JANELA_DIAS) -> dict:
    """
    O cache está sendo escrito e lido? Não apaga nem escreve nada.

    Mede três coisas, porque uma só não distingue os casos:
      - `elegiveis`: interações que CONSULTARAM o cache na janela.
      - `linhas_vigentes`: entradas não expiradas na tabela. Zero com tráfego
        elegível é o defeito que ficou meses invisível — escrita desligada.
      - `taxa_hit`: proporção que foi servida do cache. Pode ser legitimamente
        baixa (perguntas todas diferentes), por isso não alarma sozinha.
    """
    desde = _desde(janela_dias)

    elegiveis = (await db.execute(
        select(func.count())
        .select_from(Interaction)
        .where(Interaction.created_at >= desde, Interaction.mode.in_(MODOS_CACHEAVEIS))
    )).scalar_one()

    hits = (await db.execute(
        select(func.count())
        .select_from(Interaction)
        .where(
            Interaction.created_at >= desde,
            Interaction.mode.in_(MODOS_CACHEAVEIS),
            Interaction.cache_hit.is_(True),
        )
    )).scalar_one()

    linhas_vigentes = (await db.execute(
        select(func.count())
        .select_from(SemanticCache)
        .where(SemanticCache.expires_at > datetime.now(UTC))
    )).scalar_one()

    return {
        "janela_dias": janela_dias,
        "elegiveis": elegiveis,
        "hits": hits,
        "taxa_hit": round(hits / elegiveis, 4) if elegiveis else 0.0,
        "linhas_vigentes": linhas_vigentes,
    }


async def medir_custo(db: AsyncSession, janela_dias: int = JANELA_DIAS) -> dict:
    """
    Quanto o produto gastou em modelo nesta janela, e na anterior. Só leitura.

    Duas janelas e não uma: um número absoluto sozinho não diz nada sem um
    orçamento declarado, e este projeto não tem um. A comparação com a janela
    anterior responde a pergunta que realmente importa aqui — "mudou alguma
    coisa de repente?" — sem exigir que alguém acerte um teto no chute.
    """
    agora = datetime.now(UTC)
    inicio_atual = agora - timedelta(days=janela_dias)
    inicio_anterior = agora - timedelta(days=janela_dias * 2)

    async def _soma(desde: datetime, ate: datetime) -> Decimal:
        valor = (await db.execute(
            select(func.coalesce(func.sum(Interaction.token_cost_usd), 0))
            .where(Interaction.created_at >= desde, Interaction.created_at < ate)
        )).scalar_one()
        return Decimal(str(valor))

    atual = await _soma(inicio_atual, agora)
    anterior = await _soma(inicio_anterior, inicio_atual)

    return {
        "janela_dias": janela_dias,
        "custo_usd": float(atual),
        "custo_usd_anterior": float(anterior),
        "fator": float(atual / anterior) if anterior > 0 else None,
    }


async def medir_ultimo_expurgo(db: AsyncSession) -> dict:
    """
    Há quantos dias o expurgo de retenção não roda? Só leitura.

    Complementa — não substitui — o alarme dentro de `expurgo_agendado`. Aquele
    dispara quando a rodada acontece e encontra atraso; este dispara quando a
    rodada NÃO acontece, que é o modo de falha original (39 dias de silêncio).

    `nunca_registrado` é verdade legítima em banco recém-migrado, e vira alarme
    de propósito: se a primeira rodada não deixou rastro, algo impediu o expurgo
    de rodar — e é exatamente isso que se quer saber.
    """
    ultimo = (await db.execute(
        select(func.max(AuditLog.created_at)).where(AuditLog.action == ACAO_EXPURGO)
    )).scalar_one()

    if ultimo is None:
        return {"nunca_registrado": True, "dias_desde": None, "ultimo_em": None}

    return {
        "nunca_registrado": False,
        "dias_desde": (datetime.now(UTC) - ultimo).days,
        "ultimo_em": ultimo.isoformat(),
    }


async def medir_tudo(db: AsyncSession) -> dict:
    """As três medições numa leitura só, para o laço e para o script de diagnóstico."""
    return {
        "cache": await medir_cache_semantico(db),
        "custo": await medir_custo(db),
        "expurgo": await medir_ultimo_expurgo(db),
    }


# ── Decisão ──────────────────────────────────────────────────────────────────

def avaliar(medicoes: dict) -> list[dict]:
    """
    Traduz medições em alarmes. Função pura — sem banco, sem rede, sem relógio.

    Devolve uma lista de `{"tag", "mensagem", "contexto"}` pronta para
    `app.core.alarme.alarmar`. Lista vazia é o caso normal e esperado.
    """
    alarmes: list[dict] = []

    cache = medicoes["cache"]
    if cache["elegiveis"] >= MIN_AMOSTRA_CACHE and cache["linhas_vigentes"] == 0:
        alarmes.append({
            "tag": "cache_semantico_sem_escrita",
            "mensagem": (
                f"Cache semântico sem nenhuma entrada vigente, apesar de "
                f"{cache['elegiveis']} interações elegíveis nos últimos "
                f"{cache['janela_dias']} dias. A escrita provavelmente está falhando em silêncio."
            ),
            "contexto": cache,
        })

    custo = medicoes["custo"]
    anterior = Decimal(str(custo["custo_usd_anterior"]))
    atual = Decimal(str(custo["custo_usd"]))
    if anterior >= CUSTO_MINIMO_PARA_COMPARAR and atual >= anterior * FATOR_ESCALADA_CUSTO:
        alarmes.append({
            "tag": "custo_escalando",
            "mensagem": (
                f"Custo de modelo em US$ {custo['custo_usd']:.2f} nos últimos "
                f"{custo['janela_dias']} dias, contra US$ {custo['custo_usd_anterior']:.2f} "
                f"na janela anterior ({custo['fator']:.1f}x)."
            ),
            "contexto": custo,
        })

    expurgo = medicoes["expurgo"]
    if expurgo["nunca_registrado"]:
        alarmes.append({
            "tag": "expurgo_sem_rastro",
            "mensagem": (
                "Nenhuma rodada de expurgo de retenção registrada em audit_logs. "
                "A tarefa agendada pode não estar rodando."
            ),
            "contexto": expurgo,
        })
    elif expurgo["dias_desde"] > ATRASO_TOLERADO_EXPURGO_DIAS:
        alarmes.append({
            "tag": "expurgo_parado",
            "mensagem": (
                f"Expurgo de retenção não roda há {expurgo['dias_desde']} dias "
                f"(último em {expurgo['ultimo_em']})."
            ),
            "contexto": expurgo,
        })

    return alarmes
