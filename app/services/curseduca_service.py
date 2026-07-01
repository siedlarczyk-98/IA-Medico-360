"""
Validação server-to-server de membros da Curseduca (plano de melhorias, item 2.1).

O embed da Curseduca só entrega o e-mail do aluno na URL do iframe — sem SSO nem
assinatura. O header Origin é forjável server-side, então NÃO prova identidade. Para
reduzir a superfície de "qualquer e-mail" → "e-mail de membro matriculado", validamos
o e-mail contra a API da Curseduca (credenciais server-side) antes de emitir o token.

Estado atual: ESQUELETO fail-closed. A chamada HTTP concreta depende da doc/credenciais
da Curseduca (endpoint de consulta de membro + formato da resposta), que ainda não temos.
Enquanto `curseduca_validation_enabled` for False (default), `verify_active_member` é no-op
e o comportamento do embed não muda. Ao habilitar sem implementar a chamada, o endpoint
falha fechado (503) — nunca abre a autenticação com base em validação inexistente.

Para ativar:
1. Preencher CURSEDUCA_API_BASE / CURSEDUCA_API_KEY no ambiente.
2. Implementar `_fetch_member_status` com o endpoint real.
3. Setar CURSEDUCA_VALIDATION_ENABLED=true.
"""

from fastapi import HTTPException, status

from app.core.config import get_settings


class CurseducaNotConfigured(Exception):
    """Validação habilitada mas a integração ainda não foi implementada/configurada."""


async def _fetch_member_status(email: str, api_base: str, api_key: str) -> bool:
    """Consulta a API da Curseduca e retorna True se `email` é membro ativo.

    TODO(2.1): implementar com o endpoint real assim que a doc/credenciais chegarem.
    Sugerido: httpx.AsyncClient com timeout curto, autenticação por api_key,
    e mapear a resposta para um booleano de "matrícula ativa".
    """
    raise CurseducaNotConfigured(
        "Validação Curseduca habilitada, mas _fetch_member_status ainda não foi implementada."
    )


async def verify_active_member(email: str) -> None:
    """Levanta 403 se o e-mail não for membro ativo; no-op quando a validação está desligada.

    Fail-closed: se a validação está ligada mas a integração não está pronta/configurada,
    levanta 503 em vez de deixar passar.
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
            email, settings.curseduca_api_base, settings.curseduca_api_key
        )
    except CurseducaNotConfigured as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Validação de membro Curseduca habilitada mas não implementada.",
        ) from exc

    if not is_member:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "E-mail não corresponde a um membro ativo.")
