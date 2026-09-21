"""
Médico 360 — Direitos do titular (LGPD) e retenção.

A exclusão de conta vive em `auth_repository.apagar_dados_do_usuario`. Aqui ficam
os outros dois direitos, e o mapa que amarra os três (`DESTINO_DOS_DADOS`):

  Portabilidade (art. 18, V)  → `exportar_dados`
  Retenção / expurgo (art. 16) → `expurgar_dados_vencidos`

Sobre retenção: `FileExtraction` guarda o texto extraído do arquivo e, no caso de
imagem, o base64 da própria imagem. É o dado mais sensível da base — uma foto de
exame ou de receita, que o DLP não cobre (ele atua em texto). Por isso a imagem
tem prazo próprio, bem mais curto que o resto.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.calculators import CalculatorDefinition, CalculatorExecution, CalculatorFavorite
from app.models.landing_pages import LandingPage, Submission
from app.models.models import (
    ConsentLog,
    Conversation,
    FileExtraction,
    Folder,
    Interaction,
    SemanticCache,
    User,
    UserPreference,
    UserWeeklyUsage,
)
from app.models.news import Article, Favorite, Topic, TopicFeedback, UserKeyword, UserTopic

logger = logging.getLogger(__name__)

# Prazos de retenção. Escolhidos pelo grau de sensibilidade, não por conveniência.
RETENCAO_IMAGEM_DIAS = 30       # imagem crua de exame/receita — o mais sensível
RETENCAO_ARQUIVO_DIAS = 180     # texto extraído de arquivo
RETENCAO_CACHE_DIAS = 30        # cache semântico (já tem expires_at próprio)


# ── O destino de cada tabela ligada ao titular ───────────────────────────
#
# Toda tabela que chega em `users` por chave estrangeira, direta ou
# transitivamente, PRECISA estar aqui, dizendo o que acontece com ela na exclusão
# de conta e na exportação. `tests/test_destino_dos_dados.py` calcula o conjunto a
# partir do metadata e reprova se faltar alguma — mesmo mecanismo do
# `ROUTE_POLICY`. Tabela nova ligada a usuário sem destino declarado quebra o CI.
#
# Existe porque os dois direitos falharam do mesmo jeito, por esquecimento: a
# exclusão dava erro 500 para toda conta real (quatro tabelas fora da cascata) e
# a exportação omitia pastas, consentimentos, calculadoras e notícias. Nos dois
# casos alguém criou a tabela e não havia nada que obrigasse a voltar aqui.
#
# Exclusão:   apaga       — `DELETE` explícito em `apagar_dados_do_usuario`
#             cascata     — o banco apaga sozinho (`ON DELETE CASCADE`)
#             anonimiza   — a linha fica, sem `user_id`, IP nem user-agent
#             desvincula  — a linha fica, só perde a referência
# Exportação: a chave do JSON onde o dado sai, ou `None` com o motivo ao lado.

APAGA, CASCATA, ANONIMIZA, DESVINCULA = "apaga", "cascata", "anonimiza", "desvincula"

DESTINO_DOS_DADOS: dict[str, tuple[str, str | None, str]] = {
    # tabela: (na exclusão, chave na exportação, motivo/observação)
    "conversations": (APAGA, "conversas", ""),
    "interactions": (APAGA, "conversas", "dentro de cada conversa"),
    "interaction_responses": (APAGA, "conversas", "dentro de cada interação"),
    "interaction_medications": (APAGA, None, "metadado derivado da resposta, que já é exportada"),
    "pubmed_validations": (APAGA, None, "metadado derivado da resposta, que já é exportada"),
    "pharma_alerts": (APAGA, None, "metadado derivado da resposta, que já é exportada"),
    "message_embeddings": (CASCATA, None, "cópia vetorial do texto das conversas, que já é exportado"),
    "folders": (APAGA, "pastas", "inclui o contexto clínico, o texto livre mais sensível"),
    "file_extractions": (CASCATA, "arquivos_enviados", "sem o base64 da imagem"),
    "user_preferences": (APAGA, "preferencias", ""),
    "user_weekly_usage": (APAGA, "uso_semanal", ""),
    "consent_logs": (ANONIMIZA, "consentimentos", "decisão de 2026-09-21: a prova do consentimento sobrevive"),
    "audit_logs": (ANONIMIZA, None, "trilha de segurança interna; não é dado fornecido pelo titular"),
    "invite_tokens": (
        DESVINCULA, None,
        "convite criado pelo titular para terceiro; o endereçado a ele é apagado pelo e-mail",
    ),
    "calculators.calculator_executions": (APAGA, "calculadoras", "entrada clínica digitada pelo titular"),
    "calculators.calculator_favorites": (CASCATA, "calculadoras", ""),
    "news.user_topics": (CASCATA, "noticias", ""),
    "news.user_keywords": (CASCATA, "noticias", ""),
    "news.favorites": (CASCATA, "noticias", ""),
    "news.topic_feedback": (CASCATA, "noticias", ""),
    "news.digest_sends": (CASCATA, None, "registro operacional de envio; o conteúdo são artigos públicos"),
    # PENDENTE DE DECISÃO: o formulário guarda nome, e-mail, telefone e as
    # respostas (faturamento incluso) e hoje SOBREVIVE à exclusão da conta, só
    # sem o vínculo. É dado pessoal; falta decidir se o pedido de eliminação o
    # alcança ou se o lead, já entregue ao parceiro, tem base legal própria.
    "landing_pages.submissions": (DESVINCULA, "formularios_enviados", "ver nota acima"),
    "landing_pages.accounting_answers": (DESVINCULA, "formularios_enviados", "segue a submissão"),
    "landing_pages.accounting_pain_selections": (DESVINCULA, "formularios_enviados", "segue a submissão"),
    "landing_pages.benefit_selections": (DESVINCULA, "formularios_enviados", "segue a submissão"),
    "landing_pages.calculator_selections": (DESVINCULA, "formularios_enviados", "segue a submissão"),
    "landing_pages.finance_answers": (DESVINCULA, "formularios_enviados", "segue a submissão"),
    "landing_pages.partner_answers": (DESVINCULA, "formularios_enviados", "segue a submissão"),
    "landing_pages.partner_category_selections": (DESVINCULA, "formularios_enviados", "segue a submissão"),
}


def _iso(momento) -> str | None:
    return momento.isoformat() if momento else None


def _limite(dias: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=dias)


# ── Portabilidade ────────────────────────────────────────────────────────

async def exportar_dados(db: AsyncSession, user: User) -> dict:
    """
    Todos os dados do titular em formato legível e autocontido.

    Inclui o histórico clínico como o médico o escreveu — este é o dado DELE,
    entregue a ele. Não inclui id interno de outras entidades nem nada de outro
    usuário.
    """
    conversas = (
        await db.execute(
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .options(selectinload(Conversation.interactions).selectinload(Interaction.responses))
            .order_by(Conversation.created_at)
        )
    ).scalars().unique().all()

    arquivos = (
        await db.execute(
            select(FileExtraction)
            .where(FileExtraction.user_id == user.id)
            .order_by(FileExtraction.created_at)
        )
    ).scalars().all()

    pastas = (
        await db.execute(select(Folder).where(Folder.user_id == user.id).order_by(Folder.created_at))
    ).scalars().all()
    nome_da_pasta = {p.id: p.name for p in pastas}

    consentimentos = (
        await db.execute(
            select(ConsentLog).where(ConsentLog.user_id == user.id).order_by(ConsentLog.created_at)
        )
    ).scalars().all()

    preferencias = (
        await db.execute(select(UserPreference).where(UserPreference.user_id == user.id))
    ).scalars().first()

    uso = (
        await db.execute(
            select(UserWeeklyUsage)
            .where(UserWeeklyUsage.user_id == user.id)
            .order_by(UserWeeklyUsage.week_start)
        )
    ).scalars().all()

    execucoes = (
        await db.execute(
            select(CalculatorExecution, CalculatorDefinition.name)
            .join(CalculatorDefinition, CalculatorDefinition.id == CalculatorExecution.calculator_id)
            .where(CalculatorExecution.user_id == user.id)
            .order_by(CalculatorExecution.created_at)
        )
    ).all()
    calculadoras_favoritas = (
        await db.execute(
            select(CalculatorDefinition.name)
            .join(CalculatorFavorite, CalculatorFavorite.calculator_id == CalculatorDefinition.id)
            .where(CalculatorFavorite.user_id == user.id)
            .order_by(CalculatorDefinition.name)
        )
    ).scalars().all()

    temas = (
        await db.execute(
            select(Topic.nome_pt)
            .join(UserTopic, UserTopic.topic_id == Topic.id)
            .where(UserTopic.user_id == user.id)
            .order_by(Topic.nome_pt)
        )
    ).scalars().all()
    palavras_chave = (
        await db.execute(
            select(UserKeyword.termo).where(UserKeyword.user_id == user.id).order_by(UserKeyword.termo)
        )
    ).scalars().all()
    noticias_favoritas = (
        await db.execute(
            select(Article.rewritten_title, Article.original_title, Article.source_url, Favorite.created_at)
            .join(Favorite, Favorite.article_id == Article.id)
            .where(Favorite.user_id == user.id)
            .order_by(Favorite.created_at)
        )
    ).all()
    nao_interessa = (
        await db.execute(
            select(Topic.nome_pt, TopicFeedback.specialty, TopicFeedback.created_at)
            .join(Topic, Topic.id == TopicFeedback.topic_id, isouter=True)
            .where(TopicFeedback.user_id == user.id)
            .order_by(TopicFeedback.created_at)
        )
    ).all()

    submissoes = (
        await db.execute(
            select(Submission, LandingPage.slug)
            .join(LandingPage, LandingPage.id == Submission.landing_page_id)
            .where(Submission.user_id == user.id)
            .order_by(Submission.created_at)
        )
    ).all()
    respostas_por_submissao = await _respostas_dos_formularios(db, [s.id for s, _ in submissoes])

    return {
        "exportado_em": datetime.now(UTC).isoformat(),
        "titular": {
            "email": user.email,
            "nome": user.name,
            "telefone": user.phone_number,
            "crm": user.crm,
            "crm_uf": user.crm_state,
            "especialidade": user.specialty,
            "situacao": user.med_status,
            "criado_em": user.created_at.isoformat() if user.created_at else None,
        },
        "conversas": [
            {
                "titulo": c.title,
                "modulo": c.feature,
                "pasta": nome_da_pasta.get(c.folder_id),
                "criada_em": c.created_at.isoformat() if c.created_at else None,
                "interacoes": [
                    {
                        "pergunta": i.prompt_text,
                        "modo": i.mode,
                        "em": i.started_at.isoformat() if i.started_at else None,
                        "respostas": [
                            {"modelo": r.model_used, "texto": r.response_text}
                            for r in sorted(i.responses, key=lambda r: r.created_at)
                            if not r.error_message
                        ],
                    }
                    for i in sorted(c.interactions, key=lambda i: i.started_at or datetime.min)
                ],
            }
            for c in conversas
        ],
        # Sem o base64: a exportação é um JSON para leitura, e embutir imagens o
        # tornaria inutilizável. O titular pode pedir os arquivos à parte.
        "arquivos_enviados": [
            {
                "nome": a.file_name,
                "tipo": a.file_type,
                "enviado_em": a.created_at.isoformat() if a.created_at else None,
                "texto_extraido": a.extracted_text,
                "tem_imagem_armazenada": bool(a.image_base64),
            }
            for a in arquivos
        ],
        # O contexto clínico da pasta é texto livre escrito pelo médico sobre o
        # caso — o conteúdo mais sensível da conta, e ficava de fora.
        "pastas": [
            {
                "nome": p.name,
                "tipo": p.folder_kind,
                "contexto_clinico": p.clinical_context,
                "criada_em": _iso(p.created_at),
                "atualizada_em": _iso(p.updated_at),
            }
            for p in pastas
        ],
        "consentimentos": [
            {
                "tipo": c.consent_type,
                "aceito": c.accepted,
                "aceito_em": _iso(c.accepted_at),
                "revogado_em": _iso(c.revoked_at),
                "ip": str(c.ip_address) if c.ip_address else None,
                "navegador": c.user_agent,
            }
            for c in consentimentos
        ],
        "preferencias": {
            "modelos_selecionados": preferencias.selected_models,
            "interface": preferencias.ui_settings,
            "notificacoes": preferencias.notification_prefs,
        } if preferencias else None,
        "uso_semanal": [
            {"semana_de": _iso(u.week_start), "custo_usd": str(u.total_cost_usd)} for u in uso
        ],
        "calculadoras": {
            "favoritas": list(calculadoras_favoritas),
            "execucoes": [
                {
                    "calculadora": nome,
                    "entradas": e.inputs,
                    "resultado": e.result,
                    "interpretacao": e.interpretation,
                    "em": _iso(e.created_at),
                }
                for e, nome in execucoes
            ],
        },
        "noticias": {
            "temas": list(temas),
            "palavras_chave": list(palavras_chave),
            "favoritos": [
                {"titulo": reescrito or original, "link": link, "salvo_em": _iso(quando)}
                for reescrito, original, link, quando in noticias_favoritas
            ],
            "marcados_como_nao_interessa": [
                {"tema": tema, "especialidade": especialidade, "em": _iso(quando)}
                for tema, especialidade, quando in nao_interessa
            ],
        },
        "formularios_enviados": [
            {
                "pagina": slug,
                "nome": s.name,
                "email": s.email,
                "telefone": s.phone,
                "consentimento_lgpd_em": _iso(s.lgpd_consent_at),
                "avisar_quando_disponivel": s.notify_on_availability,
                "enviado_em": _iso(s.created_at),
                "respostas": respostas_por_submissao.get(s.id, {}),
            }
            for s, slug in submissoes
        ],
    }


async def _respostas_dos_formularios(db: AsyncSession, submission_ids: list) -> dict:
    """
    Respostas de cada submissão, lidas de TODA tabela filha de `submissions`.

    Genérico de propósito: cada página de captação tem suas tabelas de resposta,
    e uma página nova cria outra. Descobrir as filhas pelo metadata faz a
    exportação acompanhar sozinha, em vez de depender de alguém lembrar daqui.
    """
    if not submission_ids:
        return {}

    tabela_mae = Submission.__table__
    saida: dict = {}
    for tabela in tabela_mae.metadata.tables.values():
        coluna_fk = next(
            (fk.parent for fk in tabela.foreign_keys if fk.column.table is tabela_mae), None
        )
        if coluna_fk is None:
            continue
        linhas = (await db.execute(select(tabela).where(coluna_fk.in_(submission_ids)))).mappings()
        for linha in linhas:
            dados = {
                k: (v.isoformat() if hasattr(v, "isoformat") else v)
                for k, v in linha.items()
                if k != coluna_fk.name and not k.endswith("id")
            }
            saida.setdefault(linha[coluna_fk.name], {}).setdefault(tabela.name, []).append(dados)
    return saida


# ── Retenção ─────────────────────────────────────────────────────────────

async def medir_passivo(db: AsyncSession) -> dict[str, int]:
    """
    Quanto já passou do prazo e continua no banco. Não apaga nada.

    Serve para responder "a política está sendo cumprida?" — pergunta que ficou
    sem resposta por 39 dias em 2026-08-27, quando o agendamento do expurgo
    parou sem avisar ninguém.

    `dias_de_atraso` é medido pelo registro vencido mais antigo: um alarme que
    diz só "existe passivo" não distingue um dia de esquecimento de um trimestre.
    """
    imagens = (await db.execute(
        select(func.count())
        .select_from(FileExtraction)
        .where(
            FileExtraction.image_base64.is_not(None),
            FileExtraction.created_at < _limite(RETENCAO_IMAGEM_DIAS),
        )
    )).scalar_one()

    arquivos = (await db.execute(
        select(func.count())
        .select_from(FileExtraction)
        .where(FileExtraction.created_at < _limite(RETENCAO_ARQUIVO_DIAS))
    )).scalar_one()

    mais_antigo = (await db.execute(
        select(func.min(FileExtraction.created_at)).where(
            FileExtraction.image_base64.is_not(None),
            FileExtraction.created_at < _limite(RETENCAO_IMAGEM_DIAS),
        )
    )).scalar_one()

    atraso = 0
    if mais_antigo:
        atraso = max((datetime.now(UTC) - mais_antigo).days - RETENCAO_IMAGEM_DIAS, 0)

    return {
        "imagens_vencidas": imagens,
        "arquivos_vencidos": arquivos,
        "dias_de_atraso": atraso,
        "total": imagens + arquivos,
    }


async def expurgar_dados_vencidos(db: AsyncSession) -> dict[str, int]:
    """
    Apaga o que passou do prazo. Idempotente — pode rodar quantas vezes quiser.

    Retorna a contagem por categoria, para registrar no log e comprovar que a
    política está sendo cumprida de fato.
    """
    resultado: dict[str, int] = {}

    # 1. Imagem crua: some primeiro, mas o registro do arquivo permanece — o
    #    texto extraído ainda serve ao histórico, e apagar a linha inteira
    #    quebraria referências de interações antigas.
    r = await db.execute(
        update(FileExtraction)
        .where(
            FileExtraction.image_base64.isnot(None),
            FileExtraction.created_at < _limite(RETENCAO_IMAGEM_DIAS),
        )
        .values(image_base64=None, image_media_type=None)
    )
    resultado["imagens_apagadas"] = r.rowcount or 0

    # 2. Extração de arquivo vencida por completo.
    r = await db.execute(
        sql_delete(FileExtraction).where(
            FileExtraction.created_at < _limite(RETENCAO_ARQUIVO_DIAS)
        )
    )
    resultado["arquivos_apagados"] = r.rowcount or 0

    # 3. Cache semântico vencido. Guarda prompt de paciente e não tem dono —
    #    é o item que mais se beneficia de expurgo agressivo.
    r = await db.execute(
        sql_delete(SemanticCache).where(
            SemanticCache.created_at < _limite(RETENCAO_CACHE_DIAS)
        )
    )
    resultado["cache_apagado"] = r.rowcount or 0

    await db.commit()
    logger.info("Expurgo de retenção concluído", extra=resultado)
    return resultado

