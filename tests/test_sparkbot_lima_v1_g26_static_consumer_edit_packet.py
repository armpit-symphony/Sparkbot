"""Static checks for the Sparkbot LIMA V1-G26 consumer edit packet."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "sparkbot_lima_v1_g26_static_consumer_edit_packet.json"
)


def _load_fixture() -> dict[str, Any]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(fixture, dict)
    return fixture


def test_v1_g26_packet_files_exist() -> None:
    fixture = _load_fixture()

    assert fixture["packet_id"] == "sparkbot_lima_v1_g26_static_consumer_edit_packet"
    assert fixture["proof_gap_id"] == "V1-G26"
    assert fixture["api_status"] == "CANDIDATE_ONLY"
    assert fixture["consumer_repo"] == "Sparkbot"
    assert fixture["proof_branch"] == "v1-g26-first-consumer-repository-edit"

    for relative_path in fixture["proof_packet_files"]:
        assert (REPO_ROOT / relative_path).exists(), relative_path


def test_v1_g26_approved_scope_is_static_docs_tests_fixtures_only() -> None:
    fixture = _load_fixture()

    assert fixture["approved_file_scope"] == [
        "docs/proof_packets/SPARKBOT_LIMA_V1_G26_STATIC_CONSUMER_EDIT_PACKET.md",
        "tests/fixtures/sparkbot_lima_v1_g26_static_consumer_edit_packet.json",
        "tests/test_sparkbot_lima_v1_g26_static_consumer_edit_packet.py",
    ]
    assert fixture["static_consumer_edit_added"] is True
    assert fixture["docs_tests_fixtures_only"] is True
    assert fixture["runtime_source_files_changed"] is False


def test_v1_g26_links_required_lima_evidence() -> None:
    refs = _load_fixture()["linked_lima_evidence_refs"]

    assert refs["proof_packet_ref"] == "proof-packet:v1-g18:sparkbot"
    assert refs["compatibility_packet_ref"] == "compatibility:v1-g21:sparkbot"
    assert refs["frozen_api_packet_ref"] == "api-freeze:v1-g22"
    assert refs["v1_g23_import_plan_ref"] == "import-plan:v1-g23"
    assert refs["v1_g24_import_plan_id"] == "import-plan:v1-g24:sparkbot:001"
    assert refs["v1_g25_patch_preview_id"] == "patch-preview:v1-g25:sparkbot:001"


def test_v1_g26_runtime_and_external_boundaries_remain_false() -> None:
    fixture = _load_fixture()

    for key in (
        "sparkbot_runtime_behavior_added",
        "lima_runtime_imports_added",
        "lima_runtime_calls_added",
        "consumer_integration_added",
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

    assert fixture["proof_not_authority"] is True


def test_v1_g26_required_confirmations_are_true() -> None:
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


def test_v1_g26_packet_docs_contain_boundary_language() -> None:
    text = (
        REPO_ROOT
        / "docs"
        / "proof_packets"
        / "SPARKBOT_LIMA_V1_G26_STATIC_CONSUMER_EDIT_PACKET.md"
    ).read_text(encoding="utf-8")

    assert "static docs/tests/fixtures proof packet only" in text
    assert "No Sparkbot runtime/source file" in text
    assert "LIMA runtime imported by Sparkbot: no" in text
    assert "Product readiness claimed: no" in text


def test_v1_g26_fixture_does_not_include_raw_patch_or_sensitive_markers() -> None:
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
