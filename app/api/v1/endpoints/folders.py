from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.limiter import limiter
from app.models.models import Conversation, Folder, User
from app.schemas.conversations import FolderOut

router = APIRouter(prefix="/folders", tags=["folders"])


class FolderCreate(BaseModel):
    name: str


class FolderRename(BaseModel):
    name: str


class ConversationMoveBody(BaseModel):
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
        .order_by(Folder.createdat)
    )
    return result.scalars().all()


@router.post("", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
async def create_folder(
    body: FolderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    folder = Folder(user_id=current_user.id, name=body.name.strip())
    db.add(folder)
    await db.flush()
    await db.commit()
    await db.refresh(folder)
    return folder


@router.put("/{folder_id}", response_model=FolderOut)
async def rename_folder(
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
    await db.commit()
    await db.refresh(folder)
    return folder


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
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
async def move_conversation(
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
