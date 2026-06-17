"""Test-only fake-runtime consumer call preview for the LIMA V1 API surface.

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
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "sparkbot_lima_v1_g31_fake_runtime_consumer_call_preview.json"
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
    if str(lima_root) not in sys.path:
        sys.path.insert(0, str(lima_root))
    return importlib.import_module("lima.adapters")


def test_v1_g32_fixture_records_test_only_preview_scope() -> None:
    fixture = _load_fixture()

    assert fixture["packet_id"] == "sparkbot_lima_v1_g31_fake_runtime_consumer_call_preview"
    assert fixture["api_status"] == "CANDIDATE_ONLY"
    assert fixture["consumer_repo"] == "Sparkbot"
    assert fixture["proof_branch"] == "v1-g32-consumer-repository-test-edit"
    assert fixture["test_only_imports_added"] is True
    assert fixture["fake_runtime_preview_test_added"] is True
    assert fixture["docs_tests_fixtures_only"] is True
    assert fixture["runtime_source_files_changed"] is False


def test_v1_g32_imports_only_approved_fake_runtime_lima_symbols() -> None:
    fixture = _load_fixture()
    module = _import_lima_adapters_module()

    assert fixture["approved_import_symbols"] == [
        "lima.adapters.validate_v1_consumer_integration_compatibility_freeze",
        "lima.adapters.validate_v1_consumer_integration_proof_to_import_dry_run",
    ]
    assert hasattr(module, "validate_v1_consumer_integration_compatibility_freeze")
    assert hasattr(module, "validate_v1_consumer_integration_proof_to_import_dry_run")
    assert set(fixture["approved_import_symbols"]).issubset(
        {
            "lima.adapters." + symbol_name
            for symbol_name in getattr(module, "__all__")
        }
    )


def test_v1_g32_imported_symbols_are_not_called_or_authorizing() -> None:
    fixture = _load_fixture()

    assert fixture["imported_symbols_called"] is False
    assert fixture["fake_call_envelope_executed"] is False
    assert fixture["lima_runtime_behavior_invoked"] is False
    assert fixture["consumer_runtime_calls_added"] is False
    assert fixture["live_consumer_import_calls_added"] is False
    assert fixture["consumer_integration_added"] is False
    assert fixture["proof_not_authority"] is True


def test_v1_g32_fake_runtime_boundaries_remain_metadata_only() -> None:
    fixture = _load_fixture()

    assert fixture["fake_runtime_metadata_only"] is True
    assert fixture["network_required"] is False
    assert fixture["secrets_required"] is False
    assert fixture["external_services_required"] is False
    assert fixture["provider_model_calls_added"] is False


def test_v1_g32_runtime_and_external_boundaries_remain_false() -> None:
    fixture = _load_fixture()

    for key in (
        "shell_runtime_wiring_added",
        "secret_lookup_added",
        "credential_access_added",
        "tool_execution_added",
        "connector_browser_network_file_device_robotics_physical_world_behavior_added",
        "raw_diff_or_patch_persisted",
        "raw_file_content_persisted",
        "product_ready",
    ):
        assert fixture[key] is False


def test_v1_g32_links_required_lima_evidence() -> None:
    refs = _load_fixture()["linked_lima_evidence_refs"]

    assert refs["v1_g27_import_smoke_record_id"] == (
        "frozen-api-import-smoke:v1-g27:sparkbot:001"
    )
    assert refs["v1_g28_runtime_export_cleanup_ref"] == "runtime-export-cleanup:v1-g28"
    assert refs["v1_g29_planning_record_id"] == (
        "live-consumer-import-call-plan:v1-g29:sparkbot:001"
    )
    assert refs["v1_g30_fake_runtime_evidence_record_id"] == (
        "fake-runtime-consumer-call-evidence:v1-g30:sparkbot:001"
    )
    assert refs["v1_g31_preview_record_id"] == (
        "fake-runtime-consumer-repo-test-preview:v1-g31:sparkbot:001"
    )


def test_v1_g32_required_confirmations_are_true() -> None:
    confirmations = _load_fixture()["required_confirmations"]

    assert confirmations["no_live_import_call_confirmation"] is True
    assert confirmations["no_runtime_wiring_confirmation"] is True
    assert confirmations["no_runtime_source_change_confirmation"] is True
    assert confirmations["no_adapter_symbol_call_confirmation"] is True
    assert (
        confirmations[
            "no_provider_model_secret_credential_connector_browser_network_physical_world_confirmation"
        ]
        is True
    )
    assert (
        confirmations[
            "no_raw_content_secret_credential_customer_data_diff_patch_confirmation"
        ]
        is True
    )
    assert confirmations["proof_not_authority_confirmation"] is True


def test_v1_g32_fixture_does_not_include_raw_patch_or_sensitive_markers() -> None:
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
