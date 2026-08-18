from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Teto defensivo de chaves no payload de execucao. A validacao por campo
# (engine/validation.py) ja rejeita chaves desconhecidas, mas isso acontece
# depois de a request inteira ser materializada em memoria.
MAX_INPUT_KEYS = 100


class CalculatorListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    description: str | None
    specialty_slug: str
    is_favorite: bool = False


class CalculatorFieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    field_type: str
    unit: str | None
    required: bool
    min_value: float | None
    max_value: float | None
    options: list | None
    display_order: int


class CalculatorDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    description: str | None
    engine_type: str
    specialty_slug: str
    fields: list[CalculatorFieldOut]


class CalculatorExecuteRequest(BaseModel):
    inputs: dict
    dry_run: bool = False

    @field_validator("inputs")
    @classmethod
    def _limit_input_keys(cls, value: dict) -> dict:
        if len(value) > MAX_INPUT_KEYS:
            raise ValueError(f"inputs excede o máximo de {MAX_INPUT_KEYS} campos")
        return value


class CalculatorExecuteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    version_id: UUID | None = None
    inputs: dict
    result: dict
    interpretation: str | None
    created_at: datetime | None = None


class CalculatorExtractRequest(BaseModel):
    text: str = Field(max_length=8000)


class CalculatorExtractResponse(BaseModel):
    suggested_inputs: dict
    fields_extracted: list[str]
    interaction_id: UUID | None = None


class CalculatorExecutionHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    inputs: dict
    result: dict
    interpretation: str | None
    created_at: datetime
