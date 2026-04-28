#!/usr/bin/env bash
# Sparkbot first-run setup wizard for Docker/server installs.
#
# This script intentionally avoids printing provider key values itself. Provider
# prompts are visible by default so paste works reliably over SSH.

set -euo pipefail

SPARKBOT_SETUP_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPARKBOT_SETUP_ROOT_DIR="$(cd "${SPARKBOT_SETUP_SCRIPT_DIR}/.." && pwd)"
SPARKBOT_SETUP_ENV_FILE="${SPARKBOT_ENV_FILE:-${SPARKBOT_SETUP_ROOT_DIR}/.env.local}"
SPARKBOT_SETUP_TEMPLATE="${SPARKBOT_ENV_TEMPLATE:-${SPARKBOT_SETUP_ROOT_DIR}/.env.local.example}"

SPARKBOT_PROVIDER_KEYS=(
  "OPENAI_API_KEY:OpenAI:gpt-5-mini:openai"
  "ANTHROPIC_API_KEY:Anthropic:claude-sonnet-4-5:anthropic"
  "GOOGLE_API_KEY:Google:gemini/gemini-2.0-flash:google"
  "GROQ_API_KEY:Groq:groq/llama-3.3-70b-versatile:groq"
  "MINIMAX_API_KEY:MiniMax:minimax/MiniMax-M2.5:minimax"
  "OPENROUTER_API_KEY:OpenRouter:openrouter/openai/gpt-4o-mini:openrouter"
)
SPARKBOT_SETUP_HIDE_INPUT="${SPARKBOT_SETUP_HIDE_INPUT:-0}"

sparkbot_detect_compose() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    printf '%s\n' "docker compose"
    return 0
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    printf '%s\n' "docker-compose"
    return 0
  fi
  cat >&2 <<'EOF'
Docker Compose was not found.

Install Docker Engine or Docker Desktop, then rerun this command.
Sparkbot supports either:
  - docker compose   (Compose v2, preferred)
  - docker-compose   (legacy Compose v1)

Install guide: https://docs.docker.com/get-docker/
EOF
  return 1
}

sparkbot_ensure_env_file() {
  if [ -f "${SPARKBOT_SETUP_ENV_FILE}" ]; then
    return 0
  fi
  if [ ! -f "${SPARKBOT_SETUP_TEMPLATE}" ]; then
    echo "Missing template: ${SPARKBOT_SETUP_TEMPLATE}" >&2
    return 1
  fi
  cp "${SPARKBOT_SETUP_TEMPLATE}" "${SPARKBOT_SETUP_ENV_FILE}"
  chmod 600 "${SPARKBOT_SETUP_ENV_FILE}" 2>/dev/null || true
  echo "Created ${SPARKBOT_SETUP_ENV_FILE} from .env.local.example."
}

sparkbot_env_get() {
  local key="$1"
  local line
  [ -f "${SPARKBOT_SETUP_ENV_FILE}" ] || return 0
  while IFS= read -r line || [ -n "${line}" ]; do
    line="${line%$'\r'}"
    case "${line}" in
      "${key}="*) printf '%s\n' "${line#*=}"; return 0 ;;
    esac
  done < "${SPARKBOT_SETUP_ENV_FILE}"
}

sparkbot_env_has_value() {
  local key="$1"
  local value
  value="$(sparkbot_env_get "${key}")"
  [ -n "${value}" ] || return 1
  case "${value}" in
    REPLACE_WITH_*|changeme|please-change-this-secret-key-min-32) return 1 ;;
  esac
  return 0
}

sparkbot_env_set() {
  local key="$1"
  local value="$2"
  local file="${SPARKBOT_SETUP_ENV_FILE}"
  local tmp="${file}.tmp.$$"

  if [ -f "${file}" ] && grep -q "^${key}=" "${file}"; then
    awk -v key="${key}" -v value="${value}" '
      BEGIN { replaced = 0 }
      $0 ~ "^" key "=" {
        print key "=" value
        replaced = 1
        next
      }
      { print }
      END {
        if (!replaced) print key "=" value
      }
    ' "${file}" > "${tmp}"
    mv "${tmp}" "${file}"
  else
    printf '%s=%s\n' "${key}" "${value}" >> "${file}"
  fi
}

