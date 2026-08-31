"""
Médico 360 — Palavras-chave que o médico cadastra para acompanhar.

POR QUE ISTO NÃO É "MAIS UM TEMA"
A taxonomia curada nunca vai cobrir "amiloidose cardíaca", "hipertensão
pulmonar" ou uma droga específica. O caminho óbvio — deixar o médico criar um
tema novo — falharia em silêncio: o tagger classifica os artigos escolhendo de
uma lista FECHADA, então um tema criado pelo usuário nunca seria atribuído a
nada. Ele veria o tema marcado na tela e receberia zero destaques para sempre,
sem erro, sem log, sem nada.

São dois eixos:

    tema           -> casa contra o que o TAGGER atribuiu (news.article_topics)
    palavra-chave  -> casa contra o TEXTO do artigo (Article.busca_tsv)

Unidos só na hora de montar o feed, e distinguidos no card.

DUAS REGRAS QUE SUSTENTAM O RESTO
1. Palavra-chave é ADITIVA, nunca subtrativa: só acrescenta ao feed. Se
   filtrasse, um erro de digitação esvaziaria a tela.
2. O preview (`contar_destaques`) é chamado ANTES de salvar. É o que mata a
   falha silenciosa no nascimento: o médico vê na hora que o termo não traz
   nada, em vez de concluir em duas semanas que o produto não presta.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.news import Article, ArticleStatus, UserKeyword

logger = logging.getLogger(__name__)


class TermoInvalido(ValueError):
    """Termo recusado na entrada. A mensagem vai direto para o usuário."""


def normalizar(termo: str) -> str:
    """
    Espaços colapsados e caixa baixa.

    A unicidade por usuário depende disto: sem normalizar, "Amiloidose" e
    "amiloidose " viram duas linhas que trazem exatamente o mesmo conteúdo.
    Acento é PRESERVADO — quem tira acento aqui é o dicionário `portuguese` do
    Postgres, na hora da busca, e ele faz isso melhor do que nós faríamos.
    """
    return " ".join(termo.split()).lower()


def validar(termo: str) -> str:
    """Normaliza e recusa o que não serve. Levanta `TermoInvalido`."""
    settings = get_settings()
    limpo = normalizar(termo)

    if len(limpo) < settings.news_keyword_min_chars:
        raise TermoInvalido(
            f"Use pelo menos {settings.news_keyword_min_chars} caracteres. "
            "Abreviações como “IC” trazem resultados demais e sem relação."
        )
    if len(limpo) > 80:
        raise TermoInvalido("Use um termo mais curto (até 80 caracteres).")
    return limpo


def _consulta(termo: str):
    """
    `plainto_tsquery` e não `to_tsquery`: o usuário digita "amiloidose cardíaca"
    em linguagem natural, e o segundo exigiria operadores booleanos escritos à
    mão. `plainto_tsquery` trata os termos como E lógico, que é o que a pessoa
    espera ao digitar duas palavras.
    """
    return func.plainto_tsquery(text("'portuguese'"), termo)


def _filtro_busca(termo: str):
    """
    Condição SQL de casamento textual.

    O QUE O PISO DE RANK FAZ, DE VERDADE
    Medido no banco: um artigo com o termo no TÍTULO ranqueia ~0,67; um que só o
    tem no corpo, ~0,24. O piso padrão (0,05) deixa os dois passarem — ele corta
    só o ruído marginal, e não a menção de passagem.

    Isso é deliberado, e não um piso mal calibrado. Palavra-chave é ADITIVA e
    foi escolhida a dedo pelo médico: cortar o que ele pediu porque o termo
    aparece "só" no corpo produziria o pior resultado possível — "cadastrei
    amiloidose e nunca chegou nada". Quem separa os dois casos é a ORDENAÇÃO por
    rank, não a exclusão: o artigo que FALA do assunto aparece primeiro.

    Subir `NEWS_KEYWORD_RANK_MINIMO` para ~0,3 torna a busca só-título. Está em
    configuração justamente para isso ser ajustável com dado de uso real.
    """
    settings = get_settings()
    consulta = _consulta(termo)
    return (
        Article.busca_tsv.op("@@")(consulta),
        func.ts_rank(Article.busca_tsv, consulta) >= settings.news_keyword_rank_minimo,
    )


async def listar(db: AsyncSession, user_id) -> list[UserKeyword]:
    return list(await db.scalars(
        select(UserKeyword)
        .where(UserKeyword.user_id == user_id)
        .order_by(UserKeyword.created_at)
    ))


async def contar_destaques(db: AsyncSession, termo: str) -> int:
    """
    Quantos destaques publicados o termo traria na janela do feed.

    É o preview mostrado enquanto a pessoa digita. Sem ele, cadastrar uma
    palavra-chave é um ato de fé cujo resultado só aparece dias depois — e um
    termo que não casa com nada é indistinguível de um produto quebrado.
    """
    settings = get_settings()
    desde = datetime.now(UTC) - timedelta(days=settings.news_feed_janela_dias)

    return (await db.execute(
        select(func.count())
        .select_from(Article)
        .where(
            Article.status == ArticleStatus.PUBLISHED.value,
            Article.visible_at >= desde,
            *_filtro_busca(termo),
        )
    )).scalar_one()


async def adicionar(db: AsyncSession, user_id, termo: str) -> UserKeyword:
    """Cadastra um termo. Levanta `TermoInvalido` se não servir ou se estourar o teto."""
    settings = get_settings()
    limpo = validar(termo)

    ja_existe = await db.scalar(
        select(UserKeyword).where(
            UserKeyword.user_id == user_id, UserKeyword.termo == limpo
        )
    )
    if ja_existe:
        return ja_existe  # idempotente: cadastrar duas vezes não é erro do usuário

    quantos = (await db.execute(
        select(func.count()).select_from(UserKeyword).where(UserKeyword.user_id == user_id)
    )).scalar_one()
    if quantos >= settings.news_max_keywords:
        raise TermoInvalido(
            f"Você já acompanha {settings.news_max_keywords} termos. "
            "Remova um para adicionar outro."
        )

    keyword = UserKeyword(user_id=user_id, termo=limpo)
    db.add(keyword)
    await db.flush()
    return keyword


async def remover(db: AsyncSession, user_id, termo: str) -> bool:
    limpo = normalizar(termo)
    alvo = await db.scalar(
        select(UserKeyword).where(
            UserKeyword.user_id == user_id, UserKeyword.termo == limpo
        )
    )
    if alvo is None:
        return False
    await db.delete(alvo)
    await db.flush()
    return True


async def artigos_por_palavras(
    db: AsyncSession,
    termos: list[str],
    desde: datetime,
    limite: int,
    excluir_ids: set[int] | None = None,
) -> list[tuple[Article, list[str]]]:
    """
    Destaques que casam com QUALQUER um dos termos, e quais termos casaram.

    Uma query por termo, e não uma só com OR: o custo é irrisório (no máximo 10
    termos, índice GIN, dezenas de artigos na janela) e em troca sabemos exatamente
    QUAL termo trouxe cada artigo — que é o que o card precisa mostrar. Com um OR
    único, essa informação se perde e o "por que estou vendo isto?" fica sem
    resposta.
    """
    if not termos:
        return []

    por_artigo: dict[int, tuple[Article, list[str]]] = {}

    for termo in termos:
        condicoes = [
            Article.status == ArticleStatus.PUBLISHED.value,
            Article.visible_at >= desde,
            *_filtro_busca(termo),
        ]
        if excluir_ids:
            condicoes.append(Article.id.notin_(excluir_ids))

        # Ordena por relevância antes da data: é isto — e não o piso — que
        # separa "artigo sobre amiloidose" de "artigo que a menciona".
        achados = await db.scalars(
            select(Article)
            .where(*condicoes)
            .order_by(
                func.ts_rank(Article.busca_tsv, _consulta(termo)).desc(),
                Article.visible_at.desc(),
            )
            .limit(limite)
        )
        for artigo in achados:
            if artigo.id in por_artigo:
                por_artigo[artigo.id][1].append(termo)
            else:
                por_artigo[artigo.id] = (artigo, [termo])

    # Casar com MAIS de um termo do usuário é o sinal mais forte que existe
    # aqui: ele pediu duas coisas e o artigo tem as duas. Depois, recência.
    ordenados = sorted(
        por_artigo.values(),
        key=lambda par: (
            len(par[1]),
            par[0].visible_at or datetime.min.replace(tzinfo=UTC),
        ),
        reverse=True,
    )
    return ordenados[:limite]


async def termos_mais_cadastrados(db: AsyncSession, limite: int = 30) -> list[tuple[str, int]]:
    """
    O que os médicos procuram e a taxonomia não cobre — a lista de compras dos
    temas que faltam.

    Não é usado por nenhuma tela: existe para responder, com dado real, a
    pergunta que hoje só teria resposta por palpite. Um termo cadastrado por
    dezenas de pessoas é candidato a virar tema curado, com score e
    transversalidade, em vez de simples casamento de texto.
    """
    linhas = (await db.execute(
        select(UserKeyword.termo, func.count().label("quantos"))
        .group_by(UserKeyword.termo)
        .order_by(func.count().desc())
        .limit(limite)
    )).all()
    return [(termo, quantos) for termo, quantos in linhas]
