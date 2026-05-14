from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine, select

from app import crud
from app.core.config import settings
from app.models import User, UserCreate


def _is_sqlite_uri(uri: str) -> bool:
    return uri.strip().lower().startswith("sqlite")


def _sqlite_engine_kwargs(uri: str) -> dict[str, Any]:
    if not _is_sqlite_uri(uri):
        return {}
    return {
        "connect_args": {
            "check_same_thread": False,
            "timeout": 30,
        },
    }


def _register_sqlite_pragmas(db_engine: Engine, uri: str) -> None:
    if not _is_sqlite_uri(uri):
        return

    @event.listens_for(db_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


_database_uri = str(settings.SQLALCHEMY_DATABASE_URI)
engine = create_engine(_database_uri, **_sqlite_engine_kwargs(_database_uri))
_register_sqlite_pragmas(engine, _database_uri)


# make sure all SQLModel models are imported (app.models) before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly
# for more details: https://github.com/fastapi/full-stack-fastapi-template/issues/28


def init_db(session: Session) -> None:
    # Tables should be created with Alembic migrations
    # But if you don't want to use migrations, create
    # the tables un-commenting the next lines
    # from sqlmodel import SQLModel

    # This works because the models are already imported and registered from app.models
    # SQLModel.metadata.create_all(engine)

    user = session.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    ).first()
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
        )
        user = crud.create_user(session=session, user_create=user_in)
