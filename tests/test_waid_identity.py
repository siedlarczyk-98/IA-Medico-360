"""
Identidade verificável no embed — a troca do token da Waid.

O QUE ISTO VEIO CONSERTAR
`POST /auth/embed/token` recebia `{email}` e devolvia sessão. As duas checagens
não provavam que quem chamava era o dono do e-mail: o header `Origin` é forjável
server-side, e a validação de matrícula prova que o e-mail É de um membro, não
que o chamador É ele. Um curl com o Origin certo e o e-mail de um colega
devolvia o JWT da conta dele — e a conta dá acesso às conversas clínicas.

Agora a Waid emite um token opaco, de uso único, que só chega a quem está de
fato dentro do iframe logado. O e-mail passou a ser RESULTADO da verificação.

O teste mais importante deste arquivo é `test_erro_de_credencial_nao_manda_pedir
_outro_token`: confundir "o token queimou" com "nossa credencial está errada" é
o que produz, de um lado, médico preso numa tela que um retry resolveria, e do
outro, laço infinito de pedidos.
"""

import pytest
from sqlalchemy import select, text

from app.models.models import AuditLog
from app.models.models import User as UserModel
from app.services import auth_service
from app.services.integracoes import curseduca_service
from tests.conftest import auth_headers  # noqa: F401  (mantém o estilo dos demais)

pytestmark = pytest.mark.asyncio

ORIGEM = "https://adminportalmedico360.curseduca.pro"
IDENTIDADE = curseduca_service.IdentidadeWaid(
    uuid="6f1b0f2e-9c3a-4c2e-9c1a-1f0b2d3e4f5a",
    nome="João da Silva",
    email="joao@empresa.com",
)


class RespostaFake:
    def __init__(self, status_code: int, corpo: dict | None = None, texto: str = ""):
        self.status_code = status_code
        self._corpo = corpo or {}
        self.text = texto

    def json(self):
        return self._corpo


def _responde(monkeypatch, resposta):
    """Finge a resposta HTTP da Waid, sem tocar no disjuntor."""
    class ClienteFake:
        async def post(self, *a, **k):
            return resposta

    monkeypatch.setattr(curseduca_service, "get_client", lambda: ClienteFake())


def _credenciais_ok(monkeypatch):
    monkeypatch.setattr(
        curseduca_service,
        "_credenciais",
        lambda: ("https://prof.curseduca.pro", "chave", "bearer"),
    )


# ── A troca do token ─────────────────────────────────────────────────────────

async def test_troca_devolve_a_identidade(monkeypatch):
    _credenciais_ok(monkeypatch)
    _responde(monkeypatch, RespostaFake(200, {
        "uuid": IDENTIDADE.uuid, "name": "João da Silva", "email": "Joao@Empresa.com",
    }))

    identidade = await curseduca_service.trocar_token_de_identidade("9f2c1a")

    assert identidade.uuid == IDENTIDADE.uuid
    assert identidade.nome == "João da Silva"
    assert identidade.email == "joao@empresa.com", "e-mail deve vir normalizado"


@pytest.mark.parametrize(
    "status_http,codigo",
    [(400, "token_invalido"), (410, "token_expirado")],
)
async def test_token_queimado_ou_expirado_pede_outro(monkeypatch, status_http, codigo):
    """Acontece no uso NORMAL: recarregar a página queima o token.

    O cliente resolve sozinho pedindo outro pelo mesmo evento — por isso é uma
    exceção própria, e não a mesma de "a integração está quebrada".
    """
    _credenciais_ok(monkeypatch)
    _responde(monkeypatch, RespostaFake(status_http))

    with pytest.raises(curseduca_service.TokenDeIdentidadeInvalido) as exc:
        await curseduca_service.trocar_token_de_identidade("qualquer")

    assert exc.value.codigo == codigo


