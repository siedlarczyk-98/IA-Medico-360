"""
Roteamento dos modos PharmaDB no orquestrador — e como eles DEGRADAM.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
`orquestrador_service.py` estava em 61%, e o maior bloco descoberto era
justamente o roteamento para o PharmaDB (`_handle_pharma_check` e
`_handle_pharma`). É o caminho que decide o que o médico vê quando pergunta
sobre interação, bula, receita ou genérico — incluindo o que ele vê quando a
base está fora do ar.

A degradação é a parte que mais importa, e ela tem uma assimetria DELIBERADA que
estes testes travam:

- **Interação medicamentosa** cai para `CLINICAL_REASONING` — raciocínio clínico,
  porque a pergunta é sobre risco entre fármacos e o modelo tem algo a dizer.
- **Bula, receita e genérico** caem para `QUICK_SEARCH` — busca, porque a
  pergunta é factual (qual a posologia, qual a tarja) e raciocinar sobre ela
  seria inventar.

Nos dois casos o texto sai **precedido de um aviso** e marcado
`is_fallback=True`. Isso não é cosmético: sem o aviso, o médico leria uma
resposta construída da memória do modelo achando que veio da base oficial da
ANVISA — exatamente o risco que o `DATA_OCEAN` evita não tendo fallback nenhum.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.orquestrador_service import OrquestradorService


@pytest.fixture
def servico():
    """
    Serviço sem banco real.

    `_handle_pharma` e `_handle_pharma_check` não tocam a sessão a não ser para
    `db.add(PharmaAlert(...))`, que o dublê registra para os testes inspecionarem.
    """
    class DbFalso:
        def __init__(self):
            self.adicionados = []

        def add(self, obj):
            self.adicionados.append(obj)

    servico = OrquestradorService(db=DbFalso(), user_id=uuid4())
    return servico


def instalar_pharmadb(monkeypatch, **metodos):
    """Substitui o singleton do PharmaDB por um dublê com os métodos dados."""
    falso = SimpleNamespace(**metodos)
    monkeypatch.setattr(
        "app.services.integracoes.pharmadb_service.get_pharmadb_service",
        lambda: falso,
    )
    return falso


def instalar_extrator(monkeypatch, meds: list[dict]):
    async def _extrair(_texto):
        return meds

    monkeypatch.setattr(
        "app.services.medication_extractor.extract_medications", _extrair
    )


def capturar_fallback(monkeypatch, servico, texto="resposta do modelo"):
    """Substitui `_handle_ai_agent` e registra com qual MODO ele foi chamado."""
    chamadas = []

    async def _agente(mode, prompt, **kwargs):
        chamadas.append(mode)
        return {"text": texto, "model_id": "algum-modelo", "is_fallback": False}

    monkeypatch.setattr(servico, "_handle_ai_agent", _agente)
    return chamadas


# ── PHARMA_CHECK: interação medicamentosa ────────────────────────────────────

async def test_menos_de_dois_farmacos_pede_reformulacao_sem_chamar_a_base(
    servico, monkeypatch
):
    """
    Checar interação com um fármaco só não é pergunta respondível.

    O importante é que isto acontece ANTES de qualquer chamada — não se gasta
    requisição, e o médico recebe uma instrução do que fazer em vez de um erro.
    """
    instalar_extrator(monkeypatch, [{"raw": "AAS", "normalized": "acido acetilsalicilico"}])
    instalar_pharmadb(monkeypatch)  # sem métodos: qualquer chamada levantaria

    resposta = await servico._handle_pharma_check("posso usar AAS?", uuid4())

    assert "pelo menos 2" in resposta["text"]
    assert resposta["is_fallback"] is False


async def test_interacoes_encontradas_viram_alertas_no_banco(servico, monkeypatch):
    """
    Cada interação vira um `PharmaAlert` persistido.

    É o registro que permite auditar depois o que foi mostrado ao médico — numa
    resposta com consequência de prescrição, "o que o sistema disse" não pode
    depender de reconstruir a chamada.
    """
    instalar_extrator(monkeypatch, [
        {"raw": "Varfarina", "normalized": "varfarina"},
        {"raw": "AAS", "normalized": "acido acetilsalicilico"},
    ])

    async def _checar(_nomes):
        return {
            "status": "interacoes_encontradas",
            "total_interacoes": 1,
            "medicamentos_encontrados": ["Varfarina", "AAS"],
            "interacoes": [{
                "pa_a": "Varfarina", "pa_b": "AAS",
                "semaforo_level": 4, "semaforo_color": "RED",
                "efeito_clinico": "risco de sangramento",
            }],
        }

    instalar_pharmadb(
        monkeypatch,
        checar_interacoes=_checar,
        formatar_interacoes=lambda r: "texto formatado",
    )

    resposta = await servico._handle_pharma_check("varfarina e aas", uuid4())

    assert resposta["text"] == "texto formatado"
    assert resposta["model_id"] == "pharmadb"
    assert len(servico.db.adicionados) == 1
    alerta = servico.db.adicionados[0]
    assert alerta.alert_color == "RED"
    assert "Varfarina" in alerta.description and "sangramento" in alerta.description


async def test_base_fora_do_ar_cai_para_raciocinio_clinico_COM_aviso(
    servico, monkeypatch
):
    """
    A degradação mais importante do arquivo.

    Sem o aviso no início do texto, o médico leria uma resposta construída da
    memória do modelo achando que veio da base de interações. O
    `is_fallback=True` é o que a interface usa para marcar a resposta.
    """
    instalar_extrator(monkeypatch, [
        {"raw": "Varfarina", "normalized": "varfarina"},
        {"raw": "AAS", "normalized": "acido acetilsalicilico"},
    ])

    async def _explode(_nomes):
        raise RuntimeError("PharmaDB indisponível")

    instalar_pharmadb(monkeypatch, checar_interacoes=_explode)
    modos = capturar_fallback(monkeypatch, servico, "análise do modelo")

    resposta = await servico._handle_pharma_check("varfarina e aas", uuid4())

    # Raciocínio clínico, NÃO busca: a pergunta é sobre risco entre fármacos.
    assert modos == ["CLINICAL_REASONING"]
    assert resposta["is_fallback"] is True
    assert resposta["text"].startswith("⚠️")
    assert "temporariamente indisponível" in resposta["text"]
    # O conteúdo do modelo continua lá, depois do aviso.
    assert "análise do modelo" in resposta["text"]


# ── PHARMA_BULA / RECEITA / GENERICO ─────────────────────────────────────────

@pytest.mark.parametrize(
    ("modo", "metodo_busca", "metodo_formata"),
    [
        ("PHARMA_BULA", "buscar_bula", "formatar_bula"),
        ("PHARMA_RECEITA", "buscar_receita", "formatar_receita"),
        ("PHARMA_GENERICO", "buscar_genericos", "formatar_genericos"),
    ],
)
async def test_cada_modo_chama_o_metodo_correspondente(
    servico, monkeypatch, modo, metodo_busca, metodo_formata
):
    """
    `PHARMA_MODE_CONFIG` mapeia modo → (buscar, formatar, rótulo) por NOME de
    atributo. Um nome trocado ali devolveria a bula de um produto para quem
    perguntou o receituário — sem erro nenhum, porque as assinaturas batem.
    """
    instalar_extrator(monkeypatch, [{"raw": "Losartana", "normalized": "losartana"}])

    async def _buscar(_nome):
        return {"produto_nome": "Losartana"}

    instalar_pharmadb(monkeypatch, **{
        metodo_busca: _buscar,
        metodo_formata: lambda _r: f"saida de {metodo_formata}",
    })

    resposta = await servico._handle_pharma("losartana", modo)

    assert resposta["text"] == f"saida de {metodo_formata}"


async def test_formatador_assincrono_e_aguardado(servico, monkeypatch):
    """
    `formatar_bula` é async (chama um LLM para limpar o texto do PDF); os outros
    dois são síncronos. O `inspect.isawaitable` resolve a diferença — sem ele, a
    resposta seria a repr de uma corrotina.
    """
    instalar_extrator(monkeypatch, [{"raw": "Losartana", "normalized": "losartana"}])

    async def _buscar(_nome):
        return {"produto_nome": "Losartana"}

    async def _formatar_async(_r):
        return "bula formatada por LLM"

    instalar_pharmadb(monkeypatch, buscar_bula=_buscar, formatar_bula=_formatar_async)

    resposta = await servico._handle_pharma("losartana", "PHARMA_BULA")

    assert resposta["text"] == "bula formatada por LLM"


async def test_sem_medicamento_no_prompt_pede_o_nome(servico, monkeypatch):
    instalar_extrator(monkeypatch, [])
    instalar_pharmadb(monkeypatch)

    resposta = await servico._handle_pharma("me explica farmacologia", "PHARMA_BULA")

    assert "não identifiquei o nome do medicamento" in resposta["text"].lower()
    assert resposta["is_fallback"] is False


async def test_nao_encontrado_usa_a_mensagem_enriquecida_da_base(servico, monkeypatch):
    """
    Quando a busca não acha, a mensagem NÃO é um "não encontrado" genérico: o
    serviço consulta o histórico de comercialização para dizer se o produto foi
    descontinuado. "Não existe" e "existiu até 2023" são informações diferentes.
    """
    instalar_extrator(monkeypatch, [{"raw": "Produto X", "normalized": "produto x"}])

    async def _buscar(_nome):
        return None

    async def _mensagem(nome, contexto):
        return f"⚠️ {nome} foi descontinuado ({contexto})"

    instalar_pharmadb(
        monkeypatch, buscar_bula=_buscar, mensagem_nao_encontrado=_mensagem
    )

    resposta = await servico._handle_pharma("produto x", "PHARMA_BULA")

    assert "descontinuado" in resposta["text"]
    assert resposta["is_fallback"] is False


async def test_busca_tenta_o_nome_normalizado_quando_o_bruto_falha(
    servico, monkeypatch
):
    """
    O médico escreve "Aradois"; a base conhece "losartana". `_buscar_com_fallback`
    tenta o nome como foi escrito e depois o genérico — é o que faz a busca
    funcionar com nome comercial.
    """
    instalar_extrator(monkeypatch, [{"raw": "Aradois", "normalized": "losartana"}])
    tentativas = []

    async def _buscar(nome):
        tentativas.append(nome)
        return {"produto_nome": nome} if nome == "losartana" else None

    instalar_pharmadb(
        monkeypatch, buscar_receita=_buscar, formatar_receita=lambda r: r["produto_nome"]
    )

    resposta = await servico._handle_pharma("aradois", "PHARMA_RECEITA")

    assert tentativas == ["Aradois", "losartana"]
    assert resposta["text"] == "losartana"


async def test_base_fora_do_ar_cai_para_BUSCA_com_aviso(servico, monkeypatch):
    """
    A outra metade da assimetria: bula/receita/genérico caem para QUICK_SEARCH.

    A pergunta é factual (qual a posologia, qual a tarja) — raciocinar sobre ela
    seria inventar. Interação medicamentosa cai para CLINICAL_REASONING, pelo
    motivo oposto.
    """
    instalar_extrator(monkeypatch, [{"raw": "Losartana", "normalized": "losartana"}])

    async def _explode(_nome):
        raise RuntimeError("PharmaDB fora")

    instalar_pharmadb(monkeypatch, buscar_bula=_explode)
    modos = capturar_fallback(monkeypatch, servico, "texto do modelo")

    resposta = await servico._handle_pharma("losartana", "PHARMA_BULA")

    assert modos == ["QUICK_SEARCH"]
    assert resposta["is_fallback"] is True
    assert resposta["text"].startswith("⚠️")
    assert "PharmaDB está temporariamente indisponível" in resposta["text"]


async def test_os_dois_fallbacks_usam_modos_diferentes(servico, monkeypatch):
    """
    A assimetria em um teste só, para que ninguém a "uniformize" sem ler o
    porquê.
    """
    instalar_extrator(monkeypatch, [
        {"raw": "A", "normalized": "a"}, {"raw": "B", "normalized": "b"},
    ])

    async def _explode(*a, **k):
        raise RuntimeError("fora")

    instalar_pharmadb(monkeypatch, checar_interacoes=_explode, buscar_bula=_explode)
    modos = capturar_fallback(monkeypatch, servico)

    await servico._handle_pharma_check("a e b", uuid4())
    await servico._handle_pharma("a", "PHARMA_BULA")

    assert modos == ["CLINICAL_REASONING", "QUICK_SEARCH"]


async def test_falha_interna_da_base_chega_ao_medico_como_fallback(
    servico, monkeypatch
):
    """
    O caminho COMPLETO do achado do falso verde.

    Os outros testes deste arquivo simulam a falha levantando do lado de fora de
    `checar_interacoes`. Este usa o serviço REAL do PharmaDB com a consulta de
    interações quebrada por dentro — que é como a falha acontece em produção
    (base fora, disjuntor aberto, timeout).

    Antes da correção, esse caminho devolvia `status="sem_interacao"` e o médico
    lia "🟢 Nenhuma interação conhecida encontrada". Agora a exceção sobe até
    aqui e vira o aviso de indisponibilidade.
    """
    from app.services.integracoes.pharmadb_service import PharmaDBService

    instalar_extrator(monkeypatch, [
        {"raw": "Varfarina", "normalized": "varfarina"},
        {"raw": "AAS", "normalized": "acido acetilsalicilico"},
    ])

    real = PharmaDBService()

    async def _buscar_pa(nome):
        return {
            "varfarina": {"pa_id": 1, "nome_dcb": "Varfarina"},
            "acido acetilsalicilico": {"pa_id": 2, "nome_dcb": "AAS"},
        }[nome]

    async def _interacoes_fora(_pa_id):
        raise RuntimeError("PharmaDB fora do ar")

    real.buscar_pa = _buscar_pa
    real._interacoes_do_pa = _interacoes_fora
    monkeypatch.setattr(
        "app.services.integracoes.pharmadb_service.get_pharmadb_service", lambda: real
    )
    modos = capturar_fallback(monkeypatch, servico, "análise clínica do modelo")

    resposta = await servico._handle_pharma_check("varfarina com aas", uuid4())

    assert modos == ["CLINICAL_REASONING"]
    assert resposta["is_fallback"] is True
    assert "temporariamente indisponível" in resposta["text"]
    # O que NÃO pode aparecer, em hipótese alguma.
    assert "🟢" not in resposta["text"]
    assert "Nenhuma interação conhecida" not in resposta["text"]
    # E nenhum alerta falso foi gravado no banco.
    assert servico.db.adicionados == []


async def test_nome_de_metodo_errado_estoura_em_vez_de_virar_indisponibilidade(
    servico, monkeypatch
):
    """
    Erro de programação não pode se disfarçar de falha de infraestrutura.

    `PHARMA_MODE_CONFIG` resolve o método por NOME. Com o `getattr` dentro do
    `try`, um nome trocado ali levantava `AttributeError`, caía no `except` e
    virava "PharmaDB temporariamente indisponível": a base no ar, o médico
    recebendo o aviso de degradação, e o log apontando para o lugar errado.

    Descoberto ao testar por mutação o `test_cada_modo_chama_o_metodo_correspondente`
    — o teste falhava, mas pelo motivo errado.
    """
    instalar_extrator(monkeypatch, [{"raw": "Losartana", "normalized": "losartana"}])
    # Dublê sem o método que o modo pede.
    instalar_pharmadb(monkeypatch, buscar_bula=None)
    capturar_fallback(monkeypatch, servico)

    with pytest.raises(AttributeError):
        await servico._handle_pharma("losartana", "PHARMA_RECEITA")
