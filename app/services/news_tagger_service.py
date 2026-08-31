"""
Médico 360 — Agente Tagger: atribui temas aos artigos coletados.

É a peça que resolve a queixa que originou o módulo: médico não tolera conteúdo
fora da sua área. Sem tema, não há como filtrar; com tema livre, o filtro não
funciona. Daí o vocabulário CONTROLADO (`news.topics`).

POR QUE O VOCABULÁRIO É FECHADO
Pedindo tema livre, o modelo devolve "IC", "insuficiência cardíaca" e "ICFEr"
para três artigos do mesmo assunto. Como a escolha do usuário guarda um slug, o
casamento passa a depender de o modelo repetir a mesma grafia — e ele não repete.
Slug fora da lista é DESCARTADO com log, nunca inserido.

MESH É SINAL SECUNDÁRIO, NÃO ESPINHA DORSAL
Os descritores MeSH são vocabulário médico controlado de verdade, e vêm de graça
no XML do PubMed. Mas a indexação MEDLINE atrasa semanas, e a janela de coleta é
de 10 dias: a maioria dos artigos recém-coletados ainda está ahead-of-print, sem
MeSH nenhum. Então MeSH entra como PISTA no prompt e como reforço de score
quando existe — quem sempre funciona é o modelo.

Mesmo padrão de `app/services/specialty_detector.py`: modelo barato,
temperatura 0, resposta validada contra lista fechada.
"""

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.http_client import get_client
from app.models.news import Article, ArticleStatus, ArticleTopic, Topic

logger = logging.getLogger(__name__)

MODELO = "gpt-5.4-nano"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

# Reforço aplicado ao score quando um descritor MeSH marcado como tópico
# PRINCIPAL do artigo bate com o tema. Modesto de propósito: MeSH corrobora, não
# manda — e um artigo sem MeSH (o caso comum) não pode ficar em desvantagem.
BONUS_MESH_MAJOR = 0.15

PROMPT = """Você classifica artigos científicos médicos por tema, para um feed \
personalizado de médicos brasileiros.

Escolha APENAS temas da lista abaixo. Nunca invente um tema que não esteja nela.
No JSON, use o identificador que vem ANTES do sinal de igual — nunca o nome por extenso.

TEMAS VÁLIDOS (identificador = nome):
{temas}

Regras:
- Escolha de 1 a 5 temas. Prefira poucos e certeiros a muitos e vagos.
- Atribua a cada tema um score de 0.0 a 1.0: quanto o artigo é SOBRE aquele tema.
  1.0 = é o assunto central do artigo. 0.3 = tangencia, é mencionado.
- Temas transversais são esperados e desejáveis. Um ensaio de semaglutida em \
pacientes obesos com insuficiência cardíaca legitimamente recebe obesidade, \
diabetes e insuficiência cardíaca ao mesmo tempo.
- Se nenhum tema da lista se aplicar de verdade, devolva uma lista vazia. \
Forçar um tema errado é pior que não classificar.

Responda APENAS com JSON no formato:
{{"temas": [{{"slug": "...", "score": 0.0}}]}}

{mesh}TÍTULO: {titulo}

ABSTRACT:
{abstract}"""


