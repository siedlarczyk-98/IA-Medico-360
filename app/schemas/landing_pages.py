from pydantic import BaseModel, Field


class FinanceSubmissionRequest(BaseModel):
    # Email/nome vem da URL (embed do fornecedor), sem validacao de formato aqui:
    # um valor malformado nao pode derrubar a submissao das respostas, que e o
    # dado que importa. `email_missing` e quem marca ausencia de origem.
    name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    email_missing: bool = False
    career_stage: str = Field(min_length=1, max_length=100)
    main_pain_point: str = Field(min_length=1, max_length=100)


class SubmissionResponse(BaseModel):
    ok: bool = True
