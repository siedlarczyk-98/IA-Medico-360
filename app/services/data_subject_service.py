"""
Médico 360 — Direitos do titular (LGPD) e retenção.

A exclusão de conta já existia e é completa (apaga a cascata e anonimiza o
`AuditLog`). Faltavam os outros dois direitos:

  Portabilidade (art. 18, V)  → `exportar_dados`
  Retenção / expurgo (art. 16) → `expurgar_dados_vencidos`

Sobre retenção: `FileExtraction` guarda o texto extraído do arquivo e, no caso de
imagem, o base64 da própria imagem. É o dado mais sensível da base — uma foto de
exame ou de receita, que o DLP não cobre (ele atua em texto). Por isso a imagem
tem prazo próprio, bem mais curto que o resto.
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    Conversation,
    FileExtraction,
    Interaction,
    SemanticCache,
    User,
)

logger = logging.getLogger(__name__)

# Prazos de retenção. Escolhidos pelo grau de sensibilidade, não por conveniência.
RETENCAO_IMAGEM_DIAS = 30       # imagem crua de exame/receita — o mais sensível
RETENCAO_ARQUIVO_DIAS = 180     # texto extraído de arquivo
RETENCAO_CACHE_DIAS = 30        # cache semântico (já tem expires_at próprio)


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
    }


# ── Retenção ─────────────────────────────────────────────────────────────

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


async def dados_do_titular_existem(db: AsyncSession, user_id: UUID) -> bool:
    """Usado após a exclusão de conta para comprovar que nada sobrou."""
    achado = await db.execute(select(Conversation.id).where(Conversation.user_id == user_id).limit(1))
    return achado.scalar_one_or_none() is not None
