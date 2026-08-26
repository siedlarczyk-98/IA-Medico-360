"""
Metadados de referência da resposta (fontes + PubMed).

Estas funções são a correção do "as referências se perdem no histórico": antes,
as citações só existiam no evento SSE `done` e sumiam ao reabrir a conversa.

Sem banco de propósito — são funções puras, e o valor delas está justamente em
não depender do pipeline inteiro para serem verificadas.
"""

from dataclasses import dataclass, field

from app.services.response_metadata import build_response_metadata, read_response_metadata

# ── Dublês do resultado de validate_with_pubmed ──────────────────────────────
# O helper é duck-typed de propósito (não importa o serviço de PubMed só para
# uma anotação), então o teste espelha só a forma que ele consome.

@dataclass
class CitacaoFake:
    title: str | None = "Diretriz de cefaleia"
    pmid: str | None = "12345"
    verified: bool = True


@dataclass
class GuidelineFake:
    pmid: str = "99999"
    article_title: str = "Novo consenso 2026"
    abstract_snippet: str | None = "Trecho do resumo."


@dataclass
class PubmedFake:
    cited_guidelines_verified: list = field(default_factory=list)
    newer_guidelines_found: list = field(default_factory=list)


# ── build_response_metadata ──────────────────────────────────────────────────

def test_sem_nada_devolve_none():
    # Coluna nullable: gravar {} encheria o banco de objetos vazios.
    assert build_response_metadata() is None
    assert build_response_metadata(pubmed=PubmedFake(), citations=[]) is None


def test_guarda_citacoes():
    meta = build_response_metadata(citations=["https://a.com", "https://b.com"])
    assert meta == {"citations": ["https://a.com", "https://b.com"]}


def test_guarda_pubmed_nas_duas_listas():
    meta = build_response_metadata(
        pubmed=PubmedFake(
            cited_guidelines_verified=[CitacaoFake()],
            newer_guidelines_found=[GuidelineFake()],
        )
    )
    validacao = meta["pubmed_validation"]
    assert validacao["cited_verified"] == [
        {"title": "Diretriz de cefaleia", "pmid": "12345", "verified": True}
    ]
    assert validacao["newer_guidelines"] == [
        {"pmid": "99999", "article_title": "Novo consenso 2026", "abstract_snippet": "Trecho do resumo."}
    ]


def test_distingue_citacao_verificada_de_nao_verificada():
    # É esta distinção que a tabela pubmed_validations NÃO consegue guardar:
    # uma citação não verificada e uma diretriz nova ficam ambas com
    # relevance_score 0.0. Daí o JSONB.
    meta = build_response_metadata(
        pubmed=PubmedFake(cited_guidelines_verified=[
            CitacaoFake(title="Confere", pmid="1", verified=True),
            CitacaoFake(title="Não confere", pmid="2", verified=False),
        ])
    )
    citadas = meta["pubmed_validation"]["cited_verified"]
    assert [c["verified"] for c in citadas] == [True, False]


def test_pubmed_vazio_nao_cria_bloco():
    # Bloco "Referências verificadas" vazio na tela é pior que bloco nenhum.
    meta = build_response_metadata(pubmed=PubmedFake(), citations=["https://a.com"])
    assert "pubmed_validation" not in meta
    assert meta["citations"] == ["https://a.com"]


def test_snippet_vazio_vira_none():
    meta = build_response_metadata(
        pubmed=PubmedFake(newer_guidelines_found=[GuidelineFake(abstract_snippet="")])
    )
    assert meta["pubmed_validation"]["newer_guidelines"][0]["abstract_snippet"] is None


def test_citacoes_sao_copiadas_e_nao_referenciadas():
    # Guardar a lista do chamador deixaria o metadata mudar por baixo se ele
    # continuasse mexendo nela antes do commit.
    original = ["https://a.com"]
    meta = build_response_metadata(citations=original)
    original.append("https://intruso.com")
    assert meta["citations"] == ["https://a.com"]


# ── read_response_metadata ───────────────────────────────────────────────────

def test_le_de_volta_o_que_gravou():
    meta = build_response_metadata(
        pubmed=PubmedFake(cited_guidelines_verified=[CitacaoFake()]),
        citations=["https://a.com"],
    )
    citations, pubmed = read_response_metadata(meta)
    assert citations == ["https://a.com"]
    assert pubmed["cited_verified"][0]["pmid"] == "12345"


def test_conversa_antiga_sem_metadata_nao_quebra():
    # Não há backfill: respostas gravadas antes desta mudança têm a coluna nula.
    # Este caminho é permanente, não transitório.
    assert read_response_metadata(None) == ([], None)


def test_metadata_do_agregador_so_com_citations():
    # O agregador já gravava {"citations": [...]} — precisa continuar legível.
    citations, pubmed = read_response_metadata({"citations": ["https://a.com"]})
    assert citations == ["https://a.com"]
    assert pubmed is None


def test_metadata_corrompido_nao_derruba_a_conversa():
    # Uma conversa inteira não deve sumir da tela por causa de um JSONB torto.
    assert read_response_metadata("texto solto") == ([], None)
    assert read_response_metadata({"citations": "nao-e-lista"}) == ([], None)
    assert read_response_metadata({"pubmed_validation": []}) == ([], None)
