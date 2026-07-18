#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  if command -v python >/dev/null 2>&1; then
    PYTHON="python"
  elif command -v python.exe >/dev/null 2>&1; then
    PYTHON="python.exe"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
  else
    echo "python interpreter not found" >&2
    exit 127
  fi
fi
"$PYTHON" - <<'PY'
from pathlib import Path

files = [
    Path("backend/app/services/lima_decision_preview.py"),
    Path("backend/app/api/routes/lima.py"),
    Path("docs/capabilities.md"),
]
required = "LIMA decision preview is non-executing and does not represent active Guardian enforcement."
for path in files:
    text = path.read_text(encoding="utf-8")
    if required not in text:
        raise SystemExit(f"missing required public preview copy in {path}")
    forbidden = [
        "Guardian enforcement is active",
        "guardian_enforcement = active",
        "approval token issued",
        "execution_allowed = true",
        "side_effects_allowed = true",
    ]
    for phrase in forbidden:
        if phrase in text and phrase != required:
            raise SystemExit(f"forbidden public-safety wording in {path}: {phrase}")
print("public safety checks passed")
PY
