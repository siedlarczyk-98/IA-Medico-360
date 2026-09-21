"""
Direitos do titular (LGPD): exclusão e exportação alcançam TODA tabela.

O QUE ISTO VEIO CONSERTAR
- `DELETE /auth/me` devolvia 500 para toda conta que passou pelo onboarding ou
  fez uma pergunta: `ForeignKeyViolationError` em `consent_logs_user_id_fkey` e
  em `audit_logs_interaction_id_fkey`. O direito de eliminação estava inoperante.
- `GET /auth/me/export` omitia pastas (com o contexto clínico), consentimentos,
  calculadoras e notícias.

Os dois defeitos têm a mesma raiz: alguém criou uma tabela ligada ao usuário e
nada obrigava a voltar à exclusão e à exportação. As travas abaixo são
estruturais — o cenário vem do metadata (`fabrica_do_titular`), e o destino de
cada tabela precisa estar declarado em `DESTINO_DOS_DADOS`.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.database import Base
from app.models.models import AuditLog, ConsentLog, InviteToken, OtpCode, User
from app.services.data_subject_service import ANONIMIZA, CASCATA, DESTINO_DOS_DADOS
from tests.conftest import auth_headers
from tests.fabrica_do_titular import (
    colunas_que_apontam_para_users,
    criar_usuario_completo,
    tabelas_ligadas_a_users,
)

# ── A invariante ─────────────────────────────────────────────────────────────

def test_toda_tabela_ligada_a_usuario_tem_destino_declarado():
    ligadas = set(tabelas_ligadas_a_users())
    declaradas = set(DESTINO_DOS_DADOS)

    assert not ligadas - declaradas, (
        f"Tabela ligada a `users` sem destino declarado: {sorted(ligadas - declaradas)}. "
        "Declare em `data_subject_service.DESTINO_DOS_DADOS` o que acontece com ela na "
        "exclusão de conta e na exportação — e trate os dois casos."
    )
    assert not declaradas - ligadas, (
        f"Destino declarado para tabela que não existe ou não chega em `users`: "
        f"{sorted(declaradas - ligadas)}"
    )


def test_quem_declara_cascata_tem_cascata_no_banco():
    """`cascata` é uma promessa sobre o schema; aqui ela é conferida."""
    ligadas = set(tabelas_ligadas_a_users()) | {"users"}
    for nome, (na_exclusao, _, _) in DESTINO_DOS_DADOS.items():
        if na_exclusao != CASCATA:
            continue
        tabela = Base.metadata.tables[nome]
        regras = {
            fk.ondelete for fk in tabela.foreign_keys
            if fk.column.table.fullname in ligadas and not fk.parent.nullable
        }
        assert regras == {"CASCADE"}, (
            f"{nome} declara `cascata`, mas suas chaves obrigatórias têm ondelete={regras}. "
            "Sem CASCADE no banco, o DELETE do usuário é recusado."
        )


def test_nao_exportar_exige_motivo():
    sem_motivo = [
        nome for nome, (_, chave, motivo) in DESTINO_DOS_DADOS.items() if chave is None and not motivo
    ]
    assert not sem_motivo, f"Tabela fora da exportação sem motivo escrito: {sem_motivo}"


# ── Exclusão ─────────────────────────────────────────────────────────────────

@pytest.fixture
async def titular_completo(db, user_factory):
    user = await user_factory(name="Dra. Titular Completa", email="titular@example.com")
    linhas = await criar_usuario_completo(db, user)
    # Guardam o e-mail do titular SEM chave estrangeira: o metadata não os
    # enxerga, então entram no cenário à mão.
    daqui_a_pouco = datetime.now(UTC) + timedelta(minutes=10)
    db.add(OtpCode(email=user.email, code="123456", expires_at=daqui_a_pouco))
    db.add(InviteToken(email=user.email, expires_at=daqui_a_pouco))
    await db.commit()
    return user, linhas


async def _linhas_do_usuario(db, user_id) -> dict[str, int]:
    contagem = {}
    for coluna in colunas_que_apontam_para_users():
        n = await db.scalar(select(func.count()).select_from(coluna.table).where(coluna == user_id))
        contagem[f"{coluna.table.fullname}.{coluna.name}"] = n
    return contagem


async def test_o_cenario_cobre_toda_tabela_que_aponta_para_users(db, titular_completo):
    """Se o construtor deixar uma tabela vazia, o teste de exclusão não prova nada sobre ela."""
    user, _ = titular_completo

    vazias = [onde for onde, n in (await _linhas_do_usuario(db, user.id)).items() if n == 0]

    assert not vazias, f"`criar_usuario_completo` não populou: {vazias}"


async def test_exclusao_de_conta_completa_devolve_204_e_nao_deixa_nada(client, db, titular_completo):
    user, linhas = titular_completo
    user_id, email = user.id, user.email
    consent_id = linhas["consent_logs"]["id"]
    audit_id = linhas["audit_logs"]["id"]

    resp = await client.request(
        "DELETE", "/api/v1/auth/me",
        json={"confirm_name": "Dra. Titular Completa"},
        headers=auth_headers(user),
    )

    assert resp.status_code == 204, resp.text

    sobras = {onde: n for onde, n in (await _linhas_do_usuario(db, user_id)).items() if n}
    assert not sobras, f"Linhas ainda ligadas ao titular depois da exclusão: {sobras}"
    assert await db.scalar(select(func.count()).select_from(User).where(User.id == user_id)) == 0

    # O que guarda o e-mail sem chave estrangeira também sai.
    assert await db.scalar(select(func.count()).select_from(OtpCode).where(OtpCode.email == email)) == 0
    assert await db.scalar(select(func.count()).select_from(InviteToken).where(InviteToken.email == email)) == 0

    # Anonimizado, não apagado: a linha existe e não identifica mais ninguém.
    for modelo, pk in ((ConsentLog, consent_id), (AuditLog, audit_id)):
        registro = (await db.execute(select(modelo).where(modelo.id == pk))).scalar_one()
        assert registro.user_id is None
        assert registro.ip_address is None
        assert registro.user_agent is None
    assert (await db.execute(select(AuditLog).where(AuditLog.id == audit_id))).scalar_one().interaction_id is None


async def test_exclusao_nao_toca_nos_dados_de_outro_medico(client, db, user_factory, titular_completo):
    user, _ = titular_completo
    outro = await user_factory(name="Dr. Outro", email="outro@example.com")
    await criar_usuario_completo(db, outro)
    antes = await _linhas_do_usuario(db, outro.id)

    resp = await client.request(
        "DELETE", "/api/v1/auth/me",
        json={"confirm_name": "Dra. Titular Completa"},
        headers=auth_headers(user),
    )

    assert resp.status_code == 204
    assert await _linhas_do_usuario(db, outro.id) == antes


# ── Exportação ───────────────────────────────────────────────────────────────

def _vazio(valor) -> bool:
    if isinstance(valor, dict):
        return all(_vazio(v) for v in valor.values())
    return not valor


async def test_exportacao_traz_toda_tabela_declarada_como_exportavel(client, titular_completo):
    user, _ = titular_completo

    resp = await client.get("/api/v1/auth/me/export", headers=auth_headers(user))

    assert resp.status_code == 200
    corpo = resp.json()
    chaves = {chave for _, chave, _ in DESTINO_DOS_DADOS.values() if chave}
    faltando = sorted(c for c in chaves if c not in corpo or _vazio(corpo[c]))
    assert not faltando, (
        f"O titular tem dados nestas seções e a exportação as trouxe vazias ou ausentes: {faltando}"
    )


async def test_exportacao_inclui_o_contexto_clinico_da_pasta(client, titular_completo):
    """O texto livre mais sensível da conta era justamente o que ficava de fora."""
    user, linhas = titular_completo

    corpo = (await client.get("/api/v1/auth/me/export", headers=auth_headers(user))).json()

    assert corpo["pastas"][0]["nome"] == linhas["folders"]["name"]
    assert "contexto_clinico" in corpo["pastas"][0]


def test_anonimizadas_nao_sao_apagadas_por_engano():
    assert DESTINO_DOS_DADOS["consent_logs"][0] == ANONIMIZA
    assert DESTINO_DOS_DADOS["audit_logs"][0] == ANONIMIZA
