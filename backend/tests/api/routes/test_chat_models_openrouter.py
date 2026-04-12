import asyncio
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.api.routes.chat import llm
from app.api.routes.chat import model as model_route
from app.services.guardian import token_guardian
from app.core.config import settings
from app.core.db import engine
from app.core.security import create_access_token
from app.models import ChatUser, UserType


def _chat_headers_for_user(user_id: UUID) -> dict[str, str]:
    token = create_access_token(subject=str(user_id), expires_delta=timedelta(minutes=30))
    return {"Authorization": f"Bearer {token}"}


def _ensure_chat_user(username: str) -> UUID:
    with Session(engine) as db:
        user = db.exec(select(ChatUser).where(ChatUser.username == username)).first()
        if user:
            return user.id
        user = ChatUser(username=username, type=UserType.HUMAN, is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id


def test_llm_accepts_dynamic_openrouter_and_ollama_models(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("SPARKBOT_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("SPARKBOT_OPENROUTER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("SPARKBOT_LOCAL_MODEL", "ollama/custom-local:latest")
    monkeypatch.setenv(
        "SPARKBOT_AGENT_MODEL_OVERRIDES_JSON",
        '{"researcher":{"route":"local","model":"ollama/custom-local:latest"}}',
    )

    assert llm.is_valid_model("openrouter/anthropic/claude-3.7-sonnet")
    assert llm.is_valid_model("ollama/custom-local:latest")
    assert llm.model_label("ollama/custom-local:latest") == "Local Ollama · custom-local:latest"
    assert llm.get_model(agent_name="sparkbot") == "openrouter/openai/gpt-4o-mini"
    assert llm.get_model(agent_name="researcher") == "ollama/custom-local:latest"


def test_workstation_stack_agents_lock_to_stack_models(monkeypatch) -> None:
    monkeypatch.setenv("SPARKBOT_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("SPARKBOT_BACKUP_MODEL_1", "ollama/qwen2:latest")
    monkeypatch.setenv("SPARKBOT_BACKUP_MODEL_2", "gpt-4o-mini")
    monkeypatch.setenv("SPARKBOT_HEAVY_HITTER_MODEL", "openrouter/anthropic/claude-3.7-sonnet")

    backup_1 = llm.get_agent_route_context(
        default_model="openrouter/openai/gpt-4o-mini",
        agent_name="workstation_backup_1",
    )
    heavy_hitter = llm.get_agent_route_context(
        default_model="openrouter/openai/gpt-4o-mini",
        agent_name="workstation_heavy_hitter",
    )

    assert backup_1["provider_locked"] is True
    assert backup_1["model"] == "ollama/qwen2:latest"
    assert backup_1["requested_provider"] == "ollama"
    assert backup_1["cross_provider_fallback"] is False

    assert heavy_hitter["provider_locked"] is True
    assert heavy_hitter["model"] == "openrouter/anthropic/claude-3.7-sonnet"
    assert heavy_hitter["requested_provider"] == "openrouter"
    assert heavy_hitter["cross_provider_fallback"] is False


def test_models_config_supports_openrouter_default_with_local_override(
    client: TestClient,
    monkeypatch,
) -> None:
    operator_id = _ensure_chat_user("sparkbot-user")
    headers = _chat_headers_for_user(operator_id)

    monkeypatch.setattr(model_route, "_write_env_updates", lambda updates: None)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.delenv("SPARKBOT_DEFAULT_PROVIDER", raising=False)
    monkeypatch.delenv("SPARKBOT_MODEL", raising=False)
    monkeypatch.delenv("SPARKBOT_OPENROUTER_MODEL", raising=False)
    monkeypatch.delenv("SPARKBOT_LOCAL_MODEL", raising=False)
    monkeypatch.delenv("SPARKBOT_AGENT_MODEL_OVERRIDES_JSON", raising=False)
    monkeypatch.setenv("SPARKBOT_DEFAULT_CROSS_PROVIDER_FALLBACK", "false")

    response = client.post(
        f"{settings.API_V1_STR}/chat/models/config",
        headers=headers,
        json={
            "default_selection": {
                "provider": "openrouter",
                "model": "openrouter/openai/gpt-4o-mini",
            },
            "local_runtime": {
                "default_local_model": "ollama/custom-local:latest",
            },
            "agent_overrides": {
                "researcher": {
                    "route": "local",
                    "model": "ollama/custom-local:latest",
                }
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["default_selection"]["provider"] == "openrouter"
    assert payload["default_selection"]["model"] == "openrouter/openai/gpt-4o-mini"
    assert payload["local_runtime"]["default_local_model"] == "ollama/custom-local:latest"
    assert payload["routing_policy"]["default_provider_authoritative"] is True
    assert payload["routing_policy"]["cross_provider_fallback"] is False
    assert payload["agent_overrides"]["researcher"] == {
        "route": "local",
        "model": "ollama/custom-local:latest",
    }


def test_default_route_candidates_stay_on_selected_provider_when_cross_fallback_off(monkeypatch) -> None:
    monkeypatch.setenv("SPARKBOT_DEFAULT_CROSS_PROVIDER_FALLBACK", "false")
    monkeypatch.setenv("SPARKBOT_BACKUP_MODEL_1", "gpt-4o")
    monkeypatch.setenv("SPARKBOT_BACKUP_MODEL_2", "gpt-4o-mini")
    monkeypatch.setenv("SPARKBOT_HEAVY_HITTER_MODEL", "gpt-5-mini")
    monkeypatch.setenv("SPARKBOT_OPENROUTER_MODEL", "openrouter/openrouter/free")

    route_context = {
        "route": "default",
        "provider_locked": False,
        "requested_provider": "openrouter",
        "model": "openrouter/openrouter/free",
        "cross_provider_fallback": False,
    }

    assert llm._candidate_models(
        "openrouter/openrouter/free",
        route_context=route_context,
    ) == ["openrouter/openrouter/free"]


def test_default_route_candidates_can_cross_provider_when_explicitly_enabled(monkeypatch) -> None:
    monkeypatch.setenv("SPARKBOT_DEFAULT_CROSS_PROVIDER_FALLBACK", "true")
    monkeypatch.setenv("SPARKBOT_BACKUP_MODEL_1", "gpt-4o")
    monkeypatch.setenv("SPARKBOT_BACKUP_MODEL_2", "gpt-4o-mini")
    monkeypatch.setenv("SPARKBOT_HEAVY_HITTER_MODEL", "gpt-5-mini")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")

    route_context = {
        "route": "default",
        "provider_locked": False,
        "requested_provider": "openrouter",
        "model": "openrouter/missing-default",
        "cross_provider_fallback": True,
    }

    assert llm._candidate_models(
        "openrouter/missing-default",
        route_context=route_context,
    ) == ["gpt-4o", "gpt-4o-mini", "gpt-5-mini"]


def test_locked_local_candidates_do_not_cross_provider(monkeypatch) -> None:
    monkeypatch.setenv("SPARKBOT_BACKUP_MODEL_1", "gpt-4o")
    monkeypatch.setenv("SPARKBOT_BACKUP_MODEL_2", "gpt-4o-mini")
    monkeypatch.setenv("SPARKBOT_HEAVY_HITTER_MODEL", "gpt-5-mini")

    route_context = {
        "route": "local",
        "provider_locked": True,
        "requested_provider": "ollama",
        "model": "ollama/custom-local:latest",
    }

    assert llm._candidate_models(
        "ollama/custom-local:latest",
        route_context=route_context,
    ) == ["ollama/custom-local:latest"]


def test_locked_local_completion_returns_clear_error_without_cloud_fallback(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_acompletion(*, model: str, **kwargs):
        calls.append(model)
        raise RuntimeError("dial tcp 127.0.0.1:11434: connection refused")

    monkeypatch.setenv("SPARKBOT_BACKUP_MODEL_1", "gpt-4o")
    monkeypatch.setenv("SPARKBOT_BACKUP_MODEL_2", "gpt-4o-mini")
    monkeypatch.setenv("SPARKBOT_HEAVY_HITTER_MODEL", "gpt-5-mini")
    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)

    route_context = {
        "route": "local",
        "provider_locked": True,
        "requested_provider": "ollama",
        "model": "ollama/custom-local:latest",
    }

    with pytest.raises(RuntimeError, match="Local Ollama is forced for this agent"):
        asyncio.run(
            llm._acompletion_with_fallback(
                model="ollama/custom-local:latest",
                route_context=route_context,
                messages=[{"role": "user", "content": "test"}],
                stream=False,
            )
        )

    assert calls == ["ollama/custom-local:latest"]


def test_locked_provider_retries_without_tools_before_failing(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    class _FakeMessage:
        tool_calls = None
        content = "MINIMAX_OK"

        def model_dump(self, exclude_none: bool = True):
            return {"role": "assistant", "content": "MINIMAX_OK"}

    class _FakeResponse:
        choices = [SimpleNamespace(finish_reason="stop", message=_FakeMessage())]

    async def fake_acompletion(*, model: str, **kwargs):
        calls.append((model, "tools" in kwargs))
        if "tools" in kwargs:
            raise RuntimeError('bad_request_error: invalid param "tools"')
        return _FakeResponse()

    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)

    route_context = {
        "route": "default",
        "provider_locked": True,
        "requested_provider": "minimax",
        "model": "minimax/MiniMax-M2.5",
        "cross_provider_fallback": False,
    }

    chosen_model, response = asyncio.run(
        llm._acompletion_with_fallback(
            model="minimax/MiniMax-M2.5",
            route_context=route_context,
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "noop", "parameters": {"type": "object"}}}],
            tool_choice="auto",
            stream=False,
        )
    )

    assert chosen_model == "minimax/MiniMax-M2.5"
    assert response.choices[0].message.content == "MINIMAX_OK"
    assert calls == [
        ("minimax/MiniMax-M2.5", True),
        ("minimax/MiniMax-M2.5", False),
    ]


def test_stream_chat_with_tools_keeps_forced_local_off_token_guardian(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    class _FakeMessage:
        tool_calls = None
        content = "LOCAL_ONLY"

        def model_dump(self, exclude_none: bool = True):
            return {"role": "assistant", "content": "LOCAL_ONLY"}

    class _FakeResponse:
        choices = [SimpleNamespace(finish_reason="stop", message=_FakeMessage())]

    class _FakeStream:
        def __aiter__(self):
            self._seen = False
            return self

        async def __anext__(self):
            if self._seen:
                raise StopAsyncIteration
            self._seen = True
            return SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="LOCAL_ONLY"))]
            )

    async def fake_acompletion(*, model: str, stream: bool = False, **kwargs):
        calls.append((model, stream))
        return _FakeStream() if stream else _FakeResponse()

    async def fake_ollama_status():
        return {
            "reachable": True,
            "base_url": "http://localhost:11434",
            "models": ["custom-local:latest"],
            "model_ids": ["ollama/custom-local:latest"],
            "models_available": True,
        }

    def fail_route_model(*args, **kwargs):
        raise AssertionError("route_model should not run for forced-local routes")

    monkeypatch.setenv("SPARKBOT_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("SPARKBOT_LOCAL_MODEL", "ollama/custom-local:latest")
    monkeypatch.setenv(
        "SPARKBOT_AGENT_MODEL_OVERRIDES_JSON",
        '{"researcher":{"route":"local","model":"ollama/custom-local:latest"}}',
    )
    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(llm, "get_ollama_status", fake_ollama_status)
    monkeypatch.setattr(token_guardian, "route_model", fail_route_model)

    async def _collect_events():
        events = []
        async for event in llm.stream_chat_with_tools(
            [{"role": "user", "content": "Reply with LOCAL_ONLY"}],
            user_id="test-user",
            agent_name="researcher",
        ):
            events.append(event)
        return events

    events = asyncio.run(_collect_events())

    assert calls == [
        ("ollama/custom-local:latest", False),
    ]


def test_stream_chat_with_tools_retries_empty_plain_text_without_tools(monkeypatch) -> None:
    calls: list[tuple[str, bool, bool]] = []

    class _EmptyMessage:
        tool_calls = None
        content = None

        def model_dump(self, exclude_none: bool = True):
            return {"role": "assistant", "content": None}

    class _TextMessage:
        tool_calls = None
        content = "QWEN_LOCAL_OK"

        def model_dump(self, exclude_none: bool = True):
            return {"role": "assistant", "content": "QWEN_LOCAL_OK"}

    class _FakeResponse:
        def __init__(self, message) -> None:
            self.choices = [SimpleNamespace(finish_reason="stop", message=message)]

    async def fake_acompletion(*, model: str, stream: bool = False, **kwargs):
        calls.append((model, stream, "tools" in kwargs))
        if "tools" in kwargs:
            return _FakeResponse(_EmptyMessage())
        return _FakeResponse(_TextMessage())

    def fake_route_model(query, current_model, *, available_models=None):
        return current_model, {
            "classification": "general",
            "selected_model": current_model,
            "fallback_triggered": False,
            "fallback_reason": None,
        }

    monkeypatch.setenv("SPARKBOT_MODEL", "ollama/qwen2:latest")
    monkeypatch.setenv("SPARKBOT_DEFAULT_PROVIDER", "ollama")
    monkeypatch.setenv("SPARKBOT_LOCAL_MODEL", "ollama/qwen2:latest")
    monkeypatch.setenv("SPARKBOT_DEFAULT_CROSS_PROVIDER_FALLBACK", "false")
    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(token_guardian, "route_model", fake_route_model)

    async def _collect_events():
        events = []
        async for event in llm.stream_chat_with_tools(
            [{"role": "user", "content": "Reply with QWEN_LOCAL_OK"}],
            user_id="test-user",
        ):
            events.append(event)
        return events

    events = asyncio.run(_collect_events())

    assert calls == [
        ("ollama/qwen2:latest", False, True),
        ("ollama/qwen2:latest", False, False),
    ]
    assert [event["token"] for event in events if event.get("type") == "token"] == ["QWEN_LOCAL_OK"]
    assert any(event.get("type") == "routing" for event in events)


def test_stream_chat_with_tools_reads_structured_local_content(monkeypatch) -> None:
    calls: list[tuple[str, bool, bool]] = []

    class _StructuredMessage:
        tool_calls = None
        content = [{"type": "text", "text": "QWEN_STRUCTURED_OK"}]

        def model_dump(self, exclude_none: bool = True):
            return {"role": "assistant", "content": [{"type": "text", "text": "QWEN_STRUCTURED_OK"}]}

    class _FakeResponse:
        choices = [SimpleNamespace(finish_reason="stop", message=_StructuredMessage())]

    async def fake_acompletion(*, model: str, stream: bool = False, **kwargs):
        calls.append((model, stream, "tools" in kwargs))
        return _FakeResponse()

    def fake_route_model(query, current_model, *, available_models=None):
        return current_model, {
            "classification": "general",
            "selected_model": current_model,
            "fallback_triggered": False,
            "fallback_reason": None,
        }

    monkeypatch.setenv("SPARKBOT_MODEL", "ollama/qwen2:latest")
    monkeypatch.setenv("SPARKBOT_DEFAULT_PROVIDER", "ollama")
    monkeypatch.setenv("SPARKBOT_LOCAL_MODEL", "ollama/qwen2:latest")
    monkeypatch.setenv("SPARKBOT_DEFAULT_CROSS_PROVIDER_FALLBACK", "false")
    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(token_guardian, "route_model", fake_route_model)

    async def _collect_events():
        events = []
        async for event in llm.stream_chat_with_tools(
            [{"role": "user", "content": "Reply with QWEN_STRUCTURED_OK"}],
            user_id="test-user",
        ):
            events.append(event)
        return events

    events = asyncio.run(_collect_events())

    assert calls == [
        ("ollama/qwen2:latest", False, True),
    ]
    assert [event["token"] for event in events if event.get("type") == "token"] == ["QWEN_STRUCTURED_OK"]


def test_stream_chat_falls_back_to_non_streaming_when_structured_reply(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    class _StructuredMessage:
        tool_calls = None
        content = [{"type": "text", "text": "OLLAMA_STRUCTURED_REPLY"}]

        def model_dump(self, exclude_none: bool = True):
            return {"role": "assistant", "content": [{"type": "text", "text": "OLLAMA_STRUCTURED_REPLY"}]}

    class _FakeResponse:
        choices = [SimpleNamespace(finish_reason="stop", message=_StructuredMessage())]

    class _EmptyStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    async def fake_acompletion(*, model: str, stream: bool = False, **kwargs):
        calls.append((model, stream))
        return _EmptyStream() if stream else _FakeResponse()

    async def fake_ollama_status():
        return {
            "reachable": True,
            "base_url": "http://localhost:11434",
            "models": ["qwen2:latest"],
            "model_ids": ["ollama/qwen2:latest"],
            "models_available": True,
        }

    monkeypatch.setenv("SPARKBOT_MODEL", "ollama/qwen2:latest")
    monkeypatch.setenv("SPARKBOT_DEFAULT_PROVIDER", "ollama")
    monkeypatch.setenv("SPARKBOT_LOCAL_MODEL", "ollama/qwen2:latest")
    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(llm, "get_ollama_status", fake_ollama_status)

    async def _collect_tokens():
        tokens: list[str] = []
        async for token in llm.stream_chat(
            [{"role": "user", "content": "Reply with OLLAMA_STRUCTURED_REPLY"}],
            user_id="test-user",
        ):
            tokens.append(token)
        return tokens

    tokens = asyncio.run(_collect_tokens())

    assert tokens == ["OLLAMA_STRUCTURED_REPLY"]
    assert calls == [
        ("ollama/qwen2:latest", True),
        ("ollama/qwen2:latest", False),
    ]


def test_stream_chat_with_tools_keeps_default_openrouter_on_openrouter_provider(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []
    route_model_available_models: list[set[str]] = []

    class _FakeMessage:
        tool_calls = None

        def model_dump(self, exclude_none: bool = True):
            return {"role": "assistant", "content": "OPENROUTER_DEFAULT"}

    class _FakeResponse:
        choices = [SimpleNamespace(finish_reason="stop", message=_FakeMessage())]

    class _FakeStream:
        def __aiter__(self):
            self._seen = False
            return self

        async def __anext__(self):
            if self._seen:
                raise StopAsyncIteration
            self._seen = True
            return SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="OPENROUTER_DEFAULT"))]
            )

    async def fake_acompletion(*, model: str, stream: bool = False, **kwargs):
        calls.append((model, stream))
        return _FakeStream() if stream else _FakeResponse()

    def fake_route_model(query, current_model, *, available_models=None):
        route_model_available_models.append(set(available_models or []))
        return current_model, {
            "classification": "general",
            "selected_model": current_model,
            "fallback_triggered": False,
            "fallback_reason": None,
        }

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("SPARKBOT_MODEL", "openrouter/openrouter/free")
    monkeypatch.setenv("SPARKBOT_DEFAULT_PROVIDER", "openrouter")
    monkeypatch.setenv("SPARKBOT_DEFAULT_CROSS_PROVIDER_FALLBACK", "false")
    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(token_guardian, "route_model", fake_route_model)

    async def _collect_events():
        events = []
        async for event in llm.stream_chat_with_tools(
            [{"role": "user", "content": "Reply with OPENROUTER_DEFAULT"}],
            user_id="test-user",
        ):
            events.append(event)
        return events

    events = asyncio.run(_collect_events())

    assert calls == [
        ("openrouter/openrouter/free", False),
    ]
    assert route_model_available_models
    assert route_model_available_models[0] == {"openrouter/openrouter/free", "openrouter/openai/gpt-4o-mini"}
    routing_event = next(event for event in events if event.get("type") == "routing")
    assert routing_event["payload"]["route"] == "default"
    assert routing_event["payload"]["requested_provider"] == "openrouter"
    assert routing_event["payload"]["applied_provider"] == "openrouter"
    assert routing_event["payload"]["cross_provider_fallback"] is False


