"""
Médico 360 — Schemas do Agregador de IA.
Validação de entrada/saída conforme RN-AGR-001 a RN-AGR-004.
"""

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






# ── SSE Streaming ────────────────────────────────────────────



# ── History ──────────────────────────────────────────────────


