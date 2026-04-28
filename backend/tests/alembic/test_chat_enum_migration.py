from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import sqlalchemy as sa


ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = ROOT / "app" / "alembic" / "versions" / "2c8b4e0f1a7d_create_chat_tables.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("chat_tables_migration", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chat_table_enums_are_created_checkfirst_and_not_recreated_by_columns(monkeypatch) -> None:
    migration = _load_migration()
    created: list[tuple[str, bool]] = []
    tables: list[tuple[str, tuple[object, ...]]] = []

    for enum_type in (
        migration.USER_TYPE_ENUM,
        migration.ROOM_ROLE_ENUM,
        migration.MEETING_ARTIFACT_TYPE_ENUM,
    ):
        monkeypatch.setattr(
            enum_type,
            "create",
            lambda bind, checkfirst=False, enum_type=enum_type: created.append((enum_type.name, checkfirst)),
        )

    fake_op = SimpleNamespace(
        get_bind=lambda: object(),
        create_table=lambda name, *columns, **kwargs: tables.append((name, columns)),
        create_index=lambda *args, **kwargs: None,
        f=lambda name: name,
    )
    monkeypatch.setattr(migration, "op", fake_op)

    migration.upgrade()

    assert created == [
        ("usertype", True),
        ("roomrole", True),
        ("meetingartifacttype", True),
    ]

    enum_columns = [
        column
        for _table_name, columns in tables
        for column in columns
        if isinstance(column, sa.Column) and getattr(column.type, "name", None) in {"usertype", "roomrole", "meetingartifacttype"}
    ]
    assert enum_columns
    assert all(getattr(column.type, "create_type", None) is False for column in enum_columns)
