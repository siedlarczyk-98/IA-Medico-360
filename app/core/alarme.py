"""
Alarme operacional — um evento no Sentry quando uma garantia deixa de valer.

Extraído de `expurgo_agendado._alertar` quando o segundo alarme do projeto (a
vigilância de métricas) precisou exatamente da mesma forma: nível `warning`,
uma tag que identifica o alarme, contexto estruturado, e a garantia de que
falhar ao alarmar nunca derruba quem chamou.

Extrair na segunda ocorrência e não na quarta é deliberado. Este repositório já
pagou o preço de código copiado que depois divergiu — ver o cabeçalho de
`app/services/orquestrador_shared.py` e o de `orquestrador_modes.py`.

POR QUE `warning` É O PADRÃO
Estes alarmes não dizem "está quebrado agora"; dizem "uma garantia deixou de
ser cumprida e alguém precisa olhar". Mandar tudo como `error` mistura os dois
e treina o time a ignorar a caixa de entrada — que é exatamente como se perde a
próxima falha silenciosa.

O QUE ESTE MÓDULO NÃO É
Não é métrica. Não conta, não agrega, não desenha gráfico. É o degrau mais
barato entre "o dado existe no banco" e "alguém fica sabendo" — que era
precisamente o degrau que faltava quando o cache semântico ficou meses
desligado com `cache_hit` gravado em toda interação.
"""

import logging

logger = logging.getLogger(__name__)


def alarmar(
    *,
    tag: str,
    mensagem: str,
    contexto: dict | None = None,
    nivel: str = "warning",
) -> bool:
    """
    Reporta ao Sentry, se houver DSN. Devolve True se o evento chegou a ser enviado.

    Sem DSN é no-op silencioso: em desenvolvimento e no CI o log do chamador já
    registra o mesmo fato, e falhar aqui atrapalharia quem chamou sem informar
    ninguém.

    O valor de retorno existe para o teste conseguir afirmar o comportamento sem
    subir um Sentry de verdade.
    """
    try:
        import sentry_sdk

        # `get_client()` e `new_scope()` são a API do sentry-sdk 2.x; `Hub` e
        # `push_scope` continuam funcionando mas emitem aviso de depreciação.
        if not sentry_sdk.get_client().is_active():
            return False

        with sentry_sdk.new_scope() as scope:
            scope.set_level(nivel)
            scope.set_tag("alarme", tag)
            if contexto:
                scope.set_context(tag, contexto)
            sentry_sdk.capture_message(mensagem)
        return True
    except Exception as exc:  # noqa: BLE001 — alarmar não pode derrubar o chamador
        logger.warning("Falha ao emitir alarme '%s': %s", tag, exc)
        return False
