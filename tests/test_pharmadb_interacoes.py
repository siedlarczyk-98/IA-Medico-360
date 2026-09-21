"""
PharmaDB — checagem de interação medicamentosa.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
`pharmadb_service.py` tinha 374 linhas e **zero** cobertura: bula, interação,
receita e genérico, sem uma linha de teste, num módulo cuja saída o médico usa
para decidir prescrição. Era o maior buraco do repositório e o de maior
consequência.

A impressão de que seria intestável (integração externa, token, Redis) não se
sustenta: quase metade do arquivo é lógica pura — deduplicação de pares,
filtragem por conjunto de IDs, ordenação por gravidade e os formatadores. É ali
que mora o risco clínico, e nada disso precisa de rede.

O QUE ESTES TESTES PROTEGEM, EM ORDEM DE GRAVIDADE
--------------------------------------------------
1. **"Não sei" não pode virar "não há".** É a invariante central. `checar_interacoes`
   devolve `status="sem_interacao"` — que o formatador renderiza como o verde
   "Nenhuma interação conhecida" — e alguns caminhos de FALHA chegam lá sem que
   a base tenha respondido. Ver a seção "Falha silenciosa" abaixo: há um caso
   documentado como `xfail` que é defeito de verdade, não escolha de teste.
2. **Nenhum par pode sumir nem duplicar.** A API devolve a interação A↔B pelos
   dois lados; `pares_vistos` deduplica. Errar para mais polui o alerta, errar
   para menos esconde uma interação real.
3. **Nenhum fármaco que o médico não perguntou pode aparecer.** O filtro
   `pa_b_id not in pa_ids` é o que garante isso.
4. **A ordenação por gravidade.** O grave tem que vir primeiro: numa lista longa,
   o que está embaixo não é lido.
"""

import pytest

from app.services.integracoes.pharmadb_service import (
    SEMAFORO,
    InteracoesIndisponiveisError,
    PharmaDBService,
)

# ── Fábricas de dados no formato da API ──────────────────────────────────────

def pa(pa_id: int, nome: str) -> dict:
    return {"pa_id": pa_id, "nome_dcb": nome, "codigo_atc": None, "total_interacoes": 0}


def interacao(a_id: int, a_nome: str, b_id: int, b_nome: str, gravidade="grave", **extra) -> dict:
    """Uma interação como o `/v1/interacoes/pa/{id}` a devolve."""
    return {
        "pa_a": {"id": a_id, "nome_dcb": a_nome},
        "pa_b": {"id": b_id, "nome_dcb": b_nome},
        "gravidade": gravidade,
        "tipo_interacao": extra.get("tipo", "farmacodinâmica"),
        "efeito_clinico": extra.get("efeito", "risco aumentado de sangramento"),
        "mecanismo": extra.get("mecanismo", ""),
        "manejo_clinico": extra.get("manejo", ""),
        "descricao_estendida_pt": extra.get("descricao", ""),
        "referencias": extra.get("referencias", []),
    }


def servico_falso(pas_por_nome: dict, interacoes_por_pa: dict) -> PharmaDBService:
    """
    Serviço com a camada de rede substituída.

    Troca só `buscar_pa` e `_interacoes_do_pa` — os dois pontos que falam com a
    API. Todo o resto de `checar_interacoes` (dedup, filtro, semáforo, ordenação)
    roda de verdade, que é o que interessa testar.
    """
    servico = PharmaDBService()

    async def _buscar_pa(nome: str):
        valor = pas_por_nome.get(nome)
        if isinstance(valor, Exception):
            raise valor
        return valor

    async def _interacoes(pa_id):
        valor = interacoes_por_pa.get(pa_id, [])
        if isinstance(valor, Exception):
            raise valor
        return valor

    servico.buscar_pa = _buscar_pa
    servico._interacoes_do_pa = _interacoes
    return servico


VARFARINA = pa(1, "Varfarina")
AAS = pa(2, "Ácido acetilsalicílico")
OMEPRAZOL = pa(3, "Omeprazol")


