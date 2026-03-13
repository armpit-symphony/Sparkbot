#!/usr/bin/env bash
# Sparkbot v1 Local — bare-metal backend startup (Linux / macOS)
#
# Starts the Sparkbot backend without Docker using SQLite.
# Requires: Python 3.10+ and uv (https://docs.astral.sh/uv/)
#
# Usage:
#   bash scripts/start-local-backend.sh
#   API_PORT=8001 bash scripts/start-local-backend.sh
#
# On first run: creates the SQLite database and seeds the first superuser.
# On subsequent runs: database is reused; migrations are applied if needed.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
API_PORT="${API_PORT:-8000}"

# ── Locate uv ─────────────────────────────────────────────────────────────────
# Try PATH first; fall back to the standard install location.
if command -v uv &>/dev/null; then
    UV=uv
elif [ -x "$HOME/.local/bin/uv" ]; then
    UV="$HOME/.local/bin/uv"
else
    echo ""
    echo "ERROR: uv not found. Install it with:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo ""
    exit 1
fi

# ── Auto-generate a SECRET_KEY if not set ─────────────────────────────────────
if [ -z "$SECRET_KEY" ]; then
    export SECRET_KEY
    SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
fi

# ── V1 Local environment ──────────────────────────────────────────────────────
export V1_LOCAL_MODE=true
export DATABASE_TYPE=sqlite
export WORKSTATION_LIVE_TERMINAL_ENABLED=false
export ENVIRONMENT=local
export PROJECT_NAME="${PROJECT_NAME:-Sparkbot}"

# ── Data directory ────────────────────────────────────────────────────────────
# Default: ~/.local/share/sparkbot on Linux, ~/Library/Application Support/Sparkbot on macOS
if [ -z "$SPARKBOT_DATA_DIR" ]; then
    if [ "$(uname)" = "Darwin" ]; then
        export SPARKBOT_DATA_DIR="$HOME/Library/Application Support/Sparkbot"
    else
        export SPARKBOT_DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/sparkbot"
    fi
fi
if [ -z "$SPARKBOT_GUARDIAN_DATA_DIR" ]; then
    export SPARKBOT_GUARDIAN_DATA_DIR="$SPARKBOT_DATA_DIR/guardian"
fi
mkdir -p "$SPARKBOT_DATA_DIR"
mkdir -p "$SPARKBOT_GUARDIAN_DATA_DIR"

# ── Defaults for local single-user install ────────────────────────────────────
export SPARKBOT_PASSPHRASE="${SPARKBOT_PASSPHRASE:-sparkbot-local}"
export FIRST_SUPERUSER="${FIRST_SUPERUSER:-admin@example.com}"
export FIRST_SUPERUSER_PASSWORD="${FIRST_SUPERUSER_PASSWORD:-sparkbot-local}"
export BACKEND_CORS_ORIGINS="${BACKEND_CORS_ORIGINS:-http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173}"
export FRONTEND_HOST="${FRONTEND_HOST:-http://localhost:3000}"

echo ""
echo "Sparkbot v1 Local — bare-metal backend"
echo "  Data dir : $SPARKBOT_DATA_DIR"
echo "  Guardian : $SPARKBOT_GUARDIAN_DATA_DIR"
echo "  Port     : $API_PORT"
echo "  DB       : SQLite"
echo ""

# ── Run from backend directory ────────────────────────────────────────────────
cd "$REPO_ROOT/backend"

# Initialize database schema.
# SQLite (v1 local) uses create_all + alembic stamp to avoid ALTER TABLE issues.
# Postgres (hosted) uses normal alembic upgrade head.
echo "Initializing database schema..."
if [ "$DATABASE_TYPE" = "sqlite" ]; then
    "$UV" run python app/local_db_init.py
else
    "$UV" run alembic upgrade head
fi

# Seed first superuser if not already present
echo "Seeding initial data..."
"$UV" run python app/initial_data.py

# Start backend
echo ""
echo "Starting backend..."
echo "  Health check : http://127.0.0.1:$API_PORT/api/v1/utils/health-check/"
echo "  API docs     : http://127.0.0.1:$API_PORT/docs"
echo ""
echo "Press Ctrl+C to stop."
echo ""

exec "$UV" run fastapi run --port "$API_PORT" app/main.py
