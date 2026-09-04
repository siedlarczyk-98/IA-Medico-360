"""
Coletor, tagger e redator do módulo de notícias.

O teste central deste arquivo é `test_artigo_sem_abstract_nao_chega_ao_modelo`:
ele amarra a invariante que substituiu o fallback de scraping HTML. Sem ela, um
artigo sem abstract vira um post inteiro escrito a partir de um título solto —
o cenário de maior risco de alucinação num produto médico.
"""

import httpx
import pytest
from sqlalchemy import select

from app.models.news import Article, ArticleStatus, ArticleTopic, Topic
from app.news.journals import JOURNALS_BY_SLUG
from app.services import news_collector_service, news_tagger_service, news_writer_service
from app.services.integracoes.news_pubmed import ArtigoPubMed

# Marca apenas as funcoes async: um `pytestmark` global faria o pytest-asyncio
# reclamar de todo teste sincrono deste arquivo.
asyncio = pytest.mark.asyncio

LANCET = JOURNALS_BY_SLUG["lancet"]

ABSTRACT_VALIDO = (
    "BACKGROUND: Estudo de coorte prospectiva.\n\n"
    "METHODS: 1200 pacientes randomizados.\n\n"
    "RESULTS: Redução de 28% no desfecho primário.\n\n"
    "CONCLUSION: A intervenção foi eficaz."
)


def _pubmed(pmid="1", titulo="Um ensaio clínico", abstract=ABSTRACT_VALIDO, mesh=None):
    return ArtigoPubMed(
        pmid=pmid,
        title=titulo,
        abstract=abstract,
        authors=["Ana Silva", "Bruno Costa"],
        doi=f"10.1000/{pmid}",
        published_date=None,
        mesh_terms=mesh or [],
    )


async def _artigo(db, **kwargs) -> Article:
    padrao = dict(
        journal_slug="lancet",
        source="pubmed",
        external_id="pmid-teste",
        original_title="Título original",
        original_abstract=ABSTRACT_VALIDO,
        status=ArticleStatus.TAGGED.value,
    )
    art = Article(**{**padrao, **kwargs})
    db.add(art)
    await db.flush()
    await db.refresh(art)
    return art


# ── Filtro editorial ─────────────────────────────────────────────────────────

def test_artigo_com_estrutura_e_mantido():
    secundaria, _ = news_collector_service.eh_peca_editorial(_pubmed(), "lancet")
    assert secundaria is False


def test_item_sem_abstract_e_descartado():
    secundaria, motivo = news_collector_service.eh_peca_editorial(
        _pubmed(abstract=None), "lancet"
    )
    assert secundaria is True
    assert "abstract" in motivo


def test_carta_ao_editor_e_descartada():
    # Texto livre, sem nenhuma seção estruturada: assinatura de peça editorial.
    secundaria, _ = news_collector_service.eh_peca_editorial(
        _pubmed(abstract="Gostaria de comentar o artigo publicado na edição anterior."),
        "lancet",
    )
    assert secundaria is True


# ── Coletor ──────────────────────────────────────────────────────────────────

@asyncio
async def test_falha_do_pubmed_nao_derruba_o_job(db, monkeypatch):
    """
    NCBI fora do ar ou 429 devolvia exceção que subia até o job e o matava. O
    "fallback" que aparentava cobrir isso só cobria resposta 200 com lista
    vazia — o cenário provável não tinha cobertura nenhuma.
    """
    async def explode(*a, **kw):
        raise httpx.ConnectTimeout("NCBI fora do ar")

    monkeypatch.setattr(news_collector_service, "buscar_artigos_por_issn", explode)

    resultado = await news_collector_service.coletar_para_journal(db, LANCET)

    assert resultado["coletados"] == 0
    assert resultado["falhou"] is True


