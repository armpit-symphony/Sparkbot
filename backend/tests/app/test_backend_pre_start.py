from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import backend_pre_start


def test_validate_database_settings_reports_missing_postgres_values(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_TYPE", "postgresql")
    settings = SimpleNamespace(
        DATABASE_TYPE="postgresql",
        POSTGRES_SERVER="",
        POSTGRES_USER="sparkbot",
        POSTGRES_PASSWORD="sparkbot-local",
        POSTGRES_DB="sparkbot",
        POSTGRES_PORT=5432,
        SQLALCHEMY_DATABASE_URI="postgresql+psycopg://sparkbot:sparkbot-local@db:5432/sparkbot",
    )

    with pytest.raises(RuntimeError, match="required database settings are missing: POSTGRES_SERVER"):
        backend_pre_start.validate_database_settings(settings)


def test_validate_raw_database_env_reports_missing_postgres_values(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_TYPE", "postgresql")
    monkeypatch.delenv("POSTGRES_SERVER", raising=False)
    monkeypatch.setenv("POSTGRES_USER", "sparkbot")
    monkeypatch.setenv("POSTGRES_PASSWORD", "sparkbot-local")
    monkeypatch.setenv("POSTGRES_DB", "sparkbot")

    with pytest.raises(RuntimeError, match="required database environment variables are missing: POSTGRES_SERVER"):
        backend_pre_start.validate_raw_database_env()


def test_validate_raw_database_env_rejects_invalid_port(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_TYPE", "postgresql")
    monkeypatch.setenv("POSTGRES_SERVER", "db")
    monkeypatch.setenv("POSTGRES_USER", "sparkbot")
    monkeypatch.setenv("POSTGRES_PASSWORD", "sparkbot-local")
    monkeypatch.setenv("POSTGRES_DB", "sparkbot")
    monkeypatch.setenv("POSTGRES_PORT", "not-a-port")

    with pytest.raises(RuntimeError, match="POSTGRES_PORT must be a valid integer"):
        backend_pre_start.validate_raw_database_env()


def test_validate_database_settings_rejects_invalid_database_url(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_TYPE", "postgresql")
    settings = SimpleNamespace(
        DATABASE_TYPE="postgresql",
        POSTGRES_SERVER="db",
        POSTGRES_USER="sparkbot",
        POSTGRES_PASSWORD="sparkbot-local",
        POSTGRES_DB="sparkbot",
        POSTGRES_PORT=5432,
        SQLALCHEMY_DATABASE_URI="not a url",
    )

    with pytest.raises(RuntimeError, match="valid SQLAlchemy URL"):
        backend_pre_start.validate_database_settings(settings)


def test_validate_database_settings_accepts_local_postgres_defaults(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_TYPE", "postgresql")
    settings = SimpleNamespace(
        DATABASE_TYPE="postgresql",
        POSTGRES_SERVER="db",
        POSTGRES_USER="sparkbot",
        POSTGRES_PASSWORD="sparkbot-local",
        POSTGRES_DB="sparkbot",
        POSTGRES_PORT=5432,
        SQLALCHEMY_DATABASE_URI="postgresql+psycopg://sparkbot:sparkbot-local@db:5432/sparkbot",
    )

    backend_pre_start.validate_database_settings(settings)


def test_validate_raw_database_env_accepts_local_postgres_defaults(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_TYPE", "postgresql")
    monkeypatch.setenv("POSTGRES_SERVER", "db")
    monkeypatch.setenv("POSTGRES_USER", "sparkbot")
    monkeypatch.setenv("POSTGRES_PASSWORD", "sparkbot-local")
    monkeypatch.setenv("POSTGRES_DB", "sparkbot")
    monkeypatch.setenv("POSTGRES_PORT", "5432")

    backend_pre_start.validate_raw_database_env()
