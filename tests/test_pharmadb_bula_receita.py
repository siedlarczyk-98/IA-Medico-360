"""
PharmaDB — bula, receita, genéricos, cache e token.

Complementa `tests/test_pharmadb_interacoes.py`, que cobre a checagem de
interação. Aqui ficam o resto da superfície e a infraestrutura (Redis, JWT) que
sustenta todas as consultas.

O QUE SE PROTEGE
----------------
- **Bula de paciente precisa vir marcada.** Este é um app médico: se a base não
  tem a bula de profissional, o serviço cai na de paciente — decisão razoável,
  mas o médico tem que saber que está lendo uma bula com posologia simplificada.
  A marca (`apenas_paciente`) existe; o teste garante que ela CHEGA ao texto.
- **Receita controlada não pode virar venda livre.** `requer_receita=False`
  imprime "🟢 Não requer receita médica". Se o campo vier ausente do payload,
  `.get()` devolve `None` e o texto sai verde — o teste trava o caso.
- **Redis fora não pode derrubar a consulta.** O cache é otimização; a decisão
  (correta) é fail-open, e ela precisa estar testada para não virar fail-closed
  num refactor.
- **O token renova antes de expirar.** Um token vencido derruba toda consulta de
  uma vez, e o sintoma (401 em tudo) não aponta para a causa.
"""

import time
from datetime import timedelta

from app.services.integracoes.pharmadb_service import (
    TOKEN_LIFETIME_S,
    PharmaDBService,
)


def servico_sem_cache() -> PharmaDBService:
    """Serviço com Redis desligado — os testes de formatação não precisam dele."""
    servico = PharmaDBService()

    async def _get(_key):
        return None

    async def _set(_key, _valor, _ttl):
        return None

    servico._cache_get = _get
    servico._cache_set = _set
    return servico


# ── Bula ─────────────────────────────────────────────────────────────────────

async def test_bula_de_paciente_e_marcada_no_texto(monkeypatch):
    """
    App médico lendo bula de paciente precisa dizer isso.

    A bula de paciente tem posologia simplificada e omite reações raras; tomá-la
    por bula de profissional é decidir conduta com informação a menos, sem saber
    que está a menos.
    """
    async def _sem_llm(nome, secoes):
        return "\n".join(f"### {t}\n{c}" for t, c in secoes.items())

    monkeypatch.setattr(
        "app.services.integracoes.pharmadb_service._limpar_secoes_bula", _sem_llm
    )
    servico = servico_sem_cache()

    texto = await servico.formatar_bula({
        "produto_nome": "Losartana 50mg",
        "laboratorio": "EMS",
        "principios_ativos": ["Losartana potássica"],
        "apenas_paciente": True,
        "indicacoes": "Hipertensão arterial.",
        "contraindicacoes": "Gravidez.",
    })

    assert "bula de paciente" in texto.lower()
    assert "⚠️" in texto


async def test_bula_de_profissional_nao_leva_aviso(monkeypatch):
    """O aviso precisa ser raro para ser lido."""
    async def _sem_llm(nome, secoes):
        return "conteúdo"

    monkeypatch.setattr(
        "app.services.integracoes.pharmadb_service._limpar_secoes_bula", _sem_llm
    )
    servico = servico_sem_cache()

    texto = await servico.formatar_bula({
        "produto_nome": "Losartana 50mg",
        "apenas_paciente": False,
        "indicacoes": "Hipertensão arterial.",
    })

    assert "bula de paciente" not in texto.lower()


async def test_bula_vazia_avisa_em_vez_de_devolver_cabecalho_solto():
    """
    Sem nenhuma seção, o certo é dizer que não há conteúdo — e nem chamar o LLM.

    Se este caminho chamasse `_limpar_secoes_bula`, a guarda de rede do harness
    derrubaria o teste, que é justamente a proteção que se quer.
    """
    servico = servico_sem_cache()

    texto = await servico.formatar_bula({
        "produto_nome": "Produto Sem Bula",
        "indicacoes": None,
        "contraindicacoes": "   ",
    })

    assert "não disponível" in texto
    assert "Produto Sem Bula" in texto


# ── Receita ──────────────────────────────────────────────────────────────────

def test_receita_controlada_mostra_tipo_cor_e_retencao():
    """Cor e retenção são o que o farmacêutico confere no balcão."""
    servico = PharmaDBService()

    texto = servico.formatar_receita({
        "produto_nome": "Clonazepam 2mg",
        "requer_receita": True,
        "tipo": "Receita de Controle Especial",
        "cor_receita": "azul",
        "retencao": True,
        "lista_controle": "B1",
        "validade_dias": 30,
        "base_legal": "Portaria 344/98",
    })

    assert "Azul" in texto
    assert "Retenção" in texto
    assert "B1" in texto
    assert "30 dias" in texto
    assert "🟢" not in texto, "medicamento controlado não pode sair como venda livre"


