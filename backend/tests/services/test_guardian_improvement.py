import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.guardian import improvement


def _reset_improvement(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SPARKBOT_IMPROVEMENT_LOOP_ENABLED", "true")
    monkeypatch.setenv("SPARKBOT_IMPROVEMENT_DATA_DIR", str(tmp_path / "improvement_loop"))


def test_proposal_status_approve_and_reject(monkeypatch, tmp_path: Path) -> None:
    _reset_improvement(monkeypatch, tmp_path)

    proposal = improvement.propose_improvement(
        user_id="user-1",
        room_id="room-1",
        summary="Memoize provider readiness check to cut Command Center latency",
        evidence="Observed 3 redundant provider scans in last 5 minutes",
        suggested_change="Cache provider readiness for 30 seconds in get_provider_readiness",
        risk="low",
    )
    assert proposal is not None
    proposal_id = proposal["id"]

    rows = improvement.list_improvement_proposals(status="proposed", limit=10)
    assert any(item["id"] == proposal_id for item in rows)

    updated = improvement.update_proposal_status(
        proposal_id=proposal_id, new_status="approved", operator_id="op-1"
    )
    assert updated is not None
    assert updated["status"] == "approved"
    assert updated["approved_by"] == "op-1"
    assert "approved_at" in updated

    proposed = improvement.list_improvement_proposals(status="proposed", limit=10)
    assert all(item["id"] != proposal_id for item in proposed)
    approved = improvement.list_improvement_proposals(status="approved", limit=10)
    assert any(item["id"] == proposal_id for item in approved)

    rejected_proposal = improvement.propose_improvement(
        user_id="user-1",
        room_id="room-1",
        summary="Add a redundant retry layer to the chat router",
    )
    assert rejected_proposal is not None
    rejected_id = rejected_proposal["id"]

    after_reject = improvement.update_proposal_status(
        proposal_id=rejected_id, new_status="rejected", operator_id="op-1"
    )
    assert after_reject is not None
    assert after_reject["status"] == "rejected"


def test_update_proposal_status_invalid_inputs(monkeypatch, tmp_path: Path) -> None:
    _reset_improvement(monkeypatch, tmp_path)
    proposal = improvement.propose_improvement(user_id="u", room_id="r", summary="x")
    assert proposal is not None

    assert improvement.update_proposal_status(proposal_id="", new_status="approved") is None
    assert improvement.update_proposal_status(proposal_id=proposal["id"], new_status="garbage") is None
    assert improvement.update_proposal_status(proposal_id="does-not-exist", new_status="approved") is None


def test_guardian_data_dir_umbrella_routes_improvement_loop(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SPARKBOT_IMPROVEMENT_LOOP_ENABLED", "true")
    monkeypatch.delenv("SPARKBOT_IMPROVEMENT_DATA_DIR", raising=False)
    monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(tmp_path / "guardian-data"))

    proposal = improvement.propose_improvement(user_id="u", room_id="r", summary="x")
    assert proposal is not None
    expected = tmp_path / "guardian-data" / "improvement_loop" / "outcomes.json"
    assert expected.exists()


def test_per_feature_improvement_dir_wins_over_umbrella(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SPARKBOT_IMPROVEMENT_LOOP_ENABLED", "true")
    monkeypatch.setenv("SPARKBOT_IMPROVEMENT_DATA_DIR", str(tmp_path / "per_feature"))
    monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(tmp_path / "umbrella"))

    improvement.propose_improvement(user_id="u", room_id="r", summary="x")
    assert (tmp_path / "per_feature" / "outcomes.json").exists()
    assert not (tmp_path / "umbrella" / "improvement_loop" / "outcomes.json").exists()


def test_improvement_records_outcomes_and_promotes_patterns(monkeypatch, tmp_path: Path) -> None:
    _reset_improvement(monkeypatch, tmp_path)

    payload = {
        "classification": "coding",
        "applied_model": "ollama/qwen2:latest",
        "fallback_triggered": False,
    }
    result = improvement.record_outcome(
        user_id="user-1",
        room_id="room-1",
        route_payload=payload,
        output_text="Built a clean implementation and verified the path.",
        tool_usage_counts={"web_search": 1, "github_get_pr": 1},
        success=True,
        agent_name="researcher",
    )

    assert result is not None
    context = improvement.build_promoted_workflow_context(
        user_id="user-1",
        room_id="room-1",
        query="Help with coding work",
    )

    assert "Promoted Workflow Patterns" in context
    assert "ollama/qwen2:latest" in context
    assert "web search" in context.lower()
    assert "@researcher" in context


def test_improvement_prefers_higher_scoring_model(monkeypatch, tmp_path: Path) -> None:
    _reset_improvement(monkeypatch, tmp_path)

    preferred_payload = {
        "classification": "coding",
        "applied_model": "claude-sonnet-4-5",
        "fallback_triggered": False,
    }
    baseline_payload = {
        "classification": "coding",
        "applied_model": "gpt-4o-mini",
        "fallback_triggered": True,
    }

    for _ in range(3):
        improvement.record_outcome(
            user_id="user-1",
            room_id="room-1",
            route_payload=preferred_payload,
            output_text="Implemented the parser with tests and a migration plan.",
            tool_usage_counts={"github_get_pr": 1},
            success=True,
            agent_name="sparkbot",
        )

    for _ in range(2):
        improvement.record_outcome(
            user_id="user-1",
            room_id="room-1",
            route_payload=baseline_payload,
            output_text="ok",
            tool_usage_counts={},
            success=True,
            agent_name="sparkbot",
        )

    chosen, reason, ranking = improvement.choose_best_model(
        classification="coding",
        current_model="gpt-4o-mini",
        candidates=["gpt-4o-mini", "claude-sonnet-4-5"],
    )

    assert chosen == "claude-sonnet-4-5"
    assert reason is not None
    assert ranking[0]["model"] == "claude-sonnet-4-5"


def test_improvement_model_routing_uses_sliding_window(monkeypatch, tmp_path: Path) -> None:
    _reset_improvement(monkeypatch, tmp_path)
    old = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    store = {
        "model_outcomes": {
            "coding": {
                "stale-model": {
                    "recent_outcomes": [
                        {"created_at": old, "score": 4.0, "success": True, "tool_usage_counts": {}, "agent_name": ""}
                        for _ in range(5)
                    ]
                }
            }
        },
        "workflow_patterns": {},
        "improvement_proposals": [],
    }
    path = improvement._store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store), encoding="utf-8")

    improvement.record_outcome(
        user_id="user-1",
        room_id="room-1",
        route_payload={"classification": "coding", "applied_model": "fresh-model"},
        output_text="Implemented with tests.",
        tool_usage_counts={},
        success=True,
    )
    chosen, _, ranking = improvement.choose_best_model(
        classification="coding",
        current_model="fresh-model",
        candidates=["fresh-model", "stale-model"],
    )

    stale = next(item for item in ranking if item["model"] == "stale-model")
    assert chosen == "fresh-model"
    assert stale["attempts"] == 0


def test_improvement_proposals_are_recorded_for_approval(monkeypatch, tmp_path: Path) -> None:
    _reset_improvement(monkeypatch, tmp_path)

    proposal = improvement.propose_improvement(
        user_id="user-1",
        room_id="room-1",
        summary="Add a verifier for deployment diagnostics.",
        evidence="Task Guardian reported low-confidence deployment output.",
        suggested_change="Add a deployment verifier profile and tests before trusting the workflow.",
        risk="high",
        source="test",
    )

    assert proposal is not None
    assert proposal["approval_required"] is True
    assert proposal["status"] == "proposed"
    assert proposal["risk"] == "high"

    proposals = improvement.list_improvement_proposals(user_id="user-1", room_id="room-1")
    assert proposals[0]["id"] == proposal["id"]
    assert "deployment verifier" in proposals[0]["suggested_change"]
