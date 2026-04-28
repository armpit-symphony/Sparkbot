#!/usr/bin/env bash
# One-command Sparkbot launcher for local Docker/server installs.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SETUP_SCRIPT="${ROOT_DIR}/scripts/sparkbot-setup.sh"
ENV_FILE="${SPARKBOT_ENV_FILE:-${ROOT_DIR}/.env.local}"
SETUP_ARGS=("$@")

cd "${ROOT_DIR}"

if ! command -v docker >/dev/null 2>&1; then
  cat >&2 <<'EOF'
Docker was not found.

Install Docker Engine or Docker Desktop, then rerun:
  bash scripts/sparkbot-start.sh

Install guide: https://docs.docker.com/get-docker/
EOF
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  cat >&2 <<'EOF'
Docker is installed but the Docker daemon is not running.

Start Docker, then rerun:
  bash scripts/sparkbot-start.sh
EOF
  exit 1
fi

compose_cmd="$(bash "${SETUP_SCRIPT}" --print-compose-command)"
read -r -a compose_parts <<< "${compose_cmd}"

if [ "${#SETUP_ARGS[@]}" -gt 0 ] || [ ! -f "${ENV_FILE}" ] || ! SPARKBOT_ENV_FILE="${ENV_FILE}" bash "${SETUP_SCRIPT}" --check-config; then
  echo ""
  if [ "${#SETUP_ARGS[@]}" -gt 0 ]; then
    echo "Running Sparkbot setup with requested options."
  else
    echo "Sparkbot has not been configured yet. Starting first-run setup."
  fi
  echo ""
  SPARKBOT_ENV_FILE="${ENV_FILE}" bash "${SETUP_SCRIPT}" "${SETUP_ARGS[@]}"
fi

passphrase="sparkbot-local"
passphrase_label="sparkbot-local"
if [ -f "${ENV_FILE}" ]; then
  configured_passphrase="$(awk -F= '/^SPARKBOT_PASSPHRASE=/ {print substr($0, index($0, "=") + 1); exit}' "${ENV_FILE}")"
  if [ -n "${configured_passphrase}" ]; then
    passphrase="${configured_passphrase}"
  fi
fi
if [ "${passphrase}" != "sparkbot-local" ]; then
  passphrase_label="configured in ${ENV_FILE}"
fi

cat <<EOF

Starting Sparkbot...

Web UI: http://localhost:3000
API:    http://localhost:8000
Passphrase: ${passphrase_label}

Next steps:
  1. Open http://localhost:3000
  2. Sign in with the passphrase above
  3. Open Sparkbot Controls to change providers, models, or safety settings

Stop Sparkbot:
  ${compose_cmd} -f compose.local.yml down

Backend logs:
  ${compose_cmd} -f compose.local.yml logs -f backend

EOF

"${compose_parts[@]}" -f compose.local.yml up --build
