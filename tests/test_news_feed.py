"""
Feed personalizado e digest diário.

Os dois testes que importam mais:

  - `test_cardio_e_infecto_recebem_feeds_diferentes` — a queixa literal que
    originou o módulo, verificada de ponta a ponta sobre o mesmo acervo.
  - `test_usuario_so_com_preenchimento_nao_recebe_email` — amarra as duas fases:
    o feed completa a tela para não ficar vazia, e essa cortesia de navegação
    NUNCA pode virar motivo de interromper alguém por e-mail.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.models import UserPreference
from app.models.news import (
    Article,
    ArticleStatus,
    ArticleTopic,
    DigestSend,
    Topic,
    TopicSpecialty,
    UserTopic,
)
from app.news.taxonomia import CORE, RELEVANTE
from app.services import email_service, news_digest_service, news_feed_service

pytestmark = pytest.mark.asyncio

CARDIO = "Cardiologia"
INFECTO = "Infectologia"


async def _tema(db, slug: str, especialidades: list[tuple[str, str]]) -> Topic:
    tema = Topic(slug=slug, nome_pt=slug.replace("-", " ").capitalize())
    db.add(tema)
    await db.flush()
    for especialidade, peso in especialidades:
        db.add(TopicSpecialty(topic_id=tema.id, specialty=especialidade, peso=peso))
    await db.flush()
    return tema


async def _publicado(db, titulo: str, temas: list[tuple[Topic, float]]) -> Article:
    art = Article(
        journal_slug="lancet",
        source="pubmed",
        external_id=f"pmid-{titulo[:20]}-{len(titulo)}",
        original_title=titulo,
        original_abstract="BACKGROUND: x. RESULTS: y. CONCLUSION: z.",
        rewritten_title=titulo,
        rewritten_body="<p>corpo</p>",
        status=ArticleStatus.PUBLISHED.value,
        visible_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db.add(art)
    await db.flush()
    for tema, score in temas:
        db.add(ArticleTopic(article_id=art.id, topic_id=tema.id, score=score))
    await db.flush()
    return art


async def _escolhe(db, user, temas: list[Topic]) -> None:
    for tema in temas:
        db.add(UserTopic(user_id=user.id, topic_id=tema.id))
    await db.flush()


# ── Sugestão por especialidade ───────────────────────────────────────────────

async def test_sugestao_vem_da_especialidade(db, user):
    ic = await _tema(db, "insuficiencia-cardiaca", [(CARDIO, CORE)])
    await _tema(db, "hiv", [(INFECTO, CORE)])
    user.specialty = CARDIO
    await db.flush()

    sugeridos = await news_feed_service.temas_sugeridos_para(db, user.specialty)

    assert [t.id for t in sugeridos] == [ic.id]


async def test_tema_transversal_e_sugerido_para_ambas(db):
    """
    Obesidade é `core` de endócrino e `relevante` de cardio — e por isso aparece
    para os dois, sem nenhum caso especial em código.
    """
    obesidade = await _tema(
        db, "obesidade",
        [("Endocrinologia e Metabologia", CORE), (CARDIO, RELEVANTE)],
    )

    para_cardio = await news_feed_service.temas_sugeridos_para(db, CARDIO)
    para_endocrino = await news_feed_service.temas_sugeridos_para(
        db, "Endocrinologia e Metabologia"
    )

    assert obesidade.id in {t.id for t in para_cardio}
    assert obesidade.id in {t.id for t in para_endocrino}


# ── Feed ─────────────────────────────────────────────────────────────────────

async def test_cardio_e_infecto_recebem_feeds_diferentes(db, user_factory):
    """A queixa do chefe, verificada sobre o mesmo acervo."""
    ic = await _tema(db, "insuficiencia-cardiaca", [(CARDIO, CORE)])
    hiv = await _tema(db, "hiv", [(INFECTO, CORE)])

    art_cardio = await _publicado(db, "Novo inibidor em ICFEr", [(ic, 0.95)])
    art_infecto = await _publicado(db, "Profilaxia pré-exposição", [(hiv, 0.95)])

    cardiologista = await user_factory(email="cardio@x.com")
    cardiologista.specialty = CARDIO
    infectologista = await user_factory(email="infecto@x.com")
    infectologista.specialty = INFECTO
    await db.flush()

    await _escolhe(db, cardiologista, [ic])
    await _escolhe(db, infectologista, [hiv])

    feed_cardio, _ = await news_feed_service.montar_feed(db, cardiologista)
    feed_infecto, _ = await news_feed_service.montar_feed(db, infectologista)

    ids_cardio = {i.article.id for i in feed_cardio if not i.preenchimento}
    ids_infecto = {i.article.id for i in feed_infecto if not i.preenchimento}

    assert ids_cardio == {art_cardio.id}
    assert ids_infecto == {art_infecto.id}
    assert art_infecto.id not in ids_cardio


async def test_artigo_transversal_alcanca_as_duas_especialidades(db, user_factory):
    """
    Um ensaio de semaglutida em obesos com IC casa com cardio E endócrino.
    É o caso que um filtro binário por especialidade erraria.
    """
    obesidade = await _tema(
        db, "obesidade", [("Endocrinologia e Metabologia", CORE), (CARDIO, RELEVANTE)]
    )
    art = await _publicado(db, "Semaglutida em obesos com IC", [(obesidade, 0.9)])

    cardio = await user_factory(email="c@x.com")
    cardio.specialty = CARDIO
    endocrino = await user_factory(email="e@x.com")
    endocrino.specialty = "Endocrinologia e Metabologia"
    await db.flush()

    await _escolhe(db, cardio, [obesidade])
    await _escolhe(db, endocrino, [obesidade])

    feed_cardio, _ = await news_feed_service.montar_feed(db, cardio)
    feed_endocrino, _ = await news_feed_service.montar_feed(db, endocrino)

    assert art.id in {i.article.id for i in feed_cardio}
    assert art.id in {i.article.id for i in feed_endocrino}


async def test_score_abaixo_do_limiar_nao_entra(db, user):
    ic = await _tema(db, "insuficiencia-cardiaca", [(CARDIO, CORE)])
    await _publicado(db, "Menção de passagem a IC", [(ic, 0.05)])
    user.specialty = CARDIO
    await db.flush()
    await _escolhe(db, user, [ic])

    feed, _ = await news_feed_service.montar_feed(db, user)

    assert [i for i in feed if not i.preenchimento] == []


async def test_cards_dizem_por_que_estao_ali(db, user):
    """
    Sem os temas visíveis no card, o filtro vira caixa-preta e não há como o
    usuário — nem nós — depurar a taxonomia com base em reclamação real.
    """
    ic = await _tema(db, "insuficiencia-cardiaca", [(CARDIO, CORE)])
    await _publicado(db, "Novo inibidor", [(ic, 0.9)])
    user.specialty = CARDIO
    await db.flush()
    await _escolhe(db, user, [ic])

    feed, _ = await news_feed_service.montar_feed(db, user)

    assert feed[0].temas == [("insuficiencia-cardiaca", "Insuficiencia cardiaca")]


# ── A regra do feed vazio ────────────────────────────────────────────────────

async def test_feed_completa_com_adjacentes_marcados(db, user):
    """
    Especialidade estreita não pode resultar em tela vazia — mas o que entra
    para preencher precisa vir MARCADO, senão o usuário deixa de confiar no
    filtro.
    """
    ic = await _tema(db, "insuficiencia-cardiaca", [(CARDIO, CORE)])
    dor = await _tema(db, "dor-cronica", [(CARDIO, RELEVANTE)])

    art_adjacente = await _publicado(db, "Analgesia multimodal", [(dor, 0.8)])

    user.specialty = CARDIO
    await db.flush()
    # Escolheu só IC; não há nada de IC publicado.
    await _escolhe(db, user, [ic])

    feed, motivo = await news_feed_service.montar_feed(db, user)

    assert [i.article.id for i in feed] == [art_adjacente.id]
    assert feed[0].preenchimento is True
    assert motivo == news_feed_service.MOTIVO_SEM_MATCH


async def test_sem_conteudo_e_sem_match_sao_motivos_distintos(db, user):
    """
    Vazio porque não publicaram nada hoje, ou porque seus temas estão estreitos
    demais? Para o usuário as duas telas seriam idênticas, e ele concluiria que
    o produto morreu.
    """
    ic = await _tema(db, "insuficiencia-cardiaca", [(CARDIO, CORE)])
    user.specialty = CARDIO
    await db.flush()
    await _escolhe(db, user, [ic])

    _, motivo = await news_feed_service.montar_feed(db, user)
    assert motivo == news_feed_service.MOTIVO_SEM_CONTEUDO

    hiv = await _tema(db, "hiv", [(INFECTO, CORE)])
    await _publicado(db, "Profilaxia", [(hiv, 0.9)])

    _, motivo = await news_feed_service.montar_feed(db, user)
    assert motivo == news_feed_service.MOTIVO_SEM_MATCH


async def test_ver_tudo_ignora_o_filtro(db, user):
    """A válvula que impede o filtro de virar caixa-preta."""
    hiv = await _tema(db, "hiv", [(INFECTO, CORE)])
    art = await _publicado(db, "Profilaxia pré-exposição", [(hiv, 0.9)])
    user.specialty = CARDIO
    await db.flush()

    filtrado, _ = await news_feed_service.montar_feed(db, user)
    tudo, _ = await news_feed_service.montar_feed(db, user, todos=True)

    assert art.id not in {i.article.id for i in filtrado if not i.preenchimento}
    assert art.id in {i.article.id for i in tudo}


# ── Digest ───────────────────────────────────────────────────────────────────

async def _liga_email(db, user) -> None:
    prefs = await db.scalar(select(UserPreference).where(UserPreference.user_id == user.id))
    if prefs is None:
        prefs = UserPreference(user_id=user.id)
        db.add(prefs)
    prefs.notification_prefs = {"news": {"email": True}}
    await db.flush()


@pytest.fixture
def enviados(monkeypatch) -> list:
    """Captura os e-mails em vez de mandá-los."""
    capturados = []

    async def _fake(to_email, nome, artigos):
        capturados.append((to_email, [a.id for a in artigos]))

    monkeypatch.setattr(email_service, "send_news_digest", _fake)
    monkeypatch.setattr(news_digest_service.email_service, "send_news_digest", _fake)
    return capturados


async def test_zero_match_zero_email(db, user, enviados):
    """
    A regra mais importante do digest. "Nada para você hoje" seria exatamente o
    ruído que o módulo existe para eliminar.
    """
    await _liga_email(db, user)
    user.specialty = CARDIO
    await db.flush()

    resumo = await news_digest_service.enviar_digests(db)

    assert enviados == []
    assert resumo["enviados"] == 0
    assert resumo["sem_conteudo"] == 1


async def test_sem_opt_in_nao_recebe(db, user, enviados):
    """Opt-in explícito: ninguém passa a receber e-mail por efeito colateral de deploy."""
    ic = await _tema(db, "insuficiencia-cardiaca", [(CARDIO, CORE)])
    await _publicado(db, "Novo inibidor", [(ic, 0.95)])
    await _escolhe(db, user, [ic])
    # Preferência existe, mas com e-mail desligado.
    prefs = UserPreference(user_id=user.id, notification_prefs={"news": {"email": False}})
    db.add(prefs)
    await db.flush()

    await news_digest_service.enviar_digests(db)

    assert enviados == []


async def test_digest_envia_o_que_casou(db, user, enviados):
    ic = await _tema(db, "insuficiencia-cardiaca", [(CARDIO, CORE)])
    art = await _publicado(db, "Novo inibidor em ICFEr", [(ic, 0.95)])
    await _escolhe(db, user, [ic])
    await _liga_email(db, user)

    resumo = await news_digest_service.enviar_digests(db)

    assert resumo["enviados"] == 1
    assert enviados[0][1] == [art.id]


async def test_digest_e_idempotente(db, user, enviados):
    """
    Sem isto, um retry manda o mesmo digest duas vezes — e o segundo e-mail é
    justamente o ruído que tudo isto existe para evitar.
    """
    ic = await _tema(db, "insuficiencia-cardiaca", [(CARDIO, CORE)])
    await _publicado(db, "Novo inibidor em ICFEr", [(ic, 0.95)])
    await _escolhe(db, user, [ic])
    await _liga_email(db, user)

    await news_digest_service.enviar_digests(db)
    segunda = await news_digest_service.enviar_digests(db)

    assert len(enviados) == 1
    assert segunda["enviados"] == 0
    assert segunda["ja_enviados"] == 1

    registros = list(await db.scalars(select(DigestSend).where(DigestSend.user_id == user.id)))
    assert len(registros) == 1


async def test_limiar_do_digest_e_mais_alto_que_o_do_feed(db, user, enviados):
    """
    Navegar é barato, interromper é caro. Um score que justifica aparecer na
    lista não justifica um e-mail.
    """
    ic = await _tema(db, "insuficiencia-cardiaca", [(CARDIO, CORE)])
    # 0.4: acima do limiar do feed (0.3), abaixo do limiar do digest (0.6).
    await _publicado(db, "Menciona IC de passagem", [(ic, 0.4)])
    await _escolhe(db, user, [ic])
    await _liga_email(db, user)
    user.specialty = CARDIO
    await db.flush()

    feed, _ = await news_feed_service.montar_feed(db, user)
    await news_digest_service.enviar_digests(db)

    assert len([i for i in feed if not i.preenchimento]) == 1
    assert enviados == []


async def test_usuario_so_com_preenchimento_nao_recebe_email(db, user, enviados):
    """
    O teste que amarra as Fases 3 e 4.

    O feed completa a tela com temas adjacentes para não deixá-la vazia. Isso é
    cortesia de navegação e NÃO pode virar motivo de interromper alguém: o
    usuário não escolheu aquele tema.
    """
    ic = await _tema(db, "insuficiencia-cardiaca", [(CARDIO, CORE)])
    dor = await _tema(db, "dor-cronica", [(CARDIO, RELEVANTE)])
    await _publicado(db, "Analgesia multimodal", [(dor, 0.95)])

    user.specialty = CARDIO
    await db.flush()
    await _escolhe(db, user, [ic])  # escolheu IC; só há conteúdo de dor
    await _liga_email(db, user)

    feed, _ = await news_feed_service.montar_feed(db, user)
    await news_digest_service.enviar_digests(db)

    # A tela não ficou vazia...
    assert len(feed) == 1
    assert feed[0].preenchimento is True
    # ...e mesmo assim ninguém foi incomodado.
    assert enviados == []


async def test_sem_sendgrid_nao_estoura(db, user, monkeypatch):
    """Ambiente local sem chave: cai no log, não derruba a rodada."""
    ic = await _tema(db, "insuficiencia-cardiaca", [(CARDIO, CORE)])
    art = await _publicado(db, "Novo inibidor", [(ic, 0.95)])
    await _escolhe(db, user, [ic])
    await _liga_email(db, user)

    settings = news_digest_service.get_settings()
    monkeypatch.setattr(settings, "sendgrid_api_key", "", raising=False)

    resumo = await news_digest_service.enviar_digests(db)

    assert resumo["enviados"] == 1
    assert resumo["falhas"] == 0
    assert art.id is not None
