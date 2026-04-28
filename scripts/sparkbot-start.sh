#!/usr/bin/env bash
# One-command Sparkbot launcher for local Docker/server installs.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SETUP_SCRIPT="${ROOT_DIR}/scripts/sparkbot-setup.sh"
ENV_FILE="${SPARKBOT_ENV_FILE:-${ROOT_DIR}/.env.local}"
COMPOSE_ENV_FILE="${SPARKBOT_COMPOSE_ENV_FILE:-${ROOT_DIR}/.env}"
INSTALL_DOCKER_PLUGINS=0
START_MODE=""
START_SHOW_INPUT=0
SETUP_ARGS=()

for arg in "$@"; do
  case "${arg}" in
    --install-docker-plugins)
      INSTALL_DOCKER_PLUGINS=1
      ;;
    --local)
      START_MODE="local"
      ;;
    --server)
      START_MODE="server"
      ;;
    --show-input)
      START_SHOW_INPUT=1
      SETUP_ARGS+=("${arg}")
      ;;
    --hide-input)
      SETUP_ARGS+=("${arg}")
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

env_get_from_file() {
  local file="$1"
  local key="$2"
  local line
  [ -f "${file}" ] || return 0
  while IFS= read -r line || [ -n "${line}" ]; do
    line="${line%$'\r'}"
    case "${line}" in
      "${key}="*) printf '%s\n' "${line#*=}"; return 0 ;;
    esac
  done < "${file}"
}

env_get() {
  env_get_from_file "${ENV_FILE}" "$1"
}

env_set_in_file() {
  local file="$1"
  local key="$2"
  local value="$3"
  local tmp="${file}.tmp.$$"
  touch "${file}"
  if grep -q "^${key}=" "${file}"; then
    awk -v key="${key}" -v value="${value}" '
      $0 ~ "^" key "=" { print key "=" value; replaced = 1; next }
      { print }
      END { if (!replaced) print key "=" value }
    ' "${file}" > "${tmp}"
    mv "${tmp}" "${file}"
  else
    printf '%s=%s\n' "${key}" "${value}" >> "${file}"
  fi
}

env_set() {
  env_set_in_file "${ENV_FILE}" "$1" "$2"
}

bind_host_configured_at_start() {
  [ -f "${ENV_FILE}" ] && [ -n "$(env_get "SPARKBOT_FRONTEND_BIND_HOST")" ]
}

valid_port() {
  local port="$1"
  [[ "${port}" =~ ^[0-9]+$ ]] && [ "${port}" -ge 1 ] && [ "${port}" -le 65535 ]
}

valid_bind_host() {
  local host="$1"
  case "${host}" in
    127.0.0.1|0.0.0.0|localhost)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

weak_passphrase() {
  local value="${1:-}"
  [ -n "${value}" ] || return 0
  case "${value}" in
    sparkbot-local|changeme|changeme-in-production|changethis|password|admin123|REPLACE_WITH_*|replace-with-*|please-change*)
      return 0
      ;;
  esac
  [ "${#value}" -lt 12 ]
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

choose_frontend_bind_host() {
  local selected=""
  case "${START_MODE}" in
    local)
      selected="127.0.0.1"
      ;;
    server)
      selected="0.0.0.0"
      ;;
    "")
      selected="${SPARKBOT_FRONTEND_BIND_HOST:-}"
      if [ -z "${selected}" ] && [ "${BIND_HOST_CONFIGURED_AT_START}" = "1" ]; then
        selected="$(env_get "SPARKBOT_FRONTEND_BIND_HOST")"
      fi
      if [ -z "${selected}" ] && [ -t 0 ] && [ -t 1 ]; then
        cat <<'EOF'
Where are you running Sparkbot?

1) Personal local machine (safer)
   Binds the web UI to 127.0.0.1.

2) Cloud server / VPS / DigitalOcean
   Binds the web UI to 0.0.0.0 so your laptop or phone can reach it.
EOF
        read -r -p "Choose install mode [1]: " mode_choice
        case "${mode_choice}" in
          2) selected="0.0.0.0" ;;
          *) selected="127.0.0.1" ;;
        esac
      fi
      selected="${selected:-127.0.0.1}"
      ;;
    *)
      echo "Unknown start mode: ${START_MODE}" >&2
      exit 1
      ;;
  esac

  if ! valid_bind_host "${selected}"; then
    echo "SPARKBOT_FRONTEND_BIND_HOST must be 127.0.0.1, localhost, or 0.0.0.0." >&2
    exit 1
  fi

  env_set "SPARKBOT_FRONTEND_BIND_HOST" "${selected}"
  printf '%s\n' "${selected}"
}

sync_compose_env() {
  local frontend_port="$1"
  local frontend_bind_host="$2"
  local frontend_local_mode="$3"
  env_set_in_file "${COMPOSE_ENV_FILE}" "SPARKBOT_FRONTEND_PORT" "${frontend_port}"
  env_set_in_file "${COMPOSE_ENV_FILE}" "SPARKBOT_FRONTEND_BIND_HOST" "${frontend_bind_host}"
  env_set_in_file "${COMPOSE_ENV_FILE}" "VITE_V1_LOCAL_MODE" "${frontend_local_mode}"
}

detect_public_ip() {
  if [ -n "${SPARKBOT_PUBLIC_HOST:-}" ]; then
    printf '%s\n' "${SPARKBOT_PUBLIC_HOST}"
    return 0
  fi
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 2 https://api.ipify.org 2>/dev/null || true
  fi
}

