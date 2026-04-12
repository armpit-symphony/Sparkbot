from pathlib import Path

from app.services.guardian import improvement


def _reset_improvement(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SPARKBOT_IMPROVEMENT_LOOP_ENABLED", "true")
    monkeypatch.setenv("SPARKBOT_IMPROVEMENT_DATA_DIR", str(tmp_path / "improvement_loop"))


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
