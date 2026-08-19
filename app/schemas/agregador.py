"""
Médico 360 — Schemas do Agregador de IA.
Validação de entrada/saída conforme RN-AGR-001 a RN-AGR-004.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# ── Model Display ────────────────────────────────────────────

class AIModelDisplay(BaseModel):
    """Info de exibição de cada modelo — vem do banco."""
    model_id: str
    provider: str
    display_name: str
    cost_tier: str
    available: bool = True
    supports_vision: bool = True


# ── Request ──────────────────────────────────────────────────

class ConversationMessage(BaseModel):
    role: str   # 'user' | 'assistant'
    content: str


class AgregadorRequest(BaseModel):
    """
    RN-AGR-001: ao menos 1 modelo, até 4.
    RN-AGR-002: texto livre, limite 4000 chars.
    """
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Pergunta do médico",
    )
    models: list[str] = Field(
        ...,
        min_length=1,
        max_length=4,
        description="IDs dos modelos selecionados (1 a 4)",
    )
    conversation_id: UUID | None = Field(
        default=None,
        description="ID da conversa existente (ou None para criar nova)",
    )
    folder_id: UUID | None = Field(
        default=None,
        description="Pasta onde a nova conversa será criada (opcional).",
    )
    history: list[ConversationMessage] = Field(
        default_factory=list,
        description="Histórico de mensagens anteriores da conversa",
    )
    effort: str = Field(
        default="detalhado",
        description="Nível de esforço da resposta: 'rápido' (conciso) ou 'detalhado' (padrão).",
    )
    web_search: dict[str, bool] = Field(
        default_factory=dict,
        description="Mapa model_id → true/false para ativar busca web por modelo.",
    )
    file_id: UUID | None = Field(
        default=None,
        description="ID de uma extração de arquivo previamente enviada via /uploads/extract.",
    )

    @field_validator("models")
    @classmethod
    def unique_models(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError("Modelos duplicados não são permitidos")
        return v


# ── PubMed Validation ────────────────────────────────────────

class VerifiedCitationOut(BaseModel):
    title: str
    pmid: str | None
    verified: bool


class PubMedArticleOut(BaseModel):
    pmid: str
    article_title: str
    abstract_snippet: str


class PubmedValidationResult(BaseModel):
    cited_guidelines_verified: list[VerifiedCitationOut]
    newer_guidelines_found: list[PubMedArticleOut]
    fallback: bool


# ── Response ─────────────────────────────────────────────────

class ModelResponse(BaseModel):
    """Resposta individual de um modelo no Agregador."""
    model_id: str
    provider: str
    response_text: str
    response_time_ms: int
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    is_fallback: bool = False
    error: str | None = None
    pubmed_validation: PubmedValidationResult | None = None


class AgregadorResponse(BaseModel):
    """
    RN-AGR-003: cada resposta identifica modelo + tempo.
    Inclui disclaimer obrigatório.
    """
    interaction_id: UUID
    conversation_id: UUID
    responses: list[ModelResponse]
    disclaimer: str
    total_response_time_ms: int
    created_at: datetime
    specialty_detected: str | None = None  # <-- faltou esse
    topic_detected: str | None = None



# ── SSE Streaming ────────────────────────────────────────────

class StreamChunk(BaseModel):
    """Chunk individual para streaming SSE."""
    model_id: str
    delta: str
    done: bool = False


class StreamComplete(BaseModel):
    """Evento final do streaming SSE."""
    model_id: str
    response_time_ms: int
    tokens_in: int | None = None
    tokens_out: int | None = None


# ── History ──────────────────────────────────────────────────

class InteractionHistoryItem(BaseModel):
    """RN-AGR-004: histórico pesquisável."""
    interaction_id: UUID
    prompt_text: str
    feature: str
    mode: str | None
    models_used: list[str]
    response_time_ms: int | None
    cache_hit: bool
    created_at: datetime


class HistorySearchParams(BaseModel):
    """Parâmetros de busca no histórico."""
    query: str | None = None
    model_filter: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)