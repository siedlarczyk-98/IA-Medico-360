"""
Alarme do handshake de identidade da Waid.

A distinção que este arquivo protege é a única que importa aqui: das duas
falhas possíveis na troca do token, **uma é o cliente se recuperando e a outra
é a integração quebrada**, e só a segunda merece acordar alguém.

- `TokenDeIdentidadeInvalido` -> 401. O token queimou (um reload em voo já
  basta). O cliente pede outro pelo mesmo evento e segue — `shared/embed/
  identidade.ts` retenta até três vezes. Alarmar aqui encheria o Sentry de
  eventos que se resolveram sozinhos, que é como se treina um time a ignorar
  a caixa de entrada.
- `CurseducaNotConfigured` -> 503. Credencial nossa, permissão ausente ou a
  Waid fora do ar. Nenhum retry resolve, e enquanto durar **ninguém entra pelo
  embed** — que é o caminho principal de acesso. Sem alarme o sintoma é
  silêncio: o médico vê "não foi possível confirmar sua identidade" e o painel
  não registra nada.
"""

import pytest

from app.api.v1.endpoints import auth as auth_endpoint
from app.services.integracoes import curseduca_service

asyncio = pytest.mark.asyncio


@pytest.fixture
def alarmes(monkeypatch) -> list[dict]:
    """Captura o que teria ido ao Sentry, sem precisar de DSN."""
    registrados: list[dict] = []
    monkeypatch.setattr(
        auth_endpoint,
        "alarmar",
        lambda **kw: registrados.append(kw) or True,
    )
    return registrados


@asyncio
async def test_integracao_indisponivel_alarma(alarmes, monkeypatch):
    async def fora_do_ar(_token):
        raise curseduca_service.CurseducaNotConfigured("503 do endpoint validate")

    monkeypatch.setattr(curseduca_service, "trocar_token_de_identidade", fora_do_ar)

    with pytest.raises(auth_endpoint.HTTPException) as erro:
        await auth_endpoint._entrar_por_token_waid(None, "tok")

    assert erro.value.status_code == 503
    assert len(alarmes) == 1
    assert alarmes[0]["tag"] == "embed_identidade_indisponivel"
    # O contexto tem de dizer o que aconteceu: um alarme sem causa obriga quem
    # for atendê-lo a ir procurar no log, e é aí que o alarme perde o valor.
    assert "503" in alarmes[0]["contexto"]["erro"]


@asyncio
async def test_token_queimado_nao_alarma(alarmes, monkeypatch):
    """O caso comum e recuperável não pode virar evento."""

    async def token_velho(_token):
        raise curseduca_service.TokenDeIdentidadeInvalido("token_expirado")

    monkeypatch.setattr(curseduca_service, "trocar_token_de_identidade", token_velho)

    with pytest.raises(auth_endpoint.HTTPException) as erro:
        await auth_endpoint._entrar_por_token_waid(None, "tok")

    assert erro.value.status_code == 401
    assert alarmes == []
