"""
Envia um e-mail de TESTE para conferir como ele chega no cliente real.

Abrir o HTML no navegador mostra o layout; não mostra o que o Gmail e o Outlook
fazem com ele. Gmail descarta parte do CSS, Outlook usa o motor de renderização
do Word, e o celular corta em outra largura. Este script fecha essa distância.

    python -m scripts.enviar_email_de_teste --para voce@exemplo.com
    python -m scripts.enviar_email_de_teste --para voce@exemplo.com --qual codigo

Precisa de `SENDGRID_API_KEY` no ambiente (ou no `.env`). O assunto sai marcado
com `[TESTE]` — ninguém confunde com e-mail de verdade, nem em caixa de entrada
compartilhada.

POR QUE NÃO MANDA PARA QUALQUER UM
Só envia para UM destinatário por vez, passado à mão. Um script de teste que
aceita lista é um disparo em massa esperando acontecer.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402

EXEMPLOS = Path(__file__).resolve().parent.parent / "docs" / "exemplos-email"
MODELOS = {
    "codigo": (EXEMPLOS / "email-codigo.html", "Seu código de acesso"),
    "noticias": (EXEMPLOS / "email-noticias.html", "Seus destaques de hoje"),
}


async def enviar(para: str, quais: list[str]) -> int:
    settings = get_settings()
    if not settings.sendgrid_api_key:
        print("[ERRO] SENDGRID_API_KEY não está no ambiente.")
        print("       A chave vive no Railway; copie para o `.env` local para enviar daqui.")
        return 1

    import sendgrid
    from sendgrid.helpers.mail import Mail

    cliente = sendgrid.SendGridAPIClient(api_key=settings.sendgrid_api_key)
    for qual in quais:
        caminho, assunto = MODELOS[qual]
        if not caminho.exists():
            print(f"[ERRO] {caminho} não existe.")
            return 1

        mensagem = Mail(
            from_email=settings.sendgrid_from_email,
            to_emails=para,
            subject=f"[TESTE] {assunto} — Médico 360",
            html_content=caminho.read_text(encoding="utf-8"),
        )
        resposta = await asyncio.to_thread(cliente.send, mensagem)
        estado = "enviado" if 200 <= resposta.status_code < 300 else f"FALHOU ({resposta.status_code})"
        print(f"  {qual:9s} -> {para}: {estado}")

    print("\nConfira no celular também: é onde a maioria vai ler.")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Envia um e-mail de teste com o HTML de exemplo.")
    p.add_argument("--para", required=True, help="destinatário (um só)")
    p.add_argument("--qual", choices=[*MODELOS, "ambos"], default="ambos")
    a = p.parse_args()
    escolhidos = list(MODELOS) if a.qual == "ambos" else [a.qual]
    sys.exit(asyncio.run(enviar(a.para, escolhidos)))