@asyncio
async def test_coleta_persiste_e_deduplica(db, monkeypatch):
    async def devolve(*a, **kw):
        return [_pubmed(pmid="111"), _pubmed(pmid="222")]

    monkeypatch.setattr(news_collector_service, "buscar_artigos_por_issn", devolve)

    primeira = await news_collector_service.coletar_para_journal(db, LANCET)
    assert primeira["coletados"] == 2

    # Rodar de novo no mesmo dia não pode duplicar: é a garantia que permite ao
    # laço agendado rodar em várias réplicas sem eleição de líder.
    segunda = await news_collector_service.coletar_para_journal(db, LANCET)
    assert segunda["coletados"] == 0


@asyncio
async def test_mesh_e_persistido_quando_existe(db, monkeypatch):
    mesh = [{"descriptor": "Obesity", "major": True}]

    async def devolve(*a, **kw):
        return [_pubmed(pmid="333", mesh=mesh)]

    monkeypatch.setattr(news_collector_service, "buscar_artigos_por_issn", devolve)
    await news_collector_service.coletar_para_journal(db, LANCET)

    art = await db.scalar(select(Article).where(Article.external_id == "333"))
    assert art.mesh_terms == mesh


# ── Redator: a invariante ────────────────────────────────────────────────────

@asyncio
async def test_artigo_sem_abstract_nao_chega_ao_modelo(db, monkeypatch):
    """
    O teste que substitui o fallback de scraping.

    Não basta afirmar o status final: o ponto é que o modelo NUNCA é chamado.
    Se um dia alguém "consertar" isto chamando o LLM e descartando a resposta,
    o custo e o risco voltam sem que o status denuncie.
    """
    chamadas = []

    async def nao_deveria_ser_chamado(*a, **kw):
        chamadas.append(a)
        raise AssertionError("O redator chamou o modelo para um artigo sem abstract")

    monkeypatch.setattr(news_writer_service, "redigir", nao_deveria_ser_chamado)

    art = await _artigo(db, original_abstract=None, external_id="sem-abstract")
    resultado = await news_writer_service.redigir_lote(db)

    await db.refresh(art)
    assert art.status == ArticleStatus.SKIPPED_NO_ABSTRACT.value
    assert resultado["sem_abstract"] == 1
    assert chamadas == []


@asyncio
async def test_abstract_em_branco_conta_como_ausente(db, monkeypatch):
    monkeypatch.setattr(
        news_writer_service, "redigir",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("não deveria chamar")),
    )
    art = await _artigo(db, original_abstract="   \n  ", external_id="branco")

    await news_writer_service.redigir_lote(db)

    await db.refresh(art)
    assert art.status == ArticleStatus.SKIPPED_NO_ABSTRACT.value


@asyncio
async def test_pulado_nao_e_falha(db, monkeypatch):
    """
    `skipped_no_abstract` não pode virar `failed`: misturar os dois encheria a
    fila de falhas de itens sem conserto e esconderia as falhas de verdade.
    """
    monkeypatch.setattr(
        news_writer_service, "redigir",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("não deveria chamar")),
    )
    await _artigo(db, original_abstract=None, external_id="nao-e-falha")

    resultado = await news_writer_service.redigir_lote(db)

    assert resultado["falhas"] == 0
    assert resultado["sem_abstract"] == 1


@asyncio
async def test_artigo_com_abstract_e_publicado(db, monkeypatch):
    async def redige(article, journal, **kw):
        return "Título reescrito", "<p>Corpo</p>"

    monkeypatch.setattr(news_writer_service, "redigir", redige)

    art = await _artigo(db, external_id="ok")
    resultado = await news_writer_service.redigir_lote(db)

    await db.refresh(art)
    assert art.status == ArticleStatus.PUBLISHED.value
    assert art.rewritten_title == "Título reescrito"
    # `visible_at` é o que o feed filtra: sem ele o artigo seria publicado e
    # invisível ao mesmo tempo.
    assert art.visible_at is not None
    assert resultado["publicados"] == 1


@asyncio
async def test_falha_do_modelo_registra_erro(db, monkeypatch):
    async def falha(*a, **kw):
        raise ValueError("modelo não chamou a ferramenta")

    monkeypatch.setattr(news_writer_service, "redigir", falha)

    art = await _artigo(db, external_id="falhou")
    resultado = await news_writer_service.redigir_lote(db)

    await db.refresh(art)
    assert art.status == ArticleStatus.FAILED.value
    assert "ferramenta" in art.last_error
    assert art.retry_count == 1
    assert resultado["falhas"] == 1


