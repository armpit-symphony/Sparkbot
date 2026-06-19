"""Consumer fake-executor provider SDK/network egress smoke proof for LIMA V1-G56.

This test imports only the approved LIMA public harness symbols from the local
sibling LIMA checkout, builds sanitized V1-G48/G50/G51/G53/G54/G55 authority
metadata, and executes one bounded call through an in-process fake provider
SDK/network executor. It does not import Sparkbot runtime modules, call real
providers, use provider SDK clients, use network, look up secrets, access
credentials, execute fallback, execute tools, mutate production files, or claim
product readiness.
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
    / "sparkbot_lima_v1_g56_fake_executor_provider_sdk_network_egress_smoke.json"
)
G50_FIXTURE_PATH = (
    LIMA_REPO_ROOT
    / "tests"
    / "fixtures"
    / "runtime_extraction"
    / "v1_g50_real_provider_executor_invocation.json"
)
G51_FIXTURE_PATH = (
    LIMA_REPO_ROOT
    / "tests"
    / "fixtures"
    / "runtime_extraction"
    / "v1_g51_executable_real_provider_executor_invocation.json"
)
G53_FIXTURE_PATH = (
    LIMA_REPO_ROOT
    / "tests"
    / "fixtures"
    / "runtime_extraction"
    / "v1_g53_provider_sdk_network_credential_authority.json"
)
G54_FIXTURE_PATH = (
    LIMA_REPO_ROOT
    / "tests"
    / "fixtures"
    / "runtime_extraction"
    / "v1_g54_fake_sdk_egress_harness.json"
)
G55_FIXTURE_PATH = (
    LIMA_REPO_ROOT
    / "tests"
    / "fixtures"
    / "runtime_extraction"
    / "v1_g55_real_provider_sdk_network_egress.json"
)


def _load_fixture() -> dict[str, Any]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(fixture, dict)
    return fixture


def _load_json(path: Path) -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
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


def _egress_request(**overrides: Any) -> dict[str, Any]:
    g50 = _load_json(G50_FIXTURE_PATH)
    g51 = _load_json(G51_FIXTURE_PATH)
    g53 = _load_json(G53_FIXTURE_PATH)
    g54 = _load_json(G54_FIXTURE_PATH)
    g55 = _load_json(G55_FIXTURE_PATH)
    refs = g55["egress_request_policy_refs"]
    request = {
        "egress_request_id": "egress-request:v1-g56:sparkbot:001",
        "invocation_request_envelope": copy.deepcopy(
            g50["invocation_request_envelope"]
        ),
        "invocation_response_envelope": copy.deepcopy(
            g50["invocation_response_envelope"]
        ),
        "provider_model_scope": copy.deepcopy(g50["provider_model_scope"]),
        "credential_network_hardening_linkage": copy.deepcopy(
            g50["credential_network_hardening_linkage"]
        ),
        "g50_execution_boundary_metadata": copy.deepcopy(
            g50["execution_boundary_metadata"]
        ),
        "g51_execution_boundary": copy.deepcopy(g51["execution_boundary"]),
        "g53_provider_sdk_authority_metadata": copy.deepcopy(
            g53["provider_sdk_authority_metadata"]
        ),
        "g53_endpoint_resolution_authority_metadata": copy.deepcopy(
            g53["endpoint_resolution_authority_metadata"]
        ),
        "g53_provider_network_egress_authority_metadata": copy.deepcopy(
            g53["provider_network_egress_authority_metadata"]
        ),
        "g53_credential_reference_authority_metadata": copy.deepcopy(
            g53["credential_reference_authority_metadata"]
        ),
        "g53_authority_chain_linkage": copy.deepcopy(g53["authority_chain_linkage"]),
        "g54_fake_sdk_harness_evidence": copy.deepcopy(
            g54["fake_sdk_harness_evidence"]
        ),
        "g54_fake_egress_harness_evidence": copy.deepcopy(
            g54["fake_egress_harness_evidence"]
        ),
        "g54_authority_chain_linkage": copy.deepcopy(g54["authority_chain_linkage"]),
        "provider_sdk_network_executor_ref": (
            "provider-sdk-network-executor:v1-g56:sparkbot:fake-in-process"
        ),
        "provider_sdk_request_ref": "provider-sdk-request:v1-g56:sparkbot:redacted",
        "sanitized_input_ref": "sanitized-input:v1-g56:sparkbot:metadata-only",
        "sanitized_output_ref": "sanitized-output:v1-g56:sparkbot:metadata-only",
        "endpoint_policy_ref": refs["endpoint_policy_ref"],
        "timeout_policy_ref": refs["timeout_policy_ref"],
        "cost_policy_ref": refs["cost_policy_ref"],
        "denial_policy_ref": refs["denial_policy_ref"],
        "g55_execution_approval_linkage": copy.deepcopy(
            g55["g55_execution_approval_linkage"]
        ),
        "g55_execution_boundary": copy.deepcopy(g55["g55_execution_boundary"]),
        "audit_evidence_linkage": {
            "audit_record_ref": "audit:v1-g56:sparkbot:fake-sdk-network-egress",
            "evidence_refs": [
                "evidence:v1-g55:real-provider-sdk-network-egress-wrapper",
                "evidence:v1-g54:fake-sdk-egress-harness",
                "evidence:v1-g53:provider-sdk-network-credential-authority",
                "evidence:v1-g50:invocation-request-envelope-metadata",
                "evidence:v1-g48:credential-reference-only",
            ],
            "required": True,
            "sanitized_evidence_only": True,
        },
        "redaction_policy": {
            "redaction_policy_ref": "redaction-policy:v1-g56:sparkbot:sanitized",
            "redacted_input_required": True,
            "redacted_output_required": True,
            "raw_prompt_persistence_allowed": False,
            "raw_model_response_persistence_allowed": False,
            "raw_customer_data_persistence_allowed": False,
            "raw_secret_credential_persistence_allowed": False,
            "raw_provider_token_api_key_persistence_allowed": False,
            "raw_diff_patch_file_content_persistence_allowed": False,
        },
        "caller_injected_provider_sdk_network_executor_confirmation": True,
        "local_tests_use_fake_injected_executors_only_confirmation": True,
        "no_built_in_provider_sdk_client_confirmation": True,
        "no_sdk_dependency_confirmation": True,
        "no_direct_provider_sdk_implementation_confirmation": True,
        "no_lima_owned_endpoint_resolution_confirmation": True,
        "no_lima_owned_dns_http_socket_network_call_confirmation": True,
        "no_secret_lookup_confirmation": True,
        "no_credential_value_access_confirmation": True,
        "no_provider_token_or_api_key_access_confirmation": True,
        "no_provider_configuration_change_confirmation": True,
        "no_fallback_execution_confirmation": True,
        "no_consumer_production_runtime_integration_confirmation": True,
        "no_connector_browser_network_device_physical_world_confirmation": True,
        "no_raw_content_secret_credential_customer_data_diff_patch_confirmation": True,
        "no_product_readiness_confirmation": True,
    }
    request.update(overrides)
    return request


def _provider_sdk_network_result() -> dict[str, Any]:
    return {
        "provider_sdk_call_ref": "provider-sdk-call:v1-g56:sparkbot:fake:001",
        "provider_sdk_response_ref": (
            "provider-sdk-response:v1-g56:sparkbot:sanitized:001"
        ),
        "provider_network_egress_record_ref": (
            "provider-network-egress:v1-g56:sparkbot:fake:001"
        ),
        "redacted_output_ref": "redacted-output-ref:v1-g56:sparkbot:001",
        "redacted_output_summary_ref": "output-summary-ref:v1-g56:sparkbot:redacted",
        "finish_status": "completed",
        "usage_metadata": {
            "input_tokens": 19,
            "output_tokens": 9,
            "total_tokens": 28,
        },
        "network_call_performed_by_lima_harness": False,
        "direct_provider_egress_performed_by_lima": False,
        "secret_lookup_performed": False,
        "credential_value_accessed": False,
        "provider_token_or_api_key_accessed": False,
    }


def test_v1_g56_fixture_records_fake_executor_sdk_network_egress_scope() -> None:
    fixture = _load_fixture()

    assert fixture["packet_id"] == (
        "sparkbot_lima_v1_g56_fake_executor_provider_sdk_network_egress_smoke"
    )
    assert fixture["api_status"] == "CANDIDATE_ONLY"
    assert fixture["proof_gap_id"] == "V1-G56"
    assert fixture["consumer_repo"] == "Sparkbot"
    assert fixture["consumer_repository"] == "sparkpit-labs/Sparkbot"
    assert fixture["proof_branch"] == (
        "v1-g56-consumer-fake-executor-provider-sdk-network-egress-smoke"
    )
    assert fixture["consumer_fake_executor_provider_sdk_network_egress_smoke_added"]
    assert fixture["fake_in_process_provider_sdk_network_executor_injected"] is True
    assert fixture["fake_in_process_provider_sdk_network_executor_invoked"] is True
    assert fixture["g55_public_wrapper_invoked"] is True
    assert fixture["actual_external_provider_invoked"] is False
    assert fixture["product_ready"] is False


def test_v1_g56_consumer_file_scope_is_exact() -> None:
    fixture = _load_fixture()

    assert fixture["approved_file_scope"] == [
        "tests/test_sparkbot_lima_v1_g56_fake_executor_provider_sdk_network_egress_smoke.py",
        "tests/fixtures/sparkbot_lima_v1_g56_fake_executor_provider_sdk_network_egress_smoke.json",
    ]
    for relative_path in fixture["approved_file_scope"]:
        assert (REPO_ROOT / relative_path).exists()


def test_v1_g56_imports_only_expected_lima_public_symbols() -> None:
    fixture = _load_fixture()
    harness = _load_lima_harness()

    assert fixture["expected_lima_public_symbols"] == [
        "V1RealProviderSdkNetworkEgressError",
        "execute_v1_real_provider_sdk_network_egress",
    ]
    assert issubclass(harness.V1RealProviderSdkNetworkEgressError, ValueError)
    assert callable(harness.execute_v1_real_provider_sdk_network_egress)
    assert "backend" not in sys.modules


def test_v1_g56_fake_executor_smoke_invokes_lima_wrapper_once() -> None:
    calls: list[dict[str, Any]] = []

    def fake_executor(payload: Any) -> dict[str, Any]:
        assert isinstance(payload, dict)
        calls.append(dict(payload))
        return _provider_sdk_network_result()

    harness = _load_lima_harness()
    record = harness.execute_v1_real_provider_sdk_network_egress(
        _egress_request(),
        fake_executor,
    )
    expected = _load_fixture()["expected_execution_record"]

    assert len(calls) == 1
    assert calls[0]["egress_request_id"] == expected["egress_request_id"]
    assert calls[0]["provider_sdk_network_executor_ref"] == (
        expected["provider_sdk_network_executor_ref"]
    )
    assert calls[0]["provider_sdk_request_ref"] == expected["provider_sdk_request_ref"]
    assert calls[0]["redacted_input_ref"] == "redacted-input-ref:v1-g50:metadata-only"
    assert calls[0]["redacted_output_ref"] == (
        "redacted-output-ref:v1-g50:metadata-only"
    )
    for key, value in expected.items():
        assert record[key] == value
    assert record["capability_open"] is True
    assert record["authority_gated"] is True
    assert record["candidate_only"] is True
    assert record["caller_injected_provider_sdk_network_executor_only"] is True
    assert record["local_tests_use_fake_injected_executors_only"] is True
    assert record["provider_sdk_network_executor_invoked"] is True


def test_v1_g56_fake_executor_record_keeps_forbidden_boundaries_false() -> None:
    harness = _load_lima_harness()
    record = harness.execute_v1_real_provider_sdk_network_egress(
        _egress_request(),
        lambda payload: _provider_sdk_network_result(),
    )

    for key in (
        "built_in_provider_sdk_client_added",
        "built_in_provider_sdk_client_used",
        "real_provider_sdk_client_added_by_lima",
        "sdk_dependency_added",
        "direct_provider_sdk_implementation_added",
        "provider_endpoint_resolution_added_by_lima",
        "provider_endpoint_resolution_performed_by_lima",
        "direct_network_code_added_by_lima",
        "dns_lookup_performed_by_lima",
        "http_client_used_by_lima",
        "socket_client_used_by_lima",
        "network_call_performed_by_lima_harness",
        "direct_provider_egress_performed_by_lima",
        "provider_readiness_network_check_added",
        "secret_lookup_added",
        "credential_value_access_added",
        "credential_value_accessed",
        "provider_token_or_api_key_access_added",
        "provider_token_or_api_key_accessed",
        "provider_configuration_changes_added",
        "fallback_execution_added",
        "fallback_executed",
        "consumer_repo_mutation_added",
        "consumer_runtime_calls_added",
        "consumer_production_runtime_integration_added",
        "connector_browser_network_file_device_robotics_physical_world_behavior_added",
        "raw_prompt_persisted",
        "raw_model_response_persisted",
        "raw_customer_data_persisted",
        "raw_sensitive_content_persisted",
        "product_ready",
    ):
        assert record[key] is False


def test_v1_g56_missing_fake_executor_fails_closed() -> None:
    harness = _load_lima_harness()

    with pytest.raises(
        harness.V1RealProviderSdkNetworkEgressError,
        match="provider_sdk_network_executor",
    ):
        harness.execute_v1_real_provider_sdk_network_egress(
            _egress_request(),
            None,
        )


def test_v1_g56_fixture_runtime_and_external_boundaries_remain_false() -> None:
    fixture = _load_fixture()

    for key in (
        "consumer_runtime_source_files_changed",
        "consumer_runtime_modules_imported",
        "consumer_runtime_calls_added",
        "consumer_integration_added",
        "lima_runtime_files_changed",
        "actual_external_provider_invoked",
        "live_provider_credentials_used",
        "built_in_provider_sdk_client_added",
        "sdk_dependency_added",
        "direct_provider_sdk_added",
        "direct_network_code_added",
        "provider_endpoint_resolution_added",
        "provider_endpoint_resolution_performed",
        "network_calls_performed",
        "secret_lookup_added",
        "credential_access_added",
        "credential_value_accessed",
        "provider_token_or_api_key_accessed",
        "provider_configuration_changes_added",
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


def test_v1_g56_outputs_do_not_include_sensitive_markers() -> None:
    harness = _load_lima_harness()
    record = harness.execute_v1_real_provider_sdk_network_egress(
        _egress_request(),
        lambda payload: _provider_sdk_network_result(),
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
