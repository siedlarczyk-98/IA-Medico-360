"""
Testes do próprio harness (item 1.1 do plano de prontidão).

Se algum destes falhar, todos os testes de integração ficam sem valor: eles
estariam rodando contra o banco errado, sem isolamento entre testes, ou com
liberdade para chamar serviços externos de verdade.
"""

import pytest
from sqlalchemy import select

from app.models.models import User
from tests.conftest import TEST_DATABASE_URL, auth_headers


async def test_banco_de_teste_esta_isolado():
    """A trava do conftest apontou a aplicação para o banco de teste."""
    from app.core.config import get_settings

    assert get_settings().database_url == TEST_DATABASE_URL
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1]
    assert "rlwy.net" not in TEST_DATABASE_URL, "URL de produção vazou para os testes"


async def test_app_responde(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


async def test_usuario_autenticado_acessa_me(client, user):
    resp = await client.get("/api/v1/auth/me", headers=auth_headers(user))
    assert resp.status_code == 200
    assert resp.json()["email"] == user.email


async def test_sem_token_recebe_401(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_token_malformado_recebe_401(client):
    """`sub` que não é UUID precisa dar 401, não 500 (regressão de app/api/deps.py)."""
    import jwt as pyjwt

    from app.core.config import get_settings

    settings = get_settings()
    token = pyjwt.encode({"sub": "nao-e-uuid"}, settings.jwt_secret_key, algorithm="HS256")
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_fixture_admin_tem_papel(admin):
    assert admin.role == "admin"


# ── Isolamento entre testes ──────────────────────────────────────────────
# O par abaixo prova que o rollback funciona: o primeiro escreve, o segundo
# não pode enxergar. Se o isolamento quebrar, o segundo falha.

MARCADOR = "isolamento@example.com"


async def test_isolamento_parte1_escreve(db, user_factory):
    await user_factory(email=MARCADOR)
    achado = await db.execute(select(User).where(User.email == MARCADOR))
    assert achado.scalar_one_or_none() is not None


async def test_isolamento_parte2_nao_enxerga(db):
    achado = await db.execute(select(User).where(User.email == MARCADOR))
    assert achado.scalar_one_or_none() is None, (
        "Dado do teste anterior sobreviveu — o rollback da fixture `db` não está funcionando."
    )


# ── Rollback da app não destrói o cenário do teste ──────────────────────
# Sem `join_transaction_mode="create_savepoint"`, o `rollback()` de QUALQUER
# sessão presa a `db_conn` revertia a transação externa do harness, e os dados
# preparados pelo teste sumiam junto. Os caminhos de recuperação de erro da app
# (stream, `/query`, digest, cache semântico) eram intestáveis por isso.

async def test_rollback_na_sessao_do_teste_preserva_o_cenario(db, user_factory):
    """O caso de `get_db`: a app chama `db.rollback()` na mesma sessão do teste."""
    await user_factory(email="cenario@example.com")

    db.add(User(email="descartado@example.com", role="beta_user", status=True))
    await db.flush()
    await db.rollback()

    emails = set((await db.execute(select(User.email))).scalars())
    # Literal, e não `usuario.email`: o rollback expira os objetos da sessão.
    assert "cenario@example.com" in emails, "o rollback da app apagou o que o teste preparou"
    assert "descartado@example.com" not in emails


async def test_rollback_em_outra_sessao_preserva_o_cenario(db, user_factory, fabrica_de_sessao):
    """O caso de `async_session_factory`: o serviço abre sessão própria e reverte."""
    await user_factory(email="cenario2@example.com")

    async with fabrica_de_sessao() as outra:
        outra.add(User(email="descartado2@example.com", role="beta_user", status=True))
        await outra.flush()
        await outra.rollback()

    emails = set((await db.execute(select(User.email))).scalars())
    assert "cenario2@example.com" in emails
    assert "descartado2@example.com" not in emails


async def test_commit_da_app_nao_escapa_do_isolamento_parte1(db, user_factory):
    """`commit()` só libera o savepoint — o par abaixo prova que nada sobrevive."""
    await user_factory(email="comitado@example.com")
    await db.commit()


async def test_commit_da_app_nao_escapa_do_isolamento_parte2(db):
    achado = await db.execute(select(User).where(User.email == "comitado@example.com"))
    assert achado.scalar_one_or_none() is None, "um commit atravessou a transação do harness"


# ── Conexões reais (fixture opcional) ───────────────────────────────────

async def test_conexoes_reais_parte1_duas_sessoes_se_enxergam(fabrica_com_conexoes_reais):
    """Commit real em uma conexão é visível na outra — o que `db_conn` não permite."""
    async with fabrica_com_conexoes_reais() as a, fabrica_com_conexoes_reais() as b:
        a.add(User(email="real@example.com", role="beta_user", status=True))
        await a.commit()

        achado = await b.execute(select(User).where(User.email == "real@example.com"))
        assert achado.scalar_one_or_none() is not None


async def test_conexoes_reais_parte2_truncate_limpou(db):
    achado = await db.execute(select(User).where(User.email == "real@example.com"))
    assert achado.scalar_one_or_none() is None, (
        "O TRUNCATE de `fabrica_com_conexoes_reais` não limpou — dado comitado de "
        "verdade vazou para o resto da suíte."
    )


async def test_conexoes_reais_esgotam_o_pool_em_vez_de_pendurar(fabrica_com_conexoes_reais):
    """Terceira sessão com as duas conexões presas: erro em ~5s, não suíte travada."""
    from sqlalchemy import text
    from sqlalchemy.exc import TimeoutError as PoolTimeout

    async with fabrica_com_conexoes_reais() as a, fabrica_com_conexoes_reais() as b:
        await a.execute(text("SELECT 1"))
        await b.execute(text("SELECT 1"))
        async with fabrica_com_conexoes_reais() as c:
            with pytest.raises(PoolTimeout):
                await c.execute(text("SELECT 1"))


# ── Guarda de rede ───────────────────────────────────────────────────────

async def test_chamada_externa_e_bloqueada(bloqueia_rede_externa):
    """
    A guarda levanta `VazamentoDeRede`, que NÃO é subclasse de `Exception`.

    Isso é o que impede um `except Exception` do código sob teste de transformar
    a violação em "provedor falhou" e deixar o teste passar pelo caminho de
    contingência — eram 23 testes assim antes da correção.
    """
    import httpx

    from tests.conftest import VazamentoDeRede

    assert not issubclass(VazamentoDeRede, Exception), (
        "VazamentoDeRede precisa herdar de BaseException, senão `except Exception` "
        "a engole e a guarda volta a ser contornável."
    )

    with pytest.raises(VazamentoDeRede, match="chamada HTTP externa"):
        async with httpx.AsyncClient() as c:
            await c.get("https://api.anthropic.com/v1/messages")

    # Este teste tentou sair para a rede de PROPÓSITO e capturou a exceção. Sem
    # limpar o registro, a checagem de encerramento da fixture reprovaria aqui.
    bloqueia_rede_externa.clear()


async def test_guarda_registra_a_tentativa_mesmo_engolida(bloqueia_rede_externa):
    """
    Segunda camada: engolir a exceção não apaga o rastro.

    Um `except BaseException` — ou um `asyncio.gather` que empacota a exceção —
    ainda deixaria a chamada passar despercebida se a guarda só levantasse. Por
    isso toda tentativa é registrada, e o registro é conferido no encerramento.
    Aqui provamos o registro; a reprovação em si é o teardown da fixture, que a
    suíte inteira exercita.
    """
    import httpx

    try:
        async with httpx.AsyncClient() as c:
            await c.get("https://pharmadb.example.com/v1/bula")
    except BaseException:  # noqa: BLE001 — engolir é exatamente o caso sob teste
        pass

    assert bloqueia_rede_externa == ["GET https://pharmadb.example.com/v1/bula"], (
        "a guarda precisa REGISTRAR a tentativa, não apenas levantar — senão um "
        "`except BaseException` volta a esconder o vazamento."
    )

    bloqueia_rede_externa.clear()  # tentativa deliberada; não deve reprovar o teardown


@pytest.mark.rede_real
async def test_marca_rede_real_desarma_a_guarda():
    """A marca existe para o caso raro de teste de contrato contra o serviço real."""
    import httpx

    assert httpx.AsyncHTTPTransport.handle_async_request.__name__ != "_proibido"


async def test_cliente_de_teste_nao_e_bloqueado_pela_guarda(client):
    """
    A guarda mira o transporte de rede, não o `AsyncClient`: o cliente de teste
    também é um AsyncClient, só que sobre ASGITransport. Se alguém voltar a
    patchar a classe inteira, este teste quebra junto com todos os de integração.
    """
    assert (await client.get("/api/v1/health")).status_code == 200
