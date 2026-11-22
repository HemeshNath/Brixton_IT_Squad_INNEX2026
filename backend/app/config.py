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

    # MIRA v1 decision model (Hugging Face, Apache-2.0). Loaded in the background at server start.
    mira_enabled: bool = True
    # Old MIRA (the long prompt, 30-70 s per check) is replaced by the owner's trained model. Off: it is not even
    # loaded. On (USE_ORIGINAL_MIRA=true in .env): it decides when the trained model is missing / answers the questions.
    use_original_mira: bool = False
    # Answer the phone first and save the check row right after (history / dashboard rows appear ~1 s later)
    save_checks_in_background: bool = True
    mira_model_id: str = "sagea-ai/Mira-v1"
    mira_revision: str = "610544ecbcf6e7c0103c9b75543dcaab7ec0739d"  # pinned: the version we tested
    mira_timeout_seconds: float = 75.0  # B6: MIRA with the owner's prompt takes 26-55 s on the laptop CPU
    mira_not_sure_below: float = 0.5  # top answer probability below this -> "not sure"
    mira_local_only: bool = True  # never download at start-up; model must already be in the cache
    hf_home: str = ""  # Hugging Face cache folder, e.g. D:\hf_cache (empty = HF_HOME env var / default)

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
    whois_api_key: str = ""  # WhoisXML API key (optional); without it free RDAP/WHOIS is used

    # Time budget per check (B6): the phone waits at most 90 s. Links get this long, then MIRA mira_timeout_seconds.
    link_checks_timeout_seconds: float = 2.0  # one OTX call per link (~0.6-1.2 s); WHOIS no longer used  # B3: OTX (4 parts) + full WHOIS; slow parts keep filling the cache

    # Web admin panel (Phase 10A): ID + password sign-in, cookie session.
    admin_idle_minutes: int = 30  # signed out after this long without activity
    admin_max_failed_logins: int = 5  # then the account is locked for admin_lock_minutes
    admin_lock_minutes: int = 15
    admin_cookie_secure: bool = True  # cookie only over HTTPS; set false only for local http testing
    secrets_key: str = ""  # encrypts API keys saved in the admin panel; empty = backend/.secret_key file
    secret_key_file: str = ""  # where that file is (empty = backend/.secret_key); tests use a temp file
    admin_web_dir: Path = Field(default=BACKEND_DIR.parent / "admin_web" / "build" / "web")  # built Flutter Web app
    # The owner's trained MIRA (fine-tuned in Colab); kept outside backend/ so it is never copied to GitHub
    classifier_dir: Path = Field(default=BACKEND_DIR.parent / "models" / "checkscam-mira-ft")
    classifier_timeout_seconds: float = 15.0

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