@pytest.mark.parametrize("status_http", [401, 403, 500])
async def test_erro_de_credencial_nao_manda_pedir_outro_token(monkeypatch, status_http):
    """401/403 são configuração NOSSA — 403 é a permissão do endpoint, que a doc
    da Waid diz ser liberada à parte. Pedir outro token não conserta nada, e
    tratar como token queimado viraria laço infinito."""
    _credenciais_ok(monkeypatch)
    _responde(monkeypatch, RespostaFake(status_http, texto="nope"))

    with pytest.raises(curseduca_service.CurseducaNotConfigured):
        await curseduca_service.trocar_token_de_identidade("qualquer")


async def test_resposta_sem_uuid_e_problema_de_contrato(monkeypatch):
    """Formato inesperado não é culpa do token — mandar pedir outro entraria em laço."""
    _credenciais_ok(monkeypatch)
    _responde(monkeypatch, RespostaFake(200, {"name": "Sem uuid"}))

    with pytest.raises(curseduca_service.CurseducaNotConfigured):
        await curseduca_service.trocar_token_de_identidade("qualquer")


async def test_disjuntor_aberto_nao_chama_a_waid(monkeypatch):
    from app.core import circuit_breaker
    from app.core.circuit_breaker import Estado

    _credenciais_ok(monkeypatch)
    chamou = []

    class ClienteFake:
        async def post(self, *a, **k):
            chamou.append(1)
            return RespostaFake(200)

    monkeypatch.setattr(curseduca_service, "get_client", lambda: ClienteFake())
    circuit_breaker.curseduca._estado = Estado.ABERTO
    circuit_breaker.curseduca._aberto_em = __import__("time").monotonic()
    try:
        with pytest.raises(curseduca_service.CurseducaNotConfigured):
            await curseduca_service.trocar_token_de_identidade("x")
        assert not chamou
    finally:
        circuit_breaker.reset_todos()


# ── Resolução do usuário ─────────────────────────────────────────────────────

async def test_uuid_tem_precedencia_sobre_email(db, user_factory):
    """Se o e-mail mudou na Waid, é o uuid que reencontra a mesma pessoa."""
    user = await user_factory(email="antigo@empresa.com")
    user.waid_uuid = IDENTIDADE.uuid
    await db.flush()

    achado, criado = await auth_service.get_or_create_por_identidade_waid(db, IDENTIDADE)

    assert criado is False
    assert achado.id == user.id


async def test_backfill_grava_o_uuid_no_primeiro_login(db, user_factory):
    """A base existente migra sozinha, um login por vez — não há script."""
    user = await user_factory(email=IDENTIDADE.email)
    assert user.waid_uuid is None
    await db.flush()

    achado, criado = await auth_service.get_or_create_por_identidade_waid(db, IDENTIDADE)

    assert criado is False
    assert achado.id == user.id
    assert achado.waid_uuid == IDENTIDADE.uuid


async def test_cria_quando_nao_existe(db):
    achado, criado = await auth_service.get_or_create_por_identidade_waid(db, IDENTIDADE)

    assert criado is True
    assert achado.waid_uuid == IDENTIDADE.uuid
    assert achado.email == IDENTIDADE.email
    assert achado.name == "João da Silva"


async def test_email_alterado_na_waid_e_sincronizado(db, user_factory):
    user = await user_factory(email="antigo@empresa.com")
    user.waid_uuid = IDENTIDADE.uuid
    await db.flush()

    anterior = await auth_service.sincronizar_email_da_waid(db, user, IDENTIDADE)

    assert anterior == "antigo@empresa.com"
    assert user.email == IDENTIDADE.email


async def test_email_ja_usado_por_outra_conta_nao_derruba_o_login(db, user_factory):
    """Situação real. Barrar o login não a resolve — só tranca o médico fora."""
    outro = await user_factory(email=IDENTIDADE.email)
    user = await user_factory(email="antigo@empresa.com")
    user.waid_uuid = IDENTIDADE.uuid
    await db.flush()

    anterior = await auth_service.sincronizar_email_da_waid(db, user, IDENTIDADE)

    assert anterior is None
    assert user.email == "antigo@empresa.com"
    assert outro.email == IDENTIDADE.email