sparkbot_generate_secret_key() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets; print(secrets.token_hex(32))'
  elif command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    printf 'sparkbot-local-%s\n' "$(date +%s)"
  fi
}

sparkbot_ensure_secret_key() {
  if sparkbot_env_has_value "SECRET_KEY"; then
    return 0
  fi
  sparkbot_env_set "SECRET_KEY" "$(sparkbot_generate_secret_key)"
}

sparkbot_env_set_if_missing() {
  local key="$1"
  local value="$2"
  if ! sparkbot_env_has_value "${key}"; then
    sparkbot_env_set "${key}" "${value}"
  fi
}

sparkbot_ensure_local_docker_db_defaults() {
  case "$(basename "${SPARKBOT_SETUP_ENV_FILE}")" in
    .env.local)
      sparkbot_env_set_if_missing "DATABASE_TYPE" "postgresql"
      sparkbot_env_set_if_missing "POSTGRES_SERVER" "db"
      sparkbot_env_set_if_missing "POSTGRES_PORT" "5432"
      sparkbot_env_set_if_missing "POSTGRES_DB" "sparkbot"
      sparkbot_env_set_if_missing "POSTGRES_USER" "sparkbot"
      sparkbot_env_set_if_missing "POSTGRES_PASSWORD" "sparkbot-local"
      sparkbot_env_set_if_missing "SPARKBOT_FRONTEND_PORT" "3000"
      sparkbot_env_set_if_missing "SPARKBOT_FRONTEND_BIND_HOST" "127.0.0.1"
      ;;
  esac
}

sparkbot_cloud_provider_configured() {
  local item key env_value
  for item in "${SPARKBOT_PROVIDER_KEYS[@]}"; do
    IFS=: read -r key _label _model _provider <<< "${item}"
    env_value="${!key:-}"
    if [ -n "${env_value}" ] || sparkbot_env_has_value "${key}"; then
      return 0
    fi
  done
  return 1
}

