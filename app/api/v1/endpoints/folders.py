from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.limiter import limiter
from app.models.models import Conversation, Folder, User
from app.schemas.conversations import FolderOut

router = APIRouter(prefix="/folders", tags=["folders"])


def _limpar_evolucao(texto: str | None) -> str | None:
    """Normaliza o texto de evolução: vazio ou só espaço vira `None`.

    Guardar `""` e `None` como coisas diferentes não teria sentido para quem
    lê, e faria `formatar_bloco_evolucao` receber dois valores para o mesmo
    estado "não há evolução".
    """
    if texto is None:
        return None
    limpo = texto.strip()
    return limpo or None


# Teto do texto de evolução aceito pela API, em caracteres.
#
# O campo entra em TODA mensagem da pasta (ver `evolucao_da_pasta`), então o
# tamanho dele é custo recorrente, não custo único. 8000 caracteres ≈ 2500
# tokens — folgado para uma evolução clínica e restritivo o bastante para
# impedir que um prontuário inteiro colado aqui encareça cada pergunta.
#
# O limite vive aqui, e não no banco (a coluna é TEXT), para que um texto longo
# receba um 422 explicando o limite em vez de um 500 vindo do driver.
MAX_CHARS_EVOLUCAO = 8000


class FolderCreate(BaseModel):
    name: str
    # Opcional: o médico é perguntado na criação, mas uma pasta que é só
    # organização por tema não tem evolução nenhuma para declarar.
    clinical_context: str | None = Field(default=None, max_length=MAX_CHARS_EVOLUCAO)


class FolderRename(BaseModel):
    name: str
    # `None` aqui significa "não mexa", e NÃO "apague".
    #
    # Este endpoint era só rename. Se o campo ausente virasse `NULL` na coluna,
    # qualquer cliente que ainda mande apenas `{"name": ...}` — a versão atual
    # do frontend, entre eles — apagaria a evolução do paciente ao renomear a
    # pasta, sem pedir nada e sem aviso.
    #
    # Para LIMPAR de propósito, o cliente manda string vazia: ela é distinguível
    # de ausente e é tratada em `rename_folder`.
    clinical_context: str | None = Field(default=None, max_length=MAX_CHARS_EVOLUCAO)


class ConversationMoveBody(BaseModel):
    folder_id: UUID | None


class ConversationBulkMoveBody(BaseModel):
    conversation_ids: list[UUID] = Field(..., min_length=1, max_length=100)
    folder_id: UUID | None


@router.get("", response_model=list[FolderOut])
@limiter.limit("60/minute")
async def list_folders(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Folder)
        .where(Folder.user_id == current_user.id)
        .order_by(Folder.created_at)
    )
    return result.scalars().all()


@router.post("", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_folder(
    request: Request,
    body: FolderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    folder = Folder(
        user_id=current_user.id,
        name=body.name.strip(),
        clinical_context=_limpar_evolucao(body.clinical_context),
    )
    db.add(folder)
    await db.flush()
    await db.commit()
    await db.refresh(folder)
    return folder


@router.put("/{folder_id}", response_model=FolderOut)
@limiter.limit("30/minute")
async def rename_folder(
    request: Request,
    folder_id: UUID,
    body: FolderRename,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Folder).where(Folder.id == folder_id, Folder.user_id == current_user.id)
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pasta não encontrada")
    folder.name = body.name.strip()
    # Ausente = não mexa. String vazia = limpar. Ver `FolderRename`.
    if body.clinical_context is not None:
        folder.clinical_context = _limpar_evolucao(body.clinical_context)
    await db.commit()
    await db.refresh(folder)
    return folder


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def delete_folder(
    request: Request,
    folder_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Folder).where(Folder.id == folder_id, Folder.user_id == current_user.id)
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pasta não encontrada")
    await db.delete(folder)
    await db.commit()


@router.patch("/conversations/{conversation_id}/folder", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("60/minute")
async def move_conversation(
    request: Request,
    conversation_id: UUID,
    body: ConversationMoveBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversa não encontrada")

    if body.folder_id is not None:
        folder_result = await db.execute(
            select(Folder).where(Folder.id == body.folder_id, Folder.user_id == current_user.id)
        )
        if not folder_result.scalar_one_or_none():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Pasta não encontrada")

    conv.folder_id = body.folder_id
    await db.commit()


@router.patch("/conversations/bulk", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def bulk_move_conversations(
    request: Request,
    body: ConversationBulkMoveBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Move múltiplas conversas para uma pasta (ou remove da pasta) em uma única operação."""
    if body.folder_id is not None:
        folder_result = await db.execute(
            select(Folder).where(Folder.id == body.folder_id, Folder.user_id == current_user.id)
        )
        if not folder_result.scalar_one_or_none():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Pasta não encontrada")

    await db.execute(
        update(Conversation)
        .where(
            Conversation.id.in_(body.conversation_ids),
            Conversation.user_id == current_user.id,
        )
        .values(folder_id=body.folder_id)
    )
    await db.commit()
