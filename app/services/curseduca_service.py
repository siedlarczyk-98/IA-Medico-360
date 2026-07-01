"""
Validação server-to-server de membros da Curseduca (plano de melhorias, item 2.1).

O embed da Curseduca só entrega o e-mail do aluno na URL do iframe — sem SSO nem
assinatura. O header Origin é forjável server-side, então NÃO prova identidade. Para
reduzir a superfície de "qualquer e-mail" → "e-mail de membro matriculado", validamos
o e-mail contra a API da Curseduca (credenciais server-side) antes de emitir o token.

Contrato (Swagger Curseduca):
  GET {api_base}/api/v1/members/by?email=<email>
  Headers: api_key: <key>   e   Authorization: Bearer <access_token>
  200 -> objeto do membro ({id, name, email, ...})  => membro existe
  401 -> API Key inválida        (fail-closed: configuração errada)
  400 -> query não fornecida     (fail-closed: bug nosso)
  403 -> token ausente/negado    (fail-closed: configuração errada)

Fail-closed: enquanto a validação está ligada mas algo impede confirmar a matrícula
(credencial errada, API fora do ar), o embed é negado — nunca abre com base em dúvida.
No-op enquanto `curseduca_validation_enabled` for False (default).
"""

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings

_TIMEOUT_SECONDS = 8.0


class CurseducaNotConfigured(Exception):
    """Validação habilitada mas a integração respondeu erro de configuração/indisponibilidade."""


async def _fetch_member_status(email: str, api_base: str, api_key: str, access_token: str) -> bool:
    """Consulta a API da Curseduca e retorna True se `email` é membro. Fail-closed em erro."""
    url = f"{api_base.rstrip('/')}/api/v1/members/by"
    headers = {"api_key": api_key, "accept": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.get(url, params={"email": email}, headers=headers)
    except httpx.HTTPError as exc:
        raise CurseducaNotConfigured(f"Falha ao contatar a API da Curseduca: {exc}") from exc

    if resp.status_code == 200:
        data = resp.json()
        # Membro encontrado quando a resposta traz o e-mail do próprio membro.
        return bool(isinstance(data, dict) and data.get("email"))
    if resp.status_code == 404:
        return False  # e-mail não corresponde a nenhum membro
    # 400 (query), 401 (api_key), 403 (token), 5xx -> não dá para confirmar => fail-closed.
    raise CurseducaNotConfigured(
        f"Curseduca respondeu {resp.status_code} ao validar membro: {resp.text[:200]}"
    )


async def verify_active_member(email: str) -> None:
    """Levanta 403 se o e-mail não for membro; no-op quando a validação está desligada.

    Fail-closed: se a validação está ligada mas a integração não está pronta/configurada
    ou a API não respondeu OK, levanta 503 em vez de deixar passar.
    """
    settings = get_settings()
    if not settings.curseduca_validation_enabled:
        return

    if not settings.curseduca_api_base or not settings.curseduca_api_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Validação de membro Curseduca habilitada mas não configurada.",
        )

    try:
        is_member = await _fetch_member_status(
            email,
            settings.curseduca_api_base,
            settings.curseduca_api_key,
            settings.curseduca_access_token,
        )
    except CurseducaNotConfigured as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Não foi possível validar o membro na Curseduca no momento.",
        ) from exc

    if not is_member:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "E-mail não corresponde a um membro ativo.")
