"""
Médico 360 — Agente Redator de notícias.

Responsabilidade única: pegar Article já com temas atribuídos, gerar título +
corpo em HTML numa linguagem clara e clinicamente responsável, e publicar.

DESIGN DA PROMPT (preservado da versão original, que foi validada em produção)
- Fidelidade ao abstract; proibido inventar dados ou números.
- Tom didático mas profissional — não popularesco, não sensacionalista.
- A citação da fonte é montada de forma DETERMINÍSTICA em `_citacao_html`, não
  pelo modelo, o que elimina risco de citação incorreta.

SOBRE O FORMATO DA RESPOSTA
Usamos tool use da Anthropic em vez de pedir "responda em JSON" como texto
livre. Pedir JSON livre fazia `json.loads` quebrar esporadicamente quando o
`body_html` continha aspas duplas não escapadas (comum em nomes de escalas, ex:
escore "YEARS"). Tool use força campos já estruturados e validados contra o
schema, eliminando essa classe de erro.

POR QUE NÃO PASSA POR `ai_providers.complete()`
Aquele caminho só extrai blocos `text` da resposta e só conhece a ferramenta de
web search — ele não devolve `tool_use`. Roteá-lo por lá desmontaria exatamente
o mecanismo descrito acima. O que se aproveita de lá é o transporte: o
`http_client` compartilhado e o span de telemetria, que dão keep-alive, custo
contabilizado e rastreamento sem tocar no contrato da chamada.
"""

import logging

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.http_client import get_client
from app.core.telemetry import async_llm_span
from app.models.models import utcnow
from app.models.news import Article, ArticleStatus
from app.news.journals import JOURNALS_BY_SLUG

logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MAX_TOKENS = 1500

# Teto de retentativas por artigo. Uma falha aqui costuma ser transitória — o
# timeout de uma geração longa é o caso comum —, e o lote seguinte reprocessa.
# O teto existe para que o que NÃO tem conserto (abstract que o modelo recusa,
# journal com formato quebrado) pare de consumir chamada a cada rodada.
MAX_TENTATIVAS = 3

SYSTEM_PROMPT = """\
Você é um redator médico especializado em traduzir resumos de artigos científicos (abstracts) \
de journals de alto impacto (Lancet, JAMA, Nature Medicine, NEJM, BMJ) para uma comunidade de \
médicos e estudantes de medicina em português do Brasil.

Regras estritas:
1. NUNCA invente dados, números, resultados ou conclusões que não estejam no abstract original.
2. Se o abstract não deixar algo claro, não complete a lacuna — omita ou seja genérico.
3. Tom: didático e acessível, mas clinicamente rigoroso e profissional. Não é para leigos, \
é para quem já tem formação médica ou está se formando.
4. Estrutura sugerida do corpo: (1) contexto/pergunta clínica em 1-2 frases, (2) o que foi \
feito (desenho do estudo, população, em poucas linhas), (3) principais achados, (4) relevância \
prática para a rotina clínica ou formação.
5. Não use jargão estatístico sem explicar rapidamente o que significa (ex: não apenas "HR 0.72", \
mas "risco 28% menor").
6. Use a ferramenta `submit_post` para enviar o resultado — não escreva a resposta como texto.

O campo body_html deve ser HTML simples e válido: parágrafos em <p>, pode usar \
<strong> e <ul>/<li> quando fizer sentido. Não inclua <html>, <head> ou <body> — apenas o \
conteúdo interno do post.
"""

TOOL_SCHEMA = {
    "name": "submit_post",
    "description": "Envia o título e o corpo HTML do post reescrito.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Título do post em português"},
            "body_html": {"type": "string", "description": "Corpo do post em HTML simples"},
        },
        "required": ["title", "body_html"],
    },
}


def _prompt_usuario(article: Article, journal: str) -> str:
    autores = f"Autores: {article.authors}\n" if article.authors else ""
    return f"""\
Journal: {journal}
Título original: {article.original_title}
{autores}Abstract original:
{article.original_abstract}

Gere o título e o corpo do post seguindo as regras do sistema. Não inclua parágrafo de fonte/citação \
no final — isso é adicionado automaticamente depois.
"""


def _citacao_html(article: Article, journal: str) -> str:
    """
    Monta a referência à fonte sem passar pelo LLM, para garantir que autores,
    título e journal fiquem exatamente como foram coletados.
    """
    autores = f"{article.authors}. " if article.authors else ""
    return f"<p><em>Fonte: {autores}{article.original_title or ''} — {journal}.</em></p>"


