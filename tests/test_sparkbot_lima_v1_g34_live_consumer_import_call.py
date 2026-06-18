"""Live local import/call test for the approved LIMA V1-G34 consumer slice.

This test imports and calls only approved LIMA adapter validators with static
sanitized metadata. It does not import Sparkbot runtime modules, call providers,
execute tools, wire shells, use network, or access secrets.
"""

from __future__ import annotations

import copy
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
    / "sparkbot_lima_v1_g34_live_consumer_import_call.json"
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


def _compatibility_metadata() -> dict[str, Any]:
    return copy.deepcopy(_load_fixture()["compatibility_metadata"])


def _import_plan_metadata() -> dict[str, Any]:
    return copy.deepcopy(_load_fixture()["import_plan_metadata"])


def test_v1_g34_fixture_records_live_consumer_import_call_test_scope() -> None:
    fixture = _load_fixture()

    assert fixture["packet_id"] == "sparkbot_lima_v1_g34_live_consumer_import_call"
    assert fixture["api_status"] == "CANDIDATE_ONLY"
    assert fixture["consumer_repo"] == "Sparkbot"
    assert fixture["proof_branch"] == "v1-g34-live-consumer-import-call"
    assert fixture["live_consumer_import_call_test_added"] is True
    assert fixture["test_only_imports_added"] is True
    assert fixture["test_only_calls_added"] is True
    assert fixture["docs_tests_fixtures_only"] is True
    assert fixture["runtime_source_files_changed"] is False


def test_v1_g34_imports_only_approved_lima_adapter_symbols() -> None:
    fixture = _load_fixture()
    module = _import_lima_adapters_module()

    assert fixture["approved_import_symbols"] == [
        "lima.adapters.validate_v1_consumer_integration_compatibility_freeze",
        "lima.adapters.validate_v1_consumer_integration_proof_to_import_dry_run",
    ]
    assert fixture["approved_call_symbols"] == fixture["approved_import_symbols"]
    assert hasattr(module, "validate_v1_consumer_integration_compatibility_freeze")
    assert hasattr(module, "validate_v1_consumer_integration_proof_to_import_dry_run")
    assert set(fixture["approved_import_symbols"]).issubset(
        {"lima.adapters." + symbol for symbol in getattr(module, "__all__")}
    )


def test_v1_g34_calls_compatibility_validator_with_sanitized_metadata() -> None:
    module = _import_lima_adapters_module()

    first = module.validate_v1_consumer_integration_compatibility_freeze(
        _compatibility_metadata()
    )
    second = module.validate_v1_consumer_integration_compatibility_freeze(
        _compatibility_metadata()
    )

    assert first == second
    assert first["record_type"] == "v1_consumer_integration_compatibility_freeze"
    assert first["schema_version"] == "v1-g21-candidate"
    assert first["consumer_packet_family"] == "sparkbot"
    assert first["compatibility_metadata_only"] is True
    assert first["non_executing"] is True
    assert first["proof_not_authority"] is True
    assert first["consumer_runtime_calls_added"] is False
    assert first["provider_model_calls_added"] is False
    assert first["secret_lookup_added"] is False
    assert first["product_ready"] is False
    assert len(first["record_hash"]) == 64


def test_v1_g34_calls_import_dry_run_validator_with_sanitized_metadata() -> None:
    module = _import_lima_adapters_module()

    first = module.validate_v1_consumer_integration_proof_to_import_dry_run(
        _import_plan_metadata()
    )
    second = module.validate_v1_consumer_integration_proof_to_import_dry_run(
        _import_plan_metadata()
    )

    assert first == second
    assert first["record_type"] == "v1_consumer_integration_proof_to_import_dry_run"
    assert first["schema_version"] == "v1-g23-candidate"
    assert first["consumer_packet_family"] == "sparkbot"
    assert first["import_plan_metadata_only"] is True
    assert first["non_executing"] is True
    assert first["proof_not_authority"] is True
    assert first["consumer_runtime_calls_added"] is False
    assert first["provider_model_calls_added"] is False
    assert first["secret_lookup_added"] is False
    assert first["product_ready"] is False
    assert len(first["record_hash"]) == 64


def test_v1_g34_does_not_import_sparkbot_runtime_or_wire_shells() -> None:
    fixture = _load_fixture()

    assert fixture["consumer_runtime_modules_imported"] is False
    assert fixture["shell_runtime_wiring_added"] is False
    assert fixture["provider_model_calls_added"] is False
    assert fixture["model_request_dispatch_added"] is False
    assert "backend" not in sys.modules


def test_v1_g34_runtime_and_external_boundaries_remain_false() -> None:
    fixture = _load_fixture()

    for key in (
        "runtime_source_files_changed",
        "consumer_runtime_modules_imported",
        "shell_runtime_wiring_added",
        "provider_model_calls_added",
        "model_request_dispatch_added",
        "secret_lookup_added",
        "credential_access_added",
        "connector_browser_network_file_device_robotics_physical_world_behavior_added",
        "raw_sensitive_content_persisted",
        "product_ready",
    ):
        assert fixture[key] is False


def test_v1_g34_links_required_lima_evidence() -> None:
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
    assert refs["v1_g32_test_edit_record_id"] == (
        "consumer-repository-test-edit:v1-g32:sparkbot:001"
    )
    assert refs["v1_g33_smoke_record_id"] == (
        "consumer-fake-runtime-import-call-smoke:v1-g33:sparkbot:001"
    )


def test_v1_g34_required_confirmations_are_true() -> None:
    confirmations = _load_fixture()["required_confirmations"]

    assert confirmations["no_runtime_source_change_confirmation"] is True
    assert confirmations["no_consumer_runtime_module_import_confirmation"] is True
    assert confirmations["no_runtime_wiring_confirmation"] is True
    assert confirmations["only_approved_adapter_validator_calls_confirmation"] is True
    assert (
        confirmations[
            "no_provider_model_secret_credential_connector_browser_network_physical_world_confirmation"
        ]
        is True
    )
    assert confirmations["no_raw_sensitive_content_confirmation"] is True
    assert confirmations["proof_not_product_readiness_confirmation"] is True


def test_v1_g34_fixture_does_not_include_sensitive_markers() -> None:
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
