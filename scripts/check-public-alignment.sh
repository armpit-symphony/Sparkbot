#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "Checking alignment gates for public baseline..."

if ! command -v git >/dev/null 2>&1; then
  echo "FAIL: git is required for alignment checks"
  exit 1
fi

echo "Git branch: $(git rev-parse --abbrev-ref HEAD)"
echo "Git HEAD: $(git rev-parse --short HEAD)"

required_file_list=(
  "docs/REPOSITORY_ALIGNMENT_PROTOCOL.md"
  "docs/PUBLIC_ARTIFACT_MANIFEST.md"
  ".github/workflows/validate-public-shell.yml"
  ".github/workflows/test-backend.yml"
  ".github/workflows/test-frontend.yml"
  "scripts/check-public-safety.sh"
  "scripts/validate-public-shell.sh"
)

for required_file in "${required_file_list[@]}"; do
  if [ ! -f "${required_file}" ]; then
    echo "FAIL: missing required public-release file ${required_file}"
    exit 1
  fi
done

if ! git diff --cached --quiet; then
  echo "WARN: staged changes exist; this check validates working tree contents only."
fi

echo "Running public safety scan..."
bash scripts/check-public-safety.sh

echo "Running public shell validation..."
bash scripts/validate-public-shell.sh

SOURCE_REMOTE_NAME="source-of-truth"
if git remote | grep -q "^${SOURCE_REMOTE_NAME}$"; then
  SOURCE_REMOTE_URL="$(git remote get-url "${SOURCE_REMOTE_NAME}")"
  echo "Alignment remote found: ${SOURCE_REMOTE_NAME} (${SOURCE_REMOTE_URL})"
  git fetch "${SOURCE_REMOTE_NAME}" --prune >/dev/null 2>&1 || {
    echo "WARN: could not fetch ${SOURCE_REMOTE_NAME}; continuing with local checks only."
  }
  if ! git ls-remote --exit-code --heads "${SOURCE_REMOTE_NAME}" >/dev/null 2>&1; then
    echo "WARN: no remote heads found on ${SOURCE_REMOTE_NAME}."
  fi
else
  echo "WARN: optional source-of-truth remote '${SOURCE_REMOTE_NAME}' not configured."
fi

echo "PASS: public alignment checks complete"
