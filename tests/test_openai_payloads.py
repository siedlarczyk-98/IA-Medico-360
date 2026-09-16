"""
O corpo das requisições que os serviços auxiliares mandam à OpenAI.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
Quatro módulos compartilham a mesma forma — `client.post(...)` dentro de um
`try/except` amplo que devolve um fallback silencioso: `triage_service`,
`specialty_detector` e as duas funções de `medication_extractor`. Nenhum tinha
teste do que é ENVIADO; todos testam o que se faz com a resposta.

É exatamente a lacuna que deixou dois bugs idênticos viverem em produção:

- `semantic_cache_service`: `max_tokens` numa família gpt-5 → HTTP 400 →
  engolido pelo `except` → a tabela `semantic_cache` ficou vazia em produção
  **sem um único erro visível**.
- `pubmed_service`: o mesmo parâmetro, o mesmo 400, o mesmo silêncio — e como
  `_extract_citations` é a primeira etapa do pipeline, o PubMed **nunca** foi
  consultado durante toda a vida do arquivo. Corrigido em 2026-09-16, com
  `tests/test_pubmed_payload.py`.

Duas vezes o mesmo erro, em dois arquivos, é padrão. Estes testes olham a
requisição — não o resultado — para que não haja uma terceira.

O QUE ELES TRAVAM
-----------------
1. **O par modelo↔parâmetro.** A família gpt-5 exige `max_completion_tokens` e
   recusa `max_tokens` com 400. Cada teste afirma os dois lados: que o novo está
   presente E que o antigo não está — só a primeira metade deixaria passar um
   payload com ambos, que também é 400.
2. **`temperature=0` onde o resultado precisa ser determinístico.** Estes quatro
   serviços classificam e extraem; uma temperatura acima de zero faz a mesma
   pergunta cair em modos diferentes entre chamadas, e o cache (que assume
   determinismo) passaria a servir respostas contraditórias.
3. **Que a falha continue devolvendo o fallback**, e não propagando. O silêncio
   aqui é a decisão certa — o que faltava era alguém verificar a requisição.
"""

import json

import httpx
import pytest

from app.services import medication_extractor, specialty_detector, triage_service


@pytest.fixture(autouse=True)
def sem_cache(monkeypatch):
    """
    Desliga o Redis: com cache, o segundo teste não chegaria a fazer requisição.

    Também evita o timeout de conexão que o CI não tem.
    """
    async def _get(*a, **k):
        return None

    async def _set(*a, **k):
        return None

    monkeypatch.setattr("app.services.cache_service.get_json", _get)
    monkeypatch.setattr("app.services.cache_service.set_json", _set)


def cliente_que_captura(capturado: dict, resposta: str = "{}", status: int = 200):
    """
    Cliente httpx que grava o corpo enviado em vez de sair para a rede.

    Um `MockTransport` de verdade, e não um monkeypatch no método: assim o
    payload passa pela serialização real do httpx, que é onde um parâmetro
    inválido continuaria invisível até o 400 da API.
    """
    def responder(request: httpx.Request) -> httpx.Response:
        capturado["corpo"] = json.loads(request.content)
        capturado["url"] = str(request.url)
        capturado["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(
            status,
            json={"choices": [{"message": {"content": resposta}}]},
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(responder))


def instalar(monkeypatch, modulo: str, cliente) -> None:
    monkeypatch.setattr(f"{modulo}.get_client", lambda: cliente)


def afirmar_par_modelo_parametro(corpo: dict) -> None:
    """A regressão que já aconteceu duas vezes, verificada nos dois sentidos."""
    assert corpo["model"].startswith("gpt-5"), (
        "se o modelo saiu da família gpt-5, o parâmetro de limite de tokens "
        "precisa ser reavaliado junto — eles andam em par"
    )
    assert "max_tokens" not in corpo, (
        "a família gpt-5 recusa `max_tokens` com HTTP 400; o `except` engole o "
        "erro e o serviço passa a falhar em 100% das chamadas em silêncio"
    )
    assert corpo["max_completion_tokens"] > 0


# ── Triagem ──────────────────────────────────────────────────────────────────

async def test_triagem_manda_o_parametro_certo(monkeypatch):
    capturado: dict = {}
    cliente = cliente_que_captura(capturado, '{"mode": "QUICK_SEARCH", "confidence": 0.9}')
    instalar(monkeypatch, "app.services.triage_service", cliente)

    await triage_service.triage("dose de amoxicilina")

    afirmar_par_modelo_parametro(capturado["corpo"])