# ── Enriquecimento: fail-open ────────────────────────────────────────────────

async def test_grupos_indisponiveis_nao_barram_o_login(monkeypatch):
    """A diferença de política que este trabalho introduziu.

    Antes, instabilidade na API de membros era fail-closed e deixava TODO MUNDO
    de fora. Agora ela custa uma especialidade não preenchida, que a próxima
    entrada resolve — porque o portão passou a ser a troca do token.
    """
    async def explode(*a, **k):
        raise curseduca_service.CurseducaNotConfigured("api fora do ar")

    monkeypatch.setattr(curseduca_service, "_fetch_member", explode)
    monkeypatch.setattr(curseduca_service, "_credenciais",
                        lambda: ("https://x", "chave", "bearer"))

    async def sem_cache(_):
        return None

    async def nao_grava(*a, **k):
        return None

    from app.services import cache_service
    monkeypatch.setattr(cache_service, "get_json", sem_cache)
    monkeypatch.setattr(cache_service, "set_json", nao_grava)

    assert await curseduca_service.buscar_membro_para_enriquecer("x@y.com") is None


# ── O endpoint ───────────────────────────────────────────────────────────────

async def test_endpoint_por_token_emite_sessao_e_audita(client, db, monkeypatch):
    async def troca(_token):
        return IDENTIDADE

    monkeypatch.setattr(curseduca_service, "trocar_token_de_identidade", troca)

    async def sem_grupos(_email):
        return None

    monkeypatch.setattr(curseduca_service, "buscar_membro_para_enriquecer", sem_grupos)

    resp = await client.post(
        "/api/v1/auth/embed/token",
        json={"token": "9f2c1a"},
        headers={"Origin": ORIGEM},
    )

    assert resp.status_code == 200
    assert resp.json()["access_token"]

    criado = await db.scalar(select(UserModel).where(UserModel.waid_uuid == IDENTIDADE.uuid))
    assert criado is not None

    registros = list(await db.scalars(select(AuditLog).where(AuditLog.action == "auth.embed")))
    assert len(registros) == 1, "toda emissão por embed precisa deixar rastro"
    assert registros[0].metadata_["via"] == "token"


async def test_endpoint_recusa_token_e_email_juntos(client):
    resp = await client.post(
        "/api/v1/auth/embed/token",
        json={"token": "x", "email": "a@b.com"},
        headers={"Origin": ORIGEM},
    )
    assert resp.status_code == 422


async def test_endpoint_recusa_corpo_vazio(client):
    resp = await client.post(
        "/api/v1/auth/embed/token", json={}, headers={"Origin": ORIGEM}
    )
    assert resp.status_code == 422


async def test_token_queimado_vira_401_com_codigo(client, monkeypatch):
    """O front precisa distinguir "pede outro" de "desiste" — daí o código."""
    async def queimado(_token):
        raise curseduca_service.TokenDeIdentidadeInvalido("token_expirado")

    monkeypatch.setattr(curseduca_service, "trocar_token_de_identidade", queimado)

    resp = await client.post(
        "/api/v1/auth/embed/token", json={"token": "x"}, headers={"Origin": ORIGEM}
    )

    assert resp.status_code == 401
    assert resp.json()["detail"]["codigo"] == "token_expirado"


async def test_falha_de_credencial_vira_503(client, monkeypatch):
    async def quebrado(_token):
        raise curseduca_service.CurseducaNotConfigured("403 sem permissão")

    monkeypatch.setattr(curseduca_service, "trocar_token_de_identidade", quebrado)

    resp = await client.post(
        "/api/v1/auth/embed/token", json={"token": "x"}, headers={"Origin": ORIGEM}
    )

    assert resp.status_code == 503
    assert "403" not in resp.text, "não vazar detalhe de credencial para o cliente"