@asyncio
async def test_artigo_que_falhou_volta_no_lote_seguinte(db, monkeypatch):
    """Uma falha transitória (timeout do modelo) não pode custar a notícia."""

    async def falha(*a, **kw):
        raise ValueError("timeout simulado")

    monkeypatch.setattr(news_writer_service, "redigir", falha)
    art = await _artigo(db, external_id="transitorio")
    await news_writer_service.redigir_lote(db)
    await db.refresh(art)
    assert art.status == ArticleStatus.FAILED.value

    # Segunda rodada, agora com o modelo respondendo: o artigo tem de ser
    # recolhido pela query — é isto que `retry_count` passou a significar.
    async def redige(article, journal, **kw):
        return "Recuperado", "<p>Corpo</p>"

    monkeypatch.setattr(news_writer_service, "redigir", redige)
    resultado = await news_writer_service.redigir_lote(db)

    await db.refresh(art)
    assert art.status == ArticleStatus.PUBLISHED.value
    assert art.rewritten_title == "Recuperado"
    assert resultado["publicados"] == 1


@asyncio
async def test_artigo_para_de_ser_tentado_no_teto(db, monkeypatch):
    """O teto existe para que falha sem conserto não consuma chamada eterna."""

    async def falha(*a, **kw):
        raise ValueError("erro permanente")

    monkeypatch.setattr(news_writer_service, "redigir", falha)
    art = await _artigo(db, external_id="insistente")

    for _ in range(news_writer_service.MAX_TENTATIVAS):
        await news_writer_service.redigir_lote(db)

    await db.refresh(art)
    assert art.retry_count == news_writer_service.MAX_TENTATIVAS

    # Esgotado: a rodada seguinte não pode mais pegá-lo.
    resultado = await news_writer_service.redigir_lote(db)
    assert resultado["falhas"] == 0
    await db.refresh(art)
    assert art.retry_count == news_writer_service.MAX_TENTATIVAS


@asyncio
async def test_citacao_e_montada_sem_o_modelo():
    """A referência à fonte não passa pelo LLM — é o que garante citação correta."""
    art = Article(
        journal_slug="lancet", source="pubmed", external_id="x",
        original_title="Efeito da semaglutida", authors="Ana Silva; Bruno Costa",
    )
    html = news_writer_service._citacao_html(art, "The Lancet")

    assert "Ana Silva; Bruno Costa" in html
    assert "Efeito da semaglutida" in html
    assert "The Lancet" in html


# ── Tagger ───────────────────────────────────────────────────────────────────

def test_bonus_mesh_reforca_tema_principal():
    temas = [{"slug": "obesidade", "score": 0.6}]
    mesh = [{"descriptor": "Obesidade e tratamento do peso", "major": True}]
    nomes = {"obesidade": "Obesidade e tratamento do peso"}

    resultado = news_tagger_service._aplicar_bonus_mesh(temas, mesh, nomes)

    assert resultado[0]["score"] > 0.6
    assert resultado[0]["origem"] == "mesh"


def test_sem_mesh_o_score_nao_muda():
    """
    O caso COMUM: artigo ahead-of-print, sem MeSH. Ele não pode ficar em
    desvantagem só porque a NLM ainda não indexou.
    """
    temas = [{"slug": "obesidade", "score": 0.6}]
    resultado = news_tagger_service._aplicar_bonus_mesh(temas, None, {"obesidade": "Obesidade"})
    assert resultado[0]["score"] == 0.6


def test_mesh_nao_principal_nao_da_bonus():
    temas = [{"slug": "obesidade", "score": 0.6}]
    mesh = [{"descriptor": "Obesidade", "major": False}]
    resultado = news_tagger_service._aplicar_bonus_mesh(temas, mesh, {"obesidade": "Obesidade"})
    assert resultado[0]["score"] == 0.6


