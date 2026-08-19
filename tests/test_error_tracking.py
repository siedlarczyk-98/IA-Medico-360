"""
Scrubbing do Sentry (item 2.2 do plano de prontidão).

Estes testes existem porque a falha aqui é silenciosa e cara: o Sentry
funcionaria normalmente, os alertas chegariam, e ninguém perceberia que cada
evento carrega o prontuário junto — para fora do país, contrariando a RN-SEC-001.

O prompt clínico usado abaixo é o mesmo formato que chega em produção.
"""

import pytest
from sentry_sdk.transport import Transport

from app.core.error_tracking import MASCARA, scrub_event, setup_sentry

PROMPT_CLINICO = (
    "Paciente João da Silva, 62 anos, CPF 123.456.789-00, "
    "em uso de varfarina, com INR 4.8 e sangramento gengival."
)


def _sem_vazamento(evento) -> None:
    """Nenhum fragmento do prompt pode sobreviver em lugar nenhum do evento."""
    import json

    texto = json.dumps(evento, default=str, ensure_ascii=False)
    for fragmento in ("João da Silva", "123.456.789-00", "varfarina", "INR 4.8"):
        assert fragmento not in texto, f"'{fragmento}' vazou no evento do Sentry"


# ── Corpo da requisição ──────────────────────────────────────────────────

def test_corpo_da_requisicao_e_removido():
    evento = {"request": {"data": {"prompt": PROMPT_CLINICO}, "url": "/api/v1/orquestrador/query"}}

    limpo = scrub_event(evento)

    assert "data" not in limpo["request"]
    assert limpo["request"]["url"] == "/api/v1/orquestrador/query", "A URL é útil e deve ficar"
    _sem_vazamento(limpo)


def test_credenciais_nos_headers_sao_mascaradas():
    evento = {
        "request": {
            "headers": {
                "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.abc",
                "Cookie": "medico360_session=abc123",
                "User-Agent": "Mozilla/5.0",
            },
            "cookies": {"medico360_session": "abc123"},
        }
    }

    limpo = scrub_event(evento)

    assert limpo["request"]["headers"]["Authorization"] == MASCARA
    assert limpo["request"]["headers"]["Cookie"] == MASCARA
    assert limpo["request"]["headers"]["User-Agent"] == "Mozilla/5.0", "Header inócuo ajuda a diagnosticar"
    assert "cookies" not in limpo["request"]


def test_query_string_com_email_e_removida():
    evento = {"request": {"query_string": "email=medico@exemplo.com.br"}}
    limpo = scrub_event(evento)
    assert "query_string" not in limpo["request"]


# ── Variáveis locais: o vazamento menos óbvio ────────────────────────────

def test_variaveis_locais_do_stack_trace_sao_limpas():
    """
    É o caso mais perigoso: o Sentry envia as variáveis locais de cada frame
    por padrão, e é exatamente lá que o prompt está quando a exceção estoura.
    """
    evento = {
        "exception": {
            "values": [{
                "type": "RuntimeError",
                "stacktrace": {"frames": [{
                    "function": "query",
                    "vars": {
                        "prompt": PROMPT_CLINICO,
                        "sanitized_prompt": PROMPT_CLINICO,
                        "model_id": "claude-sonnet-4-6",
                        "user_id": "uuid-do-medico",
                    },
                }]},
            }]
        }
    }

    limpo = scrub_event(evento)

    frame = limpo["exception"]["values"][0]["stacktrace"]["frames"][0]
    assert frame["vars"]["prompt"] == MASCARA
    assert frame["vars"]["sanitized_prompt"] == MASCARA
    assert frame["vars"]["model_id"] == "claude-sonnet-4-6", "Dado técnico deve sobreviver"
    assert frame["vars"]["user_id"] == "uuid-do-medico", "O id correlaciona sem identificar"
    assert frame["function"] == "query", "O nome da função é essencial para diagnosticar"
    _sem_vazamento(limpo)


