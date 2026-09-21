"""
Login por código de e-mail, de ponta a ponta.

Era cobertura ZERO na verificação: bloqueio em 5 tentativas, expiração, uso único
— nada tinha teste. E três defeitos (item 51 da varredura de 2026-09-18):

1. O código ficava em TEXTO PURO na tabela.
2. Tentativas em paralelo não eram serializadas: cinco palpites juntos liam todos
   "0 tentativas" e contavam como uma.
3. O e-mail era enviado DENTRO da requisição: conta existente demorava segundos,
   inexistente voltava na hora — dava para enumerar quem tem conta pelo relógio.
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.deps import COOKIE_NAME
from app.core.limiter import limiter
from app.models.models import OtpCode, User
from app.services import auth_service, email_service

EMAIL = "medica@hospital.com"


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    """Isola o que NÃO é o assunto destes testes.

    - O limite por e-mail consulta o Redis, que na suíte é uma porta fechada: cada
      chamada pagaria o timeout de conexão (1 s) e mascararia a medição de tempo.
    - Envio pendente de um teste que falhou não pode vazar para o seguinte (a
      tarefa pertence ao event loop do teste que a criou).
    """
    async def _dentro_do_limite(*_a, **_kw):
        return False

    monkeypatch.setattr("app.services.cache_service.rate_limit_exceeded", _dentro_do_limite)
    auth_service._envios_em_voo.clear()
    yield
    auth_service._envios_em_voo.clear()


@pytest.fixture
def caixa_de_saida(monkeypatch):
    """Captura o que seria enviado por e-mail: {destinatário: código}."""
    enviados: dict[str, str] = {}

    async def _send(to_email, code):
        enviados[to_email] = code

    monkeypatch.setattr(email_service, "send_otp", _send)
    return enviados


async def _esperar_envios():
    if auth_service._envios_em_voo:
        await asyncio.gather(*list(auth_service._envios_em_voo), return_exceptions=True)


async def _pedir(client, email=EMAIL):
    resp = await client.post("/api/v1/auth/otp/request", json={"email": email})
    await _esperar_envios()
    return resp


async def _verificar(client, code, email=EMAIL):
    return await client.post("/api/v1/auth/otp/verify", json={"email": email, "code": code})


# ── O caminho feliz ──────────────────────────────────────────────────────────

async def test_pedir_e_verificar_o_codigo_da_sessao(client, user_factory, caixa_de_saida):
    await user_factory(email=EMAIL)

    assert (await _pedir(client)).status_code == 204
    resp = await _verificar(client, caixa_de_saida[EMAIL])

    assert resp.status_code == 200
    assert resp.json()["access_token"]
    assert COOKIE_NAME in resp.cookies


async def test_o_codigo_vale_uma_vez_so(client, user_factory, caixa_de_saida):
    await user_factory(email=EMAIL)
    await _pedir(client)
    codigo = caixa_de_saida[EMAIL]
    assert (await _verificar(client, codigo)).status_code == 200

    assert (await _verificar(client, codigo)).status_code == 400


async def test_pedir_de_novo_invalida_o_codigo_anterior(client, user_factory, caixa_de_saida):
    await user_factory(email=EMAIL)
    await _pedir(client)
    antigo = caixa_de_saida[EMAIL]
    await _pedir(client)
    novo = caixa_de_saida[EMAIL]

    if antigo != novo:  # 1 em 900 mil de coincidirem
        assert (await _verificar(client, antigo)).status_code == 400
    assert (await _verificar(client, novo)).status_code == 200


async def test_codigo_vencido_e_recusado(client, db, user_factory, caixa_de_saida):
    await user_factory(email=EMAIL)
    await _pedir(client)
    otp = (await db.execute(select(OtpCode).where(OtpCode.email == EMAIL))).scalar_one()
    otp.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db.commit()

    assert (await _verificar(client, caixa_de_saida[EMAIL])).status_code == 400


# ── 1. O código não fica em texto puro ───────────────────────────────────────

async def test_a_tabela_guarda_o_hmac_e_nao_o_codigo(client, db, user_factory, caixa_de_saida):
    await user_factory(email=EMAIL)
    await _pedir(client)

    gravado = (await db.execute(select(OtpCode.code).where(OtpCode.email == EMAIL))).scalar_one()

    assert gravado != caixa_de_saida[EMAIL]
    assert len(gravado) == 64
    assert caixa_de_saida[EMAIL] not in gravado


def test_o_mesmo_codigo_em_duas_contas_nao_da_o_mesmo_resumo():
    a = auth_service._resumo_do_codigo("a@x.com", "123456")
    b = auth_service._resumo_do_codigo("b@x.com", "123456")

    assert a != b
    assert a == auth_service._resumo_do_codigo(" A@X.com ", "123456"), "e-mail é normalizado"


# ── 2. O teto de tentativas ──────────────────────────────────────────────────

async def test_cinco_erros_bloqueiam_ate_o_codigo_certo(client, user_factory, caixa_de_saida):
    await user_factory(email=EMAIL)
    await _pedir(client)
    certo = caixa_de_saida[EMAIL]
    errado = "000000" if certo != "000000" else "111111"

    for _ in range(5):
        assert (await _verificar(client, errado)).status_code == 400

    # A rota tem um segundo freio, 5 verificações por minuto por IP. Zerado aqui
    # para o teste enxergar o bloqueio DO CÓDIGO, que é o que vale para um
    # atacante distribuído por vários IPs.
    limiter.reset()
    assert (await _verificar(client, certo)).status_code == 400, (
        "depois de 5 erros o código certo ainda entrou — força bruta fica viável"
    )


async def test_quatro_erros_ainda_deixam_entrar(client, user_factory, caixa_de_saida):
    await user_factory(email=EMAIL)
    await _pedir(client)
    certo = caixa_de_saida[EMAIL]
    errado = "000000" if certo != "000000" else "111111"
    for _ in range(4):
        await _verificar(client, errado)

    assert (await _verificar(client, certo)).status_code == 200


async def test_palpites_em_paralelo_contam_todos(fabrica_com_conexoes_reais):
    """A trava de linha. Em `db_conn` tudo divide uma conexão e a corrida não existe."""
    async with fabrica_com_conexoes_reais() as db:
        db.add(User(email=EMAIL, role="beta_user", status=True, onboarding_complete=True, name="M"))
        db.add(OtpCode(
            email=EMAIL,
            code=auth_service._resumo_do_codigo(EMAIL, "654321"),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        ))
        await db.commit()

    async def palpite():
        async with fabrica_com_conexoes_reais() as db:
            with pytest.raises(HTTPException):
                await auth_service.verify_otp(db, EMAIL, "000000")

    # Dois por vez: é o tamanho do pool da fixture, e já basta para a corrida.
    for _ in range(2):
        await asyncio.gather(palpite(), palpite())

    async with fabrica_com_conexoes_reais() as db:
        tentativas = (await db.execute(select(OtpCode.failed_attempts))).scalar_one()
    assert tentativas == 4, f"palpites simultâneos se sobrescreveram: contou {tentativas} de 4"


# ── 3. Enumeração por tempo ──────────────────────────────────────────────────

async def test_a_resposta_nao_espera_o_envio_do_email(client, user_factory, monkeypatch):
    await user_factory(email=EMAIL)
    enviado = asyncio.Event()

    async def _envio_lento(_email, _code):
        await asyncio.sleep(1.5)
        enviado.set()

    monkeypatch.setattr(email_service, "send_otp", _envio_lento)

    inicio = time.monotonic()
    resp = await client.post("/api/v1/auth/otp/request", json={"email": EMAIL})
    decorrido = time.monotonic() - inicio

    assert resp.status_code == 204
    assert decorrido < 0.75, (
        f"a resposta esperou o e-mail ({decorrido:.1f}s): conta existente demora, "
        "inexistente não — dá para enumerar pelo relógio"
    )
    await _esperar_envios()
    assert enviado.is_set(), "o e-mail tem de sair mesmo assim"


async def test_email_sem_conta_responde_igual_e_nao_grava_nada(client, db, caixa_de_saida):
    resp = await _pedir(client, "ninguem@example.com")

    assert resp.status_code == 204
    assert resp.content == b""
    assert caixa_de_saida == {}
    assert (await db.execute(select(OtpCode))).first() is None


async def test_falha_no_envio_nao_derruba_a_resposta(client, user_factory, monkeypatch, caplog):
    await user_factory(email=EMAIL)

    async def _quebrado(_email, _code):
        raise RuntimeError("SendGrid fora do ar")

    monkeypatch.setattr(email_service, "send_otp", _quebrado)

    resp = await _pedir(client)

    assert resp.status_code == 204
    assert "Falha ao enviar o código de acesso" in caplog.text
