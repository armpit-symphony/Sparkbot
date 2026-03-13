#! /usr/bin/env bash

set -e
set -x

# For PostgreSQL: wait until the DB is ready before proceeding.
# For SQLite: the DB is a local file — no wait needed.
if [ "${DATABASE_TYPE:-postgresql}" != "sqlite" ]; then
    python app/backend_pre_start.py
fi

# Run migrations (or create_all for SQLite which does not support all ALTER TABLE ops)
if [ "${DATABASE_TYPE:-postgresql}" = "sqlite" ]; then
    python app/local_db_init.py
else
    alembic upgrade head
fi

# Create initial data in DB
python app/initial_data.py