async def test_triagem_e_deterministica(monkeypatch):
    """
    A mesma pergunta tem que cair sempre no mesmo modo.

    Sem `temperature=0`, o cache de triagem (TTL de 2h) serviria um modo para
    uma pessoa e outro para a seguinte, e o roteamento viraria loteria.
    """
    capturado: dict = {}
    cliente = cliente_que_captura(capturado, '{"mode": "QUICK_SEARCH", "confidence": 0.9}')
    instalar(monkeypatch, "app.services.triage_service", cliente)

    await triage_service.triage("dose de amoxicilina")

    assert capturado["corpo"]["temperature"] == 0


async def test_triagem_com_http_400_cai_no_fallback_e_nao_levanta(monkeypatch):
    """
    O comportamento que escondeu o bug do PubMed — aqui ele é CORRETO, porque a
    triagem tem um fallback que serve (QUICK_SEARCH). O que faltava era o teste
    do payload acima, que impede o 400 de acontecer.
    """
    capturado: dict = {}
    cliente = cliente_que_captura(capturado, "{}", status=400)
    instalar(monkeypatch, "app.services.triage_service", cliente)

    resultado = await triage_service.triage("qualquer coisa")

    assert resultado["mode"] == "QUICK_SEARCH"
    assert resultado["confidence"] == 0.0


async def test_modo_fora_do_vocabulario_vira_quick_search(monkeypatch):
    """O modelo às vezes inventa um modo. Ele não pode virar rota."""
    capturado: dict = {}
    cliente = cliente_que_captura(capturado, '{"mode": "MODO_INVENTADO", "confidence": 0.99}')
    instalar(monkeypatch, "app.services.triage_service", cliente)

    resultado = await triage_service.triage("pergunta")

    assert resultado["mode"] == "QUICK_SEARCH"
    assert resultado["confidence"] == 0.5


async def test_json_em_bloco_de_markdown_e_aceito(monkeypatch):
    """O modelo devolve ```json ... ``` com frequência; o parser tira as cercas."""
    capturado: dict = {}
    cliente = cliente_que_captura(
        capturado, '```json\n{"mode": "CLINICAL_REASONING", "confidence": 0.8}\n```'
    )
    instalar(monkeypatch, "app.services.triage_service", cliente)

    resultado = await triage_service.triage("caso clínico complexo")

    assert resultado["mode"] == "CLINICAL_REASONING"


def test_o_prompt_de_triagem_nao_oferece_modo_nao_triavel():
    """
    ACHADO documentado: o prompt lista os modos que o modelo pode escolher, e
    essa lista precisa bater com a política.

    `DATA_OCEAN` está fora do prompt de propósito — é `MODOS_NAO_TRIADOS`, porque
    é lento e cobrado por uso de ferramenta, e só o médico deve acioná-lo.

    `EXAM_REVIEW` também está fora do prompt, mas **não** está em
    `MODOS_NAO_TRIADOS`. Ou seja: a triagem nunca o escolhe, mas nada no código
    declara essa intenção — quem ler a lista de não-triados vai concluir o
    contrário. É inconsistência de registro, não bug de runtime (o modo é
    alcançado por anexo, via `MODOS_PROMOVIDOS_POR_ANEXO`).

    Este teste trava o estado atual para que a divergência não cresça em
    silêncio: se alguém adicionar um modo ao prompt, tem que ser deliberado.
    """
    from app.services.orquestrador_modes import MODOS_NAO_TRIADOS

    prompt = triage_service.TRIAGE_PROMPT

    for modo in MODOS_NAO_TRIADOS:
        assert str(modo) not in prompt, (
            f"{modo} é MODOS_NAO_TRIADOS mas aparece no prompt de triagem — "
            "o modelo passaria a poder escolhê-lo"
        )

    assert "EXAM_REVIEW" not in prompt, (
        "EXAM_REVIEW fora do prompt é o estado atual; se passar a ser oferecido, "
        "revise a decisão (hoje ele é alcançado por anexo, não por triagem)"
    )


# ── Detector de especialidade ────────────────────────────────────────────────