async def redigir(article: Article, journal: str, timeout: int = 120) -> tuple[str, str]:
    """
    Chama o Claude para reescrever um artigo. Retorna (título, corpo_html).

    Levanta ValueError se o modelo não chamar a ferramenta ou devolver campo vazio.
    """
    settings = get_settings()
    client = get_client()
    prompt = _prompt_usuario(article, journal)

    payload = {
        "model": settings.news_writer_model,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "tools": [TOOL_SCHEMA],
        # `tool_choice` forçado é o que garante saída estruturada. Sem ele o
        # modelo às vezes responde em texto e voltamos ao parsing frágil.
        "tool_choice": {"type": "tool", "name": "submit_post"},
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    async with async_llm_span("anthropic", settings.news_writer_model, prompt):
        resp = await client.post(ANTHROPIC_URL, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()

    bloco = next((b for b in data.get("content", []) if b.get("type") == "tool_use"), None)
    if bloco is None:
        raise ValueError("Resposta do modelo não incluiu a chamada da ferramenta submit_post")

    titulo = bloco.get("input", {}).get("title")
    corpo = bloco.get("input", {}).get("body_html")
    if not titulo or not corpo:
        raise ValueError("Resposta do modelo veio com título ou corpo vazio")

    return titulo, f"{corpo}\n{_citacao_html(article, journal)}"


async def redigir_lote(db: AsyncSession, tamanho_lote: int = 10) -> dict:
    """
    Processa até `tamanho_lote` artigos com status `tagged`, publicando-os.

    A INVARIANTE: sem abstract, sem texto.
    Um artigo sem abstract vira `skipped_no_abstract` e NUNCA chega ao modelo.
    Escrever um post a partir de um título solto é o cenário de maior risco de
    alucinação num produto médico — e a guarda mora aqui, na fronteira perigosa,
    justamente para valer independentemente da fonte que coletou o item. O
    coletor já descarta itens sem abstract, mas confiar nisso significaria que
    qualquer fonte nova precisaria lembrar de repetir a regra.

    `skipped_no_abstract` não é `failed`: não houve erro, houve ausência de
    matéria-prima. Misturar os dois faria a fila de falhas encher de itens que
    não têm conserto e esconderia as falhas de verdade.
    """
    # `tagged` são os novos; `failed` abaixo do teto são os que merecem outra
    # chance. Um `ReadTimeout` do modelo não é veredito sobre o artigo — sem
    # esta segunda linha, `retry_count` seria incrementado e nunca lido, e todo
    # timeout viraria perda permanente de uma notícia.
    resultado = await db.execute(
        select(Article)
        .options(selectinload(Article.topics))
        .where(
            or_(
                Article.status == ArticleStatus.TAGGED.value,
                and_(
                    Article.status == ArticleStatus.FAILED.value,
                    Article.retry_count < MAX_TENTATIVAS,
                ),
            )
        )
        # Os novos primeiro: uma retentativa não deve atrasar a fila corrente.
        .order_by(Article.retry_count.asc(), Article.id.asc())
        .limit(tamanho_lote)
        .with_for_update(skip_locked=True)
    )
    artigos = list(resultado.scalars())

    publicados, falhas, pulados = 0, 0, 0

    for article in artigos:
        if not article.original_abstract or not article.original_abstract.strip():
            logger.warning(
                "Artigo id=%s sem abstract: não será redigido (pmid=%s)",
                article.id, article.external_id,
            )
            article.status = ArticleStatus.SKIPPED_NO_ABSTRACT.value
            pulados += 1
            await db.flush()
            continue

        article.status = ArticleStatus.WRITING.value
        await db.flush()

        config = JOURNALS_BY_SLUG.get(article.journal_slug)
        journal = config.display_name if config else article.journal_slug

        try:
            titulo, corpo = await redigir(article, journal)
            article.rewritten_title = titulo
            article.rewritten_body = corpo
            # Publicar é marcar visibilidade. Não há mais chamada externa a um
            # CMS: o texto já está aqui, e o feed personalizado precisa servi-lo
            # por usuário — coisa que um CMS de página única não consegue fazer.
            article.visible_at = utcnow()
            article.status = ArticleStatus.PUBLISHED.value
            publicados += 1
        except Exception as exc:
            article.status = ArticleStatus.FAILED.value
            article.last_error = str(exc)[:2000]
            article.retry_count += 1
            falhas += 1
            # Enquanto há retentativa pela frente, isto é ruído esperado (um
            # timeout do modelo costuma passar na rodada seguinte). Só o
            # esgotamento é notícia: dali em diante o artigo não volta à fila
            # sozinho, e ninguém seria avisado se o log não distinguisse.
            if article.retry_count >= MAX_TENTATIVAS:
                logger.exception(
                    "Artigo id=%s desistido após %d tentativas",
                    article.id, article.retry_count,
                )
            else:
                logger.warning(
                    "Falha ao redigir artigo id=%s (tentativa %d/%d, será reprocessado): %s",
                    article.id, article.retry_count, MAX_TENTATIVAS, exc,
                )

        await db.flush()

    logger.info(
        "Redator: %d publicado(s), %d falha(s), %d sem abstract",
        publicados, falhas, pulados,
    )
    return {"publicados": publicados, "falhas": falhas, "sem_abstract": pulados}
