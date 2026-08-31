"""
Atribui temas a destaques que foram publicados ANTES do tagger existir.

    python -m scripts.taggear_acervo_noticias            # dry-run: só mostra
    python -m scripts.taggear_acervo_noticias --aplicar  # grava

Por que existe: o pipeline novo classifica na coleta (`collected` -> `tagged`),
mas o acervo herdado da migração já está `published`. Sem tema, esses artigos
não casam com nenhum usuário — aparecem só em "Ver tudo" ou como preenchimento,
nunca no feed filtrado. Este script é de uso único, mas fica no repositório
porque a mesma situação se repete se a taxonomia ganhar temas novos e alguém
quiser reclassificar o acervo.

NÃO altera `status` nem `visible_at`: os artigos já estão publicados e visíveis,
e o que falta neles é só a etiqueta.

O dry-run é o modo padrão de propósito. Antes de gravar 66 classificações no
banco de produção, alguém precisa OLHAR se elas fazem sentido — é a única
verificação real que a taxonomia tem, já que ela nasceu de um rascunho de
engenharia e ainda não passou por revisão médica.
"""

import argparse
import asyncio
import sys

from sqlalchemy import func, select

from app.core.database import async_session_factory
from app.models.news import Article, ArticleStatus, ArticleTopic, Topic
from app.services import news_tagger_service

# Chamadas simultâneas ao modelo. Baixo de propósito: são poucas dezenas de
# artigos e não há pressa — estourar rate limit para economizar 40 segundos
# seria trocar risco por nada.
SIMULTANEAS = 4


async def _sem_tema(db) -> list[Article]:
    """Publicados que não têm nenhuma linha em article_topics."""
    return list(await db.scalars(
        select(Article)
        .where(
            Article.status == ArticleStatus.PUBLISHED.value,
            ~select(ArticleTopic.id)
            .where(ArticleTopic.article_id == Article.id)
            .exists(),
        )
        .order_by(Article.visible_at.desc())
    ))


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="Grava no banco. Sem esta flag, apenas mostra o que faria.",
    )
    parser.add_argument("--limite", type=int, default=0, help="Processa no máximo N artigos (0 = todos)")
    args = parser.parse_args()

    async with async_session_factory() as db:
        temas = list(await db.scalars(select(Topic).where(Topic.ativo.is_(True))))
        if not temas:
            print("ERRO: news.topics está vazio — rode `alembic upgrade head` antes.")
            return 1

        nomes = {t.slug: t.nome_pt for t in temas}
        por_slug = {t.slug: t for t in temas}

        artigos = await _sem_tema(db)
        if args.limite:
            artigos = artigos[: args.limite]

        if not artigos:
            print("Nenhum destaque publicado sem tema. Nada a fazer.")
            return 0

        modo = "APLICANDO" if args.aplicar else "DRY-RUN (nada será gravado)"
        print(f"{modo} — {len(artigos)} destaque(s) sem tema, {len(temas)} temas no vocabulário.\n")

        limitador = asyncio.Semaphore(SIMULTANEAS)

        async def classificar(art: Article):
            async with limitador:
                achados = await news_tagger_service._classificar(
                    art.original_title, art.original_abstract or "", art.mesh_terms, nomes
                )
                return art, news_tagger_service._aplicar_bonus_mesh(achados, art.mesh_terms, nomes)

        resultados = await asyncio.gather(*(classificar(a) for a in artigos))

        sem_nenhum = 0
        for art, achados in resultados:
            titulo = (art.rewritten_title or art.original_title)[:66]
            if not achados:
                sem_nenhum += 1
                print(f"  [SEM TEMA] {titulo}")
                continue

            etiquetas = ", ".join(f"{nomes[t['slug']]} {t['score']:.2f}" for t in achados)
            print(f"  {titulo}\n      -> {etiquetas}")

            if args.aplicar:
                for tema in achados:
                    db.add(ArticleTopic(
                        article_id=art.id,
                        topic_id=por_slug[tema["slug"]].id,
                        score=tema["score"],
                        origem=tema.get("origem", "llm"),
                    ))

        if args.aplicar:
            await db.commit()

        total_vinculos = sum(len(a) for _, a in resultados)
        print(
            f"\n{len(artigos) - sem_nenhum} classificado(s), {sem_nenhum} sem nenhum tema, "
            f"{total_vinculos} vínculo(s) {'gravado(s)' if args.aplicar else 'previsto(s)'}."
        )
        if sem_nenhum:
            # Não é falha do script: pode ser assunto que a taxonomia não cobre.
            # Vale olhar quais são — são candidatos a tema novo.
            print("Artigos sem tema são candidatos a lacuna na taxonomia; vale revisar a lista acima.")
        if not args.aplicar:
            print("Nada foi gravado. Revise a lista e rode de novo com --aplicar.")

        # Contagem final para conferir que a query de seleção estava certa.
        restantes = (await db.execute(
            select(func.count()).select_from(Article).where(
                Article.status == ArticleStatus.PUBLISHED.value,
                ~select(ArticleTopic.id).where(ArticleTopic.article_id == Article.id).exists(),
            )
        )).scalar_one()
        print(f"Publicados ainda sem tema: {restantes}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
