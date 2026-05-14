from sqlalchemy import create_engine

from app.core import db


def test_sqlite_engine_kwargs_enable_threaded_busy_timeout() -> None:
    kwargs = db._sqlite_engine_kwargs("sqlite:///sparkbot.db")

    assert kwargs["connect_args"]["check_same_thread"] is False
    assert kwargs["connect_args"]["timeout"] == 30


def test_sqlite_engine_pragmas_enable_wal_and_busy_timeout(tmp_path) -> None:
    uri = f"sqlite:///{tmp_path / 'sparkbot.db'}"
    engine = create_engine(uri, **db._sqlite_engine_kwargs(uri))
    db._register_sqlite_pragmas(engine, uri)

    with engine.connect() as conn:
        busy_timeout = conn.exec_driver_sql("PRAGMA busy_timeout").scalar_one()
        journal_mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar_one()
        synchronous = conn.exec_driver_sql("PRAGMA synchronous").scalar_one()

    assert busy_timeout == 30000
    assert str(journal_mode).lower() == "wal"
    assert synchronous == 1
