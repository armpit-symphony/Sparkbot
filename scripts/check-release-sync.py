#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
from pathlib import Path
from typing import Any


def load_contract(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"contract file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _normalize_paths(lines: list[str]) -> set[str]:
    return {line.replace("\\", "/") for line in lines if line.strip()}


def git_worktree_files(repo: Path) -> set[str]:
    tracked = subprocess.check_output(
        ["git", "-C", str(repo), "ls-files"],
        text=True,
    ).splitlines()

    status = subprocess.check_output(
        ["git", "-C", str(repo), "status", "--porcelain=1", "--untracked-files=all"],
        text=True,
    ).splitlines()

    untracked = [
        line[3:]
        for line in status
        if line.startswith("??") and len(line) > 3
    ]

    files = set(_normalize_paths(tracked) | _normalize_paths(untracked))
    return {path for path in files if (repo / path).is_file()}


def git_ls_tree(repo: Path, ref: str) -> set[str]:
    output = subprocess.check_output(
        ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", ref],
        text=True,
    )
    return _normalize_paths(output.splitlines())


def matches_any(patterns: list[str], path: str) -> bool:
    for pattern in patterns:
        if pattern.endswith("/**"):
            base = pattern[:-3]
            if path == base or path.startswith(base + "/"):
                return True
            continue
        if fnmatch.fnmatch(path, pattern):
            return True
    return False


def get_runtime_modules(contract: dict[str, Any], *, target: str) -> list[str]:
    required = contract.get("required_runtime_modules", [])
    if isinstance(required, dict):
        modules = required.get(target)
        if isinstance(modules, list):
            return [str(path) for path in modules]
    if isinstance(required, list):
        return [str(path) for path in required]
    return []


def compare_contract_sections(public: dict[str, Any], source: dict[str, Any]) -> list[str]:
    diffs: list[str] = []
    if public.get("contract_version") != source.get("contract_version"):
        diffs.append("contract_version mismatch")
    if public.get("contract_name") != source.get("contract_name"):
        diffs.append("contract_name mismatch")
    for key in ["feature_matrix", "routing_guarantees", "safety_gates", "approved_removed_artifacts", "required_runtime_modules"]:
        if key == "safety_gates":
            if json.dumps(public.get(key, {}), sort_keys=True) != json.dumps(source.get(key, {}), sort_keys=True):
                diffs.append(f"{key} mismatch")
            continue
        if public.get(key) != source.get(key):
            diffs.append(f"{key} mismatch")
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate public release sync contract")
    parser.add_argument("--public-repo", default=".", help="Path to public repo")
    parser.add_argument("--source-repo", required=True, help="Path to source-of-truth repo")
    parser.add_argument("--contract", default="docs/RELEASE_SYNC_CONTRACT.json", help="Contract file relative path")
    parser.add_argument("--source-ref", help="Git ref/branch in source repo")
    args = parser.parse_args()

    public_repo = Path(args.public_repo).resolve()
    source_repo = Path(args.source_repo).resolve()
    contract_path_public = public_repo / args.contract
    contract_path_source = source_repo / args.contract

    public_contract = load_contract(contract_path_public)
    source_contract = load_contract(contract_path_source)

    diffs = compare_contract_sections(public_contract, source_contract)
    if diffs:
        for diff in diffs:
            print(f"FAIL: contract mismatch: {diff}")
        return 1

    source_ref = args.source_ref or source_contract.get("source_of_truth", {}).get("branch")
    if not source_ref:
        print("FAIL: no source branch provided and source_of_truth.branch missing in contract")
        return 1

    public_files = git_worktree_files(public_repo)
    source_files = git_ls_tree(source_repo, source_ref)

    public_required = get_runtime_modules(public_contract, target="public")
    source_required = get_runtime_modules(source_contract, target="source")

    if not public_required:
        print("FAIL: no required runtime modules for public in contract")
        return 1
    if not source_required:
        print("FAIL: no required runtime modules for source_of_truth in contract")
        return 1

    for path in sorted(public_required):
        if path not in public_files:
            print(f"FAIL: required public runtime file missing in public repo: {path}")
            return 1

    for path in sorted(source_required):
        if path not in source_files:
            print(f"FAIL: required source runtime file missing in source branch: {path}")
            return 1

    approved_removed = [str(pattern) for pattern in source_contract.get("approved_removed_artifacts", [])]
    unexpected_removals: list[str] = []

    source_only = source_files - public_files
    for path in sorted(source_only):
        if not matches_any(approved_removed, path):
            unexpected_removals.append(path)

    if unexpected_removals:
        print("FAIL: source-only files are not approved for removal in public")
        for path in unexpected_removals[:200]:
            print(f"  - {path}")
        if len(unexpected_removals) > 200:
            print(f"  ... and {len(unexpected_removals) - 200} more")
        return 1

    if public_contract.get("source_of_truth", {}).get("repo") != source_contract.get("source_of_truth", {}).get("repo"):
        print("WARN: source_of_truth repo URI differs between repos")

    print("PASS: release-sync contract checks completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
