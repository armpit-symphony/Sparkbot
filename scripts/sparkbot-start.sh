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

env_get() {
  local key="$1"
  local line
  [ -f "${ENV_FILE}" ] || return 0
  while IFS= read -r line || [ -n "${line}" ]; do
    line="${line%$'\r'}"
    case "${line}" in
      "${key}="*) printf '%s\n' "${line#*=}"; return 0 ;;
    esac
  done < "${ENV_FILE}"
}

env_set() {
  local key="$1"
  local value="$2"
  local tmp="${ENV_FILE}.tmp.$$"
  if [ -f "${ENV_FILE}" ] && grep -q "^${key}=" "${ENV_FILE}"; then
    awk -v key="${key}" -v value="${value}" '
      $0 ~ "^" key "=" { print key "=" value; replaced = 1; next }
      { print }
      END { if (!replaced) print key "=" value }
    ' "${ENV_FILE}" > "${tmp}"
    mv "${tmp}" "${ENV_FILE}"
  else
    printf '%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
  fi
}

valid_port() {
  local port="$1"
  [[ "${port}" =~ ^[0-9]+$ ]] && [ "${port}" -ge 1 ] && [ "${port}" -le 65535 ]
}

port_available() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ! ss -ltn | awk -v port=":${port}" 'NR > 1 && $4 ~ port "$" { found = 1 } END { exit found ? 0 : 1 }'
  elif command -v lsof >/dev/null 2>&1; then
    ! lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
  else
    python3 - "${port}" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        sys.exit(1)
PY
  fi
}

next_available_port() {
  local port="$1"
  while [ "${port}" -le 65535 ]; do
    if port_available "${port}"; then
      printf '%s\n' "${port}"
      return 0
    fi
    port=$((port + 1))
  done
  return 1
}

choose_frontend_port() {
  local requested="${SPARKBOT_FRONTEND_PORT:-}"
  if [ -z "${requested}" ]; then
    requested="$(env_get "SPARKBOT_FRONTEND_PORT")"
  fi
  requested="${requested:-3000}"
  if ! valid_port "${requested}"; then
    echo "SPARKBOT_FRONTEND_PORT must be a valid TCP port from 1 to 65535." >&2
    exit 1
  fi
  if port_available "${requested}"; then
    env_set "SPARKBOT_FRONTEND_PORT" "${requested}"
    printf '%s\n' "${requested}"
    return 0
  fi

  local selected
  selected="$(next_available_port "$((requested + 1))")" || {
    echo "No available frontend port found after ${requested}." >&2
    exit 1
  }
  echo "Port ${requested} is already in use. Using ${selected} for Sparkbot web UI." >&2
  env_set "SPARKBOT_FRONTEND_PORT" "${selected}"
  printf '%s\n' "${selected}"
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

frontend_port="$(choose_frontend_port)"
export SPARKBOT_FRONTEND_PORT="${frontend_port}"

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

Web UI: http://localhost:${frontend_port}
API:    http://localhost:8000
Passphrase: ${passphrase_label}

Next steps:
  1. Open http://localhost:${frontend_port}
  2. Sign in with the passphrase above
  3. Open Sparkbot Controls to change providers, models, or safety settings

Stop Sparkbot:
  ${compose_cmd} -f compose.local.yml down

Backend logs:
  ${compose_cmd} -f compose.local.yml logs -f backend

EOF

"${compose_parts[@]}" -f compose.local.yml up --build
