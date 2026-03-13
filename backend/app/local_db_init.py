"""SQLite schema initialization for Sparkbot v1 Local.

Used by start-local-backend scripts as an alternative to `alembic upgrade head`
when DATABASE_TYPE=sqlite.

The standard Alembic migrations include op.alter_column() and op.drop_column()
calls that are not natively supported by SQLite's limited ALTER TABLE syntax.
Running them in incremental order on SQLite fails.

For a fresh local install this is not a problem: we can create all tables in
their current final form directly from the SQLModel metadata, then stamp the
Alembic version to head so that future `alembic upgrade head` calls are no-ops.

This approach is correct for v1 Local because:
- Local installs always start with an empty database.
- The final schema is what matters; the migration history is not needed.
- Postgres deployments (hosted) continue to use Alembic migrations unchanged.

Note: in-place SQLite upgrades across Sparkbot versions will require a separate
migration strategy (to be addressed in a future release).
"""
import logging
import subprocess
import sys

from sqlmodel import SQLModel

# Import all models so SQLModel.metadata is fully populated before create_all.
import app.models  # noqa: F401 — side-effect import registers all SQLModel tables
from app.core.db import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_sqlite_schema() -> None:
    """Create all tables from current SQLModel metadata and stamp Alembic head."""
    logger.info("Initializing SQLite schema from SQLModel metadata...")
    SQLModel.metadata.create_all(engine, checkfirst=True)
    logger.info("SQLite tables created (or already exist).")

    # Stamp the alembic_version table to the current head revision.
    # This creates the alembic_version table if absent and marks the DB as
    # fully migrated so that `alembic upgrade head` is a no-op.
    logger.info("Stamping Alembic revision to head...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "stamp", "head"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        logger.info("Alembic revision stamped to head.")
    else:
        # Non-fatal: the app will still run; only future alembic commands are affected.
        logger.warning("Could not stamp alembic revision: %s", result.stderr.strip())


def main() -> None:
    init_sqlite_schema()


if __name__ == "__main__":
    main()
