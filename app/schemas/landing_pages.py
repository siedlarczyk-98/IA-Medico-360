from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

# Listas de múltipla escolha dos formulários públicos. Não tinham teto nenhum: uma
# única requisição anônima com 300 mil itens virava 300 mil linhas nas tabelas de
# seleção. Os formulários reais têm de 5 a 12 opções.
#
# O teto é de QUANTIDADE e TAMANHO, e não uma lista fechada de opções, de
# propósito: as opções são frases que vivem nas páginas de captação, e espelhá-las
# aqui faria uma mudança de redação na página virar 422 — lead perdido em silêncio,
# que é pior que o abuso que isto veio fechar.
MAX_OPCOES = 30
Opcao = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Opcoes = Annotated[list[Opcao], Field(min_length=1, max_length=MAX_OPCOES)]


class _LeadBase(BaseModel):
    # Email/nome vem da URL (embed do fornecedor), sem validacao de formato aqui:
    # um valor malformado nao pode derrubar a submissao das respostas, que e o
    # dado que importa. `email_missing` e quem marca ausencia de origem.
    name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    email_missing: bool = False


class FinanceSubmissionRequest(_LeadBase):
    career_stage: str = Field(min_length=1, max_length=100)
    main_pain_point: str = Field(min_length=1, max_length=100)


class AccountingSubmissionRequest(_LeadBase):
    career_stage: str = Field(min_length=1, max_length=100)
    income_method: str = Field(min_length=1, max_length=100)
    accountant_status: str = Field(min_length=1, max_length=100)
    revenue_range: str = Field(min_length=1, max_length=100)
    willingness_to_pay: str = Field(min_length=1, max_length=100)
    pain_points: Opcoes


class PartnerSubmissionRequest(_LeadBase):
    career_stage: str = Field(min_length=1, max_length=100)
    categories: Opcoes
    desired_brands: str | None = Field(default=None, max_length=300)


class CalculatorSubmissionRequest(BaseModel):
    """Vem de dentro do produto (medico ja autenticado) — nome/email sao os da conta."""

    calculators: Opcoes
    notify_on_availability: bool = False


class SubmissionResponse(BaseModel):
    ok: bool = True


class AlreadySubmittedResponse(BaseModel):
    already_submitted: bool
