"""
Os modos de farmácia são atendidos DENTRO do stream.

Antes o stream os recusava (`unsupported_mode`) e o frontend refazia a pergunta em
`/query`: mascaramento de dados, triagem e extração do nome do medicamento pagos
duas vezes, no segundo modo mais usado. Agora é uma ida só, e o contrato SSE é o
mesmo dos outros modos — o texto só chega num evento único, porque a base
responde de uma vez.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.models import Interaction, InteractionResponse, PharmaAlert
from app.services.integracoes.pharmadb_service import PharmaDBIndisponivelError
from app.services.orquestrador_stream_service import OrquestradorStreamService
from tests.conftest import fabrica_sobre
from tests.test_orquestrador_stream import (  # noqa: F401 — fixture autouse reusada
    _coleta,
    sem_dependencias_externas,
)


@pytest.fixture
def servico(db, db_conn, user):
    return OrquestradorStreamService(fabrica_sobre(db_conn), user.id)


@pytest.fixture
def pharmadb(monkeypatch):
    """Instala um dublê do PharmaDB e o extrator de medicamentos."""
    def _instalar(meds, **metodos):
        async def _extrair(_texto):
            return meds

        monkeypatch.setattr("app.services.medication_extractor.extract_medications", _extrair)
        monkeypatch.setattr(
            "app.services.integracoes.pharmadb_service.get_pharmadb_service",
            lambda: SimpleNamespace(**metodos),
        )

    return _instalar


async def test_bula_sai_pelo_stream_com_o_contrato_sse_normal(servico, db, pharmadb):
    async def buscar_bula(_nome):
        return {"produto_nome": "Rivotril"}

    pharmadb(
        [{"raw": "Rivotril", "normalized": "clonazepam"}],
        buscar_bula=buscar_bula,
        formatar_bula=lambda _r: "## Bula de Rivotril\n\nPosologia: 0,5 mg.",
    )

    eventos = await _coleta(servico, prompt="qual a bula do Rivotril?", mode="PHARMA_BULA")

    nomes = [n for n, _ in eventos]
    assert nomes == ["start", "token", "text_done", "done"], nomes
    assert "unsupported_mode" not in str(eventos)
    assert eventos[1][1]["text"].startswith("## Bula de Rivotril")
    assert eventos[-1][1]["mode"] == "PHARMA_BULA"

    gravada = (await db.execute(select(Interaction))).scalar_one()
    resposta = (await db.execute(select(InteractionResponse))).scalar_one()
    assert gravada.status == "completed"
    assert resposta.model_used == "pharmadb"
    assert resposta.cost_usd == 0, "consulta à base não é chamada de modelo"


async def test_interacoes_gravam_os_alertas_pelo_stream(servico, db, pharmadb, monkeypatch):
    # `PHARMA_CHECK` explícito AINDA passa pela triagem, para descobrir o sub-modo
    # (ver `decidir_rota`). O fake padrão devolve QUICK_SEARCH; aqui ela confirma.
    async def _triagem(*_a, **_kw):
        return {"mode": "PHARMA_CHECK", "confidence": 0.99, "category": "PHARMA_CHECK"}

    monkeypatch.setattr("app.services.orquestrador_shared.triage", _triagem)

    async def checar_interacoes(_nomes):
        return {
            "status": "interacoes_encontradas",
            "interacoes": [{
                "pa_a": "Varfarina", "pa_b": "AAS", "efeito_clinico": "sangramento",
                "semaforo_level": 4, "semaforo_color": "RED",
            }],
        }

    pharmadb(
        [{"normalized": "varfarina"}, {"normalized": "aas"}],
        checar_interacoes=checar_interacoes,
        formatar_interacoes=lambda _r: "🔴 Varfarina ↔ AAS: sangramento",
    )

    eventos = await _coleta(servico, prompt="varfarina com AAS interage?", mode="PHARMA_CHECK")

    assert [n for n, _ in eventos][-1] == "done"
    alerta = (await db.execute(select(PharmaAlert))).scalar_one()
    assert alerta.alert_color == "RED"


async def test_base_fora_do_ar_avisa_e_marca_fallback_tambem_no_stream(
    servico, pharmadb, monkeypatch
):
    async def buscar_receita(_nome):
        raise PharmaDBIndisponivelError("falha ao consultar receituário")

    async def _agente(self, mode, prompt, **_kw):
        return {"text": "resposta do modelo", "model_id": "sonar-pro", "is_fallback": False}

    pharmadb([{"raw": "Rivotril", "normalized": "clonazepam"}], buscar_receita=buscar_receita)
    monkeypatch.setattr(
        "app.services.orquestrador_service.OrquestradorService._handle_ai_agent", _agente
    )

    eventos = await _coleta(servico, prompt="Rivotril precisa de receita?", mode="PHARMA_RECEITA")

    texto = eventos[1][1]["text"]
    assert "temporariamente indisponível" in texto
    assert "não encontrado" not in texto.lower()
    assert eventos[-1][1]["is_fallback"] is True
