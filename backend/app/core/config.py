import warnings
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import (
    AnyUrl,
    BeforeValidator,
    EmailStr,
    HttpUrl,
    PostgresDsn,
    computed_field,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "changethis"
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    FRONTEND_HOST: str = "http://localhost:5173"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            self.FRONTEND_HOST
        ]

    PROJECT_NAME: str = "Sparkbot"
    SENTRY_DSN: HttpUrl | None = None
    DATABASE_TYPE: str = "sqlite"  # sqlite or postgresql
    POSTGRES_SERVER: str = ""
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""

    # Base directory for local data files (SQLite DB, uploads, guardian vault).
    # When empty (default), files are written relative to the working directory,
    # which matches the current Docker behavior.
    # For v1 local Windows installs: set to %APPDATA%\Sparkbot (or equivalent).
    SPARKBOT_DATA_DIR: str = ""

    # v1 Local mode: disables bridge services (Telegram, Discord, WhatsApp) and
    # advanced features (live terminal) that are not needed for a standalone
    # local install. Default False preserves the existing hosted server behavior.
    V1_LOCAL_MODE: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        if self.DATABASE_TYPE == "sqlite":
            db_name = f"{self.PROJECT_NAME.lower().replace(' ', '_')}.db"
            if self.SPARKBOT_DATA_DIR:
                return f"sqlite:///{Path(self.SPARKBOT_DATA_DIR) / db_name}"
            return f"sqlite:///{db_name}"
        return PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: EmailStr | None = None
    EMAILS_FROM_NAME: str | None = None

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    EMAIL_TEST_USER: EmailStr = "test@example.com"
    FIRST_SUPERUSER: EmailStr = "admin@example.com"
    FIRST_SUPERUSER_PASSWORD: str = "admin123"

    # Sparkbot passphrase for simple chat access
    SPARKBOT_PASSPHRASE: str = "changeme-in-production"

    # Workstation live terminal (Phase 3)
    # Enables PTY shell sessions via WebSocket. Self-hosted / operator use only.
    # No command-level filtering is enforced in Phase 3 — raw shell access.
    WORKSTATION_LIVE_TERMINAL_ENABLED: bool = False

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value in {"changethis", "REPLACE_WITH_RANDOM_64_HEX"}:
            message = (
                f"The value of {var_name} is a placeholder, "
                "for security, please change it, at least for deployments."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    def _origin_host(self, origin: str) -> str:
        parsed = urlparse(origin)
        return (parsed.hostname or "").lower()

    def _is_local_origin(self, origin: str) -> bool:
        host = self._origin_host(origin)
        return host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".localhost")

    def _production_error(self, message: str) -> None:
        raise ValueError(f"Unsafe production configuration: {message}")

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        explicitly_set = self.model_fields_set
        if self.ENVIRONMENT == "production" and "SECRET_KEY" not in explicitly_set:
            self._production_error("SECRET_KEY must be explicitly set.")
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        self._check_default_secret("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD)
        _weak_defaults = {
            "",
            "admin",
            "admin123",
            "changethis",
            "letmein12345",
            "password",
            "sparkbot",
            "sparkbot-local",
            "changeme-in-production",
            "REPLACE_WITH_ADMIN_PASSWORD",
            "REPLACE_WITH_STRONG_PASSPHRASE",
        }
        if (self.FIRST_SUPERUSER_PASSWORD or "").strip().lower() in _weak_defaults:
            message = (
                'FIRST_SUPERUSER_PASSWORD is set to a known weak default. '
                'Please change it for deployments.'
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)
        if (self.SPARKBOT_PASSPHRASE or "").strip().lower() in _weak_defaults:
            message = (
                'SPARKBOT_PASSPHRASE is set to a known weak default. '
                'Please change it for deployments.'
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)
        if self.ENVIRONMENT == "production":
            if "FRONTEND_HOST" not in explicitly_set or self._is_local_origin(self.FRONTEND_HOST):
                self._production_error("FRONTEND_HOST must be the real public frontend URL.")
            if "BACKEND_CORS_ORIGINS" not in explicitly_set or not self.BACKEND_CORS_ORIGINS:
                self._production_error("BACKEND_CORS_ORIGINS must list the real allowed origin(s).")
            for origin in self.all_cors_origins:
                if origin == "*" or self._is_local_origin(origin):
                    self._production_error("wildcard and localhost CORS origins are not allowed.")
            if self.WORKSTATION_LIVE_TERMINAL_ENABLED and "WORKSTATION_LIVE_TERMINAL_ENABLED" not in explicitly_set:
                self._production_error("live terminal must only be enabled intentionally.")
        return self


settings = Settings()  # type: ignore
