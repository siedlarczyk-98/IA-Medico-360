"""
Envio de e-mail. O que a pessoa LÊ mora em `email_templates`; aqui só o envio.

Todo envio leva as duas partes, texto e HTML. Ver o cabeçalho de
`email_templates` para o porquê — em resumo: mensagem só-HTML pontua pior em
filtro de spam, e um e-mail de código de acesso no spam é o usuário sem entrar.
"""

import asyncio
import logging

from app.core.config import get_settings
from app.services import email_templates

logger = logging.getLogger(__name__)


async def _enviar(to_email: str, assunto: str, texto: str, html: str) -> None:
    """O SendGrid é síncrono; vai para uma thread para não travar o event loop."""
    settings = get_settings()

    import sendgrid
    from sendgrid.helpers.mail import Mail

    sg = sendgrid.SendGridAPIClient(api_key=settings.sendgrid_api_key)
    message = Mail(
        from_email=settings.sendgrid_from_email,
        to_emails=to_email,
        subject=assunto,
        plain_text_content=texto,
        html_content=html,
    )
    await asyncio.to_thread(sg.send, message)


async def send_otp(to_email: str, code: str) -> None:
    settings = get_settings()
    texto, html = email_templates.otp(code, settings.otp_expire_minutes)

    if not settings.sendgrid_api_key:
        # Só ocorre sem SendGrid configurado (ambiente local); em produção a chave existe.
        logger.warning("[DEV] OTP para %s: %s", to_email, code)
        return

    await _enviar(to_email, "Seu código de acesso — Médico 360", texto, html)


async def send_invite(to_email: str, invite_url: str) -> None:
    settings = get_settings()
    texto, html = email_templates.convite(invite_url)

    if not settings.sendgrid_api_key:
        # Só ocorre sem SendGrid configurado (ambiente local); em produção a chave existe.
        logger.warning("[DEV] Link de acesso para %s: %s", to_email, invite_url)
        return

    await _enviar(to_email, "Seu acesso ao Médico 360", texto, html)


async def send_news_digest(to_email: str, nome: str | None, artigos: list) -> None:
    """
    Digest dos destaques que o usuário pediu.

    `artigos` é uma lista de `(Article, motivo)`, onde `motivo` é o nome da
    palavra-chave que trouxe o item, ou `None` se ele veio por tema.

    Só é chamado quando há pelo menos um artigo: "nada para você hoje" seria
    justamente o ruído que o módulo de notícias existe para eliminar. Ver
    `app/services/news_digest_service.py`.
    """
    settings = get_settings()
    assunto, texto, html = email_templates.digest(nome, artigos, settings.noticias_url)

    if not settings.sendgrid_api_key:
        # Só ocorre sem SendGrid configurado (ambiente local); em produção a chave existe.
        logger.warning("[DEV] Digest de notícias para %s:\n%s", to_email, texto)
        return

    await _enviar(to_email, assunto, texto, html)
