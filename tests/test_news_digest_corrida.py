"""
Digest de notícias com duas réplicas: ninguém recebe e-mail em dobro.

A rodada inteira era UMA transação, com `flush` por usuário. Quando outra réplica
ganhava a corrida de um médico, o `rollback()` desfazia o registro de envio de
TODOS os anteriores — cujos e-mails já tinham saído — e a rodada seguinte mandava
tudo de novo. E o rollback expirava os objetos do ORM: o `user.email` do médico
seguinte quebrava, abortando a rodada (item 16 da varredura de 2026-09-18).

É pré-requisito para subir workers. Conexões REAIS de propósito: no harness de
conexão única o rollback da sessão principal desfaria também a linha gravada pela
"outra réplica", e o teste passaria sem provar nada.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.models.models import User
from app.models.news import DigestSend
from app.services import email_service, news_digest_service
from tests.test_news_feed import (
    CARDIO,
    CORE,
    NA_HORA_PADRAO,
    _escolhe,
    _liga_email,
    _publicado,
    _tema,
)


@pytest.fixture
def enviados(monkeypatch) -> list[str]:
    capturados: list[str] = []

    async def _fake(to_email, _nome, _artigos):
        capturados.append(to_email)

    monkeypatch.setattr(email_service, "send_news_digest", _fake)
    monkeypatch.setattr(news_digest_service.email_service, "send_news_digest", _fake)
    return capturados


async def test_perder_a_corrida_de_um_medico_nao_reenvia_os_outros(
    fabrica_com_conexoes_reais, enviados, monkeypatch
):
    async with fabrica_com_conexoes_reais() as db:
        ic = await _tema(db, "insuficiencia-cardiaca", [(CARDIO, CORE)])
        await _publicado(db, "Novo inibidor em ICFEr", [(ic, 0.95)])
        medicos = []
        for nome in ("a", "b", "c"):
            user = User(email=f"{nome}@hospital.com", role="beta_user", status=True,
                        onboarding_complete=True, name=f"Dr. {nome.upper()}")
            db.add(user)
            await db.flush()
            await _escolhe(db, user, [ic])
            await _liga_email(db, user)
            medicos.append(user)
        await db.commit()
        # A rodada percorre por `User.id`; o do meio é quem perde a corrida.
        ordenados = sorted(medicos, key=lambda u: u.id)
        primeiro, do_meio, ultimo = (u.email for u in ordenados)
        id_do_meio = ordenados[1].id

    hoje = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    original = news_digest_service._artigos_do_usuario

    async def _outra_replica_passa_na_frente(db, user_id, desde):
        artigos = await original(db, user_id, desde)
        if user_id == id_do_meio:
            # Entre a checagem "já enviei?" e a gravação, a outra réplica grava.
            async with fabrica_com_conexoes_reais() as outra:
                outra.add(DigestSend(user_id=user_id, data_ref=hoje, article_ids=[]))
                await outra.commit()
        return artigos

    monkeypatch.setattr(news_digest_service, "_artigos_do_usuario", _outra_replica_passa_na_frente)

    async with fabrica_com_conexoes_reais() as db:
        primeira = await news_digest_service.enviar_digests(db, agora=NA_HORA_PADRAO)
    monkeypatch.setattr(news_digest_service, "_artigos_do_usuario", original)
    async with fabrica_com_conexoes_reais() as db:
        segunda = await news_digest_service.enviar_digests(db, agora=NA_HORA_PADRAO)

    # A rodada não abortou: o médico DEPOIS da corrida recebeu o dele.
    assert primeira == {
        "enviados": 2, "sem_conteudo": 0, "ja_enviados": 1, "falhas": 0,
        # Todos os três estavam na faixa padrão: nenhum ficou de fora por hora.
        "fora_de_hora": 0,
    }, primeira
    assert sorted(enviados) == sorted([primeiro, ultimo])
    assert do_meio not in enviados, "este foi a outra réplica que enviou"

    # E a rodada seguinte não reenvia ninguém — o registro do primeiro sobreviveu
    # ao rollback da corrida do segundo.
    assert segunda["enviados"] == 0
    assert segunda["ja_enviados"] == 3
    assert enviados.count(primeiro) == 1, "o primeiro médico recebeu o mesmo digest duas vezes"

    async with fabrica_com_conexoes_reais() as db:
        assert await db.scalar(select(func.count()).select_from(DigestSend)) == 3