async def test_specialty_manda_o_parametro_certo(monkeypatch):
    capturado: dict = {}
    cliente = cliente_que_captura(
        capturado, '{"specialty": "Cardiologia", "topic": "insuficiência cardíaca"}'
    )
    instalar(monkeypatch, "app.services.specialty_detector", cliente)

    await specialty_detector.detect_specialty_and_topic("paciente com IC")

    afirmar_par_modelo_parametro(capturado["corpo"])
    assert capturado["corpo"]["temperature"] == 0


async def test_specialty_com_falha_nao_derruba_a_interacao(monkeypatch):
    """A especialidade é metadado: falhar nela não pode custar a resposta."""
    capturado: dict = {}
    cliente = cliente_que_captura(capturado, "{}", status=500)
    instalar(monkeypatch, "app.services.specialty_detector", cliente)

    resultado = await specialty_detector.detect_specialty_and_topic("pergunta")

    assert resultado is not None


# ── Extração de medicamentos ─────────────────────────────────────────────────

async def test_extract_medications_manda_o_parametro_certo(monkeypatch):
    capturado: dict = {}
    cliente = cliente_que_captura(
        capturado, '[{"raw": "AAS 100mg", "normalized": "acido acetilsalicilico"}]'
    )
    instalar(monkeypatch, "app.services.medication_extractor", cliente)

    await medication_extractor.extract_medications("paciente usa AAS 100mg")

    afirmar_par_modelo_parametro(capturado["corpo"])
    assert capturado["corpo"]["temperature"] == 0


async def test_extract_from_interaction_manda_o_parametro_certo(monkeypatch):
    """A segunda função do módulo — a que alimenta o PharmaDB."""
    capturado: dict = {}
    cliente = cliente_que_captura(
        capturado,
        '[{"raw": "Varfarina", "normalized": "varfarina", "source": "prompt"}]',
    )
    instalar(monkeypatch, "app.services.medication_extractor", cliente)

    await medication_extractor.extract_from_interaction("usa varfarina", ["resposta"])

    afirmar_par_modelo_parametro(capturado["corpo"])
    assert capturado["corpo"]["temperature"] == 0


async def test_medicamento_duplicado_e_removido(monkeypatch):
    """
    O nome normalizado é a chave que vai ao PharmaDB. Duplicata faria a checagem
    de interação comparar um fármaco com ele mesmo.
    """
    capturado: dict = {}
    cliente = cliente_que_captura(capturado, json.dumps([
        {"raw": "AAS", "normalized": "acido acetilsalicilico", "source": "prompt"},
        {"raw": "Aspirina", "normalized": "acido acetilsalicilico", "source": "response"},
    ]))
    instalar(monkeypatch, "app.services.medication_extractor", cliente)

    resultado = await medication_extractor.extract_from_interaction("p", ["r"])

    assert len(resultado) == 1


async def test_source_invalida_vira_response(monkeypatch):
    """`source` só pode ser 'prompt' ou 'response' — é o que distingue o que o
    médico disse do que o modelo trouxe."""
    capturado: dict = {}
    cliente = cliente_que_captura(capturado, json.dumps([
        {"raw": "Dipirona", "normalized": "dipirona", "source": "inventado"},
    ]))
    instalar(monkeypatch, "app.services.medication_extractor", cliente)

    resultado = await medication_extractor.extract_from_interaction("p", ["r"])

    assert resultado[0]["source"] == "response"


async def test_resposta_que_nao_e_lista_nao_quebra(monkeypatch):
    """O modelo às vezes devolve um objeto em vez do array pedido."""
    capturado: dict = {}
    cliente = cliente_que_captura(capturado, '{"erro": "não entendi"}')
    instalar(monkeypatch, "app.services.medication_extractor", cliente)

    assert await medication_extractor.extract_medications("texto") == []


async def test_medicamento_sem_raw_e_descartado(monkeypatch):
    """Sem o nome como o médico escreveu, não há o que mostrar de volta."""
    capturado: dict = {}
    cliente = cliente_que_captura(capturado, json.dumps([
        {"normalized": "dipirona"},
        {"raw": "Dipirona 500mg", "normalized": "dipirona"},
    ]))
    instalar(monkeypatch, "app.services.medication_extractor", cliente)

    resultado = await medication_extractor.extract_medications("texto")

    assert len(resultado) == 1
    assert resultado[0]["raw"] == "Dipirona 500mg"