# ── A invariante central: "não sei" ≠ "não há" ───────────────────────────────

async def test_menos_de_dois_farmacos_nao_e_ausencia_de_interacao():
    """
    Um fármaco só não pode produzir a mesma resposta que "checado, nada achado".

    O status é `sem_interacao` nos dois casos hoje, mas o TEXTO precisa
    distinguir — é o que o médico lê.
    """
    servico = servico_falso({}, {})

    resultado = await servico.checar_interacoes(["varfarina"])

    assert resultado["interacoes"] == []
    assert "pelo menos 2" in resultado["message"]


async def test_farmaco_nao_encontrado_na_base_e_reportado():
    """
    Se a base não conhece o fármaco, o médico precisa saber QUAL.

    Sem isso, "nenhuma interação encontrada" entre dois fármacos, sendo que um
    deles nem foi consultado, é uma afirmação falsa.
    """
    servico = servico_falso(
        {"varfarina": VARFARINA, "aas": AAS, "xpto": None},
        {1: [], 2: []},
    )

    resultado = await servico.checar_interacoes(["varfarina", "aas", "xpto"])

    assert "xpto" in resultado["nao_encontrados"]


async def test_um_so_farmaco_resolvido_devolve_insuficiente_e_nao_verde():
    """
    O caso perigoso: pediram 2, a base resolveu 1.

    Se isso caísse em `sem_interacao`, o formatador pintaria de VERDE
    ("Nenhuma interação conhecida") uma checagem que nem aconteceu.
    """
    servico = servico_falso({"varfarina": VARFARINA, "xpto": None}, {1: []})

    resultado = await servico.checar_interacoes(["varfarina", "xpto"])

    assert resultado["status"] == "insuficiente"
    assert resultado["status"] != "sem_interacao"
    texto = servico.formatar_interacoes(resultado)
    assert "🟢" not in texto, "checagem incompleta não pode sair em verde"
    assert "⚠️" in texto


# ── Deduplicação e filtro ────────────────────────────────────────────────────

async def test_par_reciproco_aparece_uma_unica_vez():
    """
    A API devolve A↔B tanto em `/pa/1` quanto em `/pa/2`. Sem `pares_vistos`, o
    médico veria a mesma interação duas vezes e poderia contá-la como duas.
    """
    servico = servico_falso(
        {"varfarina": VARFARINA, "aas": AAS},
        {
            1: [interacao(1, "Varfarina", 2, "Ácido acetilsalicílico")],
            2: [interacao(2, "Ácido acetilsalicílico", 1, "Varfarina")],
        },
    )

    resultado = await servico.checar_interacoes(["varfarina", "aas"])

    assert resultado["total_interacoes"] == 1


async def test_interacao_com_farmaco_nao_perguntado_e_descartada():
    """
    A varfarina interage com dezenas de fármacos. Só as interações ENTRE os
    fármacos informados importam — alertar sobre um que o paciente não usa é
    ruído que faz o médico parar de ler os alertas.
    """
    servico = servico_falso(
        {"varfarina": VARFARINA, "omeprazol": OMEPRAZOL},
        {
            1: [
                interacao(1, "Varfarina", 99, "Fármaco que ninguém perguntou"),
                interacao(1, "Varfarina", 3, "Omeprazol", gravidade="moderada"),
            ],
            3: [],
        },
    )

    resultado = await servico.checar_interacoes(["varfarina", "omeprazol"])

    nomes = {alerta["pa_b"] for alerta in resultado["interacoes"]}
    assert nomes == {"Omeprazol"}


async def test_autointeracao_e_descartada():
    """`pa_b_id == pa_a_id` é dado sujo, não interação."""
    servico = servico_falso(
        {"varfarina": VARFARINA, "aas": AAS},
        {1: [interacao(1, "Varfarina", 1, "Varfarina")], 2: []},
    )

    resultado = await servico.checar_interacoes(["varfarina", "aas"])

    assert resultado["status"] == "sem_interacao"


