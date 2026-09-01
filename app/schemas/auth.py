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
    """O que o médico ainda precisa informar — só isso.

    Quase tudo passou a chegar sozinho: nome e especialidade vêm do cadastro
    (webhook) ou dos grupos `[CFM]` da Curseduca. Sobrou o que nenhuma fonte
    automática tem: o estágio de carreira (o grupo não distingue residente de
    especialista) e o aceite dos Termos, que ninguém pode dar pelo titular.

    Por isso os campos são quase todos opcionais, e a validação de "está
    completo?" NÃO mora mais aqui: mora em `identidade.pendencias()`, avaliada
    no endpoint depois de aplicar o que veio. Manter a regra no schema exigiria
    que ele conhecesse o estado atual do usuário — e faria o formulário pedir de
    novo o que já está preenchido.
    """

    med_status: str
    terms_accepted: bool
    name: str | None = None
    crm: str | None = None
    crm_state: str | None = None
    enrollment_year: int | None = None
    specialty: str | None = None
    phone_number: str | None = None
    # Sem default: o aceite tem que vir explicito do cliente. Default True
    # gravaria consentimento que ninguem manifestou; default False deixaria o
    # front esquecer de enviar e o onboarding passar sem registro - que era
    # exatamente o estado anterior.
    terms_accepted: bool

    @field_validator("terms_accepted")
    @classmethod
    def exigir_aceite(cls, v: bool) -> bool:
        """
        Recusa no servidor, nao so no botao desabilitado do front: o endpoint e
        publico e nao se pode assumir que o cliente e a nossa tela.
        """
        if not v:
            raise ValueError("E necessario aceitar os Termos de Uso e a Politica de Privacidade")
        return v

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

    @field_validator("specialty")
    @classmethod
    def validate_specialty(cls, v: str | None) -> str | None:
        """Aceita o RÓTULO que o front manda e devolve o SLUG canônico.

        Antes disto o servidor gravava qualquer string: o front oferecia uma
        lista fechada, mas o endpoint é público e não se pode assumir que o
        cliente é a nossa tela. Era a origem real da divergência de vocabulário.
        """
        if v is None or not v.strip():
            return None
        from app.medicina import especialidades

        slug = especialidades.normalizar(v)
        if slug is None:
            raise ValueError(f"Especialidade desconhecida: {v}")
        return slug

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
    def crm_e_uf_andam_juntos(self) -> "OnboardingRequest":
        """Um sem o outro produziria um registro que não existe.

        Esta é a única regra condicional que sobrou no schema, porque não
        depende do estado do usuário. "Falta CRM", "falta especialidade" e
        "falta aceite" são decididos por `identidade.pendencias()` no endpoint —
        lá o servidor sabe o que já está preenchido e não pede duas vezes.
        """
        if (self.crm is None) != (self.crm_state is None):
            raise ValueError("Envie CRM e UF juntos")
        return self


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    # Correção do próprio médico. Grava com fonte `declarado`, que ganha de
    # todas as automáticas — ver `app/medicina/identidade.py`.
    specialty_slug: str | None = None
    crm: str | None = None
    crm_state: str | None = None

    _validar_crm = field_validator("crm")(OnboardingRequest.validate_crm.__func__)
    _validar_uf = field_validator("crm_state")(OnboardingRequest.validate_crm_state.__func__)

    @field_validator("specialty_slug")
    @classmethod
    def validate_specialty_slug(cls, v: str | None) -> str | None:
        if v is None:
            return v
        from app.medicina import especialidades

        slug = especialidades.normalizar(v)
        if slug is None:
            raise ValueError(f"Especialidade desconhecida: {v}")
        return slug

    @model_validator(mode="after")
    def crm_e_uf_andam_juntos(self) -> "UpdateProfileRequest":
        """Trocar só um dos dois produziria um registro que não existe."""
        if (self.crm is None) != (self.crm_state is None):
            raise ValueError("Para alterar o registro, envie CRM e UF juntos")
        return self


class DeleteAccountRequest(BaseModel):
    confirm_name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    onboarding_complete: bool
    # O que ainda falta, para a tela continuar de onde parou sem uma chamada a
    # mais. Vazio = completo. Aditivo: quem não conhece o campo ignora.
    onboarding_pendencias: list[str] = []


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

    # ── Identidade profissional (aditivo: nada acima mudou de forma) ──────
    # A forma antiga é preservada de propósito. Os três apps consomem este
    # schema hoje; reestruturar em um objeto `perfil` aninhado seria mais limpo
    # e quebraria os três de uma vez. Dá para limpar depois que todos migrarem.
    specialty: str | None = None
    specialty_slug: str | None = None
    specialty_source: str | None = None
    specialty_rqe: str | None = None
    profissao: str | None = None
    # Se o próprio médico pode trocar a especialidade nesta tela. Tranca quando
    # o valor veio de fonte automática (cadastro/WAID/CFM) — o campo é
    # identidade profissional, não preferência. O front lê daqui em vez de
    # reimplementar a regra.
    specialty_editavel: bool = True

    # O QUE FALTA NO PERFIL, decidido pelo SERVIDOR.
    # Os apps não calculam pendência — renderizam esta lista. É o que evita
    # reimplementar (e divergir) a regra de onboarding em cada frontend.
    # Valores: aceite_termos | nome | crm | especialidade.
    onboarding_pendencias: list[str] = []
