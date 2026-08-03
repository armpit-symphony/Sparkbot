#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

join_by_pipe() {
  local IFS='|'
  printf '%s' "$*"
}

strict_terms=(
  "arm""pit"
  "open""claw"
  "\\.""open""claw"
  "kal""shi"
  "we""po"
  "Her""mes"
  "remote""\\.sparkpitlabs""\\.com"
  "api""\\.sparkpitlabs""\\.com"
  "/home/""sparky"
  "/home/""youruser"
  "gh""o_"
  "sk-[A-Za-z0-9]"
  "OPENAI""_API_KEY=.*[^[:space:]]"
  "ANTHROPIC""_API_KEY=.*[^[:space:]]"
  "GOOGLE""_API_KEY=.*[^[:space:]]"
  "Tele""gram"
  "tele""gram"
  "Co""dex"
  "\\.co""dex"
  "\\.ag""ents"
  "ro""bot"
  "ro""botics"
  "physical""-control"
  "Trae""fik"
  "trae""fik"
)

strict_pattern="$(join_by_pipe "${strict_terms[@]}")"

strict_output="$(grep -RInE "${strict_pattern}" . \
  --exclude-dir=.git \
  --exclude-dir=node_modules \
  --exclude-dir=.venv-local \
  --exclude-dir=.venv-public-test \
  --exclude-dir=tests \
  --exclude=scripts/check-public-safety.sh \
  --exclude=.github/workflows/nightly-release-sync.yml \
  --exclude=.github/workflows/validate-public-shell.yml \
  | grep -v '^./docs/RELEASE_SYNC_CONTRACT.json:' || true)"

if [[ -n "${strict_output}" ]]; then
  echo "FAIL: strict public safety scan found blocked terms"
  printf '%s\n' "${strict_output}"
  exit 1
fi

echo "PASS: strict public safety scan"

identity_terms=("ph""il" "ph""illip" "Ph""ilip" "Ph""il")
identity_pattern="$(join_by_pipe "${identity_terms[@]}")"
identity_output="$(grep -RInE "${identity_pattern}" . \
  --exclude-dir=.git \
  --exclude-dir=node_modules \
  --exclude-dir=.venv-local \
  --exclude-dir=.venv-public-test \
  --exclude-dir=tests \
  --exclude=scripts/check-public-safety.sh \
  --exclude=.github/workflows/nightly-release-sync.yml \
  --exclude=.github/workflows/validate-public-shell.yml \
  | grep -v '^./docs/RELEASE_STANDARDS.md:7:' || true)"

if [[ -n "${identity_output}" ]]; then
  unexpected_identity="$(printf '%s\n' "${identity_output}" | grep -v '^./docs/RELEASE_STANDARDS.md:7:' || true)"
  if [[ -n "${unexpected_identity}" ]]; then
    echo "FAIL: publishing identity scan found unexpected matches"
    printf '%s\n' "${unexpected_identity}"
    exit 1
  fi
fi

echo "PASS: publishing identity scan"

python3 - <<'PY'
from pathlib import Path
bad = []
for p in Path('.').rglob('*'):
    ignored_dirs = {'.git', 'node_modules', '.venv-local', '.venv-public-test', 'tests'}
    if p.is_file() and p.suffix in {'.md', '.py', '.toml', '.yml', '.yaml', '.sh', '.example', '.gitignore', '.tsx', '.ts', '.css', '.html', '.json'} and not ignored_dirs.intersection(p.parts):
        text = p.read_text(errors='ignore')
        for ch in text:
            if ord(ch) > 0xFFFF:
                bad.append((str(p), ch))
if bad:
    print('FAIL: possible emoji or non-BMP characters found')
    for item in bad[:50]:
        print(item)
    raise SystemExit(1)
print('PASS: no non-BMP emoji found')
PY
