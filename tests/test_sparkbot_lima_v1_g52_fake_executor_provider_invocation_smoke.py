"""Consumer fake-executor provider invocation smoke proof for LIMA V1-G52.

This test imports only the approved LIMA public harness symbols from the local
sibling LIMA checkout, builds sanitized V1-G50 invocation envelope metadata,
and executes one bounded call through an in-process fake provider executor. It
does not import Sparkbot runtime modules, call real providers, use provider
SDKs, use network, look up secrets, access credentials, execute tools, mutate
files, or claim product readiness.
"""

from __future__ import annotations

import copy
import importlib
import json
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
    / "sparkbot_lima_v1_g52_fake_executor_provider_invocation_smoke.json"
)
G50_FIXTURE_PATH = (
    LIMA_REPO_ROOT
    / "tests"
    / "fixtures"
    / "runtime_extraction"
    / "v1_g50_real_provider_executor_invocation.json"
)


def _load_fixture() -> dict[str, Any]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(fixture, dict)
    return fixture


def _load_g50_fixture() -> dict[str, Any]:
    fixture = json.loads(G50_FIXTURE_PATH.read_text(encoding="utf-8"))
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


def _g51_execution_boundary() -> dict[str, Any]:
    return {
        "provider_executor_boundary_ref": (
            "boundary:v1-g52:sparkbot:fake-in-process"
        ),
        "caller_injected_provider_executor": True,
        "provider_executor_call_allowed": True,
        "max_attempts": 1,
        "built_in_provider_sdk_used": False,
        "direct_provider_sdk_used": False,
        "direct_network_code_used": False,
        "provider_endpoint_resolution_performed": False,
        "network_call_performed_by_lima_harness": False,
        "ambient_secret_lookup_performed": False,
        "secret_lookup_performed": False,
        "credential_value_accessed": False,
        "provider_token_or_api_key_accessed": False,
        "fallback_allowed": False,
        "tool_execution_allowed": False,
        "consumer_repo_mutation_allowed": False,
        "connector_browser_network_file_device_robotics_physical_world_behavior_allowed": False,
    }


def _execution_request(**overrides: Any) -> dict[str, Any]:
    g50 = _load_g50_fixture()
    request = {
        "invocation_id": "invocation:v1-g52:sparkbot:001",
        "invocation_request_envelope": copy.deepcopy(
            g50["invocation_request_envelope"]
        ),
        "invocation_response_envelope": copy.deepcopy(
            g50["invocation_response_envelope"]
        ),
        "provider_model_scope": copy.deepcopy(g50["provider_model_scope"]),
        "executor_authority_linkage": copy.deepcopy(
            g50["executor_authority_linkage"]
        ),
        "credential_network_hardening_linkage": copy.deepcopy(
            g50["credential_network_hardening_linkage"]
        ),
        "g50_execution_boundary_metadata": copy.deepcopy(
            g50["execution_boundary_metadata"]
        ),
        "provider_executor_ref": "provider-executor:v1-g52:sparkbot:fake-in-process",
        "provider_request_ref": "provider-request:v1-g52:sparkbot:redacted:001",
        "g51_execution_approval_linkage": {
            "approval_evidence_ref": "approval-evidence:v1-g52:sparkbot:001",
            "approval_evidence_current": True,
            "approval_scope": "v1-g51-executable-real-provider-executor-invocation",
            "grants_executable_real_provider_executor_invocation_authority": True,
            "proof_of_operator_approval": True,
        },
        "g51_execution_boundary": _g51_execution_boundary(),
        "audit_evidence_linkage": {
            "audit_record_ref": "audit:v1-g52:sparkbot:fake-executor-smoke",
            "evidence_refs": [
                "evidence:v1-g51:executable-provider-wrapper",
                "evidence:v1-g50:invocation-request-envelope-metadata",
                "evidence:v1-g49:real-provider-executor-authority-design",
                "evidence:v1-g48:credential-reference-only",
            ],
            "required": True,
            "sanitized_evidence_only": True,
        },
        "redaction_policy": {
            "redaction_policy_ref": "redaction-policy:v1-g52:sparkbot:sanitized",
            "redacted_input_required": True,
            "redacted_output_required": True,
            "raw_prompt_persistence_allowed": False,
            "raw_model_response_persistence_allowed": False,
            "raw_customer_data_persistence_allowed": False,
            "raw_secret_credential_persistence_allowed": False,
            "raw_diff_patch_file_content_persistence_allowed": False,
        },
        "caller_injected_provider_executor_confirmation": True,
        "no_built_in_provider_sdk_confirmation": True,
        "no_direct_network_code_confirmation": True,
        "no_provider_endpoint_resolution_confirmation": True,
        "no_secret_lookup_confirmation": True,
        "no_credential_value_access_confirmation": True,
        "no_provider_token_or_api_key_access_confirmation": True,
        "no_fallback_execution_confirmation": True,
        "no_connector_browser_network_physical_world_confirmation": True,
        "no_raw_prompt_model_response_customer_data_persistence_confirmation": True,
    }
    request.update(overrides)
    return request


def _provider_result() -> dict[str, Any]:
    return {
        "provider_call_ref": "provider-call-ref:v1-g52:sparkbot:fake:001",
        "redacted_output_ref": "redacted-output-ref:v1-g52:sparkbot:001",
        "redacted_output_summary_ref": "output-summary-ref:v1-g52:sparkbot:redacted",
        "finish_status": "completed",
        "usage_metadata": {
            "input_tokens": 11,
            "output_tokens": 6,
            "total_tokens": 17,
        },
    }


