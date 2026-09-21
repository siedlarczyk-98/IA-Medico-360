"""
PharmaDB fora do ar NÃO é "não encontrado na base".

O QUE ISTO VEIO CONSERTAR
Bula, receituário, genéricos, produto, princípio ativo e histórico terminavam em
`except Exception: return None`. O orquestrador lê `None` como "a base respondeu
e não tem", e respondia ao médico "não encontrado na base PharmaDB. Verifique o
nome do medicamento" com a base FORA DO AR. No receituário, "não encontrado" se
lê como "não é controlado". É a mesma classe do falso verde das interações
(`test_pharmadb_interacoes.py`), nas outras consultas.

POR QUE TRANSPORTE FALSO, E NÃO DUBLÊ DO SERVIÇO
Os 29 testes que existiam substituem o próprio `PharmaDBService` ou chamam os
formatadores com dicionários inventados: toda a camada HTTP tinha cobertura
zero, e era nela que o defeito morava. Aqui o serviço é o REAL; só o fio é
falso (`httpx.MockTransport`). Timeout, 503 e 404 percorrem o mesmo código que
percorrem em produção — token, retry de 401, disjuntor, classificação do erro.

Os corpos de resposta seguem os campos que o serviço lê. Não são gravações da
API real: gravá-las exige chave de produção, que a suíte não carrega de propósito.
"""

from uuid import uuid4

import httpx
import pytest

from app.core import circuit_breaker
from app.services.integracoes import pharmadb_service
from app.services.integracoes.pharmadb_service import (
    InteracoesIndisponiveisError,
    PharmaDBIndisponivelError,
    PharmaDBService,
)
from app.services.orquestrador_service import OrquestradorService

PRODUTO = {
    "id": 77, "nome": "Rivotril", "laboratorio": "Roche", "tarja": "preta",
    "categoria_regulatoria": "referencia", "principios_ativos": ["clonazepam"],
}
RECEITA = {
    "produto_nome": "Rivotril", "tarja": "preta", "tipo": "B1", "cor_receita": "azul",
    "requer_receita": True, "retencao": True, "vias": 1, "validade_dias": 30,
    "lista_controle": "B1", "base_legal": "Portaria 344/98", "observacao": None,
}
BULA = {
    "id": 5, "tipo": "profissional",
    "produto": {"nome": "Rivotril", "laboratorio": "Roche", "principios_ativos": ["clonazepam"]},
    "texto_indicacoes": "Transtornos de ansiedade.", "texto_contraindicacoes": "Glaucoma agudo.",
    "texto_posologia": "0,5 mg 2x/dia.", "texto_reacoes_adversas": "Sonolência.",
    "texto_interacoes": "Álcool.",
}
GENERICOS = {
    "produto_nome": "Rivotril", "categoria_regulatoria": "referencia",
    "composicao_resumo": ["clonazepam 2 mg"], "pmc_referencia_centavos": 2590,
    "total_genericos": 1, "total_similares": 0,
    "genericos": [{"nome": "Clonazepam EMS", "pmc_centavos": 990}],
    "similares_intercambiaveis": [],
}


def _base_no_ar(request: httpx.Request) -> httpx.Response:
    """A API respondendo normalmente para o Rivotril."""
    caminho = request.url.path
    if caminho == "/auth/token":
        return httpx.Response(200, json={"access_token": "token-de-teste"})
    if caminho == "/v1/produtos/busca":
        return httpx.Response(200, json={"items": [PRODUTO]})
    if caminho == "/v1/produtos/77/receita":
        return httpx.Response(200, json=RECEITA)
    if caminho == "/v1/produtos/77/genericos":
        return httpx.Response(200, json=GENERICOS)
    if caminho == "/v1/bulas/busca":
        return httpx.Response(200, json={"items": [{"id": 5, "tipo": "profissional"}]})
    if caminho == "/v1/bulas/5":
        return httpx.Response(200, json=BULA)
    return httpx.Response(404, json={"detail": "not found"})


def _base_vazia(request: httpx.Request) -> httpx.Response:
    """A API no ar, respondendo que não conhece o termo."""
    if request.url.path == "/auth/token":
        return httpx.Response(200, json={"access_token": "token-de-teste"})
    return httpx.Response(200, json={"items": []})


