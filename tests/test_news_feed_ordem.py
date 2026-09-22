"""
O feed sai em ordem cronológica — e a curadoria continua disponível.

POR QUE ESTE ARQUIVO EXISTE
O feed ordenava por score (relevância), com a data só de desempate. A tela
mostra o dia e o mês em cada linha, então a lista chegava assim ao médico:

    18 SET · 03 SET · 01 SET · 01 SET · 08 SET · 06 SET

Uma lista datada fora de ordem parece defeito, mesmo quando a ordem tem lógica.
O feedback veio do chefe da empresa, olhando a tela.

A troca tem um risco embutido, e é ele que a maior parte destes testes cobre: a
capa (`hero`) era escolhida como `items[0]`, o que só era "o mais relevante"
PORQUE a lista vinha ordenada por score. Com a ordem cronológica, `[0]` viraria
"o mais recente" em silêncio — a curadoria sumiria da tela sem ninguém notar.
Por isso o `score` passou a sair no schema.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.services import news_feed_service
from tests.conftest import auth_headers
from tests.test_news_feed import CARDIO, CORE, _escolhe, _publicado, _tema

pytestmark = pytest.mark.asyncio

AGORA = datetime.now(UTC)


async def _em(db, titulo, tema, score, dias_atras):
    """Artigo publicado há N dias, com o score dado."""
    art = await _publicado(db, titulo, [(tema, score)])
    art.visible_at = AGORA - timedelta(days=dias_atras)
    await db.flush()
    return art


async def _feed(db, user):
    itens, _ = await news_feed_service.montar_feed(db, user)
    return itens


# ── a queixa ─────────────────────────────────────────────────────────────────

async def test_feed_sai_do_mais_recente_para_o_mais_antigo(db, user):
    """A queixa literal: as datas pulavam para a frente e para trás."""
    tema = await _tema(db, "cardio", [(CARDIO, CORE)])
    user.specialty = CARDIO
    await db.flush()
    await _escolhe(db, user, [tema])

    # Publicados fora de ordem E com scores que, na ordem antiga, embaralhariam
    # tudo: o mais antigo tem o maior score.
    await _em(db, "Ha 18 dias, muito relevante", tema, 0.99, 18)
    await _em(db, "Ha 3 dias, pouco relevante", tema, 0.61, 3)
    await _em(db, "Ha 8 dias, medio", tema, 0.80, 8)
    await _em(db, "Ontem, pouco relevante", tema, 0.62, 1)

    datas = [i.article.visible_at for i in await _feed(db, user)]

    assert datas == sorted(datas, reverse=True), (
        "o feed voltou a sair fora de ordem cronologica"
    )


async def test_ordem_nao_depende_do_score(db, user):
    """O teste acima passaria por acaso se as datas seguissem os scores. Aqui a
    relação é INVERTIDA de propósito: o mais relevante é o mais antigo."""
    tema = await _tema(db, "cardio", [(CARDIO, CORE)])
    user.specialty = CARDIO
    await db.flush()
    await _escolhe(db, user, [tema])

    await _em(db, "Antigo e otimo", tema, 0.99, 20)
    await _em(db, "Recente e fraco", tema, 0.61, 1)

    titulos = [i.article.rewritten_title for i in await _feed(db, user)]
    assert titulos[0] == "Recente e fraco"


async def test_palavras_chave_entram_na_mesma_ordem(db, user):
    """O feed é montado de três blocos concatenados (temas, palavras-chave,
    preenchimento). Ordenar dentro de cada consulta ordenaria os BLOCOS, e a
    lista final continuaria pulando entre eles — que era exatamente o defeito.
    """
    from app.services import news_keyword_service

    tema = await _tema(db, "cardio", [(CARDIO, CORE)])
    user.specialty = CARDIO
    await db.flush()
    await _escolhe(db, user, [tema])

    # Um por tema, antigo; um por palavra-chave, recente. Se os blocos não
    # forem misturados, o do tema vem primeiro mesmo sendo mais velho.
    await _em(db, "Por tema, ha 10 dias", tema, 0.9, 10)
    outro = await _tema(db, "outro", [("Nefrologia", CORE)])
    recente = await _em(db, "Amiloidose renal, ontem", outro, 0.9, 1)
    await news_keyword_service.adicionar(db, user.id, "amiloidose")

    itens = await _feed(db, user)
    datas = [i.article.visible_at for i in itens]

    assert recente.id in [i.article.id for i in itens], "a palavra-chave nao trouxe o artigo"
    assert datas == sorted(datas, reverse=True), "os blocos nao foram intercalados"


async def test_ordenacao_aguenta_artigo_sem_data():
    """`visible_at` é anulável no modelo, e comparar `None` com `datetime`
    estoura em Python.

    Testado direto na função, e não pelo feed: a consulta filtra
    `visible_at >= desde`, então um artigo sem data nunca chega até aqui por
    aquele caminho. A defesa vale mesmo assim — `_em_ordem_cronologica` é
    genérica e a primeira versão deste teste, escrita pelo feed, passou a
    impressão de cobrir algo que o SQL já barrava.

    O lugar do nulo é o fim: sem data não há como posicionar.
    """
    from types import SimpleNamespace

    def item(titulo, visible_at):
        return SimpleNamespace(
            article=SimpleNamespace(visible_at=visible_at, rewritten_title=titulo)
        )

    ordenados = news_feed_service._em_ordem_cronologica([
        item("antigo", AGORA - timedelta(days=5)),
        item("sem data", None),
        item("recente", AGORA),
    ])

    assert [i.article.rewritten_title for i in ordenados] == [
        "recente", "antigo", "sem data",
    ]


# ── a curadoria não se perdeu ────────────────────────────────────────────────

async def test_score_sai_na_resposta_da_api(client, db, user):
    """É o que permite à tela escolher a capa pelo mais relevante.

    Antes o score existia só dentro do serviço; a tela deduzia relevância pela
    POSIÇÃO. Com a lista cronológica, isso deixou de funcionar — e sem o campo
    a capa viraria "o mais recente" sem ninguém perceber.
    """
    tema = await _tema(db, "cardio", [(CARDIO, CORE)])
    user.specialty = CARDIO
    await db.flush()
    await _escolhe(db, user, [tema])
    await _em(db, "Um destaque", tema, 0.87, 1)

    resp = await client.get("/api/v1/news/highlights", headers=auth_headers(user))
    assert resp.status_code == 200

    itens = resp.json()["itens"]
    assert itens, "feed vazio"
    assert itens[0]["score"] == pytest.approx(0.87, abs=0.01), (
        "o score sumiu da resposta — a capa perde o criterio de relevancia"
    )


async def test_o_mais_relevante_e_identificavel_mesmo_estando_no_fim(db, user):
    """O caso que a capa precisa resolver: o melhor item é o mais antigo, logo
    o ÚLTIMO da lista cronológica. A tela só consegue achá-lo pelo score."""
    tema = await _tema(db, "cardio", [(CARDIO, CORE)])
    user.specialty = CARDIO
    await db.flush()
    await _escolhe(db, user, [tema])

    await _em(db, "O melhor, mas antigo", tema, 0.99, 15)
    await _em(db, "Recente", tema, 0.65, 1)

    itens = await _feed(db, user)
    melhor = max(itens, key=lambda i: i.score)

    assert melhor.article.rewritten_title == "O melhor, mas antigo"
    assert itens[-1] is melhor, "o melhor deveria estar no fim (é o mais antigo)"


async def test_preenchimento_continua_marcado_apos_a_reordenacao(db, user):
    """A ordenação mistura os blocos, então a flag é a ÚNICA coisa que ainda
    distingue um item de preenchimento. Se ela se perdesse, o digest passaria a
    interromper o médico por item que ele nunca pediu."""
    escolhido = await _tema(db, "cardio", [(CARDIO, CORE)])
    adjacente = await _tema(db, "adjacente", [(CARDIO, "relevante")])
    user.specialty = CARDIO
    await db.flush()
    await _escolhe(db, user, [escolhido])

    await _em(db, "Do tema escolhido, antigo", escolhido, 0.9, 10)
    # Preenchimento mais recente: depois da reordenação ele vem ANTES.
    await _em(db, "Preenchimento, ontem", adjacente, 0.9, 1)

    itens = await _feed(db, user)
    por_titulo = {i.article.rewritten_title: i for i in itens}

    assert por_titulo["Do tema escolhido, antigo"].preenchimento is False
    if "Preenchimento, ontem" in por_titulo:
        assert por_titulo["Preenchimento, ontem"].preenchimento is True