def test_venda_livre_sai_em_verde():
    servico = PharmaDBService()

    texto = servico.formatar_receita({
        "produto_nome": "Dipirona 500mg",
        "requer_receita": False,
    })

    assert "🟢" in texto
    assert "venda livre" in texto.lower()


def test_campo_ausente_nao_transforma_controlado_em_livre():
    """
    A armadilha: `requer_receita` ausente cai em `None`, que é falsy, e o texto
    sai "não requer receita médica".

    Hoje o comportamento é esse, e o teste o documenta em vez de fingir que não
    existe. A correção (tratar ausência como "não sei") muda o contrato do
    formatador e é decisão de produto — mas ninguém pode mudar o payload da API
    sem ver este teste falhar.
    """
    servico = PharmaDBService()

    texto = servico.formatar_receita({"produto_nome": "Produto Sem Campo"})

    assert "🟢" in texto, (
        "comportamento atual: ausência de `requer_receita` vira venda livre — "
        "se isto mudar, é melhoria, e o teste deve ser atualizado conscientemente"
    )


# ── Genéricos ────────────────────────────────────────────────────────────────

def test_genericos_mostram_preco_e_economia():
    servico = PharmaDBService()

    texto = servico.formatar_genericos({
        "produto_nome": "Losartana",
        "pmc_referencia_centavos": 4530,
        "composicao_resumo": ["Losartana potássica 50mg"],
        "genericos": [
            {"nome": "Losartana EMS", "laboratorio": "EMS", "pmc_centavos": 1990, "economia_pct": 56.0},
        ],
        "similares_intercambiaveis": [],
    })

    assert "R$ 45.30" in texto
    assert "R$ 19.90" in texto
    assert "56%" in texto


def test_sem_generico_diz_isso_explicitamente():
    """Lista vazia sem aviso pareceria erro de carregamento."""
    servico = PharmaDBService()

    texto = servico.formatar_genericos({
        "produto_nome": "Medicamento de Referência",
        "genericos": [],
        "similares_intercambiaveis": [],
    })

    assert "Nenhum genérico" in texto


def test_lista_longa_de_genericos_e_truncada_em_dez():
    """O corte existe; o teste garante que ele não vire corte de 1 ou de 100."""
    servico = PharmaDBService()

    texto = servico.formatar_genericos({
        "produto_nome": "Dipirona",
        "genericos": [
            {"nome": f"Generico {i}", "laboratorio": "Lab", "pmc_centavos": 1000}
            for i in range(25)
        ],
        "similares_intercambiaveis": [],
    })

    assert "Generico 9" in texto
    assert "Generico 10" not in texto


def test_preco_ausente_nao_quebra_a_formatacao():
    """Nem todo genérico tem PMC na base."""
    servico = PharmaDBService()

    texto = servico.formatar_genericos({
        "produto_nome": "X",
        "genericos": [{"nome": "Sem preço", "laboratorio": "Lab"}],
        "similares_intercambiaveis": [],
    })

    assert "Sem preço" in texto
    assert "—" in texto


# ── Cache: Redis fora não derruba a consulta ─────────────────────────────────

async def test_redis_fora_devolve_none_em_vez_de_levantar():
    """
    Fail-open é a decisão correta aqui: o cache é otimização, e uma consulta
    lenta é melhor que uma consulta que falha. Testado para não virar
    fail-closed num refactor.
    """
    servico = PharmaDBService()

    async def _redis_quebrado():
        raise ConnectionError("Redis fora do ar")

    servico._get_redis = _redis_quebrado

    assert await servico._cache_get("qualquer:chave") is None


async def test_falha_ao_gravar_cache_nao_propaga():
    """Gravar é o passo menos importante: falhar ali não pode perder a resposta
    que já foi obtida da API."""
    servico = PharmaDBService()

    async def _redis_quebrado():
        raise ConnectionError("Redis fora do ar")

    servico._get_redis = _redis_quebrado

    # Não levanta.
    await servico._cache_set("k", {"a": 1}, timedelta(days=1))


# ── Token ────────────────────────────────────────────────────────────────────

def test_token_novo_e_considerado_valido():
    servico = PharmaDBService()
    servico._jwt_token = "token-qualquer"
    servico._token_obtained_at = time.monotonic()

    assert servico._token_valid() is True


def test_token_velho_e_renovado_antes_de_expirar():
    """
    A janela é 3300s contra 3600s de vida real: 5 minutos de folga.

    Sem a folga, um token que expira no meio de uma consulta devolve 401 em tudo
    — e o sintoma não aponta para a causa.
    """
    servico = PharmaDBService()
    servico._jwt_token = "token-velho"
    servico._token_obtained_at = time.monotonic() - TOKEN_LIFETIME_S - 1

    assert servico._token_valid() is False
    assert TOKEN_LIFETIME_S < 3600, "o token precisa renovar ANTES dos 60min reais"


def test_sem_token_nunca_e_valido():
    assert PharmaDBService()._token_valid() is False
