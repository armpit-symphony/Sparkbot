#!/usr/bin/env bash
# One-command Sparkbot launcher for local Docker/server installs.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SETUP_SCRIPT="${ROOT_DIR}/scripts/sparkbot-setup.sh"
ENV_FILE="${SPARKBOT_ENV_FILE:-${ROOT_DIR}/.env.local}"
INSTALL_DOCKER_PLUGINS=0
SETUP_ARGS=()

for arg in "$@"; do
  case "${arg}" in
    --install-docker-plugins)
      INSTALL_DOCKER_PLUGINS=1
      ;;
    *)
      SETUP_ARGS+=("${arg}")
      ;;
  esac
done

cd "${ROOT_DIR}"

install_docker_plugins() {
  echo "Installing Docker Compose v2 and buildx plugins with apt..."
  sudo apt update
  sudo apt install docker-buildx-plugin docker-compose-plugin -y
}

buildx_available() {
  docker buildx version >/dev/null 2>&1
}

print_buildx_fix() {
  cat >&2 <<'EOF'
Docker buildx is missing or not working.

Sparkbot's Dockerfiles use BuildKit features, so Docker must have a working
buildx component before `compose up --build` can run.

On Ubuntu, install the Docker plugins, then rerun:
  sudo apt update
  sudo apt install docker-buildx-plugin docker-compose-plugin -y
  bash scripts/sparkbot-start.sh

Or let Sparkbot try that install step:
  bash scripts/sparkbot-start.sh --install-docker-plugins
EOF
}

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

if [ "${INSTALL_DOCKER_PLUGINS}" = "1" ]; then
  install_docker_plugins
fi

compose_cmd="$(bash "${SETUP_SCRIPT}" --print-compose-command)"
read -r -a compose_parts <<< "${compose_cmd}"
if [ "${compose_cmd}" = "docker-compose" ]; then
  echo "Using legacy docker-compose compatibility mode"
fi

if ! buildx_available; then
  print_buildx_fix
  exit 1
fi

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
