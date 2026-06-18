"""Static consumer integration candidate evidence for LIMA V1-G38.

This test validates only the approved Sparkbot fixture metadata. It does not
import LIMA runtime modules, import Sparkbot runtime modules, call providers,
execute tools, wire shells, use network, or access secrets.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "sparkbot_lima_v1_g38_consumer_integration_candidate.json"
)


def _load_fixture() -> dict[str, Any]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(fixture, dict)
    return fixture


def test_v1_g38_fixture_records_static_candidate_scope() -> None:
    fixture = _load_fixture()

    assert fixture["packet_id"] == "sparkbot_lima_v1_g38_consumer_integration_candidate"
    assert fixture["api_status"] == "CANDIDATE_ONLY"
    assert fixture["proof_gap_id"] == "V1-G38"
    assert fixture["consumer_repo"] == "Sparkbot"
    assert fixture["consumer_repository"] == "sparkpit-labs/Sparkbot"
    assert fixture["proof_branch"] == "v1-g38-consumer-repository-edit"
    assert fixture["consumer_repository_edit_added"] is True
    assert fixture["static_candidate_integration_fixture_added"] is True
    assert fixture["static_candidate_integration_test_added"] is True
    assert fixture["docs_tests_fixtures_only"] is True


def test_v1_g38_consumer_file_scope_is_exact() -> None:
    fixture = _load_fixture()

    assert fixture["approved_file_scope"] == [
        "tests/fixtures/sparkbot_lima_v1_g38_consumer_integration_candidate.json",
        "tests/test_sparkbot_lima_v1_g38_consumer_integration_candidate.py",
    ]
    for relative_path in fixture["approved_file_scope"]:
        assert (REPO_ROOT / relative_path).exists()


def test_v1_g38_links_lima_patch_preview_and_design_evidence() -> None:
    fixture = _load_fixture()
    refs = fixture["linked_lima_evidence_refs"]

    assert fixture["source_patch_preview_record_ref"] == (
        "consumer-integration-patch-preview:v1-g37:sparkbot:001"
    )
    assert fixture["source_bounded_design_record_ref"] == (
        "bounded-consumer-integration-design:v1-g36:sparkbot:001"
    )
    assert refs["v1_g37_patch_preview_record_id"] == (
        "consumer-integration-patch-preview:v1-g37:sparkbot:001"
    )
    assert refs["v1_g36_bounded_design_record_id"] == (
        "bounded-consumer-integration-design:v1-g36:sparkbot:001"
    )
    assert refs["v1_g34_live_import_call_packet_id"] == (
        "sparkbot_lima_v1_g34_live_consumer_import_call"
    )


def test_v1_g38_static_candidate_does_not_import_or_call_runtime() -> None:
    fixture = _load_fixture()

    assert fixture["consumer_runtime_source_files_changed"] is False
    assert fixture["consumer_runtime_modules_imported"] is False
    assert fixture["adapter_symbols_called"] is False
    assert fixture["imported_symbols_called"] is False
    assert fixture["fake_call_envelope_executed"] is False
    assert fixture["lima_runtime_behavior_invoked"] is False
    assert fixture["consumer_runtime_calls_added"] is False
    assert fixture["live_consumer_import_calls_added"] is False
    assert fixture["consumer_integration_added"] is False
    assert "backend" not in sys.modules
    assert "lima" not in sys.modules


def test_v1_g38_runtime_and_external_boundaries_remain_false() -> None:
    fixture = _load_fixture()

    for key in (
        "runtime_source_files_changed",
        "shell_runtime_wiring_added",
        "provider_model_calls_added",
        "model_request_dispatch_added",
        "fallback_execution_added",
        "secret_lookup_added",
        "credential_access_added",
        "tool_execution_added",
        "connector_browser_network_file_device_robotics_physical_world_behavior_added",
        "raw_patch_body_persisted",
        "raw_diff_or_patch_persisted",
        "raw_file_content_persisted",
        "raw_sensitive_content_persisted",
        "product_ready",
    ):
        assert fixture[key] is False


def test_v1_g38_future_gates_remain_blocked() -> None:
    fixture = _load_fixture()

    assert fixture["future_required_gates"] == [
        "consumer_integration_import_smoke_approval_request",
        "shell_wiring_design_approval_request",
        "provider_model_dispatch_approval_request",
        "connector_browser_network_authority_approval_request",
        "physical_world_authority_approval_request",
        "product_readiness_approval_request",
    ]
    assert fixture["blocked_future_authorities"] == {
        "consumer_integration_import_smoke_approved": False,
        "consumer_integration_approved": False,
        "shell_wiring_implementation_approved": False,
        "provider_model_dispatch_approved": False,
        "connector_browser_network_authority_approved": False,
        "physical_world_authority_approved": False,
        "product_readiness_approved": False,
    }


def test_v1_g38_required_confirmations_are_true() -> None:
    confirmations = _load_fixture()["required_confirmations"]

    assert confirmations["consumer_repository_edit_approval_recorded_confirmation"] is True
    assert confirmations["approved_file_scope_only_confirmation"] is True
    assert confirmations["no_runtime_source_change_confirmation"] is True
    assert confirmations["no_consumer_runtime_module_import_confirmation"] is True
    assert confirmations["no_adapter_symbol_call_confirmation"] is True
    assert confirmations["no_consumer_integration_implementation_confirmation"] is True
    assert confirmations["no_runtime_wiring_confirmation"] is True
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
    assert confirmations["proof_not_integration_authority_confirmation"] is True
    assert confirmations["proof_not_product_readiness_confirmation"] is True


def test_v1_g38_fixture_does_not_include_raw_patch_or_sensitive_markers() -> None:
    output = json.dumps(_load_fixture(), sort_keys=True)

    for forbidden in (
        "diff --git",
        "@@",
        "BEGIN PATCH",
        "raw patch body",
        "raw prompt value",
        "raw customer data value",
        "provider token value",
        "api key value",
        "raw-secret-123",
    ):
        assert forbidden not in output
