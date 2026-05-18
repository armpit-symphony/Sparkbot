#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Build Sparkbot public download artifacts from committed source.

Usage:
  bash scripts/package-public-download.sh [options]

Options:
  --ref <git-ref>              Git ref/commit/tag to package. Default: HEAD
  --output-dir <path>          Directory for generated artifacts.
                               Default: dist/public-download/latest
  --artifact-prefix <prefix>   Archive filename prefix. Default: sparkbot-latest
  --notes-file <path>          Optional plaintext release notes body to append.
  --publish-dir <path>         Optional directory to copy generated artifacts into.
  --version <version>          Override version instead of reading backend/pyproject.toml.
  --help                       Show this help.

Examples:
  bash scripts/package-public-download.sh
  bash scripts/package-public-download.sh --ref sparkbot-v1.3.0 --artifact-prefix sparkbot-1.3.0 --output-dir dist/public-download/1.3.0
  bash scripts/package-public-download.sh --publish-dir /srv/www/example.com/downloads/sparkbot/latest
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

ref="HEAD"
output_dir="$repo_root/dist/public-download/latest"
artifact_prefix="sparkbot-latest"
notes_file=""
publish_dir=""
version_override=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)
      ref="${2:?missing value for --ref}"
      shift 2
      ;;
    --output-dir)
      output_dir="${2:?missing value for --output-dir}"
      shift 2
      ;;
    --artifact-prefix)
      artifact_prefix="${2:?missing value for --artifact-prefix}"
      shift 2
      ;;
    --notes-file)
      notes_file="${2:?missing value for --notes-file}"
      shift 2
      ;;
    --publish-dir)
      publish_dir="${2:?missing value for --publish-dir}"
      shift 2
      ;;
    --version)
      version_override="${2:?missing value for --version}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -n "$notes_file" && ! -f "$notes_file" ]]; then
  echo "Notes file not found: $notes_file" >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is required" >&2
  exit 1
fi