def test_v1_g52_fixture_records_fake_executor_smoke_scope() -> None:
    fixture = _load_fixture()

    assert fixture["packet_id"] == (
        "sparkbot_lima_v1_g52_fake_executor_provider_invocation_smoke"
    )
    assert fixture["api_status"] == "CANDIDATE_ONLY"
    assert fixture["proof_gap_id"] == "V1-G52"
    assert fixture["consumer_repo"] == "Sparkbot"
    assert fixture["consumer_repository"] == "sparkpit-labs/Sparkbot"
    assert fixture["proof_branch"] == (
        "v1-g52-consumer-fake-executor-provider-invocation-smoke"
    )
    assert fixture["consumer_fake_executor_provider_invocation_smoke_added"] is True
    assert fixture["v1_g50_invocation_envelope_metadata_built"] is True
    assert fixture["fake_in_process_provider_executor_injected"] is True
    assert fixture["fake_in_process_provider_executor_invoked"] is True
    assert fixture["actual_external_provider_invoked"] is False
    assert fixture["product_ready"] is False


def test_v1_g52_consumer_file_scope_is_exact() -> None:
    fixture = _load_fixture()

    assert fixture["approved_file_scope"] == [
        "tests/test_sparkbot_lima_v1_g52_fake_executor_provider_invocation_smoke.py",
        "tests/fixtures/sparkbot_lima_v1_g52_fake_executor_provider_invocation_smoke.json",
    ]
    for relative_path in fixture["approved_file_scope"]:
        assert (REPO_ROOT / relative_path).exists()


def test_v1_g52_imports_only_expected_lima_public_symbols() -> None:
    fixture = _load_fixture()
    harness = _load_lima_harness()

    assert fixture["expected_lima_public_symbols"] == [
        "V1ExecutableRealProviderExecutorInvocationError",
        "execute_v1_executable_real_provider_executor_invocation",
    ]
    assert issubclass(
        harness.V1ExecutableRealProviderExecutorInvocationError,
        ValueError,
    )
    assert callable(harness.execute_v1_executable_real_provider_executor_invocation)
    assert "backend" not in sys.modules


def test_v1_g52_fake_executor_smoke_invokes_lima_wrapper_once() -> None:
    calls: list[dict[str, Any]] = []

    def fake_executor(payload: Any) -> dict[str, Any]:
        assert isinstance(payload, dict)
        calls.append(dict(payload))
        return _provider_result()

    harness = _load_lima_harness()
    record = harness.execute_v1_executable_real_provider_executor_invocation(
        _execution_request(),
        fake_executor,
    )
    expected = _load_fixture()["expected_execution_record"]

    assert len(calls) == 1
    assert calls[0]["invocation_id"] == expected["invocation_id"]
    assert calls[0]["provider_executor_ref"] == expected["provider_executor_ref"]
    assert calls[0]["provider_request_ref"] == expected["provider_request_ref"]
    assert calls[0]["redacted_input_ref"] == "redacted-input-ref:v1-g50:metadata-only"
    assert calls[0]["redacted_output_ref"] == (
        "redacted-output-ref:v1-g50:metadata-only"
    )
    for key, value in expected.items():
        assert record[key] == value
    assert record["capability_open"] is True
    assert record["authority_gated"] is True
    assert record["caller_injected_provider_executor_only"] is True
    assert record["local_tests_use_fake_injected_executors_only"] is True
    assert record["provider_executor_invoked"] is True
    assert record["model_request_dispatched"] is True


def test_v1_g52_fake_executor_record_keeps_forbidden_boundaries_false() -> None:
    harness = _load_lima_harness()
    record = harness.execute_v1_executable_real_provider_executor_invocation(
        _execution_request(),
        lambda payload: _provider_result(),
    )

    for key in (
        "built_in_provider_sdk_added",
        "built_in_provider_sdk_used",
        "direct_provider_sdk_added",
        "direct_provider_sdk_used",
        "direct_network_code_added",
        "direct_network_code_used",
        "network_call_performed_by_lima_harness",
        "provider_endpoint_resolution_added",
        "provider_endpoint_resolution_performed",
        "secret_lookup_added",
        "credential_value_access_added",
        "credential_value_accessed",
        "provider_token_or_api_key_access_added",
        "provider_token_or_api_key_accessed",
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


def test_v1_g52_missing_fake_executor_fails_closed() -> None:
    harness = _load_lima_harness()

    with pytest.raises(
        harness.V1ExecutableRealProviderExecutorInvocationError,
        match="provider_executor",
    ):
        harness.execute_v1_executable_real_provider_executor_invocation(
            _execution_request(),
            None,
        )


def test_v1_g52_fixture_runtime_and_external_boundaries_remain_false() -> None:
    fixture = _load_fixture()

    for key in (
        "consumer_runtime_source_files_changed",
        "consumer_runtime_modules_imported",
        "consumer_runtime_calls_added",
        "consumer_integration_added",
        "lima_runtime_files_changed",
        "actual_external_provider_invoked",
        "live_provider_credentials_used",
        "direct_provider_sdk_added",
        "direct_provider_sdk_used",
        "direct_network_code_added",
        "direct_network_code_used",
        "provider_endpoint_resolution_added",
        "provider_endpoint_resolution_performed",
        "network_calls_performed",
        "secret_lookup_added",
        "credential_access_added",
        "credential_value_accessed",
        "provider_token_or_api_key_accessed",
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


def test_v1_g52_outputs_do_not_include_sensitive_markers() -> None:
    harness = _load_lima_harness()
    record = harness.execute_v1_executable_real_provider_executor_invocation(
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
