from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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


class CalculatorExecuteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    version_id: UUID | None = None
    inputs: dict
    result: dict
    interpretation: str | None
    createdat: datetime | None = None


class CalculatorExtractRequest(BaseModel):
    text: str


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
    createdat: datetime