def test_variaveis_aninhadas_tambem_sao_limpas():
    evento = {
        "exception": {"values": [{"stacktrace": {"frames": [{
            "vars": {"request": {"body": {"prompt": PROMPT_CLINICO}}},
        }]}}]}
    }

    _sem_vazamento(scrub_event(evento))


def test_lista_de_mensagens_e_limpa():
    """Histórico de conversa chega como lista de dicionários."""
    evento = {
        "extra": {
            "history": [
                {"role": "user", "content": PROMPT_CLINICO},
                {"role": "assistant", "content": "Suspender varfarina e reavaliar INR."},
            ]
        }
    }

    _sem_vazamento(scrub_event(evento))


# ── Identificação do usuário ─────────────────────────────────────────────

def test_usuario_mantem_id_e_perde_email():
    evento = {"user": {"id": "abc-123", "email": "medico@exemplo.com.br", "ip_address": "1.2.3.4"}}

    limpo = scrub_event(evento)

    assert limpo["user"] == {"id": "abc-123"}


# ── Migalhas e contexto ──────────────────────────────────────────────────

def test_breadcrumbs_sao_limpas():
    evento = {
        "breadcrumbs": {"values": [
            {"category": "query", "message": PROMPT_CLINICO},
            {"category": "http", "data": {"url": "/api/v1/orquestrador/query"}},
        ]}
    }

    _sem_vazamento(scrub_event(evento))


# ── Comportamento de falha ───────────────────────────────────────────────

def test_falha_no_scrubbing_descarta_o_evento():
    """
    Falha fechada: perder um alerta é aceitável, vazar prontuário não.
    Um evento que não é dicionário faz o scrubbing estourar.
    """
    assert scrub_event("isto não é um evento") is None


def test_evento_tecnico_atravessa_intacto():
    """Contraprova: sem isto, um scrubbing que apagasse tudo passaria nos testes acima."""
    evento = {
        "level": "error",
        "logger": "app.services.orquestrador_service",
        "exception": {"values": [{"type": "TimeoutError", "value": "provider timeout"}]},
        "request": {"url": "/api/v1/orquestrador/query", "method": "POST"},
    }

    limpo = scrub_event(evento)

    assert limpo["level"] == "error"
    assert limpo["logger"] == "app.services.orquestrador_service"
    assert limpo["exception"]["values"][0]["type"] == "TimeoutError"
    assert limpo["request"]["method"] == "POST"


# ── Inicialização ────────────────────────────────────────────────────────

def test_sem_dsn_e_no_op():
    assert setup_sentry(dsn="", environment="development") is False


@pytest.mark.parametrize("campo", ["prompt", "userPrompt", "PROMPT_TEXT", "extracted_text", "senha"])
def test_variacoes_de_nome_sao_pegas(campo):
    """A comparação é por substring em minúsculas — cobre camelCase e prefixos."""
    evento = {"extra": {campo: PROMPT_CLINICO}}
    assert scrub_event(evento)["extra"][campo] == MASCARA


# ── Ponta a ponta: Sentry ativo de verdade ───────────────────────────────
# Os testes acima exercitam o `before_send` com eventos montados à mão. Este
# liga o SDK real, provoca uma exceção com o prompt vivo no escopo e inspeciona
# o evento que SAIRIA pela rede. É a diferença entre "a função limpa" e "o
# pipeline limpa".

class TransporteEspiao(Transport):
    """Substitui o transporte HTTP do Sentry e guarda o envelope que sairia."""

    def __init__(self):
        self.eventos: list[dict] = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.headers.get("type") == "event":
                self.eventos.append(item.payload.json)

    def flush(self, *args, **kwargs):
        return None

    def kill(self):
        return None


