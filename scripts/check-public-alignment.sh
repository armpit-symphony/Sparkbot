#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if ! command -v git >/dev/null 2>&1; then
  echo "FAIL: git is required for alignment checks"
  exit 1
fi

echo "Checking alignment gates for public baseline..."

echo "Git branch: $(git rev-parse --abbrev-ref HEAD)"
echo "Git HEAD: $(git rev-parse --short HEAD)"

required_file_list=(
  "docs/REPOSITORY_ALIGNMENT_PROTOCOL.md"
  "docs/PUBLIC_ARTIFACT_MANIFEST.md"
  "docs/RELEASE_SYNC_CONTRACT.json"
  ".github/workflows/validate-public-shell.yml"
  ".github/workflows/test-backend.yml"
  ".github/workflows/test-frontend.yml"
  "scripts/check-public-safety.sh"
  "scripts/check-public-alignment.sh"
  "scripts/check-public-safety.sh"
  "scripts/validate-public-shell.sh"
  "scripts/check-release-sync.sh"
  "scripts/check-release-sync.py"
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

echo "Running source-of-truth/public release sync checks..."

normalize_repo_path() {
  local repo="${1}"
  if [[ "$repo" =~ ^[A-Za-z]:\\ ]]; then
    local drive="${repo:0:1}"
    local rest="${repo:3}"
    rest="${rest//\\//}"
    printf '/mnt/%s/%s' "${drive,,}" "${rest}"
    return
  fi
  echo "$repo"
}

SOURCE_REMOTE_NAME="source-of-truth"
if git remote | grep -q "^${SOURCE_REMOTE_NAME}$"; then
  SOURCE_REMOTE_URL="$(git remote get-url "${SOURCE_REMOTE_NAME}")"
  echo "Alignment remote found: ${SOURCE_REMOTE_NAME} (${SOURCE_REMOTE_URL})"
  SOURCE_REPO=""

  if [[ "$SOURCE_REMOTE_URL" == file://* ]]; then
    SOURCE_REPO="${SOURCE_REMOTE_URL#file://}"
  elif [[ "$SOURCE_REMOTE_URL" == [A-Za-z]:\\* ]]; then
    SOURCE_REPO="${SOURCE_REMOTE_URL}"
  fi

  if [[ -n "$SOURCE_REPO" ]]; then
    SOURCE_REPO="$(normalize_repo_path "$SOURCE_REPO")"
    bash scripts/check-release-sync.sh --source-repo "$SOURCE_REPO"
  else
    echo "WARN: source-of-truth remote is not a local path; run nightly sync via clone workflow."
    bash scripts/check-release-sync.sh --source-repo "$(pwd)"
  fi
else
  echo "WARN: optional source-of-truth remote '${SOURCE_REMOTE_NAME}' not configured."
  echo "PASS: continuing with local artifact contract checks."
  bash scripts/check-release-sync.sh --source-repo "$(pwd)"
fi

echo "PASS: public alignment checks complete"
