"""
Médico 360 — Configuração centralizada via pydantic-settings.
Carrega variáveis de .env ou variáveis de ambiente do Railway.
"""

from functools import lru_cache
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
    jwt_access_token_expire_minutes: int = 1440  # 24h

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
    invite_token_expire_hours: int = 72
    otp_expire_minutes: int = 10
    allow_public_registration: bool = False

    # --- Embed SSO ---
    embed_allowed_origins: list[str] = ["https://adminportalmedico360.curseduca.pro"]

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Agregador ---
    max_models_per_query: int = 4
    max_prompt_chars: int = 4000
    default_timeout_seconds: int = 30

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