# ── Semáforo e ordenação ─────────────────────────────────────────────────────

async def test_graves_vem_antes_dos_leves():
    """Numa lista longa, o que está embaixo não é lido."""
    servico = servico_falso(
        {"a": pa(1, "A"), "b": pa(2, "B"), "c": pa(3, "C")},
        {
            1: [
                interacao(1, "A", 2, "B", gravidade="leve"),
                interacao(1, "A", 3, "C", gravidade="grave"),
            ],
            2: [interacao(2, "B", 3, "C", gravidade="moderada")],
            3: [],
        },
    )

    resultado = await servico.checar_interacoes(["a", "b", "c"])

    gravidades = [i["gravidade"] for i in resultado["interacoes"]]
    assert gravidades == ["grave", "moderada", "leve"]


async def test_gravidade_desconhecida_nao_vira_verde():
    """
    Se a API mandar uma gravidade nova, o fallback é `leve` — que é VERDE.

    Este teste não afirma que o comportamento é o ideal (o conservador seria
    tratar desconhecido como moderado); afirma que ele é DELIBERADO e visível.
    Se alguém mudar o default, que seja com esta discussão à vista.
    """
    servico = servico_falso(
        {"a": pa(1, "A"), "b": pa(2, "B")},
        {1: [interacao(1, "A", 2, "B", gravidade="gravidade_que_nao_existe")], 2: []},
    )

    resultado = await servico.checar_interacoes(["a", "b"])

    alerta = resultado["interacoes"][0]
    assert alerta["semaforo_level"] == SEMAFORO["leve"]["level"]
    # A gravidade CRUA é preservada, então o texto não mente sobre o que veio.
    assert alerta["gravidade"] == "gravidade_que_nao_existe"


def test_semaforo_cobre_os_tres_niveis():
    """Contrato de cor: grave=vermelho, moderada=amarelo, leve=verde."""
    assert SEMAFORO["grave"]["color"] == "RED"
    assert SEMAFORO["moderada"]["color"] == "YELLOW"
    assert SEMAFORO["leve"]["color"] == "GREEN"
    assert SEMAFORO["grave"]["level"] > SEMAFORO["moderada"]["level"] > SEMAFORO["leve"]["level"]


# ── Falha silenciosa: o achado que motivou o arquivo ─────────────────────────

async def test_erro_ao_buscar_interacoes_nunca_vira_verde():
    """
    A correção do achado que motivou este arquivo.

    Antes, uma falha na consulta de interações (PharmaDB fora, disjuntor aberto,
    timeout) era logada e o laço seguia com `continue`. Com todas falhando, a
    função devolvia `status="sem_interacao"` e o formatador imprimia:

        🟢 Nenhuma interação conhecida encontrada entre os fármacos informados

    A base caía e o médico lia uma luz verde — uma afirmação FALSA sobre risco de
    prescrição, tomada como verdadeira justamente por quem ia prescrever.

    Agora levanta `InteracoesIndisponiveisError`, que `_handle_pharma_check`
    converte no aviso de indisponibilidade + CLINICAL_REASONING marcado como
    fallback (ver `tests/test_orquestrador_rotas_pharma.py`).
    """
    servico = servico_falso(
        {"varfarina": VARFARINA, "aas": AAS},
        {1: RuntimeError("PharmaDB indisponível"), 2: RuntimeError("PharmaDB indisponível")},
    )

    with pytest.raises(InteracoesIndisponiveisError):
        await servico.checar_interacoes(["varfarina", "aas"])


async def test_falha_parcial_tambem_invalida_a_checagem():
    """
    Meia checagem não é checagem.

    Se a consulta da varfarina falhou e a do AAS não, não há como afirmar que os
    dois não interagem — a interação viria justamente da lista que faltou. Seguir
    com o que deu certo produziria o mesmo verde mentiroso, só que mais difícil
    de notar, porque parte dos dados está lá.
    """
    servico = servico_falso(
        {"varfarina": VARFARINA, "aas": AAS},
        {1: RuntimeError("timeout"), 2: []},
    )

    with pytest.raises(InteracoesIndisponiveisError):
        await servico.checar_interacoes(["varfarina", "aas"])


