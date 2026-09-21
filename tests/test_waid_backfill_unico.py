"""
O backfill de `waid_uuid` é ÚNICO — a vinculação não se reescreve.

O docstring de `get_or_create_por_identidade_waid`, o log da função e a migration
`008_waid_uuid` sempre afirmaram isso ("o backfill é preguiçoso, um login por
vez"). O código não cumpria: faltava a guarda, e toda vez que a busca por uuid
falhava e a por e-mail acertava, a vinculação era sobrescrita em silêncio —
enquanto o log seguia dizendo "primeiro login".

Não precisa de atacante: basta o LMS re-provisionar a conta de um médico com uuid
novo para o mesmo e-mail. Com duas identidades no mesmo e-mail, a vinculação
alternava a cada login.

`test_waid_identity.py::test_backfill_grava_o_uuid_no_primeiro_login` cobre o
caso feliz — ele assere `waid_uuid is None` ANTES de chamar, que é exatamente a
situação em que a guarda ausente não fazia diferença. Estes cobrem o resto.
"""

import pytest

from app.services import auth_service
from app.services.integracoes import curseduca_service

pytestmark = pytest.mark.asyncio

UUID_ORIGINAL = "6f1b0f2e-9c3a-4c2e-9c1a-1f0b2d3e4f5a"
UUID_NOVO = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _identidade(uuid: str, email: str, nome: str = "Dra. Teste"):
    return curseduca_service.IdentidadeWaid(uuid=uuid, nome=nome, email=email)


async def test_conta_com_uuid_divergente_nao_e_sobrescrita(db, user_factory):
    """
    O caminho real: a conta já tem um vínculo, e chega uma identidade nova com o
    mesmo e-mail. O vínculo existente tem de permanecer.
    """
    user = await user_factory(email="medico@empresa.com")
    user.waid_uuid = UUID_ORIGINAL
    await db.flush()

    # INVERTIDO em 2026-09-21. Este teste exigia `achado.id == user.id`: a conta
    # existente era DEVOLVIDA a quem chegava com outra identidade. O vínculo
    # ficava intacto, e era só isso que se conferia — mas o desconhecido entrava
    # na conta e lia o histórico clínico dela. Agora não há conta devolvida.
    user_id = user.id
    with pytest.raises(auth_service.IdentidadeDivergente) as recusa:
        await auth_service.get_or_create_por_identidade_waid(
            db, _identidade(UUID_NOVO, "medico@empresa.com")
        )

    assert recusa.value.user_id == user_id
    await db.refresh(user)
    assert user.waid_uuid == UUID_ORIGINAL, (
        "A vinculação foi sobrescrita — o backfill tem de ser único"
    )


async def test_backfill_ainda_preenche_quando_esta_vazio(db, user_factory):
    """
    O contraponto: a guarda não pode matar o backfill legítimo, que é a razão de
    a busca por e-mail existir nesta função.
    """
    user = await user_factory(email="sem-uuid@empresa.com")
    assert user.waid_uuid is None
    await db.flush()

    achado, criado = await auth_service.get_or_create_por_identidade_waid(
        db, _identidade(UUID_NOVO, "sem-uuid@empresa.com")
    )

    assert criado is False
    assert achado.id == user.id
    assert achado.waid_uuid == UUID_NOVO


async def test_login_repetido_e_estavel(db, user_factory):
    """
    Dois logins seguidos com a MESMA identidade não podem produzir estados
    diferentes — era o sintoma do vínculo alternando.
    """
    await user_factory(email="estavel@empresa.com")
    identidade = _identidade(UUID_ORIGINAL, "estavel@empresa.com")

    primeiro, _ = await auth_service.get_or_create_por_identidade_waid(db, identidade)
    segundo, _ = await auth_service.get_or_create_por_identidade_waid(db, identidade)

    assert primeiro.id == segundo.id
    assert segundo.waid_uuid == UUID_ORIGINAL


async def test_alternancia_entre_duas_identidades_nao_acontece(db, user_factory):
    """
    O sintoma descrito na análise, reproduzido: dois logins alternados com uuids
    diferentes no mesmo e-mail. Antes da guarda, `waid_uuid` trocava a cada
    chamada. Agora o primeiro vínculo vence e permanece — e, desde 2026-09-21,
    a identidade nova nem recebe a conta: é recusada toda vez.
    """
    await user_factory(email="alterna@empresa.com")

    primeiro, _ = await auth_service.get_or_create_por_identidade_waid(
        db, _identidade(UUID_ORIGINAL, "alterna@empresa.com")
    )
    assert primeiro.waid_uuid == UUID_ORIGINAL

    for _ in range(3):
        with pytest.raises(auth_service.IdentidadeDivergente):
            await auth_service.get_or_create_por_identidade_waid(
                db, _identidade(UUID_NOVO, "alterna@empresa.com")
            )
        await db.refresh(primeiro)
        assert primeiro.waid_uuid == UUID_ORIGINAL, "A vinculação alternou entre identidades"

    # E o dono legítimo continua entrando normalmente.
    de_novo, _ = await auth_service.get_or_create_por_identidade_waid(
        db, _identidade(UUID_ORIGINAL, "alterna@empresa.com")
    )
    assert de_novo.id == primeiro.id
