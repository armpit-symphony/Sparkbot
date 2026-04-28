#! /usr/bin/env bash

set -Eeuo pipefail

on_error() {
    local exit_code=$?
    echo ""
    echo "Sparkbot prestart failed while running: ${BASH_COMMAND}" >&2
    echo "Exit code: ${exit_code}" >&2
    echo "The full exception should be visible above. Provider secrets are not printed by this script." >&2
    exit "${exit_code}"
}
trap on_error ERR

# For PostgreSQL: wait until the DB is ready before proceeding.
# For SQLite: the DB is a local file — no wait needed.
if [ "${DATABASE_TYPE:-postgresql}" != "sqlite" ]; then
    python app/backend_pre_start.py
fi

# Run migrations (or create_all for SQLite which does not support all ALTER TABLE ops)
if [ "${DATABASE_TYPE:-postgresql}" = "sqlite" ]; then
    python app/local_db_init.py
else
    echo "Running database migrations..."
    alembic upgrade head
fi

# Create initial data in DB
echo "Creating initial data..."
python app/initial_data.py
