"""
Médico 360 — Configuração centralizada via pydantic-settings.
Carrega variáveis de .env ou variáveis de ambiente do Railway.
"""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- App ---
    app_name: str = "Médico 360"
    app_env: str = "development"
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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
