"""
Palavras-chave do médico — o eixo separado dos temas.

Os testes que mais importam aqui:

  - `test_preview_bate_com_o_que_o_feed_entrega`: se o preview mentir, ele deixa
    de ser defesa contra falha silenciosa e vira mais uma fonte dela.
  - `test_palavra_chave_acrescenta_sem_remover`: a regra de ser ADITIVA. Se um
    dia alguém a fizer filtrar, um erro de digitação esvazia a tela do usuário.
  - `test_usuario_so_com_palavra_chave_recebe_email`: palavra-chave é pedido
    explícito e por isso PODE interromper — ao contrário do preenchimento.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.models import UserPreference
from app.models.news import Article, ArticleStatus, ArticleTopic, Topic, TopicSpecialty, UserTopic
from app.news.taxonomia import CORE
from app.services import email_service, news_digest_service, news_feed_service, news_keyword_service

# Marca apenas as funcoes async: um `pytestmark` global faria o pytest-asyncio
# reclamar de todo teste sincrono deste arquivo.
asyncio = pytest.mark.asyncio

CARDIO = "Cardiologia"


async def _publicado(db, titulo: str, corpo: str = "<p>corpo comum</p>") -> Article:
    art = Article(
        journal_slug="lancet",
        source="pubmed",
        external_id=f"kw-{abs(hash(titulo)) % 10**9}",
        original_title=titulo,
        original_abstract="BACKGROUND: x. RESULTS: y. CONCLUSION: z.",
        rewritten_title=titulo,
        rewritten_body=corpo,
        status=ArticleStatus.PUBLISHED.value,
        visible_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db.add(art)
    await db.flush()
    return art


# ── Validação de entrada ─────────────────────────────────────────────────────

def test_normaliza_caixa_e_espacos():
    assert news_keyword_service.normalizar("  Amiloidose  Cardíaca ") == "amiloidose cardíaca"


def test_acento_e_preservado_na_normalizacao():
    """
    Quem tira acento é o dicionário `portuguese` do Postgres, na busca. Tirar
    aqui também faria o termo guardado divergir do que o médico digitou, sem
    ganho nenhum no casamento.
    """
    assert "í" in news_keyword_service.normalizar("Cardíaca")


def test_termo_curto_e_recusado():
    with pytest.raises(news_keyword_service.TermoInvalido) as exc:
        news_keyword_service.validar("IC")
    assert "caracteres" in str(exc.value)


def test_termo_longo_demais_e_recusado():
    with pytest.raises(news_keyword_service.TermoInvalido):
        news_keyword_service.validar("a" * 200)


@asyncio
async def test_teto_de_termos_e_respeitado(db, user):
    """Sem teto, alguém cola 200 termos, tudo casa, e o filtro morre."""
    settings = get_settings()
    for i in range(settings.news_max_keywords):
        await news_keyword_service.adicionar(db, user.id, f"termo-numero-{i:03d}")

    with pytest.raises(news_keyword_service.TermoInvalido) as exc:
        await news_keyword_service.adicionar(db, user.id, "um-termo-a-mais")
    assert str(settings.news_max_keywords) in str(exc.value)


@asyncio
async def test_cadastrar_duas_vezes_nao_duplica(db, user):
    """Repetir não é erro do usuário — e não pode gerar duas linhas iguais."""
    a = await news_keyword_service.adicionar(db, user.id, "amiloidose")
    b = await news_keyword_service.adicionar(db, user.id, "  Amiloidose ")
    assert a.id == b.id
    assert len(await news_keyword_service.listar(db, user.id)) == 1


@asyncio
async def test_remover(db, user):
    await news_keyword_service.adicionar(db, user.id, "amiloidose")
    assert await news_keyword_service.remover(db, user.id, "AMILOIDOSE") is True
    assert await news_keyword_service.listar(db, user.id) == []


# ── Busca ────────────────────────────────────────────────────────────────────

@asyncio
async def test_casa_no_titulo(db):
    await _publicado(db, "Amiloidose cardíaca por transtirretina em idosos")
    assert await news_keyword_service.contar_destaques(db, "amiloidose") == 1


@asyncio
async def test_stemming_do_portugues_funciona(db):
    """
    "cardíacas" acha "cardíaca". É o dicionário do Postgres fazendo o trabalho —
    e o motivo de a busca ser sobre o texto em PORTUGUÊS (`rewritten_*`) e não
    sobre o abstract original em inglês.
    """
    await _publicado(db, "Complicações cardíacas em pacientes idosos")
    assert await news_keyword_service.contar_destaques(db, "cardíaca") >= 1


@asyncio
async def test_termo_ausente_devolve_zero(db):
    await _publicado(db, "Um título sobre outra coisa completamente diferente")
    assert await news_keyword_service.contar_destaques(db, "amiloidose") == 0


@asyncio
async def test_titulo_ranqueia_acima_do_corpo(db):
    """
    Os pesos A (título) e B (corpo) são o que separa "artigo SOBRE amiloidose"
    de "artigo que a menciona". Quem usa isso é a ORDENAÇÃO — o piso de rank é
    deliberadamente inclusivo, para não produzir "cadastrei e nunca veio nada".
    """
    no_corpo = await _publicado(
        db, "Um estudo de coorte prospectivo", "<p>Menciona amiloidose de passagem.</p>"
    )
    no_titulo = await _publicado(db, "Amiloidose cardíaca: rastreamento e diagnóstico")

    achados = await news_keyword_service.artigos_por_palavras(
        db, ["amiloidose"], datetime.now(UTC) - timedelta(days=30), limite=10
    )
    ids = [a.id for a, _ in achados]

    assert no_titulo.id in ids and no_corpo.id in ids, "os dois devem entrar"
    assert ids.index(no_titulo.id) < ids.index(no_corpo.id), "o do título vem primeiro"


@asyncio
async def test_artigo_traz_qual_termo_casou(db):
    """Sem isso, o card não consegue responder 'por que estou vendo isto?'."""
    await _publicado(db, "Amiloidose cardíaca e insuficiência de fração preservada")
    achados = await news_keyword_service.artigos_por_palavras(
        db, ["amiloidose", "sarcoidose"], datetime.now(UTC) - timedelta(days=30), limite=10
    )
    assert achados[0][1] == ["amiloidose"]


@asyncio
async def test_fora_da_janela_nao_conta(db):
    art = await _publicado(db, "Amiloidose cardíaca em idosos")
    art.visible_at = datetime.now(UTC) - timedelta(days=400)
    await db.flush()
    assert await news_keyword_service.contar_destaques(db, "amiloidose") == 0


@asyncio
async def test_preview_bate_com_o_que_o_feed_entrega(db, user):
    """
    Se o preview disser 2 e o feed entregar 0, ele deixa de ser defesa contra a
    falha silenciosa e vira mais uma fonte dela.
    """
    await _publicado(db, "Amiloidose cardíaca por transtirretina")
    await _publicado(db, "Novo tratamento para amiloidose sistêmica")

    previsto = await news_keyword_service.contar_destaques(db, "amiloidose")
    await news_keyword_service.adicionar(db, user.id, "amiloidose")

    feed, _ = await news_feed_service.montar_feed(db, user)
    entregues = [i for i in feed if "amiloidose" in i.palavras]

    assert previsto == len(entregues) == 2


# ── Integração com o feed ────────────────────────────────────────────────────

@asyncio
async def test_palavra_chave_acrescenta_sem_remover(db, user):
    """
    ADITIVA, nunca subtrativa. Se filtrasse, um erro de digitação esvaziaria a
    tela — e o usuário não teria como saber por quê.
    """
    tema = Topic(slug="insuficiencia-cardiaca", nome_pt="Insuficiência cardíaca")
    db.add(tema)
    await db.flush()
    db.add(TopicSpecialty(topic_id=tema.id, specialty=CARDIO, peso=CORE))
    por_tema = await _publicado(db, "Novo inibidor em ICFEr")
    db.add(ArticleTopic(article_id=por_tema.id, topic_id=tema.id, score=0.9))
    db.add(UserTopic(user_id=user.id, topic_id=tema.id))
    user.specialty = CARDIO
    await db.flush()

    antes, _ = await news_feed_service.montar_feed(db, user)

    por_palavra = await _publicado(db, "Amiloidose cardíaca por transtirretina")
    await news_keyword_service.adicionar(db, user.id, "amiloidose")

    depois, _ = await news_feed_service.montar_feed(db, user)

    ids_antes = {i.article.id for i in antes}
    ids_depois = {i.article.id for i in depois}
    assert ids_antes <= ids_depois, "nada do que já estava pode sumir"
    assert por_palavra.id in ids_depois


@asyncio
async def test_item_de_palavra_chave_nao_e_preenchimento(db, user):
    """
    A distinção importa no digest: preenchimento nunca manda e-mail, palavra-
    chave manda. Confundir os dois quebraria as duas regras de uma vez.
    """
    await _publicado(db, "Amiloidose cardíaca por transtirretina")
    await news_keyword_service.adicionar(db, user.id, "amiloidose")

    feed, _ = await news_feed_service.montar_feed(db, user)
    item = next(i for i in feed if "amiloidose" in i.palavras)
    assert item.preenchimento is False


# ── Integração com o digest ──────────────────────────────────────────────────

@pytest.fixture
def enviados(monkeypatch) -> list:
    capturados = []

    async def _fake(to_email, nome, artigos):
        capturados.append((to_email, [(a.id, motivo) for a, motivo in artigos]))

    monkeypatch.setattr(email_service, "send_news_digest", _fake)
    monkeypatch.setattr(news_digest_service.email_service, "send_news_digest", _fake)
    return capturados


async def _liga_email(db, user) -> None:
    prefs = await db.scalar(select(UserPreference).where(UserPreference.user_id == user.id))
    if prefs is None:
        prefs = UserPreference(user_id=user.id)
        db.add(prefs)
    prefs.notification_prefs = {"news": {"email": True}}
    await db.flush()


@asyncio
async def test_usuario_so_com_palavra_chave_recebe_email(db, user, enviados):
    """
    Cadastrar um termo é pedido explícito e deliberado — sinal mais forte que um
    tema pré-marcado. Por isso PODE interromper, ao contrário do preenchimento.
    """
    art = await _publicado(db, "Amiloidose cardíaca por transtirretina")
    await news_keyword_service.adicionar(db, user.id, "amiloidose")
    await _liga_email(db, user)

    resumo = await news_digest_service.enviar_digests(db)

    assert resumo["enviados"] == 1
    assert enviados[0][1] == [(art.id, "amiloidose")]


@asyncio
async def test_email_nomeia_o_motivo(db, user, enviados):
    """
    Dizer o porquê dentro do e-mail é o que permite à pessoa saber o que
    desligar, se aquilo estiver incomodando.
    """
    await _publicado(db, "Amiloidose cardíaca por transtirretina")
    await news_keyword_service.adicionar(db, user.id, "amiloidose")
    await _liga_email(db, user)

    await news_digest_service.enviar_digests(db)

    _, itens = enviados[0]
    assert itens[0][1] == "amiloidose"


@asyncio
async def test_sem_match_nenhum_continua_sem_email(db, user, enviados):
    """A regra original não pode ter sido quebrada pela nova fonte."""
    await _publicado(db, "Um destaque sobre outro assunto qualquer")
    await news_keyword_service.adicionar(db, user.id, "amiloidose")
    await _liga_email(db, user)

    resumo = await news_digest_service.enviar_digests(db)

    assert enviados == []
    assert resumo["enviados"] == 0