def test_stream_chat_with_tools_keeps_default_local_on_ollama_provider(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []
    route_model_available_models: list[set[str]] = []

    class _FakeMessage:
        tool_calls = None

        def model_dump(self, exclude_none: bool = True):
            return {"role": "assistant", "content": "LOCAL_DEFAULT"}

    class _FakeResponse:
        choices = [SimpleNamespace(finish_reason="stop", message=_FakeMessage())]

    class _FakeStream:
        def __aiter__(self):
            self._seen = False
            return self

        async def __anext__(self):
            if self._seen:
                raise StopAsyncIteration
            self._seen = True
            return SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="LOCAL_DEFAULT"))]
            )

    async def fake_acompletion(*, model: str, stream: bool = False, **kwargs):
        calls.append((model, stream))
        return _FakeStream() if stream else _FakeResponse()

    async def fake_ollama_status():
        return {
            "reachable": True,
            "base_url": "http://localhost:11434",
            "models": ["custom-local:latest"],
            "model_ids": ["ollama/custom-local:latest"],
            "models_available": True,
        }

    def fake_route_model(query, current_model, *, available_models=None):
        route_model_available_models.append(set(available_models or []))
        return current_model, {
            "classification": "general",
            "selected_model": current_model,
            "fallback_triggered": False,
            "fallback_reason": None,
        }

    monkeypatch.setenv("SPARKBOT_MODEL", "ollama/custom-local:latest")
    monkeypatch.setenv("SPARKBOT_DEFAULT_PROVIDER", "ollama")
    monkeypatch.setenv("SPARKBOT_LOCAL_MODEL", "ollama/custom-local:latest")
    monkeypatch.setenv("SPARKBOT_DEFAULT_CROSS_PROVIDER_FALLBACK", "false")
    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(llm, "get_ollama_status", fake_ollama_status)
    monkeypatch.setattr(token_guardian, "route_model", fake_route_model)

    async def _collect_events():
        events = []
        async for event in llm.stream_chat_with_tools(
            [{"role": "user", "content": "Reply with LOCAL_DEFAULT"}],
            user_id="test-user",
        ):
            events.append(event)
        return events

    events = asyncio.run(_collect_events())

    assert calls == [
        ("ollama/custom-local:latest", False),
    ]
    assert route_model_available_models
    assert "ollama/custom-local:latest" in route_model_available_models[0]
    assert all(model.startswith("ollama/") for model in route_model_available_models[0])
    routing_event = next(event for event in events if event.get("type") == "routing")
    assert routing_event["payload"]["route"] == "default"
    assert routing_event["payload"]["requested_provider"] == "ollama"
    assert routing_event["payload"]["applied_provider"] == "ollama"
    assert routing_event["payload"]["cross_provider_fallback"] is False


