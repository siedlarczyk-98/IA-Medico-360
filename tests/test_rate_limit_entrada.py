"""
As rotas de ENTRADA aguentam um evento — dezenas de médicos atrás do mesmo IP.

Antes do login não há token, e o limitador conta por endereço. Num evento o Wi-Fi
do local (ou o CGNAT da operadora) põe todo mundo atrás de um IP só. Com os
limites antigos, o 11º médico a abrir o app no mesmo minuto levava 429 no embed,
e o plano B — código por e-mail — travava no 4º pedido em 15 minutos.

Todos os testes aqui saem do MESMO IP (o cliente ASGI), que é a condição do
evento. O teto por IP continua existindo: sem ele, um endereço só nos faria
chamar a Waid ou o SendGrid em laço.
"""

import pytest

from app.api.v1.endpoints import auth as rotas_auth
from app.services.integracoes import curseduca_service

pytestmark = pytest.mark.asyncio

ORIGEM = "https://adminportalmedico360.curseduca.pro"
MEDICOS_NO_EVENTO = 40


def _teto(limite: str) -> int:
    """`"120/minute"` → 120."""
    return int(limite.split("/")[0])


def _waid_emite_um_medico_por_token(monkeypatch):
    """Cada token vira um médico diferente — como na Waid de verdade."""

    async def troca(token):
        return curseduca_service.IdentidadeWaid(
            uuid=f"00000000-0000-4000-8000-{int(token):012d}",
            nome=f"Médico {token}",
            email=f"medico{token}@evento.com",
        )

    async def sem_grupos(_email):
        return None

    monkeypatch.setattr(curseduca_service, "trocar_token_de_identidade", troca)
    monkeypatch.setattr(curseduca_service, "buscar_membro_para_enriquecer", sem_grupos)


async def test_quarenta_medicos_no_mesmo_wifi_entram_pelo_embed(client, monkeypatch):
    _waid_emite_um_medico_por_token(monkeypatch)

    status = []
    for i in range(MEDICOS_NO_EVENTO):
        # Cada médico é um aparelho novo, sem cookie. Sem limpar, o cliente de
        # teste reenviaria o cookie de sessão do médico anterior, o limitador
        # contaria por ELE e não pelo IP — e o teste passaria com o limite antigo.
        client.cookies.clear()
        resp = await client.post(
            "/api/v1/auth/embed/token", json={"token": str(i)}, headers={"Origin": ORIGEM}
        )
        status.append(resp.status_code)

    assert status == [200] * MEDICOS_NO_EVENTO, (
        f"o {status.index(429) + 1}º médico no mesmo IP foi barrado" if 429 in status else status
    )


async def test_o_embed_ainda_tem_teto_por_ip(client, monkeypatch):
    """Tokens inválidos em laço, de um endereço só: a Waid não pode virar alvo nosso."""

    async def queimado(_token):
        raise curseduca_service.TokenDeIdentidadeInvalido("token_invalido")

    monkeypatch.setattr(curseduca_service, "trocar_token_de_identidade", queimado)
    teto = _teto(rotas_auth.LIMITE_EMBED_POR_IP)

    for _ in range(teto):
        resp = await client.post(
            "/api/v1/auth/embed/token", json={"token": "x"}, headers={"Origin": ORIGEM}
        )
        assert resp.status_code == 401

    estourou = await client.post(
        "/api/v1/auth/embed/token", json={"token": "x"}, headers={"Origin": ORIGEM}
    )
    assert estourou.status_code == 429


async def test_pedido_de_codigo_nao_trava_no_quarto_medico(client):
    """O plano B precisa funcionar justamente quando o embed falha para muitos."""
    status = [
        (await client.post("/api/v1/auth/otp/request", json={"email": f"m{i}@evento.com"})).status_code
        for i in range(20)
    ]

    assert 429 not in status, f"o {status.index(429) + 1}º pedido de código foi barrado"


async def test_verificacao_de_codigo_nao_trava_o_evento(client):
    status = [
        (
            await client.post(
                "/api/v1/auth/otp/verify", json={"email": f"m{i}@evento.com", "code": "000000"}
            )
        ).status_code
        for i in range(20)
    ]

    assert 429 not in status, f"a {status.index(429) + 1}ª verificação foi barrada"
