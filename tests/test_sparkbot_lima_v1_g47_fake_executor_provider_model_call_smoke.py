"""Consumer fake-executor provider/model call smoke proof for LIMA V1-G47.

This test imports only the approved LIMA public harness symbols from the local
sibling LIMA checkout, validates sanitized authority metadata, and executes one
bounded call through an in-process fake provider executor. It does not import
Sparkbot runtime modules, call real providers, use provider SDKs, use network,
look up secrets, access credentials, execute tools, mutate files, or claim
product readiness.
"""

from __future__ import annotations

import json
import importlib
import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
LIMA_REPO_ROOT = REPO_ROOT.parent / "LIMA-AI-OS"
FIXTURE_PATH = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "sparkbot_lima_v1_g47_fake_executor_provider_model_call_smoke.json"
)


def _load_fixture() -> dict[str, Any]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(fixture, dict)
    return fixture


def _load_lima_harness() -> Any:
    if str(LIMA_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(LIMA_REPO_ROOT))
    return importlib.import_module("lima.harness")


def _clear_lima_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "lima" or module_name.startswith("lima."):
            del sys.modules[module_name]


@pytest.fixture(autouse=True)
def _cleanup_lima_modules() -> None:
    yield
    _clear_lima_modules()


def _authority_metadata(**overrides: Any) -> dict[str, Any]:
    record = {
        "authority_id": "authority:v1-g47:sparkbot:001",
        "request_or_guardian_decision_linkage": {
            "request_id": "request:v1-g47:sparkbot:001",
            "guardian_decision_id": "decision:v1-g47:sparkbot:001",
            "linkage_required": True,
            "proof_not_execution": True,
            "grants_execution_authority": False,
        },
        "tenant_scope": "tenant:sparkbot-local",
        "shell_scope": "shell:sparkbot",
        "actor_scope": "actor:v1-g47-smoke",
        "session_scope": "session:local",
        "source_provider_model_route_authority_ref": "route:v1-g20:sparkbot:001",
        "source_provider_model_dispatch_evidence_ref": (
            "provider-model-dispatch:v1-g43:sparkbot:fake-provider:001"
        ),
        "provider_id": "provider:fake-executor:sparkbot",
        "model_id": "model:fake-executor-smoke",
        "model_role": "primary",
        "provider_boundary_metadata": {
            "provider_boundary_ref": "provider-boundary:v1-g47:sparkbot:fake",
            "provider_class": "fake_executor_metadata",
            "provider_configured_for_scope": True,
            "live_provider_call_authority_policy_bound": True,
            "live_provider_call_execution_allowed": False,
            "provider_readiness_network_check_allowed": False,
            "token_guardian_live_routing_allowed": False,
            "proof_not_execution": True,
        },
        "credential_reference_metadata": {
            "credential_ref": "credential-ref:v1-g47:sparkbot:none",
            "provider_is_no_key_local": True,
            "reference_only": True,
            "secret_lookup_performed": False,
            "credential_value_accessed": False,
            "raw_secret_present": False,
            "credential_value_present": False,
            "provider_token_present": False,
        },
        "network_policy_reference_metadata": {
            "network_policy_ref": "network-policy:v1-g47:sparkbot:none",
            "reference_only": True,
            "network_scope_bound": True,
            "network_call_performed": False,
            "provider_endpoint_resolution_performed": False,
            "proof_not_execution": True,
        },
        "prompt_reference_metadata": {
            "prompt_ref": "prompt-ref:v1-g47:sparkbot:redacted-summary",
            "prompt_context_class": "redacted_summary",
            "reference_only": True,
            "redacted": True,
            "raw_prompt_present": False,
            "raw_customer_data_present": False,
        },
        "output_handling_policy": {
            "output_policy_ref": "output-policy:v1-g47:sparkbot:redacted",
            "audit_output_ref": "audit-output:v1-g47:sparkbot:redacted-summary",
            "redacted_output_required": True,
            "raw_model_response_present": False,
            "persist_raw_model_response": False,
            "proof_not_execution": True,
        },
        "data_sensitivity": "internal",
        "budget_class": "medium",
        "estimated_cost_class": "free",
        "latency_tier": "interactive",
        "approval_evidence_linkage": {
            "approval_required_by_policy": True,
            "approval_evidence_ref": "approval-evidence:v1-g47:sparkbot:001",
            "approval_evidence_current": True,
            "proof_not_execution": True,
            "grants_execution_authority": False,
        },
        "audit_evidence_linkage": {
            "audit_record_ref": "audit:v1-g47:sparkbot:fake-executor-smoke",
            "evidence_refs": [
                "route:v1-g20:sparkbot:001",
                "provider-model-dispatch:v1-g43:sparkbot:fake-provider:001",
            ],
            "required": True,
            "proof_not_execution": True,
        },
        "proof_not_execution_confirmation": True,
        "no_raw_prompt_model_response_customer_data_confirmation": True,
        "no_secret_lookup_confirmation": True,
        "no_credential_value_access_confirmation": True,
        "no_network_call_confirmation": True,
        "no_live_provider_call_execution_confirmation": True,
        "no_fallback_execution_confirmation": True,
    }
    record.update(overrides)
    return record


