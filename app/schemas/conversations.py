from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime
    updated_at: datetime


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    feature: str  # "ORQUESTRADOR" | "AGREGADOR"
    folder_id: UUID | None = None
    updated_at: datetime
    created_at: datetime


class CitedGuideline(BaseModel):
    title: str | None = None
    pmid: str | None = None
    verified: bool = False


class NewerGuideline(BaseModel):
    pmid: str | None = None
    article_title: str | None = None
    abstract_snippet: str | None = None


class PubmedValidationOut(BaseModel):
    cited_verified: list[CitedGuideline] = []
    newer_guidelines: list[NewerGuideline] = []


class ConversationMessage(BaseModel):
    role: str        # "user" | "assistant"
    content: str
    mode: str | None = None   # model_id (AGREGADOR) or mode name (ORQUESTRADOR)
    # Referências da resposta. Vêm de InteractionResponse.extra_metadata e
    # chegam vazias em conversas anteriores à mudança que passou a gravá-las
    # (não há backfill) — a interface trata ausência como "sem fontes".
    citations: list[str] = []
    pubmed_validation: PubmedValidationOut | None = None


class ConversationDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    feature: str
    messages: list[ConversationMessage]
    created_at: datetime
    updated_at: datetime