def test_stream_chat_falls_back_to_non_streaming_when_stream_is_empty(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    class _FakeMessage:
        tool_calls = None
        content = "OLLAMA_VISIBLE_REPLY"

        def model_dump(self, exclude_none: bool = True):
            return {"role": "assistant", "content": "OLLAMA_VISIBLE_REPLY"}

    class _FakeResponse:
        choices = [SimpleNamespace(finish_reason="stop", message=_FakeMessage())]

    class _EmptyStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    async def fake_acompletion(*, model: str, stream: bool = False, **kwargs):
        calls.append((model, stream))
        return _EmptyStream() if stream else _FakeResponse()

    async def fake_ollama_status():
        return {
            "reachable": True,
            "base_url": "http://localhost:11434",
            "models": ["qwen2:latest"],
            "model_ids": ["ollama/qwen2:latest"],
            "models_available": True,
        }

    monkeypatch.setenv("SPARKBOT_MODEL", "ollama/qwen2:latest")
    monkeypatch.setenv("SPARKBOT_DEFAULT_PROVIDER", "ollama")
    monkeypatch.setenv("SPARKBOT_LOCAL_MODEL", "ollama/qwen2:latest")
    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(llm, "get_ollama_status", fake_ollama_status)

    async def _collect_tokens():
        tokens: list[str] = []
        async for token in llm.stream_chat(
            [{"role": "user", "content": "Reply with OLLAMA_VISIBLE_REPLY"}],
            user_id="test-user",
        ):
            tokens.append(token)
        return tokens

    tokens = asyncio.run(_collect_tokens())

    assert tokens == ["OLLAMA_VISIBLE_REPLY"]
    assert calls == [
        ("ollama/qwen2:latest", True),
        ("ollama/qwen2:latest", False),
    ]


def test_models_config_reports_live_ollama_status_separately(
    client: TestClient,
    monkeypatch,
) -> None:
    operator_id = _ensure_chat_user("sparkbot-user")
    headers = _chat_headers_for_user(operator_id)

    async def fake_ollama_status():
        return {
            "reachable": True,
            "base_url": "http://localhost:11434",
            "models": ["llama3.2:1b"],
            "model_ids": ["ollama/llama3.2:1b"],
            "models_available": True,
        }

    monkeypatch.setenv("SPARKBOT_LOCAL_MODEL", "ollama/llama3.2:1b")
    monkeypatch.setenv(
        "SPARKBOT_AGENT_MODEL_OVERRIDES_JSON",
        '{"researcher":{"route":"local","model":"ollama/llama3.2:1b"}}',
    )
    monkeypatch.setattr(model_route, "_write_env_updates", lambda updates: None)
    monkeypatch.setattr(model_route, "get_ollama_status", fake_ollama_status)

    response = client.get(
        f"{settings.API_V1_STR}/chat/models/config",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    ollama_provider = next(
        provider for provider in payload["providers"] if provider["id"] == "ollama"
    )
    assert ollama_provider["configured"] is True
    assert ollama_provider["reachable"] is True
    assert ollama_provider["models_available"] is True
    assert ollama_provider["available_models"] == ["ollama/llama3.2:1b"]
    assert payload["ollama_status"]["reachable"] is True
