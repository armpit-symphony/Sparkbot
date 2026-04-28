import logging
import os
import sys

from sqlalchemy import Engine
from sqlalchemy.engine import make_url
from sqlmodel import Session, select
from tenacity import after_log, before_log, retry, stop_after_attempt, wait_fixed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

max_tries = 60 * 5  # 5 minutes
wait_seconds = 1


@retry(
    stop=stop_after_attempt(max_tries),
    wait=wait_fixed(wait_seconds),
    before=before_log(logger, logging.INFO),
    after=after_log(logger, logging.WARN),
)
def init(db_engine: Engine) -> None:
    try:
        with Session(db_engine) as session:
            # Try to create session to check if DB is awake
            session.exec(select(1))
    except Exception as e:
        logger.exception("Database readiness check failed")
        raise e


def validate_database_settings(settings) -> None:
    database_type = os.getenv("DATABASE_TYPE", settings.DATABASE_TYPE).strip().lower()
    if database_type == "sqlite":
        return
    if database_type != "postgresql":
        raise RuntimeError(
            "Invalid DATABASE_TYPE for prestart. Expected 'postgresql' or 'sqlite'."
        )

    required = {
        "POSTGRES_SERVER": settings.POSTGRES_SERVER,
        "POSTGRES_USER": settings.POSTGRES_USER,
        "POSTGRES_PASSWORD": settings.POSTGRES_PASSWORD,
        "POSTGRES_DB": settings.POSTGRES_DB,
    }
    missing = [name for name, value in required.items() if not str(value or "").strip()]
    if missing:
        raise RuntimeError(
            "PostgreSQL is selected but required database settings are missing: "
            + ", ".join(missing)
            + ". For local Docker installs, run `bash scripts/sparkbot-start.sh` "
            "so .env.local and compose defaults are generated."
        )

    try:
        int(settings.POSTGRES_PORT)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("POSTGRES_PORT must be a valid integer.") from exc

    try:
        make_url(str(settings.SQLALCHEMY_DATABASE_URI))
    except Exception as exc:
        raise RuntimeError(
            "Database settings did not produce a valid SQLAlchemy URL. "
            "Check POSTGRES_SERVER, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_DB."
        ) from exc


def validate_raw_database_env() -> None:
    database_type = os.getenv("DATABASE_TYPE", "sqlite").strip().lower()
    if database_type == "sqlite":
        return
    if database_type != "postgresql":
        raise RuntimeError(
            "Invalid DATABASE_TYPE for prestart. Expected 'postgresql' or 'sqlite'."
        )

    missing = [
        name
        for name in ("POSTGRES_SERVER", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
        if not os.getenv(name, "").strip()
    ]
    if missing:
        raise RuntimeError(
            "PostgreSQL is selected but required database environment variables are missing: "
            + ", ".join(missing)
            + ". For local Docker installs, run `bash scripts/sparkbot-start.sh`."
        )

    raw_port = os.getenv("POSTGRES_PORT", "5432").strip()
    try:
        int(raw_port)
    except ValueError as exc:
        raise RuntimeError("POSTGRES_PORT must be a valid integer.") from exc

    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        try:
            make_url(database_url)
        except Exception as exc:
            raise RuntimeError("DATABASE_URL is set but is not a valid SQLAlchemy URL.") from exc


def main() -> None:
    try:
        logger.info("Validating raw database environment")
        validate_raw_database_env()
        logger.info("Validating database settings")
        from app.core.config import settings

        validate_database_settings(settings)
        from app.core.db import engine

        logger.info("Initializing service")
        init(engine)
        logger.info("Service finished initializing")
    except Exception:
        logger.exception("Prestart failed before migrations")
        print(
            "\nPrestart failed. Check the exception above for the exact cause. "
            "If this is a local Docker install, rerun `bash scripts/sparkbot-start.sh` "
            "to regenerate .env.local and verify Docker/Postgres settings.\n",
            file=sys.stderr,
        )
        raise


if __name__ == "__main__":
    main()
