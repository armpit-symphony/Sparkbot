from app.services.guardian import token_guardian


def test_token_guardian_shadow_route_returns_decision(monkeypatch) -> None:
    monkeypatch.setenv("SPARKBOT_TOKEN_GUARDIAN_SHADOW_ENABLED", "true")
    token_guardian._pipeline.cache_clear()
    token_guardian._monitor.cache_clear()

    result = token_guardian.run_shadow_route(
        "Write a Python function to parse CSV rows.",
        "gpt-4o-mini",
    )

    assert result is not None
    assert result["classification"] in {"coding", "creative", "general", "reasoning", "data_analysis", "simple_qa"}
    assert result["current_model"] == "gpt-4o-mini"
    assert "selected_model" in result
    assert result["estimated_tokens"] > 0
    assert "would_switch_models" in result


def test_token_guardian_shadow_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("SPARKBOT_TOKEN_GUARDIAN_SHADOW_ENABLED", "false")
    token_guardian._pipeline.cache_clear()
    token_guardian._monitor.cache_clear()

    result = token_guardian.run_shadow_route("What time is it?", "gpt-4o-mini")

    assert result is None