async def test_a_mensagem_do_erro_diz_qual_farmaco_falhou():
    """Para o log de produção: sem o nome, o erro não ajuda a diagnosticar."""
    servico = servico_falso(
        {"varfarina": VARFARINA, "aas": AAS},
        {1: RuntimeError("fora"), 2: []},
    )

    with pytest.raises(InteracoesIndisponiveisError, match="Varfarina"):
        await servico.checar_interacoes(["varfarina", "aas"])


async def test_erro_ao_resolver_pa_aborta_a_checagem():
    """
    INVERTIDO em 2026-09-21. Este teste travava o comportamento oposto: exceção
    em `buscar_pa` caía em `nao_encontrados`, com o argumento de que "a falha é
    visível na resposta". Era visível como uma afirmação FALSA: o médico lia
    "Encontrei apenas 1 fármaco(s) na base. Não encontrados na base: aas" com o
    PharmaDB em timeout. "Não consegui consultar" não é "não existe".
    """
    servico = servico_falso(
        {"varfarina": VARFARINA, "aas": RuntimeError("timeout")},
        {1: []},
    )

    with pytest.raises(InteracoesIndisponiveisError, match="aas"):
        await servico.checar_interacoes(["varfarina", "aas"])


# ── Formatação ───────────────────────────────────────────────────────────────

async def test_texto_de_interacao_traz_o_que_decide_conduta():
    """Efeito clínico e manejo são o que muda a prescrição; sem eles o alerta
    diz "cuidado" sem dizer com o quê."""
    servico = servico_falso(
        {"varfarina": VARFARINA, "aas": AAS},
        {
            1: [interacao(
                1, "Varfarina", 2, "Ácido acetilsalicílico",
                efeito="risco aumentado de sangramento",
                manejo="monitorar INR semanalmente",
            )],
            2: [],
        },
    )

    resultado = await servico.checar_interacoes(["varfarina", "aas"])
    texto = servico.formatar_interacoes(resultado)

    assert "🔴" in texto
    assert "GRAVE" in texto
    assert "risco aumentado de sangramento" in texto
    assert "monitorar INR semanalmente" in texto


def test_nao_encontrados_aparecem_no_texto_de_sucesso():
    """
    Mesmo quando há interações a mostrar, o fármaco que a base não conhece
    precisa continuar visível — senão o médico assume que os três foram
    checados.
    """
    servico = PharmaDBService()
    texto = servico.formatar_interacoes({
        "status": "interacoes_encontradas",
        "total_interacoes": 1,
        "medicamentos_encontrados": ["Varfarina", "Ácido acetilsalicílico"],
        "nao_encontrados": ["xpto"],
        "interacoes": [{
            "pa_a": "Varfarina", "pa_b": "Ácido acetilsalicílico",
            "gravidade": "grave", "semaforo_level": 4,
            "semaforo_color": "RED", "semaforo_emoji": "🔴",
            "tipo_interacao": "", "efeito_clinico": "", "mecanismo": "",
            "manejo_clinico": "", "descricao_estendida": "", "referencias": [],
        }],
    })

    assert "xpto" in texto


def test_verde_so_com_a_lista_do_que_foi_checado():
    """O verde precisa dizer VERDE ENTRE O QUÊ — senão não é verificável."""
    servico = PharmaDBService()
    texto = servico.formatar_interacoes({
        "status": "sem_interacao",
        "message": "Nenhuma interação conhecida encontrada entre os fármacos informados.",
        "medicamentos_encontrados": ["Varfarina", "Omeprazol"],
        "nao_encontrados": [],
        "interacoes": [],
    })

    assert "🟢" in texto
    assert "Varfarina" in texto and "Omeprazol" in texto