def _authority_record() -> dict[str, Any]:
    harness = _load_lima_harness()
    return harness.validate_v1_live_provider_model_call_authority(
        _authority_metadata()
    )


def _execution_request(**overrides: Any) -> dict[str, Any]:
    request = {
        "execution_id": "execution:v1-g47:sparkbot:001",
        "authority_record": _authority_record(),
        "provider_executor_ref": "provider-executor:v1-g47:sparkbot:fake-only",
        "provider_request_ref": "provider-request:v1-g47:sparkbot:redacted:001",
        "redacted_prompt_ref": "prompt-ref:v1-g47:sparkbot:redacted-summary",
        "redacted_input_summary_ref": "input-summary:v1-g47:sparkbot:redacted",
        "execution_approval_linkage": {
            "approval_evidence_ref": "approval-evidence:v1-g47:sparkbot:001",
            "approval_evidence_current": True,
            "approval_scope": "v1-g46-live-provider-model-call-execution",
            "grants_live_provider_execution_authority": True,
            "proof_of_operator_approval": True,
        },
        "audit_evidence_linkage": {
            "audit_record_ref": "audit:v1-g47:sparkbot:fake-executor-smoke",
            "evidence_refs": [
                "authority:v1-g47:sparkbot:001",
                "provider-model-dispatch:v1-g43:sparkbot:fake-provider:001",
            ],
            "required": True,
            "sanitized_evidence_only": True,
        },
        "redaction_policy": {
            "redaction_policy_ref": "redaction-policy:v1-g47:sparkbot:sanitized",
            "redacted_input_required": True,
            "redacted_output_required": True,
            "raw_prompt_persistence_allowed": False,
            "raw_model_response_persistence_allowed": False,
            "raw_customer_data_persistence_allowed": False,
            "raw_secret_credential_persistence_allowed": False,
        },
        "execution_boundary": {
            "provider_executor_boundary_ref": "boundary:v1-g47:sparkbot:fake-injected",
            "provider_executor_injected": True,
            "direct_provider_sdk_used": False,
            "direct_network_code_used": False,
            "ambient_secret_lookup_performed": False,
            "credential_value_accessed": False,
            "fallback_allowed": False,
            "tool_execution_allowed": False,
            "consumer_repo_mutation_allowed": False,
            "connector_browser_network_file_device_robotics_physical_world_behavior_allowed": False,
        },
        "provider_executor_injected_confirmation": True,
        "no_direct_provider_sdk_confirmation": True,
        "no_direct_network_code_confirmation": True,
        "no_ambient_secret_lookup_confirmation": True,
        "no_credential_value_access_confirmation": True,
        "no_fallback_execution_confirmation": True,
        "no_raw_prompt_model_response_customer_data_persistence_confirmation": True,
    }
    request.update(overrides)
    return request


def _provider_result() -> dict[str, Any]:
    return {
        "provider_call_id": "provider-call:v1-g47:sparkbot:fake:001",
        "output_ref": "audit-output:v1-g47:sparkbot:redacted-summary",
        "redacted_output_summary_ref": "output-summary:v1-g47:sparkbot:redacted",
        "finish_status": "completed",
        "usage_metadata": {
            "input_tokens": 5,
            "output_tokens": 3,
            "total_tokens": 8,
        },
    }


def test_v1_g47_fixture_records_fake_executor_smoke_scope() -> None:
    fixture = _load_fixture()

    assert fixture["packet_id"] == (
        "sparkbot_lima_v1_g47_fake_executor_provider_model_call_smoke"
    )
    assert fixture["api_status"] == "CANDIDATE_ONLY"
    assert fixture["proof_gap_id"] == "V1-G47"
    assert fixture["consumer_repo"] == "Sparkbot"
    assert fixture["consumer_repository"] == "sparkpit-labs/Sparkbot"
    assert fixture["proof_branch"] == (
        "v1-g47-consumer-fake-executor-provider-model-call-smoke"
    )
    assert fixture["consumer_fake_executor_provider_model_call_smoke_added"] is True
    assert fixture["fake_provider_executor_injected"] is True
    assert fixture["fake_provider_executor_invoked"] is True
    assert fixture["product_ready"] is False


def test_v1_g47_consumer_file_scope_is_exact() -> None:
    fixture = _load_fixture()

    assert fixture["approved_file_scope"] == [
        "tests/fixtures/sparkbot_lima_v1_g47_fake_executor_provider_model_call_smoke.json",
        "tests/test_sparkbot_lima_v1_g47_fake_executor_provider_model_call_smoke.py",
    ]
    for relative_path in fixture["approved_file_scope"]:
        assert (REPO_ROOT / relative_path).exists()


