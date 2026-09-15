"""
Médico 360 — Rastreamento de erro (Sentry).

RN-SEC-001 vale aqui também: um Sentry na configuração padrão captura corpo de
requisição, cookies e AS VARIÁVEIS LOCAIS de cada frame do stack trace. Nesta
aplicação isso significa o prompt clínico bruto — antes do DLP — sendo enviado
para fora do país num evento de erro. A ferramenta de observabilidade viraria
exatamente o vazamento que o DLP existe para impedir.

Por isso o `before_send` abaixo é obrigatório e testado (`tests/test_error_tracking.py`),
não uma precaução opcional. A regra é lista de bloqueio por NOME de campo, não
inspeção de conteúdo: é mais previsível e não depende de acertar um regex.

No-op quando `sentry_dsn` está vazio — igual ao Phoenix.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Campos que podem carregar conteúdo clínico, PII ou credencial. Comparação é
# por substring no nome, em minúsculas — "user_prompt" e "promptText" batem.
CAMPOS_BLOQUEADOS = frozenset({
    "prompt", "text", "content", "message", "messages", "answer", "resposta",
    "extracted_text", "response_text", "description", "descricao",
    "body", "payload", "inputs", "query",
    "email", "cpf", "phone", "telefone", "name", "nome", "crm",
    "password", "senha", "token", "secret", "api_key", "apikey",
    "authorization", "cookie", "session",
    "image_base64", "base64", "file", "arquivo",
})

MASCARA = "[REMOVIDO PELO SCRUBBING]"

_MAX_PROFUNDIDADE = 8


def _bloqueado(chave) -> bool:
    """Aceita str e bytes: no ASGI os nomes de header chegam como bytes."""
    if isinstance(chave, bytes):
        chave = chave.decode("latin-1", "replace")
    k = str(chave).lower()
    return any(proibido in k for proibido in CAMPOS_BLOQUEADOS)


def _e_par_bloqueado(valor) -> bool:
    """
    Reconhece o formato de header do ASGI: `[b"authorization", b"Bearer ..."]`.

    Sem isso o scrubbing por nome de campo nao alcanca nada: `scope["headers"]` e
    `request.headers` sao LISTAS DE PARES, nao dicionarios, e aparecem como
    variaveis locais dos frames do stack trace. Foi assim que o token de sessao
    vazou numa simulacao de requisicao real, mesmo com todos os testes de unidade
    (que usavam dados em formato de dicionario) passando.
    """
    return (
        isinstance(valor, list | tuple)
        and len(valor) == 2
        and isinstance(valor[0], str | bytes)
        and _bloqueado(valor[0])
    )


# NÃO ancore no fecha-parênteses. O `safe_repr` do SDK TRUNCA valores longos,
# e um prompt clínico é longo: o repr chega cortado no meio, sem o `)` final.
# Com `...\)$` o padrão não casava exatamente no caso que mais importa — o
# objeto com muito texto dentro — e passava intacto.
# O nome aceita qualificador: uma classe declarada DENTRO de uma função (closure,
# factory, fixture de teste) tem repr `modulo.funcao.<locals>.Classe(...)`, com os
# sinais `<` e `>` no meio. Sem aceitá-los, justamente esses objetos passavam.
_REPR_DE_OBJETO = re.compile(r"^[A-Za-z_][A-Za-z0-9_.<>]*\((?P<campos>.+)", re.DOTALL)
_CAMPO_NO_REPR = re.compile(r"(?:^|[,(\s])(?P<nome>[A-Za-z_][A-Za-z0-9_]*)=")


def _repr_de_objeto_bloqueado(valor: Any) -> bool:
    """Reconhece o repr de um objeto JÁ serializado em string pelo Sentry.

    Este é o furo que `_limpa` sozinho não fecha, e o motivo é de ORDEM: o SDK
    chama `safe_repr()` nas variáveis locais ANTES de entregar o evento ao
    `before_send`. Quando o scrubbing roda, o que está em `frame["vars"]` não é
    mais o objeto — é uma `str` como:

        "SanitizationResult(sanitized_text='Paciente [PACIENTE]...', was_sanitized=True)"

    A comparação por nome de variável não alcança isso: a chave é `dlp_result`,
    que não bate na blocklist, e o conteúdo clínico está DENTRO do valor. Foi
    assim que o prompt saiu num teste ponta a ponta com todos os testes de
    unidade verdes — o mesmo formato de ponto cego dos headers do ASGI
    (ver `_e_par_bloqueado`).

    Detecta por FORMATO, não por nome de classe: qualquer repr cujo conjunto de
    campos toque a blocklist é mascarado inteiro. Uma lista de nomes de classe
    envelheceria a cada objeto novo que passasse pelos frames.
    """
    if not isinstance(valor, str) or "=" not in valor:
        return False
    casado = _REPR_DE_OBJETO.match(valor.strip())
    if casado is None:
        return False
    return any(
        _bloqueado(m.group("nome"))
        for m in _CAMPO_NO_REPR.finditer(casado.group("campos"))
    )


def _campos_de_objeto(valor: Any) -> dict | None:
    """Devolve os atributos de um objeto comum, ou None se não for um.

    Exclui tipos que já têm tratamento próprio e os primitivos, cujo `__dict__`
    não interessa (ou nem existe).
    """
    if isinstance(valor, type):  # a classe em si, não uma instância
        return None
    if isinstance(valor, str | bytes | int | float | bool | type(None)):
        return None
    atributos = getattr(valor, "__dict__", None)
    if isinstance(atributos, dict) and atributos:
        return atributos
    # Pydantic v2 e afins: sem `__dict__` útil, mas com `__slots__`.
    slots = getattr(type(valor), "__slots__", None)
    if slots:
        return {
            nome: getattr(valor, nome)
            for nome in slots
            if isinstance(nome, str) and hasattr(valor, nome)
        }
    return None


def _limpa(valor: Any, profundidade: int = 0) -> Any:
    """Percorre a estrutura e mascara todo valor sob chave bloqueada."""
    if profundidade > _MAX_PROFUNDIDADE:
        return MASCARA

    # Antes de qualquer coisa: repr de objeto já virado string pelo `safe_repr`
    # do SDK. Vem como `str` comum, sob um nome de variável que não diz nada
    # (`dlp_result`, `request`, `resultado`), com o conteúdo clínico dentro.
    if _repr_de_objeto_bloqueado(valor):
        return MASCARA

    if isinstance(valor, dict):
        return {
            chave: MASCARA if _bloqueado(chave) else _limpa(v, profundidade + 1)
            for chave, v in valor.items()
        }
    if isinstance(valor, list | tuple):
        if _e_par_bloqueado(valor):
            return [valor[0], MASCARA]
        return [_limpa(v, profundidade + 1) for v in valor]

    # OBJETOS. Sem isto, `_limpa` devolvia intacta qualquer dataclass, modelo
    # Pydantic ou instância comum que aparecesse nos frames — e a blocklist por
    # nome nunca era consultada para os campos DENTRO dela. O `safe_repr` do
    # Sentry então serializava o objeto inteiro, com o conteúdo junto.
    #
    # Foi assim que `SanitizationResult.original_text` (já removido) levava o
    # prompt clínico bruto para fora. A correção não depende daquele campo: vale
    # para qualquer objeto que carregue texto sob um nome bloqueado.
    #
    # Devolve dict porque o destino é serialização, não reconstrução do objeto —
    # e o nome da classe fica registrado para o alerta continuar diagnosticável.
    campos = _campos_de_objeto(valor)
    if campos is not None:
        limpos = {
            chave: MASCARA if _bloqueado(chave) else _limpa(v, profundidade + 1)
            for chave, v in campos.items()
        }
        return {"__class__": type(valor).__name__, **limpos}

    return valor


def scrub_event(event: dict, hint: dict | None = None) -> dict | None:
    """
    `before_send` do Sentry. Remove tudo que possa carregar dado de paciente.

    Falha fechada: se o scrubbing der erro, o evento é DESCARTADO em vez de
    enviado sem limpeza — perder um alerta é melhor que vazar prontuário.
    """
    try:
        # 1. Corpo da requisição: nunca é necessário para diagnosticar, e é
        #    justamente onde o prompt chega.
        requisicao = event.get("request")
        if isinstance(requisicao, dict):
            requisicao.pop("data", None)
            requisicao.pop("cookies", None)
            cabecalhos = requisicao.get("headers")
            if isinstance(cabecalhos, dict):
                requisicao["headers"] = {
                    k: (MASCARA if _bloqueado(k) else v) for k, v in cabecalhos.items()
                }
            # A query string pode carregar e-mail (ex.: ?email=...).
            requisicao.pop("query_string", None)

        # 2. Variáveis locais dos frames — o vazamento menos óbvio e o mais grave.
        for excecao in (event.get("exception") or {}).get("values", []) or []:
            for frame in (excecao.get("stacktrace") or {}).get("frames", []) or []:
                if isinstance(frame.get("vars"), dict):
                    frame["vars"] = _limpa(frame["vars"])

        # 3. Idem para threads (stack trace sem exceção).
        for thread in (event.get("threads") or {}).get("values", []) or []:
            for frame in (thread.get("stacktrace") or {}).get("frames", []) or []:
                if isinstance(frame.get("vars"), dict):
                    frame["vars"] = _limpa(frame["vars"])

        # 4. Contexto adicional e migalhas de navegação.
        for secao in ("extra", "contexts", "tags"):
            if isinstance(event.get(secao), dict):
                event[secao] = _limpa(event[secao])

        migalhas = event.get("breadcrumbs")
        if isinstance(migalhas, dict) and isinstance(migalhas.get("values"), list):
            migalhas["values"] = _limpa(migalhas["values"])

        # 5. Identificação: id do usuário serve para correlacionar; e-mail não.
        usuario = event.get("user")
        if isinstance(usuario, dict):
            event["user"] = {"id": usuario.get("id")} if usuario.get("id") else {}

        return event
    except Exception as e:
        logger.error("Scrubbing do Sentry falhou; evento descartado. %s", e)
        return None


def setup_sentry(
    dsn: str,
    environment: str,
    release: str | None = None,
    traces_sample_rate: float = 0.0,
) -> bool:
    """Inicializa o Sentry. Retorna False (no-op) se não houver DSN configurado.

    `traces_sample_rate` default 0.0 mantém o comportamento antigo para qualquer
    chamador que não o passe (testes, scripts): tracing é opt-in explícito.
    """
    if not dsn:
        return False

    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=release,
            # Nunca ligar: é o que manda cookies, headers e corpo por padrão.
            send_default_pii=False,
            before_send=scrub_event,
            before_send_transaction=scrub_event,
            # Amostra de transações: o que dá TAXA de resposta por rota, e a
            # única leitura capaz de separar o 401 que é fluxo normal do embed
            # do 401 que é rota quebrada — um alarme por evento não distingue
            # os dois. Trace de LLM continua no Phoenix; isto aqui é HTTP.
            #
            # Passa pelo mesmo `before_send_transaction=scrub_event`, então a
            # query string e o corpo saem antes de sair da máquina — a URL da
            # transação chegaria a carregar `?email=` sem isso.
            traces_sample_rate=traces_sample_rate,
        )
        return True
    except Exception as e:
        logger.error("Sentry não inicializado: %s", e)
        return False
