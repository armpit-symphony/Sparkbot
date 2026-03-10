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
  bash scripts/package-public-download.sh --publish-dir /var/www/sparkpitlabs.com/downloads/sparkbot/latest
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

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

if ! command -v zip >/dev/null 2>&1; then
  echo "zip is required" >&2
  exit 1
fi

commit="$(git -C "$repo_root" rev-parse "${ref}^{commit}")"
short_commit="$(git -C "$repo_root" rev-parse --short=12 "$commit")"
tag_name="$(git -C "$repo_root" tag --points-at "$commit" | head -n 1 || true)"

read_version_from_ref() {
  git -C "$repo_root" show "${commit}:backend/pyproject.toml" | python3 -c '
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
  "$stage_repo/LOGBOOK_handoff.md" \
  "$stage_repo/FRESH_INSTALL_CHECKLIST.md" \
  "$stage_repo/consumer_readiness_checklist.md" \
  "$stage_repo/release-notes.md"

find "$stage_repo" \
  -type d \
  \( -name "__pycache__" -o -name ".pytest_cache" -o -name ".mypy_cache" -o -name ".ruff_cache" -o -name "node_modules" -o -name "dist" \) \
  -prune -exec rm -rf {} +

find "$stage_repo" \
  -type f \
  \( -name "*.pyc" -o -name "*.pyo" -o -name "*.bak" -o -name "*.bak_*" \) \
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
(
  cd "$stage_dir"
  zip -qr "$output_dir/$zip_name" sparkbot-v2
)

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
  echo "- LOGBOOK_handoff.md"
  echo "- FRESH_INSTALL_CHECKLIST.md"
  echo "- consumer_readiness_checklist.md"
  echo "- release-notes.md"
  echo "- backup files (*.bak, *.bak_*)"
  echo "- Python bytecode and cache directories"
  echo "- node_modules and dist directories"
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
