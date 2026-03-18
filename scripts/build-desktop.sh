#!/usr/bin/env bash
# Local desktop build helper — Linux / macOS only.
# Mirrors the CI pipeline but skips artifact upload.
# Usage: bash scripts/build-desktop.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ── Detect target triple ──────────────────────────────────────────────────────
if [[ "$OSTYPE" == "darwin"* ]]; then
  ARCH="$(uname -m)"
  if [[ "$ARCH" == "arm64" ]]; then
    TARGET_TRIPLE="aarch64-apple-darwin"
  else
    TARGET_TRIPLE="x86_64-apple-darwin"
  fi
elif [[ "$OSTYPE" == "linux"* ]]; then
  TARGET_TRIPLE="x86_64-unknown-linux-gnu"
else
  echo "Unsupported platform: $OSTYPE (use CI for Windows)" >&2
  exit 1
fi

echo "==> Platform: $OSTYPE  Triple: $TARGET_TRIPLE"

# ── Backend sidecar (PyInstaller) ─────────────────────────────────────────────
echo "==> Building PyInstaller backend sidecar..."
cd backend
uv run python -m PyInstaller \
  --distpath "../src-tauri/binaries" \
  --noconfirm \
  "../sparkbot-backend.spec"
cd "$REPO_ROOT"

echo "==> Renaming sidecar → sparkbot-backend-${TARGET_TRIPLE}"
mv "src-tauri/binaries/sparkbot-backend" \
   "src-tauri/binaries/sparkbot-backend-${TARGET_TRIPLE}"

# ── Frontend (Vite, V1 local mode) ────────────────────────────────────────────
echo "==> Building frontend (V1 local mode)..."
node scripts/run-desktop-frontend.mjs build

# ── Tauri installer ───────────────────────────────────────────────────────────
echo "==> Building Tauri installer..."
cargo tauri build --config src-tauri/tauri.conf.json

echo ""
echo "==> Done. Installer written to:"
find src-tauri/target/release/bundle -type f \( -name "*.dmg" -o -name "*.AppImage" \) 2>/dev/null || true
