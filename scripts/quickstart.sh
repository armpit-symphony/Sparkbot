#!/usr/bin/env bash
# Sparkbot Quick Start — Linux / macOS
#
# Starts Sparkbot on your local machine using Docker.
# After running this script, open http://localhost:3000
#
# Usage:
#   bash scripts/quickstart.sh
#
# To set API keys before starting:
#   export OPENAI_API_KEY=sk-...
#   bash scripts/quickstart.sh
#
# Or create .env.local from the template first:
#   cp .env.example .env.local   (then edit .env.local with your keys)

set -euo pipefail

# ── checks ────────────────────────────────────────────────────────────────────

if ! command -v docker &>/dev/null; then
  echo ""
  echo "Docker is required but not found."
  echo "Install Docker Desktop from: https://docs.docker.com/get-docker/"
  echo ""
  exit 1
fi

if ! docker info &>/dev/null; then
  echo ""
  echo "Docker daemon is not running. Please start Docker Desktop and try again."
  echo ""
  exit 1
fi

# ── API key prompt ─────────────────────────────────────────────────────────────

if [ -z "${OPENAI_API_KEY:-}" ] && \
   [ -z "${ANTHROPIC_API_KEY:-}" ] && \
   [ -z "${GOOGLE_API_KEY:-}" ] && \
   [ -z "${GROQ_API_KEY:-}" ] && \
   [ ! -f ".env.local" ]; then
  echo ""
  echo "No LLM API key found. At least one is required."
  echo "Press Enter to skip and add keys to .env.local later."
  echo ""
  read -rp "  OpenAI API key (sk-...): " input_key
  if [ -n "$input_key" ]; then
    export OPENAI_API_KEY="$input_key"
  fi
  echo ""
fi

# ── generate secret key if not set ────────────────────────────────────────────

if [ -z "${SECRET_KEY:-}" ]; then
  if command -v python3 &>/dev/null; then
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  elif command -v openssl &>/dev/null; then
    SECRET_KEY=$(openssl rand -hex 32)
  else
    SECRET_KEY="please-change-this-key-$(date +%s)"
  fi
  export SECRET_KEY
fi

# ── start ─────────────────────────────────────────────────────────────────────

echo ""
echo "Starting Sparkbot..."
echo ""

docker compose -f compose.local.yml up --build -d

echo ""
echo "Sparkbot is running!"
echo ""
echo "  Web UI:    http://localhost:3000"
echo "  API:       http://localhost:8000"
echo "  API docs:  http://localhost:8000/docs"
echo ""
echo "Default passphrase: sparkbot-local"
echo "  (set SPARKBOT_PASSPHRASE in .env.local to change)"
echo ""
echo "CLI chat:"
echo "  python sparkbot-cli.py"
echo ""
echo "To stop:      docker compose -f compose.local.yml down"
echo "To view logs: docker compose -f compose.local.yml logs -f backend"
echo ""
