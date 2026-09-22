"""
Periodicidade do digest, de ponta a ponta.

A agenda pura já é coberta em `test_news_digest_agenda.py`. Aqui é o que só
aparece com banco e HTTP: cada médico sai na SUA faixa, o semanal olha a semana
inteira, e salvar a preferência sem mandar a agenda não apaga a que a pessoa
escolheu.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.models import UserPreference
from app.services import news_digest_service
from tests.test_news_feed import (
    CARDIO,
    CORE,
    _escolhe,
    _liga_email,
    _publicado,
    _tema,
)

pytestmark = pytest.mark.asyncio

MANHA = datetime(2026, 9, 21, 10, tzinfo=UTC)   # segunda, 7h BRT
TARDE = datetime(2026, 9, 21, 16, tzinfo=UTC)   # segunda, 13h BRT
NOITE = datetime(2026, 9, 21, 22, tzinfo=UTC)   # segunda, 19h BRT
QUARTA_MANHA = datetime(2026, 9, 23, 10, tzinfo=UTC)


async def _agenda(db, user, **agenda):
    """Grava a agenda do usuário, preservando o opt-in de e-mail."""
    prefs = await db.scalar(select(UserPreference).where(UserPreference.user_id == user.id))
    atuais = dict(prefs.notification_prefs or {})
    atuais["news"] = {**atuais.get("news", {}), "agenda": agenda}
    prefs.notification_prefs = atuais
    await db.flush()


@pytest.fixture
def enviados(monkeypatch) -> list:
    capturados = []

    async def _fake(to_email, _nome, artigos):
        capturados.append((to_email, artigos))

    from app.services import email_service

    monkeypatch.setattr(email_service, "send_news_digest", _fake)
    monkeypatch.setattr(news_digest_service.email_service, "send_news_digest", _fake)
    return capturados


async def _publicado_em(db, titulo, tema, quando):
    """`_publicado` com `visible_at` amarrado ao relógio DO TESTE.

    O helper original grava `visible_at = agora_real - 1h`. Como aqui o relógio
    é fixo, isso faria o teste depender da data em que ele roda: hoje passa
    porque a data real coincide com a do teste, amanhã não. Fixar o instante é
    o que mantém o teste dizendo a mesma coisa daqui a um ano.
    """
    art = await _publicado(db, titulo, [(tema, 0.95)])
    art.visible_at = quando
    await db.flush()
    return art


async def _medico_pronto(db, user_factory, email: str):
    """Usuário com opt-in, tema escolhido e um artigo casando."""
    user = await user_factory(email=email)
    user.specialty = CARDIO
    await db.flush()
    await _liga_email(db, user)
    return user


# ── cada um na sua faixa ─────────────────────────────────────────────────────

async def test_cada_medico_recebe_na_faixa_que_escolheu(
    db, user_factory, enviados
):
    """O ponto do item: três médicos, três faixas, três rodadas diferentes."""
    tema = await _tema(db, "cardio", [(CARDIO, CORE)])
    await _publicado_em(db, "Novo escore de risco em IC", tema, MANHA - timedelta(hours=1))

    cedo = await _medico_pronto(db, user_factory, "cedo@example.com")
    meio = await _medico_pronto(db, user_factory, "meio@example.com")
    tarde = await _medico_pronto(db, user_factory, "tarde@example.com")
    for u in (cedo, meio, tarde):
        await _escolhe(db, u, [tema])
    await _agenda(db, cedo, frequencia="diario", faixa="manha")
    await _agenda(db, meio, frequencia="diario", faixa="tarde")
    await _agenda(db, tarde, frequencia="diario", faixa="noite")

    await news_digest_service.enviar_digests(db, agora=MANHA)
    assert [e for e, _ in enviados] == ["cedo@example.com"]

    await news_digest_service.enviar_digests(db, agora=TARDE)
    assert [e for e, _ in enviados] == ["cedo@example.com", "meio@example.com"]

    await news_digest_service.enviar_digests(db, agora=NOITE)
    assert [e for e, _ in enviados] == [
        "cedo@example.com", "meio@example.com", "tarde@example.com",
    ]


async def test_fora_da_faixa_ninguem_recebe_e_o_resumo_diz_isso(
    db, user, enviados
):
    """Uma rodada às 3h UTC não é a hora de ninguém — e o resumo precisa
    distinguir isso de "a tarefa morreu"."""
    tema = await _tema(db, "cardio", [(CARDIO, CORE)])
    await _publicado_em(db, "Artigo qualquer", tema, MANHA - timedelta(hours=1))
    user.specialty = CARDIO
    await db.flush()
    await _liga_email(db, user)
    await _escolhe(db, user, [tema])

    resumo = await news_digest_service.enviar_digests(
        db, agora=datetime(2026, 9, 21, 3, tzinfo=UTC)
    )

    assert enviados == []
    assert resumo["enviados"] == 0
    assert resumo["fora_de_hora"] == 1


async def test_quem_nunca_escolheu_continua_no_padrao(db, user, enviados):
    """Ninguém muda de horário por efeito colateral de um deploy nosso: sem
    agenda gravada, o comportamento é o de antes — diário, de manhã."""
    tema = await _tema(db, "cardio", [(CARDIO, CORE)])
    await _publicado_em(db, "Artigo qualquer", tema, MANHA - timedelta(hours=1))
    user.specialty = CARDIO
    await db.flush()
    await _liga_email(db, user)
    await _escolhe(db, user, [tema])
    # nenhuma agenda gravada

    await news_digest_service.enviar_digests(db, agora=MANHA)
    assert len(enviados) == 1


# ── semanal ──────────────────────────────────────────────────────────────────

async def test_semanal_nao_sai_nos_outros_dias(db, user, enviados):
    tema = await _tema(db, "cardio", [(CARDIO, CORE)])
    await _publicado_em(db, "Artigo qualquer", tema, MANHA - timedelta(hours=1))
    user.specialty = CARDIO
    await db.flush()
    await _liga_email(db, user)
    await _escolhe(db, user, [tema])
    await _agenda(db, user, frequencia="semanal", dia_semana=2, faixa="manha")

    # Segunda: não é o dia.
    await news_digest_service.enviar_digests(db, agora=MANHA)
    assert enviados == []

    # Quarta: é.
    await news_digest_service.enviar_digests(db, agora=QUARTA_MANHA)
    assert len(enviados) == 1


async def test_semanal_alcanca_artigo_de_cinco_dias_atras(db, user, enviados):
    """A janela acompanha a frequência. Com a janela de 2 dias do diário, quem
    escolheu semanal perderia quase tudo que saiu na semana — o oposto do que
    pediu."""
    tema = await _tema(db, "cardio", [(CARDIO, CORE)])
    antigo = await _publicado_em(
        db, "Saiu na sexta passada", tema, QUARTA_MANHA - timedelta(days=5)
    )

    user.specialty = CARDIO
    await db.flush()
    await _liga_email(db, user)
    await _escolhe(db, user, [tema])
    await _agenda(db, user, frequencia="semanal", dia_semana=2, faixa="manha")

    await news_digest_service.enviar_digests(db, agora=QUARTA_MANHA)

    assert len(enviados) == 1
    _, artigos = enviados[0]
    assert [a.id for a, _ in artigos] == [antigo.id]


async def test_diario_nao_alcanca_artigo_de_cinco_dias_atras(db, user, enviados):
    """O contraponto do teste acima: a janela curta do diário continua curta."""
    tema = await _tema(db, "cardio", [(CARDIO, CORE)])
    await _publicado_em(db, "Saiu na quarta passada", tema, MANHA - timedelta(days=5))

    user.specialty = CARDIO
    await db.flush()
    await _liga_email(db, user)
    await _escolhe(db, user, [tema])
    await _agenda(db, user, frequencia="diario", faixa="manha")

    resumo = await news_digest_service.enviar_digests(db, agora=MANHA)

    assert enviados == []
    assert resumo["sem_conteudo"] == 1


# ── a preferência pela API ───────────────────────────────────────────────────

async def test_get_devolve_agenda_padrao_para_quem_nunca_escolheu(as_user):
    r = await as_user.get("/api/v1/news/me/preferences")
    assert r.status_code == 200
    assert r.json()["agenda"] == {
        "frequencia": "diario", "dia_semana": 0, "faixa": "manha",
    }


async def test_put_grava_e_get_devolve_a_agenda(as_user):
    r = await as_user.put(
        "/api/v1/news/me/preferences",
        json={"email": True, "agenda": {
            "frequencia": "semanal", "dia_semana": 4, "faixa": "noite",
        }},
    )
    assert r.status_code == 200
    assert r.json()["agenda"]["frequencia"] == "semanal"

    r = await as_user.get("/api/v1/news/me/preferences")
    assert r.json()["agenda"] == {
        "frequencia": "semanal", "dia_semana": 4, "faixa": "noite",
    }


async def test_put_sem_agenda_nao_apaga_a_que_existia(as_user):
    """CAMPO AUSENTE = NÃO MEXA.

    O botão de desligar o e-mail manda só `email`. Se isso zerasse a agenda, a
    pessoa que religasse depois passaria a receber noutro horário sem nunca ter
    pedido — e ninguém ligaria uma coisa à outra.
    """
    await as_user.put(
        "/api/v1/news/me/preferences",
        json={"email": True, "agenda": {
            "frequencia": "semanal", "dia_semana": 3, "faixa": "tarde",
        }},
    )

    r = await as_user.put(
        "/api/v1/news/me/preferences",
        json={"email": False},
    )
    assert r.status_code == 200
    assert r.json()["email"] is False
    assert r.json()["agenda"] == {
        "frequencia": "semanal", "dia_semana": 3, "faixa": "tarde",
    }


async def test_put_recusa_frequencia_desconhecida(as_user):
    r = await as_user.put(
        "/api/v1/news/me/preferences",
        json={"email": True, "agenda": {"frequencia": "mensal"}},
    )
    assert r.status_code == 422


async def test_put_recusa_dia_fora_da_semana(as_user):
    r = await as_user.put(
        "/api/v1/news/me/preferences",
        json={"email": True, "agenda": {"frequencia": "semanal", "dia_semana": 9}},
    )
    assert r.status_code == 422