def test_v1_g47_imports_only_expected_lima_public_symbols() -> None:
    fixture = _load_fixture()
    harness = _load_lima_harness()

    assert fixture["expected_lima_public_symbols"] == [
        "V1LiveProviderModelCallExecutionError",
        "execute_v1_live_provider_model_call",
        "validate_v1_live_provider_model_call_authority",
    ]
    assert issubclass(harness.V1LiveProviderModelCallExecutionError, ValueError)
    assert callable(harness.execute_v1_live_provider_model_call)
    assert callable(harness.validate_v1_live_provider_model_call_authority)
    assert "backend" not in sys.modules


def test_v1_g47_fake_executor_smoke_invokes_lima_wrapper_once() -> None:
    calls: list[dict[str, Any]] = []

    def fake_executor(payload: Any) -> dict[str, Any]:
        assert isinstance(payload, dict)
        calls.append(dict(payload))
        return _provider_result()

    harness = _load_lima_harness()
    record = harness.execute_v1_live_provider_model_call(
        _execution_request(),
        fake_executor,
    )
    expected = _load_fixture()["expected_execution_record"]

    assert len(calls) == 1
    assert calls[0]["execution_id"] == expected["execution_id"]
    assert calls[0]["authority_id"] == expected["authority_id"]
    assert calls[0]["provider_executor_ref"] == expected["provider_executor_ref"]
    assert calls[0]["provider_request_ref"] == expected["provider_request_ref"]
    assert calls[0]["redacted_prompt_ref"] == expected["redacted_prompt_ref"]
    assert calls[0]["redacted_input_summary_ref"] == expected[
        "redacted_input_summary_ref"
    ]
    for key, value in expected.items():
        assert record[key] == value
    assert record["capability_open"] is True
    assert record["authority_gated"] is True
    assert record["provider_executor_invoked"] is True
    assert record["model_request_dispatched"] is True


def test_v1_g47_fake_executor_record_keeps_forbidden_boundaries_false() -> None:
    harness = _load_lima_harness()
    record = harness.execute_v1_live_provider_model_call(
        _execution_request(),
        lambda payload: _provider_result(),
    )

    for key in (
        "direct_provider_sdk_added",
        "direct_provider_sdk_used",
        "direct_network_code_added",
        "direct_network_code_used",
        "network_call_performed_by_lima_harness",
        "provider_readiness_network_check_added",
        "token_guardian_live_routing_added",
        "secret_lookup_added",
        "credential_value_access_added",
        "credential_access_added",
        "fallback_execution_added",
        "fallback_executed",
        "tool_execution_added",
        "tool_executed",
        "consumer_repo_mutation_added",
        "consumer_code_imported",
        "consumer_runtime_calls_added",
        "consumer_integration_added",
        "connector_invoked",
        "browser_action_executed",
        "network_action_executed",
        "device_command_invoked",
        "physical_world_invoked",
        "raw_prompt_persisted",
        "raw_model_response_persisted",
        "raw_customer_data_persisted",
        "raw_sensitive_content_persisted",
        "product_ready",
    ):
        assert record[key] is False


def test_v1_g47_missing_fake_executor_fails_closed() -> None:
    harness = _load_lima_harness()

    with pytest.raises(
        harness.V1LiveProviderModelCallExecutionError,
        match="provider_executor",
    ):
        harness.execute_v1_live_provider_model_call(_execution_request(), None)


def test_v1_g47_fixture_runtime_and_external_boundaries_remain_false() -> None:
    fixture = _load_fixture()

    for key in (
        "consumer_runtime_source_files_changed",
        "consumer_runtime_modules_imported",
        "consumer_runtime_calls_added",
        "consumer_integration_added",
        "lima_runtime_files_changed",
        "real_provider_executor_invoked",
        "direct_provider_sdk_added",
        "direct_provider_sdk_used",
        "direct_network_code_added",
        "direct_network_code_used",
        "network_calls_performed",
        "secret_lookup_added",
        "credential_access_added",
        "credential_value_accessed",
        "fallback_execution_added",
        "tool_execution_added",
        "connector_browser_network_file_device_robotics_physical_world_behavior_added",
        "raw_prompt_persisted",
        "raw_model_response_persisted",
        "raw_customer_data_persisted",
        "raw_diff_or_patch_persisted",
        "raw_file_content_persisted",
        "credential_or_secret_persisted",
        "product_ready",
    ):
        assert fixture[key] is False


def test_v1_g47_outputs_do_not_include_sensitive_markers() -> None:
    harness = _load_lima_harness()
    record = harness.execute_v1_live_provider_model_call(
        _execution_request(),
        lambda payload: _provider_result(),
    )
    output = json.dumps({"fixture": _load_fixture(), "record": record}, sort_keys=True)

    for forbidden in (
        "diff --git",
        "@@",
        "BEGIN PATCH",
        "raw patch body",
        "raw prompt value",
        "raw model response value",
        "raw customer data value",
        "provider credential value",
        "provider token value",
        "api key value",
        "raw-secret-123",
    ):
        assert forbidden not in output
