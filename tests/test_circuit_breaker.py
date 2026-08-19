"""
Disjuntor das integrações externas (item 3.1 do plano de prontidão).

O que ele resolve não é a integração CAIR — os `try/except` dos serviços já
degradam a resposta. É a integração ficar LENTA: sem disjuntor, cada consulta
espera o timeout inteiro (15s no PharmaDB) antes de desistir, segurando conexão.
Uma dependência doente degrada o sistema todo.
"""

import asyncio

import pytest

from app.core import circuit_breaker
from app.core.circuit_breaker import CircuitoAberto, Disjuntor, Estado


@pytest.fixture(autouse=True)
def circuitos_limpos():
    circuit_breaker.reset_todos()
    yield
    circuit_breaker.reset_todos()


async def _ok():
    return "resposta"


async def _falha():
    raise RuntimeError("integração fora do ar")


# ── Estado normal ────────────────────────────────────────────────────────

async def test_chamada_bem_sucedida_passa():
    d = Disjuntor("teste", limite_falhas=3)
    assert await d.chama(_ok) == "resposta"
    assert d.estado is Estado.FECHADO


async def test_falhas_abaixo_do_limite_nao_abrem():
    d = Disjuntor("teste", limite_falhas=3)

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await d.chama(_falha)

    assert d.estado is Estado.FECHADO


async def test_sucesso_zera_o_contador():
    """Falhas esparsas não podem somar até abrir — só sequência importa."""
    d = Disjuntor("teste", limite_falhas=3)

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await d.chama(_falha)
    await d.chama(_ok)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await d.chama(_falha)

    assert d.estado is Estado.FECHADO


# ── Abertura ─────────────────────────────────────────────────────────────

async def test_abre_ao_atingir_o_limite():
    d = Disjuntor("teste", limite_falhas=3)

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await d.chama(_falha)

    assert d.estado is Estado.ABERTO


async def test_aberto_falha_sem_chamar_a_integracao():
    """O ponto todo: não gastar mais um timeout numa integração que já se sabe fora."""
    d = Disjuntor("teste", limite_falhas=1)
    chamadas = []

    async def _conta_e_falha():
        chamadas.append(1)
        raise RuntimeError("fora do ar")

    with pytest.raises(RuntimeError):
        await d.chama(_conta_e_falha)

    with pytest.raises(CircuitoAberto):
        await d.chama(_conta_e_falha)

    assert len(chamadas) == 1, "A integração foi chamada com o circuito aberto"


async def test_falha_rapido_quando_aberto():
    """Com o circuito aberto a resposta é imediata, não espera o timeout."""
    import time

    d = Disjuntor("teste", limite_falhas=1)

    async def _lento():
        await asyncio.sleep(2)
        raise RuntimeError("timeout")

    with pytest.raises(RuntimeError):
        await d.chama(_lento)

    inicio = time.monotonic()
    with pytest.raises(CircuitoAberto):
        await d.chama(_lento)
    # Margem folgada de propósito: o ponto é 'imediato vs. os 2s do sleep',
    # e margem apertada vira teste intermitente sob instrumentação de cobertura.
    assert time.monotonic() - inicio < 0.5


async def test_excecao_informa_quando_tentar_de_novo():
    d = Disjuntor("pharmadb", limite_falhas=1, descanso_segundos=30)
    with pytest.raises(RuntimeError):
        await d.chama(_falha)

    with pytest.raises(CircuitoAberto) as exc:
        await d.chama(_ok)

    assert exc.value.nome == "pharmadb"
    assert 0 < exc.value.segundos_restantes <= 30


# ── Recuperação ──────────────────────────────────────────────────────────

async def test_passa_a_meio_aberto_apos_o_descanso():
    d = Disjuntor("teste", limite_falhas=1, descanso_segundos=0.2)
    with pytest.raises(RuntimeError):
        await d.chama(_falha)
    assert d.estado is Estado.ABERTO

    await asyncio.sleep(0.3)

    assert d.estado is Estado.MEIO_ABERTO


async def test_sucesso_em_meio_aberto_religa():
    d = Disjuntor("teste", limite_falhas=1, descanso_segundos=0.2)
    with pytest.raises(RuntimeError):
        await d.chama(_falha)
    await asyncio.sleep(0.3)

    assert await d.chama(_ok) == "resposta"
    assert d.estado is Estado.FECHADO


async def test_falha_em_meio_aberto_reabre_na_hora():
    """
    Não vale gastar mais N tentativas para descobrir que ainda está fora:
    uma falha no teste de terreno reabre imediatamente.
    """
    d = Disjuntor("teste", limite_falhas=5, descanso_segundos=0.2)
    with pytest.raises(RuntimeError):
        await d.chama(_falha)
    d._estado = Estado.ABERTO  # força o estado como se tivesse batido o limite
    await asyncio.sleep(0.3)
    assert d.estado is Estado.MEIO_ABERTO

    with pytest.raises(RuntimeError):
        await d.chama(_falha)

    assert d.estado is Estado.ABERTO


# ── Integração com os serviços ───────────────────────────────────────────

async def test_curseduca_traduz_circuito_aberto_para_fail_closed():
    """
    Circuito aberto na Curseduca precisa virar `CurseducaNotConfigured`, que o
    endpoint converte em 503 — nunca em "membro válido".
    """
    from app.services.curseduca_service import CurseducaNotConfigured, _fetch_member_status

    circuit_breaker.curseduca._estado = Estado.ABERTO
    circuit_breaker.curseduca._aberto_em = __import__("time").monotonic()

    with pytest.raises(CurseducaNotConfigured):
        await _fetch_member_status("alguem@example.com", "https://api.exemplo", "chave", "token")


def test_estado_geral_lista_as_integracoes():
    estado = circuit_breaker.estado_geral()
    assert set(estado) == {"pharmadb", "pubmed", "curseduca"}
    assert all(v == "fechado" for v in estado.values())