@pytest.fixture
def sentry_espiao():
    import sentry_sdk

    espiao = TransporteEspiao()
    cliente = sentry_sdk.Client(
        dsn="https://chave@exemplo.ingest.sentry.io/1",
        transport=espiao,
        before_send=scrub_event,
        send_default_pii=False,
        include_local_variables=True,
        default_integrations=False,
    )
    escopo = sentry_sdk.get_global_scope()
    anterior = escopo.client
    escopo.set_client(cliente)
    yield espiao
    escopo.set_client(anterior)


def test_excecao_real_nao_leva_o_prompt(sentry_espiao):
    """
    Simula o que acontece quando um provider estoura no meio do orquestrador:
    o prompt clínico está vivo como variável local no frame da exceção.
    """
    import sentry_sdk

    def chamada_ao_provider(prompt: str, model_id: str):
        sanitized_prompt = prompt  # noqa: F841 — precisa existir no frame
        raise RuntimeError("provider timeout")

    try:
        chamada_ao_provider(PROMPT_CLINICO, "claude-sonnet-4-6")
    except RuntimeError:
        sentry_sdk.capture_exception()

    sentry_sdk.flush(timeout=2)

    assert sentry_espiao.eventos, "Nenhum evento chegou ao transporte"
    evento = sentry_espiao.eventos[0]
    _sem_vazamento(evento)

    # E o alerta continua útil: dá para saber o que quebrou e onde.
    import json

    texto = json.dumps(evento, default=str)
    assert "provider timeout" in texto
    assert "chamada_ao_provider" in texto


# ── Regressao: headers do ASGI sao LISTA DE PARES, nao dicionario ────────
# Todos os testes acima usavam dados em formato de dicionario, e passavam. Uma
# simulacao de requisicao real (scripts/simular_erro_de_usuario.py) mostrou o
# token de sessao vazando mesmo assim: nos frames do stack trace aparecem os
# objetos `scope` e `request` do ASGI, cujos headers sao pares [chave, valor]
# em bytes. O scrubbing por chave de dicionario nao alcancava nada ali.

HEADERS_ASGI = [
    [b"host", b"medico360.com.br"],
    [b"authorization", b"Bearer eyJhbGciOiJIUzI1NiJ9.token-secreto.assinatura"],
    [b"cookie", b"medico360_session=sessao-secreta"],
    [b"user-agent", b"Mozilla/5.0"],
]


def test_headers_em_pares_de_bytes_sao_mascarados():
    evento = {
        "exception": {"values": [{"stacktrace": {"frames": [{
            "vars": {"scope": {"headers": HEADERS_ASGI}},
        }]}}]}
    }

    limpo = scrub_event(evento)

    import json
    texto = json.dumps(limpo, default=str)
    assert "token-secreto" not in texto
    assert "sessao-secreta" not in texto
    # Header inocuo sobrevive: o objetivo e mascarar credencial, nao apagar contexto.
    assert "Mozilla/5.0" in texto
    assert "medico360.com.br" in texto


def test_par_de_header_preserva_o_nome_do_campo():
    """Saber QUE havia um Authorization ajuda a diagnosticar; o valor, nao."""
    evento = {"extra": {"headers": [[b"authorization", b"Bearer segredo"]]}}

    par = scrub_event(evento)["extra"]["headers"][0]

    assert par[0] == b"authorization"
    assert par[1] == MASCARA


def test_pares_em_str_tambem_funcionam():
    """Nem todo framework entrega bytes."""
    evento = {"extra": {"h": [("Authorization", "Bearer segredo"), ("Accept", "*/*")]}}

    limpo = scrub_event(evento)["extra"]["h"]

    assert limpo[0][1] == MASCARA
    assert limpo[1][1] == "*/*"


def test_lista_comum_nao_e_confundida_com_par_de_header():
    """Contraprova: lista de dois elementos cujo primeiro nao e campo bloqueado."""
    evento = {"extra": {"coordenadas": [["latitude", "-23.55"], ["longitude", "-46.63"]]}}

    limpo = scrub_event(evento)["extra"]["coordenadas"]

    assert limpo == [["latitude", "-23.55"], ["longitude", "-46.63"]]
