from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = Path(__file__).parents[3] / "scripts" / "check_coverage_policy.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_coverage_policy", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


coverage_policy = load_script()


def policy(
    *,
    patch_minimum: str = "90",
    baseline_covered: int = 90,
    baseline_statements: int = 100,
    tolerance: str = "0",
):
    return coverage_policy.CoveragePolicy(
        minimum_patch_percent=Decimal(patch_minimum),
        baseline_sha="a" * 40,
        baseline_covered=baseline_covered,
        baseline_statements=baseline_statements,
        total_tolerance_points=Decimal(tolerance),
        coverage_path_prefix="backend",
        production_source_path="backend/app",
    )


def coverage(
    *,
    executed: list[int],
    missing: list[int],
    total_covered: int = 90,
    total_statements: int = 100,
):
    return {
        "files": {
            "app/example.py": {
                "executed_lines": executed,
                "missing_lines": missing,
            }
        },
        "totals": {
            "covered_lines": total_covered,
            "num_statements": total_statements,
        },
    }


def evaluate(executed: list[int], missing: list[int], changed: set[int], **kwargs):
    return coverage_policy.evaluate_coverage(
        policy(**kwargs),
        coverage(executed=executed, missing=missing),
        {"backend/app/example.py": changed},
    )


def test_patch_coverage_above_ninety_percent_passes() -> None:
    result = evaluate(list(range(1, 20)), [20], set(range(1, 21)))

    assert result.patch_percent == Decimal("95")
    assert result.patch_passes


def test_patch_coverage_exactly_ninety_percent_passes() -> None:
    result = evaluate(list(range(1, 10)), [10], set(range(1, 11)))

    assert result.patch_percent == Decimal("90")
    assert result.patch_passes


def test_patch_coverage_below_ninety_percent_fails() -> None:
    result = evaluate(list(range(1, 9)), [9, 10], set(range(1, 11)))

    assert result.patch_percent == Decimal("80")
    assert not result.patch_passes
    assert not result.passes


def test_no_changed_executable_lines_passes_explicitly() -> None:
    result = evaluate([3], [5], {1, 2, 4})

    assert result.patch_statements == 0
    assert result.patch_percent is None
    assert result.patch_passes


@pytest.mark.parametrize(
    ("covered", "statements"),
    [(91, 100), (90, 100)],
)
def test_total_coverage_increase_or_no_change_passes(
    covered: int, statements: int
) -> None:
    result = coverage_policy.evaluate_coverage(
        policy(),
        coverage(
            executed=[1],
            missing=[],
            total_covered=covered,
            total_statements=statements,
        ),
        {},
    )

    assert result.total_passes


def test_meaningful_total_coverage_regression_fails() -> None:
    result = coverage_policy.evaluate_coverage(
        policy(tolerance="0.02"),
        coverage(executed=[1], missing=[], total_covered=899, total_statements=1000),
        {},
    )

    assert not result.total_passes
    assert not result.passes


def test_deleted_lines_do_not_count_as_uncovered_new_code() -> None:
    diff = """\
diff --git a/backend/app/example.py b/backend/app/example.py
--- a/backend/app/example.py
+++ b/backend/app/example.py
@@ -1,2 +1,0 @@
-removed = 1
-also_removed = 2
@@ -10,0 +9 @@
+added = 3
"""

    changed = coverage_policy.parse_added_lines(diff)

    assert changed == {"backend/app/example.py": {9}}


def test_comments_and_blank_lines_are_not_executable_changed_lines() -> None:
    result = evaluate([3], [5], {1, 2, 3, 4, 5})

    assert result.patch_statements == 2
    assert result.patch_covered == 1


@pytest.mark.parametrize(
    "invalid_data",
    [
        {},
        {"files": {}, "totals": {}},
        {"files": [], "totals": {"covered_lines": 1, "num_statements": 1}},
    ],
)
def test_malformed_coverage_data_fails_closed(invalid_data: object) -> None:
    with pytest.raises(coverage_policy.CoveragePolicyError):
        coverage_policy.evaluate_coverage(policy(), invalid_data, {})


def test_missing_coverage_file_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(coverage_policy.CoveragePolicyError):
        coverage_policy.load_json(tmp_path / "missing.json")


def test_changed_production_file_missing_from_coverage_fails_closed() -> None:
    data = coverage(executed=[1], missing=[])

    with pytest.raises(coverage_policy.CoveragePolicyError):
        coverage_policy.evaluate_coverage(
            policy(), data, {"backend/app/not-reported.py": {1}}
        )
