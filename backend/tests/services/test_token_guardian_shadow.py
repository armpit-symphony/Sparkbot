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


def test_token_guardian_live_routes_to_configured_model(monkeypatch) -> None:
    monkeypatch.setenv("SPARKBOT_TOKEN_GUARDIAN_MODE", "live")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")

    recorded: list[tuple[int, str, str]] = []

    class _FakeMonitor:
        def record_usage(self, tokens: int, model: str, action: str = "unknown", is_output: bool = False):
            recorded.append((tokens, model, action))

        def get_stats(self):
            return {}

    monkeypatch.setattr(token_guardian, "_monitor", lambda: _FakeMonitor())
    monkeypatch.setattr(
        token_guardian,
        "_build_route_payload",
        lambda query, current_model, mode: {
            "mode": mode,
            "classification": "coding",
            "selected_model": "claude-sonnet-4-5",
            "current_model": current_model,
            "estimated_tokens": 42,
            "estimated_cost": 0.0001,
            "estimated_current_cost": 0.0002,
            "estimated_savings": 0.0001,
            "would_switch_models": True,
        },
    )

    chosen, payload = token_guardian.route_model(
        "Write a parser",
        "gpt-4o-mini",
        available_models={"gpt-4o-mini", "claude-sonnet-4-5"},
    )

    assert chosen == "claude-sonnet-4-5"
    assert payload is not None
    assert payload["live_routed"] is True
    assert payload["live_ready"] is True
    assert payload["fallback_reason"] in {None, ""}
    assert recorded == [(42, "claude-sonnet-4-5", "token_guardian_live")]


def test_token_guardian_live_falls_back_to_current_when_selected_model_is_not_usable(monkeypatch) -> None:
    monkeypatch.setenv("SPARKBOT_TOKEN_GUARDIAN_MODE", "live")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SPARKBOT_TOKEN_GUARDIAN_LIVE_MODELS", raising=False)

    recorded: list[tuple[int, str, str]] = []

    class _FakeMonitor:
        def record_usage(self, tokens: int, model: str, action: str = "unknown", is_output: bool = False):
            recorded.append((tokens, model, action))

        def get_stats(self):
            return {}

    monkeypatch.setattr(token_guardian, "_monitor", lambda: _FakeMonitor())
    monkeypatch.setattr(
        token_guardian,
        "_build_route_payload",
        lambda query, current_model, mode: {
            "mode": mode,
            "classification": "coding",
            "selected_model": "claude-sonnet-4-5",
            "current_model": current_model,
            "estimated_tokens": 21,
            "estimated_cost": 0.0003,
            "estimated_current_cost": 0.0001,
            "estimated_savings": 0.0,
            "would_switch_models": True,
        },
    )

    chosen, payload = token_guardian.route_model(
        "Write a parser",
        "gpt-4o-mini",
        available_models={"gpt-4o-mini", "claude-sonnet-4-5"},
    )

    assert chosen == "gpt-4o-mini"
    assert payload is not None
    assert payload["live_routed"] is False
    assert "unavailable" in str(payload["fallback_reason"]).lower()
    assert recorded == [(21, "gpt-4o-mini", "token_guardian_live")]


def test_token_guardian_live_respects_allowlist(monkeypatch) -> None:
    monkeypatch.setenv("SPARKBOT_TOKEN_GUARDIAN_MODE", "live")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    monkeypatch.setenv("SPARKBOT_TOKEN_GUARDIAN_LIVE_MODELS", "gpt-4o-mini")

    class _FakeMonitor:
        def record_usage(self, tokens: int, model: str, action: str = "unknown", is_output: bool = False):
            return None

        def get_stats(self):
            return {}

    monkeypatch.setattr(token_guardian, "_monitor", lambda: _FakeMonitor())
    monkeypatch.setattr(
        token_guardian,
        "_build_route_payload",
        lambda query, current_model, mode: {
            "mode": mode,
            "classification": "coding",
            "selected_model": "claude-sonnet-4-5",
            "current_model": current_model,
            "estimated_tokens": 9,
            "estimated_cost": 0.0001,
            "estimated_current_cost": 0.0001,
            "estimated_savings": 0.0,
            "would_switch_models": True,
        },
    )

    chosen, payload = token_guardian.route_model(
        "Write a parser",
        "gpt-4o-mini",
        available_models={"gpt-4o-mini", "claude-sonnet-4-5"},
    )

    assert chosen == "gpt-4o-mini"
    assert payload is not None
    assert payload["selected_model_allowed"] is False
    assert payload["allowed_live_models"] == ["gpt-4o-mini"]
