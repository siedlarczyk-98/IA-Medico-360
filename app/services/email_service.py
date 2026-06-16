import asyncio
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def send_otp(to_email: str, code: str) -> None:
    settings = get_settings()
    if not settings.sendgrid_api_key:
        # Só ocorre sem SendGrid configurado (ambiente local); em produção a chave existe.
        logger.warning("[DEV] OTP para %s: %s", to_email, code)
        return

    import sendgrid
    from sendgrid.helpers.mail import Mail

    sg = sendgrid.SendGridAPIClient(api_key=settings.sendgrid_api_key)
    message = Mail(
        from_email=settings.sendgrid_from_email,
        to_emails=to_email,
        subject="Seu código de acesso — Médico 360",
        plain_text_content=(
            f"Seu código de acesso é: {code}\n\n"
            f"Válido por {settings.otp_expire_minutes} minutos.\n\n"
            "Se você não solicitou este código, ignore este email."
        ),
    )
    await asyncio.to_thread(sg.send, message)


async def send_invite(to_email: str, invite_url: str) -> None:
    settings = get_settings()
    if not settings.sendgrid_api_key:
        # Só ocorre sem SendGrid configurado (ambiente local); em produção a chave existe.
        logger.warning("[DEV] Link de acesso para %s: %s", to_email, invite_url)
        return

    import sendgrid
    from sendgrid.helpers.mail import Mail

    sg = sendgrid.SendGridAPIClient(api_key=settings.sendgrid_api_key)
    message = Mail(
        from_email=settings.sendgrid_from_email,
        to_emails=to_email,
        subject="Seu acesso ao Médico 360",
        plain_text_content=(
            f"Olá!\n\n"
            f"Você foi convidado para acessar o Médico 360.\n\n"
            f"Clique no link abaixo para criar sua conta:\n{invite_url}\n\n"
            f"O link é válido por 72 horas.\n\n"
            "Se você não solicitou este acesso, ignore este email."
        ),
    )
    await asyncio.to_thread(sg.send, message)
