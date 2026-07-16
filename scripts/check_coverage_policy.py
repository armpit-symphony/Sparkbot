#!/usr/bin/env python3
"""Enforce patch coverage and total-coverage non-regression."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any


HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


class CoveragePolicyError(Exception):
    """Raised when policy inputs are missing or malformed."""


@dataclass(frozen=True)
class CoveragePolicy:
    minimum_patch_percent: Decimal
    baseline_sha: str
    baseline_covered: int
    baseline_statements: int
    total_tolerance_points: Decimal
    coverage_path_prefix: str
    production_source_path: str

    @property
    def baseline_percent(self) -> Decimal:
        return percentage(self.baseline_covered, self.baseline_statements)


@dataclass(frozen=True)
class CoverageResult:
    patch_covered: int
    patch_statements: int
    total_covered: int
    total_statements: int
    policy: CoveragePolicy

    @property
    def patch_percent(self) -> Decimal | None:
        if self.patch_statements == 0:
            return None
        return percentage(self.patch_covered, self.patch_statements)

    @property
    def total_percent(self) -> Decimal:
        return percentage(self.total_covered, self.total_statements)

    @property
    def minimum_total_percent(self) -> Decimal:
        return self.policy.baseline_percent - self.policy.total_tolerance_points

    @property
    def patch_passes(self) -> bool:
        return self.patch_percent is None or (
            self.patch_percent >= self.policy.minimum_patch_percent
        )

    @property
    def total_passes(self) -> bool:
        return self.total_percent >= self.minimum_total_percent

    @property
    def passes(self) -> bool:
        return self.patch_passes and self.total_passes


def percentage(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        raise CoveragePolicyError("coverage denominator must be greater than zero")
    return Decimal(numerator) * Decimal(100) / Decimal(denominator)


def require_int(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CoveragePolicyError(f"{field} must be an integer >= {minimum}")
    return value


def require_decimal(value: Any, field: str, *, minimum: Decimal) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise CoveragePolicyError(f"{field} must be numeric") from exc
    if not result.is_finite() or result < minimum:
        raise CoveragePolicyError(f"{field} must be >= {minimum}")
    return result


def normalize_path(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise CoveragePolicyError(f"{field} must be a path string")
    normalized = PurePosixPath(value.replace("\\", "/")).as_posix().strip("/")
    if not normalized or normalized == "." or ".." in PurePosixPath(normalized).parts:
        raise CoveragePolicyError(f"{field} must be a repository-relative path")
    return normalized


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CoveragePolicyError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CoveragePolicyError(f"{path} must contain a JSON object")
    return value


def load_policy(path: Path) -> CoveragePolicy:
    data = load_json(path)
    baseline = data.get("total_coverage_baseline")
    if not isinstance(baseline, dict):
        raise CoveragePolicyError("total_coverage_baseline must be an object")

    baseline_sha = baseline.get("base_sha")
    if not isinstance(baseline_sha, str) or not re.fullmatch(
        r"[0-9a-f]{40}", baseline_sha
    ):
        raise CoveragePolicyError("total_coverage_baseline.base_sha must be a full SHA")

    baseline_covered = require_int(
        baseline.get("covered_lines"), "total_coverage_baseline.covered_lines"
    )
    baseline_statements = require_int(
        baseline.get("total_statements"),
        "total_coverage_baseline.total_statements",
        minimum=1,
    )
    if baseline_covered > baseline_statements:
        raise CoveragePolicyError("baseline covered lines exceed total statements")

    return CoveragePolicy(
        minimum_patch_percent=require_decimal(
            data.get("minimum_patch_coverage_percent"),
            "minimum_patch_coverage_percent",
            minimum=Decimal(0),
        ),
        baseline_sha=baseline_sha,
        baseline_covered=baseline_covered,
        baseline_statements=baseline_statements,
        total_tolerance_points=require_decimal(
            data.get("total_regression_tolerance_percentage_points"),
            "total_regression_tolerance_percentage_points",
            minimum=Decimal(0),
        ),
        coverage_path_prefix=normalize_path(
            data.get("coverage_path_prefix"), "coverage_path_prefix"
        ),
        production_source_path=normalize_path(
            data.get("production_source_path"), "production_source_path"
        ),
    )


def parse_added_lines(diff_text: str) -> dict[str, set[int]]:
    """Return added line numbers per new-side path from a unified Git diff."""
    added: dict[str, set[int]] = {}
    current_path: str | None = None
    new_line: int | None = None

    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            marker = line[4:].split("\t", 1)[0]
            if marker == "/dev/null":
                current_path = None
            elif marker.startswith("b/"):
                current_path = normalize_path(marker[2:], "diff path")
                added.setdefault(current_path, set())
            else:
                raise CoveragePolicyError(f"unsupported new-side diff path: {marker}")
            new_line = None
            continue

        match = HUNK_HEADER.match(line)
        if match:
            new_line = int(match.group(1))
            continue

        if current_path is None or new_line is None:
            continue
        if line.startswith("+"):
            added[current_path].add(new_line)
            new_line += 1
        elif line.startswith("-"):
            continue
        elif line.startswith("\\ No newline at end of file"):
            continue
        else:
            new_line += 1

    return added


def get_git_diff(repo_root: Path, base_ref: str, head_ref: str) -> str:
    command = [
        "git",
        "diff",
        "--unified=0",
        "--no-color",
        f"{base_ref}...{head_ref}",
        "--",
        "*.py",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise CoveragePolicyError(
            f"cannot calculate Git diff: {detail.strip()}"
        ) from exc
    return result.stdout


def coverage_repo_path(coverage_path: str, prefix: str) -> str:
    normalized = normalize_path(coverage_path, "coverage file path")
    if normalized == prefix or normalized.startswith(f"{prefix}/"):
        return normalized
    return f"{prefix}/{normalized}"


def require_line_set(file_data: dict[str, Any], field: str) -> set[int]:
    value = file_data.get(field)
    if not isinstance(value, list):
        raise CoveragePolicyError(f"coverage file {field} must be a list")
    return {
        require_int(item, f"coverage file {field} entry", minimum=1) for item in value
    }


def evaluate_coverage(
    policy: CoveragePolicy,
    coverage_data: dict[str, Any],
    added_lines: dict[str, set[int]],
) -> CoverageResult:
    files = coverage_data.get("files")
    totals = coverage_data.get("totals")
    if not isinstance(files, dict) or not isinstance(totals, dict):
        raise CoveragePolicyError("coverage JSON requires files and totals objects")

    total_covered = require_int(totals.get("covered_lines"), "totals.covered_lines")
    total_statements = require_int(
        totals.get("num_statements"), "totals.num_statements", minimum=1
    )
    if total_covered > total_statements:
        raise CoveragePolicyError("total covered lines exceed total statements")

    coverage_files: dict[str, dict[str, Any]] = {}
    for raw_path, file_data in files.items():
        if not isinstance(raw_path, str) or not isinstance(file_data, dict):
            raise CoveragePolicyError("coverage files must map paths to objects")
        repo_path = coverage_repo_path(raw_path, policy.coverage_path_prefix)
        if repo_path in coverage_files:
            raise CoveragePolicyError(
                f"duplicate normalized coverage path: {repo_path}"
            )
        coverage_files[repo_path] = file_data

    patch_covered = 0
    patch_statements = 0
    source_prefix = f"{policy.production_source_path}/"
    for path, changed in sorted(added_lines.items()):
        if not path.endswith(".py") or not (
            path == policy.production_source_path or path.startswith(source_prefix)
        ):
            continue
        file_data = coverage_files.get(path)
        if file_data is None:
            raise CoveragePolicyError(
                f"changed production file missing from coverage JSON: {path}"
            )
        executed = require_line_set(file_data, "executed_lines")
        missing = require_line_set(file_data, "missing_lines")
        statements = executed | missing
        changed_statements = changed & statements
        patch_statements += len(changed_statements)
        patch_covered += len(changed_statements & executed)

    return CoverageResult(
        patch_covered=patch_covered,
        patch_statements=patch_statements,
        total_covered=total_covered,
        total_statements=total_statements,
        policy=policy,
    )


def format_percent(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.0001'))}%"


def print_result(result: CoverageResult) -> None:
    if result.patch_percent is None:
        print("PATCH_COVERAGE=PASS covered=0 executable=0 percent=N/A")
    else:
        patch_status = "PASS" if result.patch_passes else "FAIL"
        print(
            f"PATCH_COVERAGE={patch_status} covered={result.patch_covered} "
            f"executable={result.patch_statements} "
            f"percent={format_percent(result.patch_percent)} "
            f"minimum={format_percent(result.policy.minimum_patch_percent)}"
        )

    total_status = "PASS" if result.total_passes else "FAIL"
    print(
        f"TOTAL_COVERAGE={total_status} covered={result.total_covered} "
        f"statements={result.total_statements} "
        f"percent={format_percent(result.total_percent)} "
        f"baseline={format_percent(result.policy.baseline_percent)} "
        f"tolerance_pp={result.policy.total_tolerance_points.quantize(Decimal('0.0001'))}pp "
        f"minimum={format_percent(result.minimum_total_percent)}"
    )
    print(f"COVERAGE_POLICY={'PASS' if result.passes else 'FAIL'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-json", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=Path("ci/coverage-policy.json"))
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        policy = load_policy(args.policy)
        coverage_data = load_json(args.coverage_json)
        diff_text = get_git_diff(args.repo_root, args.base_ref, args.head_ref)
        result = evaluate_coverage(policy, coverage_data, parse_added_lines(diff_text))
    except CoveragePolicyError as exc:
        print(f"COVERAGE_POLICY=ERROR {exc}", file=sys.stderr)
        return 2

    print_result(result)
    return 0 if result.passes else 1


if __name__ == "__main__":
    raise SystemExit(main())
