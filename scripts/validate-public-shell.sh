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
"$PYTHON" -m compileall backend/app backend/tests >/tmp/sparkbot-public-shell-compile.log
"$PYTHON" -m pytest \
  backend/tests/services/test_lima_decision_preview.py \
  backend/tests/api/routes/test_lima_decision_preview.py \
  backend/tests/app/test_config_public_safety.py \
  backend/tests/api/routes/test_lima_robotics_bridge.py \
  -q