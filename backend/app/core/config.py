"""
Application configuration, read once from the environment and ``backend/.env``.

Every setting that differs between machines (secrets, email account, URLs, file locations) lives
here. Business rules that the team may tune (tiers, costs, timings, the learning loop) are kept
separately in ``crm_settings.json`` and loaded by :mod:`app.core.rules`.

The ``.env`` file is loaded into the process environment at import time, so modules that read a
variable at call time (for example the Gemini client) see the same values as this object.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]  # .../backend
PROJECT_DIR = BACKEND_DIR.parent  # repository root
ENV_FILE = BACKEND_DIR / ".env"

load_dotenv(ENV_FILE, override=False)


class Settings(BaseSettings):
    """Typed view of the environment. Field names map to upper-case variables (``DEMO_MODE``...)."""

    # an empty value (KEY= in .env) means "use the default", so .env.example can be copied as it is
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False, env_ignore_empty=True)

    app_name: str = "X Education CRM"
    environment: str = Field(default="development", description="development | production | test")
    demo_mode: bool = Field(default=True, description="Short automation timings for demonstrations")
    log_level: str = "INFO"

    # file locations (all inside backend/data by default; the folder is not tracked by git)
    data_dir: Path = BACKEND_DIR / "data"
    database_path: Path | None = Field(default=None, validation_alias=AliasChoices("DATABASE_PATH", "DB_PATH"))
    models_dir: Path | None = None
    simulation_db_path: Path | None = Field(
        default=None, validation_alias=AliasChoices("SIMULATION_DB_PATH", "SIM_WORLD_DB")
    )
    rules_path: Path = Field(
        default=PROJECT_DIR / "crm_settings.json", validation_alias=AliasChoices("RULES_PATH", "CRM_SETTINGS")
    )
    log_file: Path | None = None

    # security
    jwt_secret: str | None = Field(default=None, description="Empty: a random secret is kept in the database")
    learner_token_hours: int = 24 * 7
    crm_token_hours: int = 12
    otp_expiry_minutes: int = 10

    # the owner account of the CRM (an admin whose password stays in this file)
    crm_owner_email: str = Field(
        default="admin@xeducation.in", validation_alias=AliasChoices("CRM_OWNER_EMAIL", "MARKETING_EMAIL")
    )
    crm_owner_password: str | None = Field(
        default=None, validation_alias=AliasChoices("CRM_OWNER_PASSWORD", "MARKETING_PASSWORD")
    )
    crm_owner_name: str = Field(default="Admin", validation_alias=AliasChoices("CRM_OWNER_NAME", "MARKETING_NAME"))

    # outbound email (optional: without it, codes and emails are written to the log). Gmail by default; any mail
    # server works with SMTP_HOST, SMTP_PORT and SMTP_SECURITY (ssl, starttls, or none for a local relay)
    gmail_user: str = Field(default="", validation_alias=AliasChoices("GMAIL_USER", "SMTP_USER", "EMAIL_FROM"))
    gmail_app_password: str = Field(default="", validation_alias=AliasChoices("GMAIL_APP_PASSWORD", "SMTP_PASSWORD"))
    email_from: str = ""
    brevo_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int | None = None
    smtp_security: str = ""

    # Gemini (optional: without it, messages are written from templates)
    gemini_api_key: str = ""
    gemini_model: str = ""

    # URLs
    public_site_url: str = Field(
        default="http://localhost:5173", validation_alias=AliasChoices("PUBLIC_SITE_URL", "USER_FRONTEND_URL")
    )
    dashboard_url: str = "http://localhost:5174"
    api_url: str = Field(default="http://127.0.0.1:8000", validation_alias=AliasChoices("API_URL", "SIM_API_URL"))
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ]
    )

    # background work
    scheduler_enabled: bool = True
    simulation_enabled: bool | None = None  # None: crm_settings.json decides
    keep_alive_enabled: bool = True
    keep_alive_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("KEEP_ALIVE_URL", "RENDER_EXTERNAL_URL"),
    )
    keep_alive_interval_minutes: int = 9

    @field_validator("public_site_url", "dashboard_url", "api_url")
    @classmethod
    def _no_trailing_slash(cls, v: str) -> str:
        # on Windows "localhost" is tried as IPv6 first (about 2 s per connection) for server-to-server calls
        return v.rstrip("/")

    @property
    def db_path(self) -> Path:
        return Path(self.database_path) if self.database_path else self.data_dir / "xeducation.db"

    @property
    def model_dir(self) -> Path:
        return Path(self.models_dir) if self.models_dir else self.data_dir / "models"

    @property
    def simulation_db(self) -> Path:
        return Path(self.simulation_db_path) if self.simulation_db_path else self.data_dir / "simulation_world.db"

    @property
    def log_path(self) -> Path:
        return Path(self.log_file) if self.log_file else self.data_dir / "logs" / "app.log"

    @property
    def owner_password_from_env(self) -> bool:
        """True when CRM_OWNER_PASSWORD is set: the owner's password is managed in backend/.env. Otherwise a random
        password is made at the first start (see app.services.team.ensure_owner) and can be changed in the CRM."""
        return bool((self.crm_owner_password or "").strip())

    @property
    def initial_password_file(self) -> Path:
        return self.data_dir / "initial-admin-password.txt"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.model_dir.mkdir(parents=True, exist_ok=True)
    return s
