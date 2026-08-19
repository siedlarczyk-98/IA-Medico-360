"""
Verificacao ponta a ponta do Sentry — envia UM evento de teste.

Confirma duas coisas ao mesmo tempo:
  1. O DSN esta configurado e o evento chega ao painel.
  2. O scrubbing funciona no ambiente real — o prompt clinico NAO aparece.

Rodar no ambiente que se quer verificar:

    python -m scripts.verificar_sentry

Sem SENTRY_DSN configurado ele avisa e sai sem fazer nada. Nao escreve no banco,
nao chama provedor de IA, nao tem efeito colateral algum.

O evento vai com a tag `verificacao=manual` e o titulo abaixo, para ser facil de
achar e de marcar como resolvido no painel depois.
"""

import sys

from app.core.config import get_settings
from app.core.error_tracking import setup_sentry

TITULO = "VERIFICACAO DE SCRUBBING — pode ignorar este erro"

# Sintetico, no formato que chega em producao. Nenhum dado real.
PROMPT_DE_TESTE = (
    "Paciente Joao da Silva, 62 anos, CPF 123.456.789-00, "
    "telefone (11) 99999-0000, em uso de varfarina com INR 4.8."
)

# Fragmentos que NAO podem aparecer no evento. Sao os mesmos que os testes
# automatizados verificam (tests/test_error_tracking.py).
NAO_PODE_VAZAR = ["Joao da Silva", "123.456.789-00", "99999-0000", "varfarina", "INR 4.8"]


def main() -> int:
    settings = get_settings()

    if not settings.sentry_dsn:
        print("SENTRY_DSN nao configurado neste ambiente — nada a verificar.")
        return 1

    if not setup_sentry(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        release=settings.sentry_release or None,
    ):
        print("Falha ao inicializar o Sentry. Verifique o DSN.")
        return 1

    import sentry_sdk

    sentry_sdk.set_tag("verificacao", "manual")

    def simula_chamada_ao_provider(prompt: str, model_id: str):
        """O prompt fica vivo como variavel local — e o caso que mais importa."""
        sanitized_prompt = prompt  # noqa: F841 — precisa existir no frame
        historico = [{"role": "user", "content": prompt}]  # noqa: F841
        raise RuntimeError(TITULO)

    try:
        simula_chamada_ao_provider(PROMPT_DE_TESTE, "claude-sonnet-4-6")
    except RuntimeError:
        sentry_sdk.capture_exception()

    sentry_sdk.flush(timeout=10)

    print(f"Evento enviado para o ambiente '{settings.app_env}'.")
    print()
    print("Agora abra o painel do Sentry, ache a issue:")
    print(f'  "{TITULO}"')
    print()
    print("E confirme que NENHUM destes aparece em lugar nenhum do evento")
    print("(inclusive em 'Local Variables' dentro do stack trace):")
    for fragmento in NAO_PODE_VAZAR:
        print(f"  - {fragmento}")
    print()
    print("Se algum aparecer, o scrubbing nao esta ativo: PARE e me avise.")
    print("Depois de conferir, marque a issue como resolvida.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
