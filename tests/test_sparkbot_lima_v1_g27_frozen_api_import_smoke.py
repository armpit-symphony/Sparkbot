"""Test-only import smoke for the frozen LIMA V1 API surface.

This test imports approved LIMA symbols only. It does not call them, import
Sparkbot runtime modules, call providers, execute tools, or wire runtime paths.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "sparkbot_lima_v1_g27_frozen_api_import_smoke.json"
)


def _load_fixture() -> dict[str, Any]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(fixture, dict)
    return fixture


def _lima_repo_root() -> Path:
    configured = os.environ.get("LIMA_AI_OS_REPO")
    if configured:
        return Path(configured)
    return REPO_ROOT.parent / "LIMA-AI-OS"


def _import_lima_adapters_module() -> Any:
    lima_root = _lima_repo_root()
    assert (lima_root / "lima" / "adapters" / "__init__.py").exists(), lima_root
    sys.path.insert(0, str(lima_root))
    return importlib.import_module("lima.adapters")


def test_v1_g27_fixture_records_test_only_import_smoke_scope() -> None:
    fixture = _load_fixture()

    assert fixture["packet_id"] == "sparkbot_lima_v1_g27_frozen_api_import_smoke"
    assert fixture["api_status"] == "CANDIDATE_ONLY"
    assert fixture["consumer_repo"] == "Sparkbot"
    assert fixture["proof_branch"] == "v1-g27-first-consumer-frozen-api-import-smoke"
    assert fixture["test_only_import_smoke_added"] is True
    assert fixture["docs_tests_fixtures_only"] is True
    assert fixture["runtime_source_files_changed"] is False


def test_v1_g27_imports_only_approved_frozen_lima_api_symbols() -> None:
    fixture = _load_fixture()
    module = _import_lima_adapters_module()

    assert fixture["approved_import_smoke_symbols"] == [
        "lima.adapters.validate_v1_consumer_integration_compatibility_freeze",
        "lima.adapters.V1ConsumerIntegrationCompatibilityError",
    ]
    assert hasattr(module, "validate_v1_consumer_integration_compatibility_freeze")
    assert hasattr(module, "V1ConsumerIntegrationCompatibilityError")


def test_v1_g27_imported_symbols_are_not_called_or_authorizing() -> None:
    fixture = _load_fixture()

    assert fixture["imported_symbols_called"] is False
    assert fixture["lima_runtime_behavior_invoked"] is False
    assert fixture["consumer_runtime_calls_added"] is False
    assert fixture["consumer_integration_added"] is False
    assert fixture["proof_not_authority"] is True


def test_v1_g27_runtime_and_external_boundaries_remain_false() -> None:
    fixture = _load_fixture()

    for key in (
        "sparkbot_runtime_behavior_added",
        "shell_runtime_wiring_added",
        "runtime_export_cleanup_approved",
        "runtime_export_cleanup_added",
        "provider_model_calls_added",
        "secret_lookup_added",
        "credential_access_added",
        "tool_execution_added",
        "connector_browser_network_file_device_robotics_physical_world_behavior_added",
        "raw_diff_or_patch_persisted",
        "raw_file_content_persisted",
        "product_ready",
    ):
        assert fixture[key] is False


def test_v1_g27_links_required_prior_evidence() -> None:
    refs = _load_fixture()["linked_lima_evidence_refs"]

    assert refs["frozen_api_packet_ref"] == "api-freeze:v1-g22"
    assert refs["v1_g24_import_plan_id"] == "import-plan:v1-g24:sparkbot:001"
    assert refs["v1_g25_patch_preview_id"] == "patch-preview:v1-g25:sparkbot:001"
    assert refs["v1_g26_static_consumer_edit_id"] == (
        "static-consumer-edit:v1-g26:sparkbot:001"
    )


def test_v1_g27_required_confirmations_are_true() -> None:
    confirmations = _load_fixture()["required_confirmations"]

    assert confirmations["no_live_import_call_confirmation"] is True
    assert confirmations["no_runtime_wiring_confirmation"] is True
    assert confirmations["no_runtime_export_cleanup_confirmation"] is True
    assert (
        confirmations[
            "no_raw_content_secret_credential_customer_data_diff_patch_confirmation"
        ]
        is True
    )
    assert confirmations["proof_not_authority_confirmation"] is True


def test_v1_g27_fixture_does_not_include_raw_patch_or_sensitive_markers() -> None:
    output = json.dumps(_load_fixture(), sort_keys=True)

    for forbidden in (
        "diff --git",
        "@@",
        "BEGIN PATCH",
        "raw prompt value",
        "raw customer data value",
        "provider token value",
        "api key value",
        "raw-secret-123",
    ):
        assert forbidden not in output