find_python_bin() {
  local candidate
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys' >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

if ! python_bin="$(find_python_bin)"; then
  echo "python3 or python is required" >&2
  exit 1
fi

commit="$(git -C "$repo_root" rev-parse "${ref}^{commit}")"
short_commit="$(git -C "$repo_root" rev-parse --short=12 "$commit")"
tag_name="$(git -C "$repo_root" tag --points-at "$commit" | head -n 1 || true)"

read_version_from_ref() {
  git -C "$repo_root" show "${commit}:backend/pyproject.toml" | "$python_bin" -c '
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore

data = tomllib.loads(sys.stdin.read())
print(data["project"]["version"])
'
}

if [[ -n "$version_override" ]]; then
  version="$version_override"
else
  version="$(read_version_from_ref)"
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
stage_dir="$workdir/stage"
stage_repo="$stage_dir/sparkbot-v2"
mkdir -p "$stage_dir"

git -C "$repo_root" archive --format=tar --prefix="sparkbot-v2/" "$commit" | tar -xf - -C "$stage_dir"

# Remove internal-only docs and any tracked backup/junk files from the staged public bundle.
rm -f \
  "$stage_repo/FRESH_INSTALL_CHECKLIST.md" \
  "$stage_repo/consumer_readiness_checklist.md" \
  "$stage_repo/guardian_suite_integration.md" \
  "$stage_repo/release-notes.md" \
  "$stage_repo/sparkbot-backend.spec" \
  "$stage_repo/copier.yml"

# Remove readiness audits, extraction notes, private runtime research, and other
# repo-internal planning docs from public source bundles. The public bundle keeps
# install/setup docs, README, generated release notes, and product-facing docs.
rm -rf "$stage_repo/docs/audits"
rm -rf "$stage_repo/docs/release-notes"
rm -f \
  "$stage_repo/docs/COMMAND_CENTER_SECURITY_AUDIT.md" \
  "$stage_repo/docs/INVITE_WING_MODEL_SEATS_STATUS.md" \
  "$stage_repo/docs/LIMA_RUNTIME_ALIGNMENT_NOTES.md" \
  "$stage_repo/docs/P0_STABILIZATION_STATUS.md" \
  "$stage_repo/docs/PERSISTENT_MEMORY_SPINE_AUDIT.md" \
  "$stage_repo/docs/PUBLIC_PACKAGE_PROMPT_CLEANUP_STATUS.md" \
  "$stage_repo/docs/PUBLIC_SHELL_LAYER_PLAN.md" \
  "$stage_repo/docs/PUBLIC_SURFACE_UX_STATUS.md" \
  "$stage_repo/docs/ROUNDTABLE_MANAGER_FLOW_PLAN.md" \
  "$stage_repo/docs/UNIFIED_CONTEXT_SPINE_STATUS.md" \
  "$stage_repo/docs/lima-robo-os-integration.md"
rm -f \
  "$stage_repo"/docs/PUBLIC_RELEASE_*.md \
  "$stage_repo"/docs/release-readiness-*.md \
  "$stage_repo"/docs/*_AUDIT.md \
  "$stage_repo"/docs/*_STATUS.md \
  "$stage_repo"/docs/*LIMA*.md \
  "$stage_repo"/docs/lima-*.md

# Public packages keep the Robo Preview API surface but replace the private
# R&D bridge implementation with a non-executing stub. The full bridge source
# remains only in the R&D repo behind explicit private flags.
cat > "$stage_repo/backend/app/services/lima_robotics_bridge.py" <<'PY'
from __future__ import annotations

from typing import Any, Literal

RobotEnvironment = Literal["replay", "simulation", "real_hardware"]
RobotRiskLevel = Literal["read_only", "low", "medium", "high", "blocked"]
PRIVATE_ROBO_BRIDGE_ENV = "SPARKBOT_PRIVATE_ROBO_BRIDGE_ENABLED"
ROBO_PREVIEW_DETAIL = (
    "Robo Preview is a public-safe, non-executing demo surface. "
    "Real robotics, IoT, drone, or hardware control is not included in Sparkbot Public."
)


class LimaBridgeError(RuntimeError):
    """Raised when a Robo Preview request asks for unavailable live control."""


def private_robo_bridge_enabled() -> bool:
    return False


def configured_mcp_url() -> str:
    return ""


def bridge_status() -> dict[str, Any]:
    return {
        "configured": False,
        "mcpUrlConfigured": False,
        "privateBridgeConfigured": False,
        "privateBridgeEnabled": False,
        "safeTarget": "",
        "mode": "robo_preview",
        "previewOnly": True,
        "message": ROBO_PREVIEW_DETAIL,
    }


async def list_lima_tools() -> list[dict[str, Any]]:
    return []


def resolve_robot_command(
    requested_action: str,
    *,
    mcp_tool_name: str = "",
    mcp_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "toolName": mcp_tool_name or "robo_preview",
        "arguments": dict(mcp_args or {}),
        "parsedIntent": "preview_only",
        "requestedAction": requested_action,
    }


def classify_robot_command(
    *,
    environment: RobotEnvironment,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    return {
        "riskLevel": "blocked",
        "approvalRequired": False,
        "guardianDecision": "preview_only",
        "reason": ROBO_PREVIEW_DETAIL,
    }


def public_preview_contract(
    *,
    source_user: str,
    robot_id: str,
    environment: RobotEnvironment,
    requested_action: str,
    mcp_tool_name: str = "",
    mcp_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = resolve_robot_command(
        requested_action,
        mcp_tool_name=mcp_tool_name,
        mcp_args=mcp_args,
    )
    return {
        "executed": False,
        "blocked": True,
        "preview_only": True,
        "contract": {
            "source_user": source_user,
            "robot_id": robot_id,
            "environment": environment,
            "requested_action": requested_action,
            "risk_level": "blocked",
            "approval_required": False,
            "guardian_decision": "preview_only",
            "mcp_tool_name": resolved["toolName"],
            "mcp_args": resolved["arguments"],
            "parsed_intent": resolved["parsedIntent"],
            "safety_reason": ROBO_PREVIEW_DETAIL,
        },
        "bridge": bridge_status(),
        "message": ROBO_PREVIEW_DETAIL,
    }


async def execute_robot_command(
    *,
    source_user: str,
    requested_action: str,
    robot_id: str = "default",
    environment: RobotEnvironment = "simulation",
    mcp_tool_name: str = "",
    mcp_args: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    return public_preview_contract(
        source_user=source_user,
        robot_id=robot_id,
        environment=environment,
        requested_action=requested_action,
        mcp_tool_name=mcp_tool_name,
        mcp_args=mcp_args,
    )


async def emergency_stop(*, source_user: str, robot_id: str = "default") -> dict[str, Any]:
    raise LimaBridgeError("Robo Preview does not expose live emergency-stop control.")
PY

# Remove desktop build artifacts not relevant to the Docker/CLI self-hosted install.
rm -rf "$stage_repo/src-tauri"

# Remove Copier scaffolding artifacts (project template config, not for end users).
rm -rf "$stage_repo/.copier"

find "$stage_repo" \
  -type d \
  \( -name "__pycache__" -o -name ".pytest_cache" -o -name ".mypy_cache" -o -name ".ruff_cache" -o -name ".cache" -o -name ".venv" -o -name ".venv-ci" -o -name "venv" -o -name "node_modules" -o -name "dist" -o -name "build" -o -name "coverage" -o -name "logs" \) \
  -prune -exec rm -rf {} +

find "$stage_repo" \
  -type f \
  \( -name "*.pyc" -o -name "*.pyo" -o -name "*.bak" -o -name "*.bak_*" -o -name "*.log" -o -name "*.jsonl" -o -name "*.sqlite" -o -name "*.db" -o -name "*.pem" -o -name "*.key" -o -name "*.p12" -o -name "*.pfx" -o -name ".env" -o -name ".env.local" -o -name ".env.production" -o -name ".env.development" -o -name "file_v*_proposals.py" -o -name "*_proposals.py" \) \
  -delete

mkdir -p "$output_dir"

tarball_name="${artifact_prefix}.tar.gz"
zip_name="${artifact_prefix}.zip"
cli_name="sparkbot-cli.py"
checksums_name="SHA256SUMS"
notes_name="RELEASE-NOTES.txt"

rm -f \
  "$output_dir/$tarball_name" \
  "$output_dir/$zip_name" \
  "$output_dir/$cli_name" \
  "$output_dir/$checksums_name" \
  "$output_dir/$notes_name"

tar -czf "$output_dir/$tarball_name" -C "$stage_dir" sparkbot-v2
if command -v zip >/dev/null 2>&1; then
  (
    cd "$stage_dir"
    zip -qr "$output_dir/$zip_name" sparkbot-v2
  )
else
  "$python_bin" - "$stage_dir" "$output_dir/$zip_name" <<'PY'
import os
import sys
import zipfile

stage_dir, zip_path = sys.argv[1], sys.argv[2]
source_root = os.path.join(stage_dir, "sparkbot-v2")
if not os.path.isdir(source_root):
    raise SystemExit(f"stage source not found: {source_root}")

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for root, dirs, files in os.walk(source_root):
        dirs.sort()
        files.sort()
        for name in files:
            path = os.path.join(root, name)
            arcname = os.path.relpath(path, stage_dir).replace(os.sep, "/")
            archive.write(path, arcname)
PY
fi

cp "$repo_root/sparkbot-cli.py" "$output_dir/$cli_name"
chmod 755 "$output_dir/$cli_name"

{
  echo "Sparkbot public download bundle"
  echo "Version: $version"
  echo "Git ref: $ref"
  echo "Git commit: $commit"
  if [[ -n "$tag_name" ]]; then
    echo "Git tag: $tag_name"
  fi
  echo "Built on: $(date -u +"%Y-%m-%d %H:%M:%S UTC")"
  echo "Artifact prefix: $artifact_prefix"
  echo
  echo "Packaging source:"
  echo "- committed source exported with git archive"
  echo "- packaged from repo root folder name: sparkbot-v2"
  echo
  echo "Excluded from the public bundle:"
  echo "- FRESH_INSTALL_CHECKLIST.md"
  echo "- consumer_readiness_checklist.md"
  echo "- release-notes.md"
  echo "- guardian_suite_integration.md"
  echo "- docs/audits/ and public-readiness/status/audit docs"
  echo "- docs/release-notes/ historical release notes"
  echo "- private LIMA/Robo runtime research docs"
  echo "- private Robo bridge implementation (replaced by public Robo Preview stub)"
  echo "- sparkbot-backend.spec (PyInstaller desktop build artifact)"
  echo "- copier.yml + .copier/ (project scaffolding config)"
  echo "- src-tauri/ (Tauri desktop shell source)"
  echo "- proposal scripts and scratch files"
  echo "- dotenv files, logs, local databases, key/certificate files"
  echo "- backup files (*.bak, *.bak_*)"
  echo "- Python bytecode and cache directories"
  echo "- node_modules, dist, build, coverage, virtualenv, and cache directories"
  if [[ -n "$notes_file" ]]; then
    echo
    echo "Release notes:"
    cat "$notes_file"
  fi
} > "$output_dir/$notes_name"

(
  cd "$output_dir"
  sha256sum "$tarball_name" "$zip_name" "$cli_name" > "$checksums_name"
)

if [[ -n "$publish_dir" ]]; then
  mkdir -p "$publish_dir"
  install -m 0644 "$output_dir/$tarball_name" "$publish_dir/$tarball_name"
  install -m 0644 "$output_dir/$zip_name" "$publish_dir/$zip_name"
  install -m 0755 "$output_dir/$cli_name" "$publish_dir/$cli_name"
  install -m 0644 "$output_dir/$checksums_name" "$publish_dir/$checksums_name"
  install -m 0644 "$output_dir/$notes_name" "$publish_dir/$notes_name"
fi

cat <<EOF
Built public download artifacts:
  ref:            $ref
  commit:         $commit
  version:        $version
  output dir:     $output_dir
  tarball:        $output_dir/$tarball_name
  zip:            $output_dir/$zip_name
  cli:            $output_dir/$cli_name
  checksums:      $output_dir/$checksums_name
  release notes:  $output_dir/$notes_name
EOF

if [[ -n "$publish_dir" ]]; then
  echo "  publish dir:    $publish_dir"
fi