def _so_a_consulta(falha):
    """Autenticação funciona; toda consulta depois dela sofre `falha`."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/token":
            return httpx.Response(200, json={"access_token": "token-de-teste"})
        return falha(request)
    return handler


def _503(_request):
    return httpx.Response(503, text="upstream unavailable")


def _timeout(request):
    raise httpx.ReadTimeout("", request=request)


def _sem_conexao(request):
    raise httpx.ConnectError("connection refused", request=request)


def _malformado(_request):
    # 200 com corpo que não é o contrato: item sem `id`/`nome`.
    return httpx.Response(200, json={"items": [{"inesperado": True}]})


QUEDAS = [
    pytest.param(_so_a_consulta(_503), id="503"),
    pytest.param(_so_a_consulta(_timeout), id="timeout"),
    pytest.param(_so_a_consulta(_sem_conexao), id="sem-conexao"),
    pytest.param(_503, id="autenticacao-fora"),
    pytest.param(_so_a_consulta(_malformado), id="resposta-malformada"),
]

CONSULTAS = ["buscar_bula", "buscar_receita", "buscar_genericos", "buscar_produto", "buscar_pa"]


@pytest.fixture
def servico_com(monkeypatch):
    """`PharmaDBService` real sobre um transporte falso, sem Redis."""
    clientes = []

    def _montar(handler) -> PharmaDBService:
        cliente = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        clientes.append(cliente)
        monkeypatch.setattr(pharmadb_service, "get_client", lambda: cliente)

        servico = PharmaDBService()

        async def _sem_cache_get(_chave):
            return None

        async def _sem_cache_set(*_a, **_kw):
            return None

        servico._cache_get = _sem_cache_get
        servico._cache_set = _sem_cache_set
        return servico

    return _montar


# ── Queda vira exceção, em toda consulta ─────────────────────────────────────

@pytest.mark.parametrize("queda", QUEDAS)
@pytest.mark.parametrize("consulta", CONSULTAS)
async def test_queda_levanta_indisponibilidade_e_nunca_devolve_none(servico_com, consulta, queda):
    servico = servico_com(queda)

    with pytest.raises(PharmaDBIndisponivelError):
        await getattr(servico, consulta)("rivotril")


# Sem o caso "malformada": o histórico repassa o JSON como veio, não há contrato
# de campos para violar.
@pytest.mark.parametrize("queda", QUEDAS[:-1])
async def test_historico_tambem_levanta(servico_com, queda):
    with pytest.raises(PharmaDBIndisponivelError):
        await servico_com(queda).get_historico_comercializacao(77)


async def test_circuito_aberto_e_indisponibilidade(servico_com):
    """Com o disjuntor aberto nenhuma chamada sai — e isso também não é "não achei"."""
    servico = servico_com(_base_no_ar)
    circuit_breaker.pharmadb._estado = circuit_breaker.Estado.ABERTO
    circuit_breaker.pharmadb._aberto_em = __import__("time").monotonic()

    with pytest.raises(PharmaDBIndisponivelError):
        await servico.buscar_receita("rivotril")


# ── `None` continua existindo, e significa uma coisa só ──────────────────────

@pytest.mark.parametrize("consulta", CONSULTAS)
async def test_base_no_ar_sem_resultado_devolve_none(servico_com, consulta):
    assert await getattr(servico_com(_base_vazia), consulta)("medicamento-inexistente") is None


async def test_404_no_detalhe_e_nao_encontrado(servico_com):
    """Produto existe, mas a base responde 404 para o receituário dele."""
    def handler(request):
        if request.url.path == "/v1/produtos/77/receita":
            return httpx.Response(404, json={"detail": "sem regime cadastrado"})
        return _base_no_ar(request)

    assert await servico_com(handler).buscar_receita("rivotril") is None


# ── O caminho feliz, pela camada HTTP de verdade ─────────────────────────────

async def test_receita_controlada_chega_inteira(servico_com):
    receita = await servico_com(_base_no_ar).buscar_receita("rivotril")

    assert receita["tarja"] == "preta"
    assert receita["lista_controle"] == "B1"
    assert receita["retencao"] is True


async def test_bula_profissional_chega_inteira(servico_com):
    bula = await servico_com(_base_no_ar).buscar_bula("rivotril")

    assert bula["tipo"] == "profissional"
    assert bula["apenas_paciente"] is False
    assert bula["posologia"] == "0,5 mg 2x/dia."


async def test_genericos_chegam_inteiros(servico_com):
    genericos = await servico_com(_base_no_ar).buscar_genericos("rivotril")

    assert genericos["total_genericos"] == 1
    assert genericos["genericos"][0]["nome"] == "Clonazepam EMS"


async def test_token_expirado_no_servidor_e_renovado_uma_vez(servico_com):
    """401 na consulta derruba o token em cache, e a segunda tentativa passa."""
    tokens_emitidos = []

    def handler(request):
        if request.url.path == "/auth/token":
            tokens_emitidos.append(f"token-{len(tokens_emitidos) + 1}")
            return httpx.Response(200, json={"access_token": tokens_emitidos[-1]})
        if request.headers["Authorization"] == "Bearer token-1":
            return httpx.Response(401, json={"detail": "expired"})
        return _base_no_ar(request)

    produto = await servico_com(handler).buscar_produto("rivotril")

    assert produto["produto_id"] == 77
    assert tokens_emitidos == ["token-1", "token-2"]


# ── Interações: PA que falhou não é PA não encontrado ────────────────────────

async def test_queda_ao_resolver_pa_aborta_a_checagem(servico_com):
    with pytest.raises(InteracoesIndisponiveisError):
        await servico_com(_so_a_consulta(_503)).checar_interacoes(["varfarina", "aas"])


# ── De ponta a ponta: o que o médico lê ──────────────────────────────────────

@pytest.fixture
def orquestrador(monkeypatch):
    async def _extrair(_texto):
        return [{"raw": "Rivotril", "normalized": "clonazepam"}]

    async def _agente(self, mode, prompt, **_kw):
        return {"text": f"[{mode}] resposta do modelo", "model_id": "modelo", "is_fallback": False}

    monkeypatch.setattr("app.services.medication_extractor.extract_medications", _extrair)
    monkeypatch.setattr(OrquestradorService, "_handle_ai_agent", _agente)
    return OrquestradorService(db=None, user_id=uuid4())


@pytest.mark.parametrize("modo", ["PHARMA_RECEITA", "PHARMA_BULA", "PHARMA_GENERICO"])
@pytest.mark.parametrize("queda", QUEDAS)
async def test_medico_le_aviso_de_indisponibilidade_e_nao_nao_encontrado(
    servico_com, orquestrador, monkeypatch, modo, queda
):
    servico = servico_com(queda)
    monkeypatch.setattr(pharmadb_service, "get_pharmadb_service", lambda: servico)

    resposta = await orquestrador._handle_pharma("Rivotril precisa de receita?", modo)

    assert "temporariamente indisponível" in resposta["text"]
    assert resposta["is_fallback"] is True
    assert "não encontrado" not in resposta["text"].lower(), (
        "Com a base fora do ar o médico leu 'não encontrado' — no receituário "
        "isso se confunde com 'não é controlado'."
    )


async def test_queda_entre_a_busca_e_a_mensagem_tambem_vira_aviso(
    servico_com, orquestrador, monkeypatch
):
    """
    A bula respondeu "vazio" e a base caiu logo depois, na consulta de produto
    que enriquece a mensagem de não encontrado. Antes isso saía do `try`.
    """
    def handler(request):
        if request.url.path == "/v1/bulas/busca":
            return httpx.Response(200, json={"items": []})
        return _so_a_consulta(_503)(request)

    servico = servico_com(handler)
    monkeypatch.setattr(pharmadb_service, "get_pharmadb_service", lambda: servico)

    resposta = await orquestrador._handle_pharma("bula do Rivotril", "PHARMA_BULA")

    assert "temporariamente indisponível" in resposta["text"]
    assert resposta["is_fallback"] is True


async def test_nao_encontrado_de_verdade_continua_dizendo_nao_encontrado(
    servico_com, orquestrador, monkeypatch
):
    """A correção não pode ter transformado todo vazio em "indisponível"."""
    servico = servico_com(_base_vazia)
    monkeypatch.setattr(pharmadb_service, "get_pharmadb_service", lambda: servico)

    resposta = await orquestrador._handle_pharma("receita de Xyzabc", "PHARMA_RECEITA")

    assert "não encontrado na base PharmaDB" in resposta["text"]
    assert resposta["is_fallback"] is False