sparkbot_ollama_configured() {
  local primary local_model
  primary="$(sparkbot_env_get "SPARKBOT_MODEL")"
  local_model="$(sparkbot_env_get "SPARKBOT_LOCAL_MODEL")"
  [[ "${primary}" == ollama/* || "${local_model}" == ollama/* ]]
}

sparkbot_has_model_provider_config() {
  sparkbot_cloud_provider_configured || sparkbot_ollama_configured
}

sparkbot_model_provider() {
  local model="$1"
  case "${model}" in
    openrouter/*) printf '%s\n' "openrouter" ;;
    ollama/*) printf '%s\n' "ollama" ;;
    gpt-*|codex-*) printf '%s\n' "openai" ;;
    claude*) printf '%s\n' "anthropic" ;;
    gemini/*) printf '%s\n' "google" ;;
    groq/*) printf '%s\n' "groq" ;;
    minimax/*) printf '%s\n' "minimax" ;;
    *) printf '%s\n' "other" ;;
  esac
}

sparkbot_model_is_usable() {
  local model="$1"
  local provider key _label _model _provider item
  [ -n "${model}" ] || return 1
  provider="$(sparkbot_model_provider "${model}")"
  if [ "${provider}" = "ollama" ]; then
    sparkbot_ollama_configured
    return $?
  fi
  for item in "${SPARKBOT_PROVIDER_KEYS[@]}"; do
    IFS=: read -r key _label _model _provider <<< "${item}"
    if [ "${_provider}" = "${provider}" ] && { [ -n "${!key:-}" ] || sparkbot_env_has_value "${key}"; }; then
      return 0
    fi
  done
  return 1
}

sparkbot_yes_no() {
  local prompt="$1"
  local default="${2:-yes}"
  local suffix raw
  if [ "${SPARKBOT_SETUP_ASSUME_YES:-}" = "1" ]; then
    return 0
  fi
  if [ "${default}" = "yes" ]; then
    suffix="Y/n"
  else
    suffix="y/N"
  fi
  while true; do
    read -r -p "${prompt} [${suffix}]: " raw
    raw="$(printf '%s' "${raw}" | tr '[:upper:]' '[:lower:]')"
    if [ -z "${raw}" ]; then
      [ "${default}" = "yes" ]
      return $?
    fi
    case "${raw}" in
      y|yes) return 0 ;;
      n|no) return 1 ;;
      *) echo "Enter y or n." ;;
    esac
  done
}

sparkbot_ssh_session() {
  [ -n "${SSH_CONNECTION:-}" ] || [ -n "${SSH_TTY:-}" ] || [ -n "${SSH_CLIENT:-}" ]
}

sparkbot_prompt_secret() {
  local prompt="$1"
  local value
  if [ "${SPARKBOT_SETUP_HIDE_INPUT}" = "1" ]; then
    echo "Input will be hidden. Paste/type your key, then press Enter." >&2
    printf '%s: ' "${prompt}" >&2
    read -r -s value
    printf '\n' >&2
  else
    if sparkbot_ssh_session; then
      echo "SSH session detected. Provider key input will be visible so paste works reliably." >&2
    fi
    echo "Your key will be visible while typing in this terminal session." >&2
    printf '%s: ' "${prompt}" >&2
    read -r value
  fi
  printf '%s' "${value}"
}

sparkbot_store_provider_key() {
  local key="$1"
  local label="$2"
  local existing
  existing="$(sparkbot_env_get "${key}")"

  if [ -n "${existing}" ]; then
    if [ "${SPARKBOT_SETUP_NONINTERACTIVE:-}" = "1" ] && [ "${SPARKBOT_SETUP_OVERWRITE:-}" != "1" ]; then
      return 0
    fi
    if ! sparkbot_yes_no "${label} key is already set. Replace it?" "no"; then
      return 0
    fi
  fi

  local incoming="${!key:-}"
  if [ -z "${incoming}" ] && [ "${SPARKBOT_SETUP_NONINTERACTIVE:-}" != "1" ]; then
    incoming="$(sparkbot_prompt_secret "${label} API key (Enter to skip)")"
  fi
  if [ -n "${incoming}" ]; then
    sparkbot_env_set "${key}" "${incoming}"
    echo "${label} key saved."
  fi
}

sparkbot_pick_default_model() {
  local configured=()
  local item key label model provider idx raw
  local current_model
  current_model="$(sparkbot_env_get "SPARKBOT_MODEL")"

  if sparkbot_model_is_usable "${current_model}"; then
    if [ "${SPARKBOT_SETUP_NONINTERACTIVE:-}" = "1" ]; then
      return 0
    fi
    if sparkbot_yes_no "Keep existing default model ${current_model}?" "yes"; then
      return 0
    fi
  fi

  for item in "${SPARKBOT_PROVIDER_KEYS[@]}"; do
    IFS=: read -r key label model provider <<< "${item}"
    if [ -n "${!key:-}" ] || sparkbot_env_has_value "${key}"; then
      configured+=("${provider}:${model}:${label}")
    fi
  done
  if sparkbot_ollama_configured; then
    local local_model
    local_model="$(sparkbot_env_get "SPARKBOT_LOCAL_MODEL")"
    [ -n "${local_model}" ] || local_model="$(sparkbot_env_get "SPARKBOT_MODEL")"
    configured+=("ollama:${local_model}:Local Ollama")
  fi

  if [ "${#configured[@]}" -eq 0 ]; then
    return 1
  fi

  if [ "${SPARKBOT_SETUP_NONINTERACTIVE:-}" = "1" ]; then
    IFS=: read -r provider model _label <<< "${configured[0]}"
    sparkbot_env_set "SPARKBOT_DEFAULT_PROVIDER" "${provider}"
    sparkbot_env_set "SPARKBOT_MODEL" "${model}"
    sparkbot_env_set "SPARKBOT_HEAVY_HITTER_MODEL" "${model}"
    return 0
  fi

  echo ""
  echo "Choose the default model Sparkbot should use first:"
  idx=1
  for item in "${configured[@]}"; do
    IFS=: read -r provider model label <<< "${item}"
    echo "  ${idx}. ${label} - ${model}"
    idx=$((idx + 1))
  done
  while true; do
    read -r -p "Default model [1]: " raw
    raw="${raw:-1}"
    if [[ "${raw}" =~ ^[0-9]+$ ]] && [ "${raw}" -ge 1 ] && [ "${raw}" -le "${#configured[@]}" ]; then
      IFS=: read -r provider model _label <<< "${configured[$((raw - 1))]}"
      sparkbot_env_set "SPARKBOT_DEFAULT_PROVIDER" "${provider}"
      sparkbot_env_set "SPARKBOT_MODEL" "${model}"
      sparkbot_env_set "SPARKBOT_HEAVY_HITTER_MODEL" "${model}"
      echo "Default model saved."
      return 0
    fi
    echo "Enter a number from the list."
  done
}

sparkbot_prompt_ollama() {
  local existing_model base_url model use_ollama
  existing_model="$(sparkbot_env_get "SPARKBOT_LOCAL_MODEL")"
  if [ -z "${existing_model}" ]; then
    existing_model="$(sparkbot_env_get "SPARKBOT_MODEL")"
    [[ "${existing_model}" == ollama/* ]] || existing_model="ollama/phi4-mini"
  fi

  if [ "${SPARKBOT_SETUP_NONINTERACTIVE:-}" = "1" ]; then
    if [ -n "${SPARKBOT_SETUP_OLLAMA_MODEL:-}" ]; then
      sparkbot_env_set "OLLAMA_API_BASE" "${SPARKBOT_SETUP_OLLAMA_BASE_URL:-http://host.docker.internal:11434}"
      sparkbot_env_set "SPARKBOT_LOCAL_MODEL" "${SPARKBOT_SETUP_OLLAMA_MODEL}"
    fi
    return 0
  fi

  if sparkbot_ollama_configured; then
    use_ollama="yes"
  else
    use_ollama="no"
  fi
  if ! sparkbot_yes_no "Use a local Ollama model?" "${use_ollama}"; then
    return 0
  fi
  read -r -p "Ollama model [${existing_model}]: " model
  model="${model:-${existing_model}}"
  if [[ "${model}" != ollama/* ]]; then
    model="ollama/${model}"
  fi
  base_url="$(sparkbot_env_get "OLLAMA_API_BASE")"
  base_url="${base_url:-http://host.docker.internal:11434}"
  read -r -p "Ollama API URL visible from Docker [${base_url}]: " input_base_url
  base_url="${input_base_url:-${base_url}}"
  sparkbot_env_set "OLLAMA_API_BASE" "${base_url}"
  sparkbot_env_set "SPARKBOT_LOCAL_MODEL" "${model}"
  echo "Local Ollama route saved."
}

sparkbot_setup_wizard() {
  local compose_cmd item key label _model _provider
  if [ "${SPARKBOT_SETUP_SKIP_COMPOSE_CHECK:-}" = "1" ]; then
    echo "Skipping Docker Compose check."
  else
    compose_cmd="$(sparkbot_detect_compose)"
    echo "Using Docker Compose command: ${compose_cmd}"
  fi

  sparkbot_ensure_env_file
  sparkbot_ensure_secret_key
  sparkbot_ensure_local_docker_db_defaults

  echo ""
  echo "Sparkbot setup"
  echo "Add at least one cloud provider key, or choose a local Ollama model."
  echo "Press Enter at any key prompt to skip that provider."
  echo "Provider key prompts are visible by default so SSH paste works reliably."
  echo "Use --hide-input if you prefer hidden provider key entry."
  echo ""

  for item in "${SPARKBOT_PROVIDER_KEYS[@]}"; do
    IFS=: read -r key label _model _provider <<< "${item}"
    sparkbot_store_provider_key "${key}" "${label}"
  done

  sparkbot_prompt_ollama

  if ! sparkbot_has_model_provider_config; then
    cat >&2 <<'EOF'

No model provider is configured yet.
Run this setup again and add at least one provider key, or choose a local Ollama model.
EOF
    return 1
  fi

  sparkbot_pick_default_model
  echo ""
  echo "Setup complete. Secrets were written to ${SPARKBOT_SETUP_ENV_FILE} and were not printed."
}

sparkbot_setup_main() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --show-input)
        SPARKBOT_SETUP_HIDE_INPUT=0
        shift
        ;;
      --hide-input)
        SPARKBOT_SETUP_HIDE_INPUT=1
        shift
        ;;
      --from-env)
        SPARKBOT_SETUP_NONINTERACTIVE=1
        shift
        ;;
      --openai-key)
        [ "$#" -ge 2 ] || { echo "--openai-key requires a value." >&2; return 2; }
        OPENAI_API_KEY="$2"
        SPARKBOT_SETUP_NONINTERACTIVE=1
        shift 2
        ;;
      --anthropic-key)
        [ "$#" -ge 2 ] || { echo "--anthropic-key requires a value." >&2; return 2; }
        ANTHROPIC_API_KEY="$2"
        SPARKBOT_SETUP_NONINTERACTIVE=1
        shift 2
        ;;
      --google-key)
        [ "$#" -ge 2 ] || { echo "--google-key requires a value." >&2; return 2; }
        GOOGLE_API_KEY="$2"
        SPARKBOT_SETUP_NONINTERACTIVE=1
        shift 2
        ;;
      --groq-key)
        [ "$#" -ge 2 ] || { echo "--groq-key requires a value." >&2; return 2; }
        GROQ_API_KEY="$2"
        SPARKBOT_SETUP_NONINTERACTIVE=1
        shift 2
        ;;
      --minimax-key)
        [ "$#" -ge 2 ] || { echo "--minimax-key requires a value." >&2; return 2; }
        MINIMAX_API_KEY="$2"
        SPARKBOT_SETUP_NONINTERACTIVE=1
        shift 2
        ;;
      --openrouter-key)
        [ "$#" -ge 2 ] || { echo "--openrouter-key requires a value." >&2; return 2; }
        OPENROUTER_API_KEY="$2"
        SPARKBOT_SETUP_NONINTERACTIVE=1
        shift 2
        ;;
      --)
        shift
        break
        ;;
      *)
        break
        ;;
    esac
  done

  case "${1:-}" in
    --print-compose-command)
      sparkbot_detect_compose
      ;;
    --check-config)
      sparkbot_has_model_provider_config
      ;;
    --non-interactive)
      SPARKBOT_SETUP_NONINTERACTIVE=1 sparkbot_setup_wizard
      ;;
    -h|--help)
      cat <<'EOF'
Usage: bash scripts/sparkbot-setup.sh [options]

Guides first-run Docker/server setup, writes .env.local safely, and detects
Docker Compose v2 or legacy docker-compose.

Options:
  --show-input             Compatibility alias; provider input is visible by default.
  --hide-input             Hide provider key input (not recommended over SSH).
  --from-env               Import exported provider key environment variables.
  --openai-key KEY         Save an OpenAI API key.
  --anthropic-key KEY      Save an Anthropic API key.
  --google-key KEY         Save a Google API key.
  --groq-key KEY           Save a Groq API key.
  --minimax-key KEY        Save a MiniMax API key.
  --openrouter-key KEY     Save an OpenRouter API key.
EOF
      ;;
    *)
      sparkbot_setup_wizard
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  sparkbot_setup_main "$@"
fi
