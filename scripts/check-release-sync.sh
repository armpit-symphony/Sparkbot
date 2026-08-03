#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "FAIL: python3 required" >&2
  exit 1
fi

CONTRACT_FILE="docs/RELEASE_SYNC_CONTRACT.json"
SOURCE_REPO=""
SOURCE_REF=""
if git remote get-url source-of-truth >/dev/null 2>&1; then
  SOURCE_REPO="$(git -C "$ROOT_DIR" remote get-url source-of-truth)"
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-repo)
      SOURCE_REPO="${2:?missing value for --source-repo}"
      shift 2
      ;;
    --source-ref)
      SOURCE_REF="${2:?missing value for --source-ref}"
      SOURCE_REF="${SOURCE_REF%$'\r'}"
      shift 2
      ;;
    --contract)
      CONTRACT_FILE="${2:?missing value for --contract}"
      CONTRACT_FILE="${CONTRACT_FILE%$'\r'}"
      shift 2
      ;;
    --help|-h)
      echo "Usage: $0 --source-repo <path> [--source-ref <branch>] [--contract path]"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$SOURCE_REPO" ]]; then
  echo "FAIL: source-of-truth repo not set. Provide with --source-repo or configure git remote source-of-truth." >&2
  exit 1
fi

CMD=(--public-repo "$ROOT_DIR" --source-repo "$SOURCE_REPO" --contract "$CONTRACT_FILE")
if [[ -n "$SOURCE_REF" ]]; then
  CMD+=(--source-ref "$SOURCE_REF")
fi

python3 "$ROOT_DIR/scripts/check-release-sync.py" "${CMD[@]}"
