
from decimal import Decimal
from typing import NamedTuple

from cachetools import TTLCache
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ModelPricing


class Pricing(NamedTuple):
    """Snapshot dos preços — não a instância ORM, que ficaria detached da sessão
    de origem e estouraria em qualquer acesso lazy vindo de outra requisição."""

    provider_type: str
    input_per_million: Decimal
    output_per_million: Decimal


# In-memory cache — ModelPricing é estático (muda raramente), TTL de 1h
_pricing_cache: TTLCache = TTLCache(maxsize=200, ttl=3600)


async def get_model_pricing(db: AsyncSession, model_id: str) -> Pricing | None:
    """Retorna os preços do modelo com cache em memória (TTL 1h)."""
    if model_id in _pricing_cache:
        return _pricing_cache[model_id]
    result = await db.execute(
        select(
            ModelPricing.provider_type,
            ModelPricing.input_per_million,
            ModelPricing.output_per_million,
        ).where(
            ModelPricing.model_id == model_id,
            ModelPricing.status.is_(True),
        )
    )
    row = result.one_or_none()
    if row is None:
        return None
    pricing = Pricing(row.provider_type, row.input_per_million, row.output_per_million)
    _pricing_cache[model_id] = pricing
    return pricing


async def calculate_cost(
    db: AsyncSession,
    model_id: str,
    tokens_in: int | None,
    tokens_out: int | None,
) -> Decimal:
    """Calcula o custo em USD de uma chamada a um modelo."""
    pricing = await get_model_pricing(db, model_id)
    if not pricing:
        return Decimal("0")

    cost_in = Decimal(str(tokens_in or 0)) * pricing.input_per_million / Decimal("1000000")
    cost_out = Decimal(str(tokens_out or 0)) * pricing.output_per_million / Decimal("1000000")

    return (cost_in + cost_out).quantize(Decimal("0.000001"))


# ── Custo de ferramentas integradas ──────────────────────────────────────────
#
# Separado do custo por token porque a grandeza é outra: o Data Ocean cobra por
# GB processado, a busca por chamada e por página lida, a execução de código por
# minuto. Nada disso cabe em `input_per_million`/`output_per_million`.
#
# Por que uma constante no código, e não uma tabela no banco como
# `model_pricing`: são quatro valores que mudam com a política de preços do
# fornecedor, não por modelo. Uma tabela nova exigiria migration, seed e uma
# tela para editar quatro números — e o histórico de quanto se pagou fica
# preservado de qualquer forma, porque o CONSUMO é gravado cru em
# `extra_metadata`. Se os preços mudarem, o cálculo antigo pode ser refeito.
#
# ATENÇÃO: enquanto os valores forem `None`, `calcular_custo_ferramentas`
# devolve zero e o custo deste modo fica SUBESTIMADO nos relatórios. Isso é
# deliberado — ver `PRECOS_FERRAMENTAS_USD`.

# Câmbio usado para converter os preços da Maritaca, que são cobrados em REAIS,
# para o dólar em que o resto do sistema calcula custo.
#
# ISTO É UM GAP CONHECIDO E ACEITO, não um descuido.
#
# O valor é FIXO. O dólar flutua, então todo custo gravado para este provider
# carrega o erro entre esta taxa e a taxa do dia. Com o dólar a R$ 5,60, um
# custo calculado aqui está ~7% subestimado; a R$ 4,80, ~8% superestimado.
#
# Por que aceitar: a alternativa é consultar cotação a cada chamada, o que
# acrescenta uma dependência externa (e um modo de falha novo) no caminho de
# resposta ao médico, para corrigir um erro de poucos por cento sobre um custo
# que já é de centavos por consulta. A ordem de grandeza — que é o que importa
# para decidir se o modo está caro — não muda.
#
# Quando revisar: se o dólar sair da faixa de R$ 4,80 a R$ 5,60, ou se o custo
# deste modo passar a ser material no total da plataforma. O consumo bruto está
# gravado em `extra_metadata`, então recalcular o histórico com outra taxa é
# possível a qualquer momento.
BRL_POR_USD = Decimal("5.20")

# Preços das ferramentas integradas, EM REAIS, como a Maritaca publica.
#
# Guardados na moeda original de propósito: é o número que dá para conferir
# contra a fatura e contra a página de preços. A conversão acontece no cálculo,
# num lugar só, em vez de espalhar valores já convertidos que ninguém consegue
# auditar.
PRECOS_FERRAMENTAS_BRL: dict[str, Decimal] = {
    "data_ocean_gb_processed": Decimal("0.10"),    # R$ por GB processado
    "web_search_calls": Decimal("0.0165"),         # R$ por busca
    "page_reads": Decimal("0.066"),                # R$ por página lida
    # A Maritaca arredonda para cima o minuto de execução. Não replicamos o
    # arredondamento: a API já devolve `code_execution_minutes` arredondado.
    "code_execution_minutes": Decimal("0.016"),    # R$ por minuto
}


def custo_de_ferramentas_e_conhecido() -> bool:
    """Diz se a tabela de preços das ferramentas está preenchida.

    Hoje sempre True — existe para que um preço que venha a faltar (uma
    ferramenta nova da Maritaca, por exemplo) apareça como lacuna explícita em
    vez de virar zero silencioso no relatório.
    """
    return all(PRECOS_FERRAMENTAS_BRL.get(u) is not None for u in _UNIDADES_COBRADAS)


# Unidades que a API reporta em `usage.tool_execution_details`. Se a Maritaca
# passar a reportar uma unidade nova e ninguém puser o preço dela aqui,
# `custo_de_ferramentas_e_conhecido()` passa a devolver False — que é o aviso.
_UNIDADES_COBRADAS: frozenset[str] = frozenset({
    "data_ocean_gb_processed",
    "web_search_calls",
    "page_reads",
    "code_execution_minutes",
})


def calcular_custo_ferramentas(tool_usage: dict | None) -> Decimal:
    """
    Converte o consumo de ferramentas em dólar.

    Devolve zero quando não há consumo — o caso da maioria das respostas.

    O resultado sai em USD, convertido de BRL por `BRL_POR_USD`, que é uma taxa
    FIXA: ver o comentário daquela constante sobre o erro que isso embute e
    quando revisá-la.

    Uma unidade sem preço na tabela é ignorada em vez de derrubar o cálculo: o
    custo das demais ainda é melhor que custo nenhum, e
    `custo_de_ferramentas_e_conhecido()` sinaliza a lacuna.
    """
    if not tool_usage:
        return Decimal("0")

    total_brl = Decimal("0")
    for unidade, consumo in tool_usage.items():
        preco = PRECOS_FERRAMENTAS_BRL.get(unidade)
        if preco is None or not consumo:
            continue
        total_brl += Decimal(str(consumo)) * preco

    # A divisão vem DEPOIS da soma: converter cada parcela e somar acumularia
    # erro de arredondamento em valores que já são frações de centavo.
    return (total_brl / BRL_POR_USD).quantize(Decimal("0.000001"))
