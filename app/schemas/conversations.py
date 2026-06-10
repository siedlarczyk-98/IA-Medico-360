from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    createdat: datetime
    updatedat: datetime


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    feature: str  # "ORQUESTRADOR" | "AGREGADOR"
    folder_id: UUID | None = None
    updatedat: datetime
    createdat: datetime


class ConversationMessage(BaseModel):
    role: str        # "user" | "assistant"
    content: str
    mode: str | None = None   # model_id (AGREGADOR) or mode name (ORQUESTRADOR)


class ConversationDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    feature: str
    messages: list[ConversationMessage]
    createdat: datetime
    updatedat: datetime
