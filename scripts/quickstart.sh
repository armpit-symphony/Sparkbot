#!/usr/bin/env bash
# Backward-compatible alias for the guided server launcher.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/sparkbot-start.sh" "$@"
