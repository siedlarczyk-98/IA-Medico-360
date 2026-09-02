"""
Exclusão de conta (LGPD art. 18, VI).

A cascata vivia inline no endpoint `DELETE /auth/me` e não tinha teste nenhum —
25 linhas de SQL cru cuja ORDEM é o que impede o Postgres de recusar por chave
estrangeira, sem nada verificando essa ordem. Ao movê-la para o repositório ela
ficou testável sem HTTP; estes testes são a cobertura que faltava.

O caso que mais importa é `test_audit_log_sobrevive`: apagar a trilha de
auditoria destruiria a prova de que as ações aconteceram. A lei pede remover o
dado pessoal, não o registro de que houve atividade.
"""

import pytest
from sqlalchemy import select

from app.models.models import AuditLog, UserPreference
from app.models.models import User as UserModel
from app.repositories import auth_repository

pytestmark = pytest.mark.asyncio


async def test_apaga_o_usuario_e_o_que_pertence_a_ele(db, user_factory):
    user = await user_factory()
    db.add(UserPreference(user_id=user.id, ui_settings={"tema": "escuro"}))
    await db.flush()
    user_id = user.id

    await auth_repository.apagar_dados_do_usuario(db, user_id)
    await db.flush()

    assert await db.scalar(select(UserModel).where(UserModel.id == user_id)) is None
    assert await db.scalar(
        select(UserPreference).where(UserPreference.user_id == user_id)
    ) is None


async def test_audit_log_sobrevive_com_user_id_nulo(db, user_factory):
    """A trilha de auditoria é prova, não dado pessoal do titular.

    Apagá-la junto destruiria o registro de que as ações aconteceram. O que sai
    é o vínculo com a pessoa — o evento permanece.
    """
    user = await user_factory()
    db.add(AuditLog(user_id=user.id, action="invite.generate", entity_type="invite"))
    await db.flush()
    user_id = user.id

    await auth_repository.apagar_dados_do_usuario(db, user_id)
    await db.flush()

    registros = list(await db.scalars(select(AuditLog).where(AuditLog.action == "invite.generate")))
    assert len(registros) == 1, "O registro de auditoria não pode ser apagado"
    assert registros[0].user_id is None, "O vínculo com a pessoa é que precisa sair"


async def test_usuario_sem_nada_nao_quebra(db, user_factory):
    """Quem entrou pelo embed e nunca usou o produto não tem conversa nenhuma.

    As queries de coleta devolvem lista vazia, e o `IN ()` que sairia dali é o
    tipo de coisa que só falha em produção.
    """
    user = await user_factory()
    await db.flush()
    user_id = user.id

    await auth_repository.apagar_dados_do_usuario(db, user_id)
    await db.flush()

    assert await db.scalar(select(UserModel).where(UserModel.id == user_id)) is None


async def test_nao_toca_em_outros_usuarios(db, user_factory):
    """O filtro por `user_id` está em toda query — uma que faltasse apagaria a base."""
    alvo = await user_factory()
    vizinho = await user_factory()
    db.add(UserPreference(user_id=vizinho.id, ui_settings={"tema": "claro"}))
    await db.flush()
    vizinho_id = vizinho.id

    await auth_repository.apagar_dados_do_usuario(db, alvo.id)
    await db.flush()

    assert await db.scalar(select(UserModel).where(UserModel.id == vizinho_id)) is not None
    assert await db.scalar(
        select(UserPreference).where(UserPreference.user_id == vizinho_id)
    ) is not None