async def test_caminho_por_email_desligado_recusa(client, monkeypatch):
    """O estado da Fase 4: com o fallback desligado, só o token entra."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "embed_email_fallback_enabled", False)

    resp = await client.post(
        "/api/v1/auth/embed/token",
        json={"email": "alguem@empresa.com"},
        headers={"Origin": ORIGEM},
    )

    assert resp.status_code == 400


# ── Identidade sem sessão (landing pages) ────────────────────────────────────

async def test_identidade_sem_sessao_nao_cria_usuario(client, db, monkeypatch):
    """As LPs são PÚBLICAS e só querem pré-preencher um formulário.

    Criar conta a partir de um formulário de captação seria inventar
    consentimento que ninguém deu — e quem abre uma LP pode nem ser cliente.
    """
    async def troca(_token):
        return IDENTIDADE

    monkeypatch.setattr(curseduca_service, "trocar_token_de_identidade", troca)

    antes = (await db.execute(text("SELECT count(*) FROM users"))).scalar_one()
    resp = await client.post(
        "/api/v1/auth/embed/identidade", json={"token": "9f2c1a"},
        headers={"Origin": ORIGEM},
    )
    depois = (await db.execute(text("SELECT count(*) FROM users"))).scalar_one()

    assert resp.status_code == 200
    assert resp.json() == {"nome": "João da Silva", "email": IDENTIDADE.email}
    assert depois == antes, "não pode criar conta"


async def test_identidade_sem_sessao_nao_emite_token(client, monkeypatch):
    """Nem sessão: a resposta não pode trazer nada que sirva de credencial."""
    async def troca(_token):
        return IDENTIDADE

    monkeypatch.setattr(curseduca_service, "trocar_token_de_identidade", troca)

    resp = await client.post(
        "/api/v1/auth/embed/identidade", json={"token": "x"}, headers={"Origin": ORIGEM}
    )

    assert "access_token" not in resp.json()
    assert "set-cookie" not in {k.lower() for k in resp.headers}


async def test_identidade_sem_sessao_exige_token_valido(client, monkeypatch):
    async def queimado(_token):
        raise curseduca_service.TokenDeIdentidadeInvalido("token_expirado")

    monkeypatch.setattr(curseduca_service, "trocar_token_de_identidade", queimado)

    resp = await client.post(
        "/api/v1/auth/embed/identidade", json={"token": "x"}, headers={"Origin": ORIGEM}
    )

    assert resp.status_code == 401
    assert resp.json()["detail"]["codigo"] == "token_expirado"


async def test_identidade_sem_sessao_recusa_email(client):
    """O expurgo do e-mail vale aqui também: só token."""
    resp = await client.post(
        "/api/v1/auth/embed/identidade",
        json={"email": "alguem@empresa.com"},
        headers={"Origin": ORIGEM},
    )
    assert resp.status_code == 400


async def test_caminho_por_email_ainda_funciona_se_religado(client, db, monkeypatch):
    """A escada de emergência precisa funcionar quando for puxada.

    O caminho por e-mail está DESLIGADO por padrão desde 02/09/2026 — é isso
    que fecha a vulnerabilidade. Mas continua religável por variável de
    ambiente enquanto os seis apps não estiverem verificados em produção.

    Uma saída de emergência que ninguém testa não é saída. Este teste existe
    para que, no dia em que alguém precisar religar às pressas, o caminho
    esteja íntegro — e some junto com o ramo, quando a trava de startup entrar.
    """
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "embed_email_fallback_enabled", True)

    async def membro_valido(_email):
        return {"email": "legado@empresa.com", "groups": []}

    monkeypatch.setattr(curseduca_service, "verify_active_member", membro_valido)

    resp = await client.post(
        "/api/v1/auth/embed/token",
        json={"email": "legado@empresa.com"},
        headers={"Origin": ORIGEM},
    )

    assert resp.status_code == 200
    assert resp.json()["access_token"]

    # E fica registrado como legado, para o log ser a evidência de que alguém
    # ainda depende dele.
    registros = list(await db.scalars(
        select(AuditLog).where(AuditLog.action == "auth.embed")
    ))
    assert any(r.metadata_["via"] == "email" for r in registros)
