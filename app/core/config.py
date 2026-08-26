"""
Médico 360 — Configuração centralizada via pydantic-settings.
Carrega variáveis de .env ou variáveis de ambiente do Railway.
"""

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- App ---
    app_name: str = "Médico 360"
    # SEM padrão de propósito. Todo o endurecimento de produção está atrás de
    # `is_production` — docs fechada, cookie Secure, validação fail-closed do
    # embed SSO. Com um padrão, esquecer de definir a variável fazia a aplicação
    # rodar em modo de desenvolvimento em produção, silenciosamente. Aconteceu.
    # Agora falta de APP_ENV derruba o startup com mensagem clara.
    app_env: Literal["development", "staging", "production"]
    app_debug: bool = False
    log_level: str = "INFO"

    # --- Database ---
    database_url: str

    # --- JWT ---
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60  # 1h (padrão seguro; ajustável via env)

    # --- AI Providers ---
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_ai_api_key: str = ""
    perplexity_api_key: str = ""
    pharmadb_api_key: str = ""
    pubmed_api_key: str = ""
    
    # --- SendGrid ---
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = "noreply@medico360.com.br"

    # --- Auth ---
    frontend_url: str = "http://localhost:5173"
    calculadoras_url: str = "http://localhost:5174"
    invite_token_expire_hours: int = 72
    otp_expire_minutes: int = 10
    allow_public_registration: bool = False
    cookie_domain: str | None = None

    # --- Embed SSO ---
    # Default cobre o único parceiro atual; sobrescrever via env EMBED_ALLOWED_ORIGINS
    # (lista JSON, ex.: '["https://a.com","https://b.com"]') para adicionar parceiros sem alterar código.
    embed_allowed_origins: list[str] = ["https://adminportalmedico360.curseduca.pro"]

    # --- Landing Pages ---
    # Cada LP (lp-financas, lp-contabilidade, ...) tem seu proprio dominio Railway;
    # adicionar via env LANDING_PAGES_ORIGINS conforme sobem novas LPs.
    # `NoDecode` desliga o auto-parse JSON do pydantic-settings pra esse campo: por
    # padrao ele roda ANTES de qualquer field_validator e derruba o processo inteiro
    # no import se a env nao vier com colchetes/aspas exatos (foi o que aconteceu em
    # producao). O validator abaixo assume o parsing e aceita formatos mais tolerantes.
    landing_pages_origins: Annotated[list[str], NoDecode] = ["http://localhost:5175"]

    @field_validator("landing_pages_origins", mode="before")
    @classmethod
    def _parse_landing_pages_origins(cls, v: object) -> object:
        """Aceita JSON array (`["a","b"]`), CSV (`a,b`) ou uma URL unica (`a`)."""
        if not isinstance(v, str) or not v.strip():
            return v
        stripped = v.strip()
        if stripped.startswith("["):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass
        return [origin.strip() for origin in stripped.split(",") if origin.strip()]

    # Validação server-to-server de membro Curseduca (plano 2.1). Fail-closed quando
    # habilitada: sem base+key configuradas, o embed retorna 503 em vez de abrir.
    curseduca_validation_enabled: bool = False
    curseduca_api_base: str = "https://prof.curseduca.pro"
    curseduca_api_key: str = ""
    curseduca_access_token: str = ""  # Bearer estático (o endpoint members/by exige, além da api_key)

    # --- Intercom (Identity Verification / Messenger Security) ---
    # Secret do Web SDK; usado para gerar o user_hash (HMAC) do Messenger.
    intercom_identity_secret: str = ""

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Rastreamento de erro (Sentry) ---
    # Vazio desliga o Sentry. O scrubbing de PII em `app/core/error_tracking.py`
    # é obrigatório: sem ele o prompt clínico bruto sai em cada evento de erro.
    sentry_dsn: str = ""
    sentry_release: str = ""

    # --- Observabilidade (Arize Phoenix) ---
    phoenix_api_key: str = ""
    phoenix_project_name: str = "medico-360"
    phoenix_endpoint: str = "https://app.phoenix.arize.com/s/ruben-nogueira"

    # --- Agregador ---
    max_models_per_query: int = 4
    max_prompt_chars: int = 4000
    default_timeout_seconds: int = 30

    # --- Calculadoras ---
    # Teto de caracteres para inputs do tipo `text` quando a calculadora nao
    # declara `max_length` proprio (RN-CALC: inputs sao persistidos em JSONB).
    calculator_text_field_max_chars: int = 2000
    # Cache in-process do catalogo de calculadoras (dados quase estaticos,
    # alterados apenas por seed/migration).
    calculator_catalog_cache_ttl_seconds: int = 300
    # Chamadas simultaneas ao LLM de extracao por processo, para o /extract nao
    # esgotar o pool de conexoes compartilhado com as demais integracoes.
    calculator_extraction_max_concurrency: int = 8
    calculator_extraction_timeout_seconds: int = 15

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        """Falha rápido no startup se chaves de segurança essenciais estiverem vazias em produção,
        em vez de deixar auth/JWT ou o SendGrid falharem silenciosamente em runtime."""
        if not self.is_production:
            return self

        missing = [
            name
            for name, value in (
                ("jwt_secret_key", self.jwt_secret_key),
                ("database_url", self.database_url),
                ("sendgrid_api_key", self.sendgrid_api_key),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"Variáveis obrigatórias vazias em produção: {', '.join(missing)}")

        # O embed SSO só prova identidade via validação server-to-server: sem ela, o
        # endpoint confia apenas no header Origin (forjável) e emite JWT para qualquer
        # e-mail. Em produção isso é fail-closed no startup, não opt-in.
        if not self.curseduca_validation_enabled:
            raise ValueError(
                "CURSEDUCA_VALIDATION_ENABLED deve ser true em produção: sem ela o "
                "/auth/embed/token emite token para qualquer e-mail informado."
            )
        embed_missing = [
            name
            for name, value in (
                ("curseduca_api_base", self.curseduca_api_base),
                ("curseduca_api_key", self.curseduca_api_key),
            )
            if not value
        ]
        if embed_missing:
            raise ValueError(
                "Validação Curseduca habilitada mas sem credenciais: "
                f"{', '.join(embed_missing)}"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