async def _classificar(titulo: str, abstract: str, mesh: list[dict] | None, temas: dict[str, str]) -> list[dict]:
    """
    Pede ao modelo os temas do artigo. Devolve [{"slug", "score"}] já validado
    contra o vocabulário; em qualquer falha, devolve lista vazia.

    Falhar para lista vazia e não levantar é deliberado: um artigo sem tema fica
    invisível no feed, o que é ruim mas recuperável (o `vigilancia_service`
    acusa), enquanto uma exceção aqui derrubaria o lote inteiro.
    """
    settings = get_settings()

    lista = "\n".join(f"- {slug}: {nome}" for slug, nome in temas.items())
    dica_mesh = ""
    if mesh:
        principais = [t["descriptor"] for t in mesh if t.get("major")]
        outros = [t["descriptor"] for t in mesh if not t.get("major")]
        if principais or outros:
            dica_mesh = (
                "TERMOS MeSH ATRIBUÍDOS PELA NLM (use como pista, não como resposta):\n"
                f"  principais: {', '.join(principais) or '(nenhum)'}\n"
                f"  demais: {', '.join(outros[:15]) or '(nenhum)'}\n\n"
            )

    prompt = PROMPT.format(
        temas=lista,
        mesh=dica_mesh,
        titulo=titulo,
        abstract=(abstract or "")[:6000],
    )

    try:
        client = get_client()
        resp = await client.post(
            OPENAI_URL,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODELO,
                "messages": [{"role": "user", "content": prompt}],
                "max_completion_tokens": 300,
                "temperature": 0,
            },
            timeout=30,
        )
        resp.raise_for_status()
        bruto = resp.json()["choices"][0]["message"]["content"].strip()
        bruto = bruto.replace("```json", "").replace("```", "").strip()
        itens = json.loads(bruto).get("temas", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tagger falhou ao classificar %r: %s", titulo[:80], exc)
        return []

    validos: list[dict] = []
    descartados: list[str] = []
    for item in itens:
        slug = str(item.get("slug", "")).strip()
        # Tolerância a resposta com o rótulo colado ("slug = nome" ou "slug: nome").
        # O prompt já pede só o identificador; isto é defesa em profundidade,
        # porque o modo de falha é uma classificação certa virar lista vazia.
        if slug not in temas:
            for separador in (" = ", ":", "="):
                if separador in slug and slug.split(separador)[0].strip() in temas:
                    slug = slug.split(separador)[0].strip()
                    break
        if slug not in temas:
            # Pode ser assunto que a taxonomia ainda não cobre — candidato a tema
            # novo. WARNING e não INFO: quando isto acontece com TODOS os itens, o
            # artigo fica sem tema nenhum e o sintoma é indistinguível de
            # "nada se aplica". Foi assim que um defeito de prompt passou batido.
            descartados.append(slug)
            continue
        try:
            score = max(0.0, min(1.0, float(item.get("score", 0))))
        except (TypeError, ValueError):
            continue
        # Score zero é o modelo dizendo "não é sobre isto". Medido em produção:
        # ele preenche a lista até 5 itens com zeros — um carcinoma hepatocelular
        # voltou com "Câncer de mama 0.00" e "Neoplasias hematológicas 0.00".
        # Guardar isso é sujar `article_topics` com linhas que nenhuma query usa.
        if score <= 0:
            continue
        validos.append({"slug": slug, "score": score})

    if descartados:
        logger.warning(
            "Tagger descartou %d slug(s) fora do vocabulário em %r: %s",
            len(descartados), titulo[:60], descartados,
        )

    return validos


def _aplicar_bonus_mesh(temas: list[dict], mesh: list[dict] | None, nomes: dict[str, str]) -> list[dict]:
    """
    Reforça o score de temas cujo nome aparece entre os descritores MeSH
    principais. Casamento por substring, propositalmente simples: MeSH é sinal
    de apoio, e um mapeamento MeSH->tema completo seria um projeto próprio.
    """
    if not mesh:
        return temas

    principais = " | ".join(t["descriptor"].lower() for t in mesh if t.get("major"))
    if not principais:
        return temas

    for tema in temas:
        nome = nomes.get(tema["slug"], "").lower()
        if nome and nome in principais:
            tema["score"] = min(1.0, tema["score"] + BONUS_MESH_MAJOR)
            tema["origem"] = "mesh"

    return temas


async def taggear_lote(db: AsyncSession, tamanho_lote: int = 20) -> dict:
    """
    Classifica até `tamanho_lote` artigos `collected`, movendo-os para `tagged`.

    Artigo que não recebe tema nenhum AINDA avança para `tagged`: ele será
    redigido e publicado, apenas não casará com nenhum filtro — vai aparecer só
    para quem pedir "ver tudo". Travá-lo aqui esconderia conteúdo legítimo por
    uma limitação nossa de taxonomia.
    """
    temas_rows = list(await db.scalars(select(Topic).where(Topic.ativo.is_(True))))
    if not temas_rows:
        logger.error("Nenhum tema ativo em news.topics — o tagger não tem vocabulário")
        return {"taggeados": 0, "sem_tema": 0, "erro": "vocabulario_vazio"}

    nomes = {t.slug: t.nome_pt for t in temas_rows}
    por_slug = {t.slug: t for t in temas_rows}

    resultado = await db.execute(
        select(Article)
        .where(Article.status == ArticleStatus.COLLECTED.value)
        .limit(tamanho_lote)
        .with_for_update(skip_locked=True)
    )
    artigos = list(resultado.scalars())

    taggeados, sem_tema = 0, 0

    for article in artigos:
        atribuidos = await _classificar(
            article.original_title, article.original_abstract or "", article.mesh_terms, nomes
        )
        atribuidos = _aplicar_bonus_mesh(atribuidos, article.mesh_terms, nomes)

        for tema in atribuidos:
            db.add(
                ArticleTopic(
                    article_id=article.id,
                    topic_id=por_slug[tema["slug"]].id,
                    score=tema["score"],
                    origem=tema.get("origem", "llm"),
                )
            )

        if atribuidos:
            taggeados += 1
        else:
            sem_tema += 1
            logger.info("Artigo id=%s ficou sem nenhum tema", article.id)

        article.status = ArticleStatus.TAGGED.value
        await db.flush()

    logger.info("Tagger: %d com tema, %d sem tema", taggeados, sem_tema)
    return {"taggeados": taggeados, "sem_tema": sem_tema}