class _RespostaFake:
    """Resposta mínima de um POST httpx, com o conteúdo que o modelo teria devolvido."""

    def __init__(self, conteudo: str):
        self._conteudo = conteudo

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": self._conteudo}}]}


class _ClientFake:
    def __init__(self, conteudo: str):
        self._conteudo = conteudo

    async def post(self, *a, **kw):
        return _RespostaFake(self._conteudo)


@asyncio
async def test_classificar_descarta_slug_fora_do_vocabulario(monkeypatch):
    """
    A garantia que faz o vocabulário ser realmente FECHADO.

    O mock aqui é o cliente HTTP, e não `_classificar`: a validação mora dentro
    dela, então substituí-la testaria o mock. Slug inventado pelo modelo não pode
    virar linha no banco — ele nunca casaria com a escolha de nenhum usuário e só
    sujaria os dados.
    """
    resposta = '{"temas": [{"slug": "obesidade", "score": 0.9}, {"slug": "inventado", "score": 0.8}]}'
    monkeypatch.setattr(news_tagger_service, "get_client", lambda: _ClientFake(resposta))

    validos = await news_tagger_service._classificar(
        "Título", ABSTRACT_VALIDO, None, {"obesidade": "Obesidade"}
    )

    assert [t["slug"] for t in validos] == ["obesidade"]


@asyncio
async def test_classificar_normaliza_score_fora_da_faixa(monkeypatch):
    resposta = '{"temas": [{"slug": "obesidade", "score": 7.5}]}'
    monkeypatch.setattr(news_tagger_service, "get_client", lambda: _ClientFake(resposta))

    validos = await news_tagger_service._classificar(
        "Título", ABSTRACT_VALIDO, None, {"obesidade": "Obesidade"}
    )

    assert validos[0]["score"] == 1.0


@asyncio
async def test_classificar_devolve_vazio_se_o_modelo_falhar(monkeypatch):
    """
    Falhar para lista vazia e não levantar é deliberado: um artigo sem tema é
    ruim mas recuperável (a vigilância acusa), enquanto uma exceção aqui
    derrubaria o lote inteiro.
    """
    monkeypatch.setattr(news_tagger_service, "get_client", lambda: _ClientFake("isto não é json"))

    validos = await news_tagger_service._classificar(
        "Título", ABSTRACT_VALIDO, None, {"obesidade": "Obesidade"}
    )

    assert validos == []


@asyncio
async def test_tagger_grava_vinculos_do_artigo(db, monkeypatch):
    tema = Topic(slug="obesidade", nome_pt="Obesidade e tratamento do peso")
    db.add(tema)
    await db.flush()

    art = await _artigo(db, status=ArticleStatus.COLLECTED.value, external_id="tag-1")

    async def classifica(*a, **kw):
        return [{"slug": "obesidade", "score": 0.9}]

    monkeypatch.setattr(news_tagger_service, "_classificar", classifica)

    await news_tagger_service.taggear_lote(db)

    vinculos = list(await db.scalars(
        select(ArticleTopic).where(ArticleTopic.article_id == art.id)
    ))
    assert len(vinculos) == 1
    assert vinculos[0].topic_id == tema.id

    await db.refresh(art)
    assert art.status == ArticleStatus.TAGGED.value


@asyncio
async def test_artigo_sem_tema_ainda_avanca(db, monkeypatch):
    """
    Sem tema o artigo fica invisível no feed filtrado, mas travá-lo em
    `collected` esconderia conteúdo legítimo por limitação NOSSA de taxonomia.
    Ele avança e aparece em "ver tudo".
    """
    db.add(Topic(slug="obesidade", nome_pt="Obesidade"))
    await db.flush()

    art = await _artigo(db, status=ArticleStatus.COLLECTED.value, external_id="sem-tema")

    async def nada(*a, **kw):
        return []

    monkeypatch.setattr(news_tagger_service, "_classificar", nada)

    resultado = await news_tagger_service.taggear_lote(db)

    await db.refresh(art)
    assert art.status == ArticleStatus.TAGGED.value
    assert resultado["sem_tema"] == 1
