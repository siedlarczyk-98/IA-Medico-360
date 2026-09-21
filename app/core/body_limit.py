"""
Recusa corpo de requisição grande demais ANTES de recebê-lo.

Sem isto o servidor aceitava qualquer tamanho. No upload, o framework grava o
corpo multipart inteiro (em memória até 1 MB, depois em disco) antes de o handler
rodar, e o handler ainda o lia todo para a memória para só então medir: um envio
de 1 GB custava 1 GB antes do "arquivo maior que 10 MB". Nas rotas JSON o corpo
vai inteiro para a memória ao ser interpretado. Um único cliente derrubava o
container.

A checagem é pelo cabeçalho `Content-Length`, que todo navegador manda em
`fetch` com corpo — barato e antes de ler um byte. Corpo SEM o cabeçalho
(transferência em blocos) passa; o upload se protege sozinho lendo em blocos até
o limite (`endpoints/uploads.py`).

ASGI puro, não `BaseHTTPMiddleware`: esta última envolve o corpo num stream
próprio e interfere nas respostas em streaming do orquestrador.
"""

import json

from app.services.file_extractor_service import MAX_FILE_BYTES

PREFIXO_DE_UPLOAD = "/api/v1/uploads"
# O multipart embrulha o arquivo em fronteiras e cabeçalhos de parte.
LIMITE_UPLOAD = MAX_FILE_BYTES + 1024 * 1024
# Nenhuma rota JSON chega perto: o prompt tem teto de caracteres e anexos viajam
# por `file_id`, não no corpo.
LIMITE_GERAL = 2 * 1024 * 1024


class LimiteDeCorpoMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declarado = dict(scope["headers"]).get(b"content-length")
        limite = LIMITE_UPLOAD if scope["path"].startswith(PREFIXO_DE_UPLOAD) else LIMITE_GERAL
        try:
            grande_demais = declarado is not None and int(declarado) > limite
        except ValueError:
            grande_demais = False  # cabeçalho inválido: o servidor HTTP já recusa

        if not grande_demais:
            await self.app(scope, receive, send)
            return

        corpo = json.dumps(
            {"detail": f"Requisição grande demais (limite de {limite // (1024 * 1024)} MB)."},
            ensure_ascii=False,
        ).encode()
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(corpo)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": corpo})
