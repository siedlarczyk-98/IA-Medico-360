from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    # "clinical" (paciente) ou "general" (estudo, gestão, tema).
    folder_kind: str = "clinical"
    # Evolução do paciente / contexto do caso escrito pelo médico. Devolvido
    # na íntegra para que a tela de edição mostre o que está gravado — é o
    # próprio médico lendo o que ele escreveu, não exposição de dado alheio.
    clinical_context: str | None = None
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


class ConversationRename(BaseModel):
    """Novo título da conversa, dado pelo médico.

    120 caracteres: cabe numa linha da lista com folga no computador e já corta
    no celular; a coluna aceita 500, mas título que precisa de parágrafo é
    anotação, e para isso existe o contexto da pasta.
    """

    title: str = Field(max_length=120)

    @field_validator("title")
    @classmethod
    def _sem_espacos_nas_pontas(cls, valor: str) -> str:
        valor = " ".join(valor.split())
        if not valor:
            raise ValueError("O título não pode ficar vazio.")
        return valor


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


class AttachmentOut(BaseModel):
    """
    Anexo de uma mensagem. Só metadados — o conteúdo extraído já está embutido
    no texto da mensagem, e o base64 da imagem não deve trafegar de volta na
    listagem da conversa.
    """
    id: UUID
    file_name: str
    file_type: str  # "pdf" | "docx" | "xlsx" | "image"


class CitacaoOut(BaseModel):
    """Uma fonte citada. `title` é `None` em conversas anteriores à mudança."""
    url: str
    title: str | None = None


class ConversationMessage(BaseModel):
    role: str        # "user" | "assistant"
    content: str
    # Anexos enviados junto da mensagem. Vazio em mensagens anteriores à
    # migration 001, que não têm vínculo — não há como inferir retroativamente.
    attachments: list[AttachmentOut] = []
    mode: str | None = None   # model_id (AGREGADOR) or mode name (ORQUESTRADOR)
    # Referências da resposta. Vêm de InteractionResponse.extra_metadata e
    # chegam vazias em conversas anteriores à mudança que passou a gravá-las
    # (não há backfill) — a interface trata ausência como "sem fontes".
    #
    # `{"url", "title"}` por fonte. Conversas gravadas antes de o título passar
    # a ser guardado têm só a URL no JSONB e são convertidas na leitura, por
    # `read_response_metadata` — `title` vem `None` e a interface mostra o
    # domínio. A conversão é permanente: não há backfill do título.
    citations: list[CitacaoOut] = []
    pubmed_validation: PubmedValidationOut | None = None
    # `True` quando o modelo do modo falhou e a resposta veio de um fallback —
    # ou, nos modos sem fallback (DATA_OCEAN), quando é a mensagem genérica de
    # erro. Sem isto, ao reabrir a conversa o médico não distingue uma consulta
    # ao DATASUS que falhou de uma que deu certo: as duas são só texto.
    is_fallback: bool = False


class ConversationDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    feature: str
    # A pasta acompanha o detalhe para que a interface possa avisar o médico de
    # que respostas nesta conversa podem trazer material de outras conversas da
    # mesma pasta. Sem esse aviso, o cruzamento acontece sem ele saber.
    folder_id: UUID | None = None
    folder_name: str | None = None
    messages: list[ConversationMessage]
    created_at: datetime
    updated_at: datetime