prompt_server_passphrase() {
  local first second
  while true; do
    if [ "${START_SHOW_INPUT}" = "1" ]; then
      printf 'Create Sparkbot server passphrase: ' >&2
      read -r first
      printf 'Confirm passphrase: ' >&2
      read -r second
    else
      echo "Input will be hidden. Paste/type the new server passphrase, then press Enter." >&2
      printf 'Create Sparkbot server passphrase: ' >&2
      read -r -s first
      printf '\n' >&2
      echo "Input will be hidden. Paste/type it again, then press Enter." >&2
      printf 'Confirm passphrase: ' >&2
      read -r -s second
      printf '\n' >&2
    fi
    if [ "${first}" != "${second}" ]; then
      echo "Passphrases did not match. Try again." >&2
      continue
    fi
    if weak_passphrase "${first}"; then
      echo "Passphrase must be at least 12 characters and cannot use Sparkbot defaults or placeholders." >&2
      continue
    fi
    printf '%s' "${first}"
    return 0
  done
}

ensure_server_auth() {
  local configured="${SPARKBOT_PASSPHRASE:-}"
  if [ -z "${configured}" ]; then
    configured="$(env_get "SPARKBOT_PASSPHRASE")"
  fi

  if truthy "${SPARKBOT_AUTH_DISABLED:-}" || truthy "$(env_get "SPARKBOT_AUTH_DISABLED")"; then
    cat >&2 <<'EOF'
Server mode refuses to start because auth is disabled.
Remove SPARKBOT_AUTH_DISABLED or set it to false before exposing Sparkbot.
EOF
    exit 1
  fi

  if ! weak_passphrase "${configured}"; then
    env_set "SPARKBOT_PASSPHRASE" "${configured}"
    return 0
  fi

  if [ -t 0 ] || [ "${START_SHOW_INPUT}" = "1" ]; then
    cat >&2 <<'EOF'
Server mode requires authentication. Do not expose Sparkbot without a passphrase or reverse proxy auth.
Create a new Sparkbot passphrase before startup.
EOF
    configured="$(prompt_server_passphrase)"
    env_set "SPARKBOT_PASSPHRASE" "${configured}"
    return 0
  fi

  cat >&2 <<'EOF'
Server mode requires authentication. Do not expose Sparkbot without a passphrase or reverse proxy auth.
SPARKBOT_PASSPHRASE is missing, blank, too short, a placeholder, or a default value.
Set a strong passphrase, then rerun:
  export SPARKBOT_PASSPHRASE="replace-with-a-long-private-passphrase"
  bash scripts/sparkbot-start.sh --server
EOF
  exit 1
}

configure_auth_mode() {
  local frontend_bind_host="$1"
  local local_mode="true"
  if [ "${frontend_bind_host}" = "0.0.0.0" ]; then
    ensure_server_auth
    local_mode="false"
  fi
  env_set "V1_LOCAL_MODE" "${local_mode}"
  printf '%s\n' "${local_mode}"
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

BIND_HOST_CONFIGURED_AT_START=0
if bind_host_configured_at_start; then
  BIND_HOST_CONFIGURED_AT_START=1
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
frontend_bind_host="$(choose_frontend_bind_host)"
frontend_local_mode="$(configure_auth_mode "${frontend_bind_host}")"
export SPARKBOT_FRONTEND_PORT="${frontend_port}"
export SPARKBOT_FRONTEND_BIND_HOST="${frontend_bind_host}"
export VITE_V1_LOCAL_MODE="${frontend_local_mode}"
sync_compose_env "${frontend_port}" "${frontend_bind_host}" "${frontend_local_mode}"

web_url="http://localhost:${frontend_port}"
public_ip=""
if [ "${frontend_bind_host}" = "0.0.0.0" ]; then
  public_ip="$(detect_public_ip)"
  public_ip="${public_ip:-<server-ip>}"
  web_url="http://${public_ip}:${frontend_port}"
fi

passphrase=""
passphrase_label="configured in ${ENV_FILE}"
if [ -f "${ENV_FILE}" ]; then
  configured_passphrase="$(awk -F= '/^SPARKBOT_PASSPHRASE=/ {print substr($0, index($0, "=") + 1); exit}' "${ENV_FILE}")"
  if [ -n "${configured_passphrase}" ]; then
    passphrase="${configured_passphrase}"
  fi
fi
if [ -z "${passphrase}" ]; then
  passphrase_label="not configured"
elif [ "${passphrase}" = "sparkbot-local" ]; then
  passphrase_label="local default configured"
fi

cat <<EOF

Starting Sparkbot in the background...

Bind host: ${frontend_bind_host}
Web UI: ${web_url}
API:    http://localhost:8000
Passphrase: ${passphrase_label}
EOF

if [ "${frontend_bind_host}" = "0.0.0.0" ]; then
  cat <<EOF
Detected public IP: ${public_ip}
Open Sparkbot:
${web_url}

Security warning:
  Server mode requires authentication. Do not expose Sparkbot without a passphrase or reverse proxy auth.
  Server mode exposes the Sparkbot web UI on the server network interface.
  Restrict access with a firewall/security group or put Sparkbot behind a
  reverse proxy with authentication before using it on an open network.
EOF
fi

cat <<EOF

Next steps:
  1. Open ${web_url}
  2. Sign in with your configured passphrase
  3. Open Sparkbot Controls to change providers, models, or safety settings

Stop Sparkbot:
  ${compose_cmd} -f compose.local.yml down

Backend logs:
  ${compose_cmd} -f compose.local.yml logs -f backend

EOF

"${compose_parts[@]}" -f compose.local.yml up --build -d
