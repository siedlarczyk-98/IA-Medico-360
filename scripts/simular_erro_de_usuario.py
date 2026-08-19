"""
Simula uma requisicao REAL de usuario que estoura, e envia o evento ao Sentry.

Complementa `scripts/verificar_sentry.py`: aquele exercita as variaveis locais
do stack trace; este exercita o contexto de REQUISICAO — corpo, headers, cookie
e query string, que e o que o Sentry envia por padrao e onde o prompt clinico
chegaria inteiro.

Rodar no ambiente que se quer verificar:

    python -m scripts.simular_erro_de_usuario

Nao altera o servidor em execucao: registra a rota temporaria neste processo,
que morre junto com o script. Nao escreve no banco, nao chama provedor de IA.
"""

import asyncio
import sys

from app.core.config import get_settings
from app.core.error_tracking import setup_sentry

ROTA = "/__simulacao_de_erro__"

CORPO = {
    "prompt": (
        "Paciente Joao da Silva, 62 anos, CPF 123.456.789-00, "
        "telefone (11) 99999-0000, em uso de varfarina com INR 4.8."
    ),
    "conversation_id": None,
    "models": ["claude-sonnet-4-6"],
}

CABECALHOS = {
    "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.token-de-simulacao.assinatura",
    "Cookie": "medico360_session=sessao-de-simulacao",
    "User-Agent": "simulacao/1.0",
}

NAO_PODE_VAZAR = [
    "Joao da Silva", "123.456.789-00", "99999-0000", "varfarina", "INR 4.8",
    "token-de-simulacao", "sessao-de-simulacao",
]


async def _executar() -> int:
    settings = get_settings()

    if not settings.sentry_dsn:
        print("SENTRY_DSN nao configurado neste ambiente — nada a simular.")
        return 1

    if not setup_sentry(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        release=settings.sentry_release or None,
    ):
        print("Falha ao inicializar o Sentry. Verifique o DSN.")
        return 1

    import sentry_sdk
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    sentry_sdk.set_tag("verificacao", "simulacao-de-requisicao")

    # Rota temporaria: existe so neste processo. O servidor em execucao no
    # Railway nao e afetado — por isso nao adicionamos /sentry-debug ao codigo.
    @app.post(ROTA)
    async def _estoura(payload: dict):
        prompt_do_medico = payload.get("prompt")  # noqa: F841 — vivo no frame
        raise RuntimeError("SIMULACAO DE ERRO — pode ignorar")

    transporte = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transporte, base_url="http://simulacao") as cliente:
        resposta = await cliente.post(
            f"{ROTA}?email=medico@exemplo.com.br", json=CORPO, headers=CABECALHOS
        )

    sentry_sdk.flush(timeout=10)

    print(f"Resposta ao 'usuario': {resposta.status_code} {resposta.text.strip()[:60]}")
    print(f"Ambiente: {settings.app_env}")
    print()
    print("Abra o Sentry e ache a issue: \"SIMULACAO DE ERRO — pode ignorar\"")
    print()
    print("Confirme que NENHUM destes aparece em lugar nenhum do evento —")
    print("olhe especialmente em Request (body/headers/cookies) e em Local Variables:")
    for fragmento in NAO_PODE_VAZAR:
        print(f"  - {fragmento}")
    print()
    print("O que DEVE aparecer (alerta util): a URL, o metodo POST, o nome da")
    print("funcao e o tipo do erro.")
    print()
    print("Se algum fragmento vazar, o scrubbing falhou: PARE de usar o Sentry e avise.")
    return 0


def main() -> int:
    return asyncio.run(_executar())


if __name__ == "__main__":
    sys.exit(main())
