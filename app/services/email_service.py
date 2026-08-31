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


async def send_news_digest(to_email: str, nome: str | None, artigos: list) -> None:
    """
    Digest diário dos destaques que o usuário pediu.

    `artigos` é uma lista de `(Article, motivo)`, onde `motivo` é o nome da
    palavra-chave que trouxe o item, ou `None` se ele veio por tema. Dizer o
    porquê dentro do e-mail não é enfeite: é o que permite à pessoa saber
    exatamente o que desligar, se aquilo estiver incomodando.

    Só é chamado quando há pelo menos um artigo: "nada para você hoje" seria
    justamente o ruído que o módulo de notícias existe para eliminar. Ver
    `app/services/news_digest_service.py`.
    """
    settings = get_settings()
    base = settings.noticias_url.rstrip("/")

    saudacao = f"Olá, {nome.split()[0]}!" if nome else "Olá!"
    plural = "s" if len(artigos) > 1 else ""
    itens = "\n\n".join(
        f"- {a.rewritten_title}"
        + (f'\n  (porque você acompanha "{motivo}")' if motivo else "")
        + f"\n  {base}/artigo/{a.id}"
        for a, motivo in artigos
    )

    corpo = (
        f"{saudacao}\n\n"
        f"{len(artigos)} novo{plural} destaque{plural} dos seus temas:\n\n"
        f"{itens}\n\n"
        f"Ver tudo: {base}\n\n"
        f"Para não receber mais estes e-mails, ajuste suas preferências em {base}/preferencias"
    )

    if not settings.sendgrid_api_key:
        # Só ocorre sem SendGrid configurado (ambiente local); em produção a chave existe.
        logger.warning("[DEV] Digest de notícias para %s:\n%s", to_email, corpo)
        return

    import sendgrid
    from sendgrid.helpers.mail import Mail

    sg = sendgrid.SendGridAPIClient(api_key=settings.sendgrid_api_key)
    message = Mail(
        from_email=settings.sendgrid_from_email,
        to_emails=to_email,
        subject=f"{len(artigos)} destaque{plural} dos seus temas — Médico 360",
        plain_text_content=corpo,
    )
    await asyncio.to_thread(sg.send, message)
