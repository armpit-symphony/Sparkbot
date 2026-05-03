import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.fixture(autouse=True)
def clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "ENVIRONMENT",
        "PROJECT_NAME",
        "SECRET_KEY",
        "FRONTEND_HOST",
        "BACKEND_CORS_ORIGINS",
        "FIRST_SUPERUSER_PASSWORD",
        "SPARKBOT_PASSPHRASE",
        "WORKSTATION_LIVE_TERMINAL_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)


def test_clean_checkout_settings_have_safe_test_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.PROJECT_NAME == "Sparkbot"
    assert settings.WORKSTATION_LIVE_TERMINAL_ENABLED is False


def test_production_rejects_missing_explicit_secret_key() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY must be explicitly set"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            FRONTEND_HOST="https://sparkpitlabs.com",
            BACKEND_CORS_ORIGINS="https://sparkpitlabs.com",
            FIRST_SUPERUSER_PASSWORD="strong-admin-password",
            SPARKBOT_PASSPHRASE="strong-server-passphrase",
        )


def test_production_rejects_localhost_cors() -> None:
    with pytest.raises(ValidationError, match="wildcard and localhost CORS origins"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY="test-secret-key-that-is-long-enough",
            FRONTEND_HOST="https://sparkpitlabs.com",
            BACKEND_CORS_ORIGINS="https://sparkpitlabs.com,http://localhost:5173",
            FIRST_SUPERUSER_PASSWORD="strong-admin-password",
            SPARKBOT_PASSPHRASE="strong-server-passphrase",
        )


def test_production_accepts_real_frontend_and_cors_origins() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SECRET_KEY="test-secret-key-that-is-long-enough",
        FRONTEND_HOST="https://sparkpitlabs.com",
        BACKEND_CORS_ORIGINS="https://sparkpitlabs.com",
        FIRST_SUPERUSER_PASSWORD="strong-admin-password",
        SPARKBOT_PASSPHRASE="strong-server-passphrase",
    )

    assert settings.all_cors_origins == [
        "https://sparkpitlabs.com",
        "https://sparkpitlabs.com",
    ]
