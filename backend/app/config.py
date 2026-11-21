"""App settings, read from environment variables and backend/.env (see .env.example)."""
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "CheckScam API"
    version: str = "0.3.0"
    debug: bool = False

    # Development sign-in with the "X-Dev-User" header. Only active when debug is also on.
    allow_dev_auth: bool = False

    # Comma-separated origins allowed by CORS. The mobile app does not need CORS; keep empty unless a web client exists.
    cors_origins: str = ""

    # Database: Supabase Postgres URL in production, local SQLite file by default.
    database_url: str = f"sqlite:///{BACKEND_DIR / 'checkscam.db'}"

    # Firebase service-account JSON path (used to verify ID tokens).
    firebase_credentials: str = ""

    # MIRA v1 decision model (Hugging Face).
    mira_enabled: bool = True
    mira_model_id: str = "sagea-ai/Mira-v1"
    mira_revision: str = "main"  # pin to a commit hash once tested
    mira_timeout_seconds: float = 3.0

    # AlienVault OTX.
    otx_api_key: str = ""
    # A slow OTX call keeps running in the background up to this long and fills the cache;
    # the check itself never waits longer than check_timeout_seconds.
    otx_timeout_seconds: float = 15.0
    otx_daily_limit: int = 5000
    otx_cache_hours: int = 24

    # Domain age (RDAP/WHOIS). Like OTX, slow lookups finish in the background and fill the cache.
    whois_enabled: bool = True
    whois_timeout_seconds: float = 10.0
    domain_cache_days: int = 7

    rate_limit: str = "60/minute"
    check_timeout_seconds: float = 6.0
    store_message_text: bool = True  # masked text only

    data_dir: Path = Field(default=BACKEND_DIR / "app" / "data")

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, url: str) -> str:
        """Supabase shows 'postgresql://...'; SQLAlchemy needs the driver name we installed (psycopg 3)."""
        url = url.strip()
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    @property
    def dev_auth_active(self) -> bool:
        return self.debug and self.allow_dev_auth

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
