import re
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

MED_STATUS_VALUES = {"graduando", "generalista", "residente", "especialista"}
BRAZIL_STATES = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
    "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
    "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


class RegisterRequest(BaseModel):
    email: EmailStr


class InviteGenerateRequest(BaseModel):
    email: EmailStr | None = None
    expires_hours: int = Field(default=72, gt=0, le=720)


class InviteGenerateResponse(BaseModel):
    invite_url: str
    token: str
    expires_at: datetime


class InviteAcceptRequest(BaseModel):
    token: str
    email: EmailStr | None = None


class OTPRequest(BaseModel):
    email: EmailStr


class OTPVerify(BaseModel):
    email: EmailStr
    code: str

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not re.match(r"^\d{6}$", v):
            raise ValueError("Código deve ter exatamente 6 dígitos numéricos")
        return v


class OnboardingRequest(BaseModel):
    name: str
    phone_number: str
    med_status: str
    crm: str | None = None
    crm_state: str | None = None
    enrollment_year: int | None = None
    specialty: str | None = None

    @field_validator("med_status")
    @classmethod
    def validate_med_status(cls, v: str) -> str:
        if v not in MED_STATUS_VALUES:
            raise ValueError(f"med_status deve ser um de: {', '.join(sorted(MED_STATUS_VALUES))}")
        return v

    @field_validator("crm_state")
    @classmethod
    def validate_crm_state(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.upper().strip()
        if v not in BRAZIL_STATES:
            raise ValueError(f"CRM_UF inválido: {v}")
        return v

    @field_validator("crm")
    @classmethod
    def validate_crm(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v.isdigit():
            raise ValueError("CRM deve conter apenas números")
        return v

    @field_validator("enrollment_year")
    @classmethod
    def validate_enrollment_year(cls, v: int | None) -> int | None:
        if v is None:
            return v
        current_year = date.today().year
        if v < 1950 or v > current_year:
            raise ValueError(f"Ano de ingresso deve estar entre 1950 e {current_year}")
        return v

    @model_validator(mode="after")
    def validate_conditional_fields(self) -> "OnboardingRequest":
        if self.med_status == "graduando":
            if not self.enrollment_year:
                raise ValueError("Ano de ingresso é obrigatório para alunos de graduação")
        else:
            if not self.crm or not self.crm_state:
                raise ValueError("CRM e UF são obrigatórios para médicos formados")
            if self.med_status in ("residente", "especialista") and not self.specialty:
                raise ValueError("Especialidade é obrigatória para residentes e especialistas")
        return self


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    email: str | None = None


class DeleteAccountRequest(BaseModel):
    confirm_name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    onboarding_complete: bool


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str | None
    crm: str | None
    crm_state: str | None
    phone_number: str | None
    role: str
    med_status: str | None
    onboarding_complete: bool
    # HMAC para o Messenger Security do Intercom (gerado sob demanda, não persistido)
    intercom_user_hash: str | None = None
