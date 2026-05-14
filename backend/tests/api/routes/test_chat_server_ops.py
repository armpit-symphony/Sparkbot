import asyncio
import sys

import pytest

from app.api.routes.chat import tools


def test_server_manage_service_rejects_unapproved_service_when_security_on(monkeypatch) -> None:
    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "true")
    monkeypatch.setattr(tools, "_ALLOWED_LOCAL_SERVICES", {"sparkbot-v2"})

    result = asyncio.run(tools._server_manage_service("nginx", "restart"))

    assert "Service is not allowed" in result


def test_server_manage_service_allows_safe_service_names_when_security_off(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_run_exec(argv, timeout):
        captured["argv"] = argv
        captured["timeout"] = timeout
        return 0, "ok"

    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "false")
    monkeypatch.setattr(tools, "_ALLOWED_LOCAL_SERVICES", {"sparkbot-v2"})
    monkeypatch.setattr(tools, "_run_exec", fake_run_exec)

    result = asyncio.run(tools._server_manage_service("kalshi-bot-1", "restart"))

    assert "SUCCESS" in result
    assert "kalshi-bot-1" in " ".join(captured["argv"])


def test_ssh_read_command_requires_configured_hosts_when_security_on(monkeypatch) -> None:
    monkeypatch.setenv("SPARKBOT_GUARDIAN_POLICY_ENABLED", "true")
    monkeypatch.setattr(tools, "_ALLOWED_SSH_HOSTS", set())

    result = asyncio.run(tools._ssh_read_command("office-pc", "system_overview"))

    assert "SSH access is not configured" in result


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only journalctl path; Windows uses Get-EventLog")
def test_server_read_command_service_logs_uses_allowed_service_linux(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_run_profile_commands(commands, timeout):
        captured["commands"] = commands
        captured["timeout"] = timeout
        return "ok"

    monkeypatch.setattr(tools, "_ALLOWED_LOCAL_SERVICES", {"sparkbot-v2"})
    monkeypatch.setattr(tools, "_SERVER_COMMAND_TIMEOUT_SECONDS", 17)
    monkeypatch.setattr(tools, "_run_profile_commands", fake_run_profile_commands)

    result = asyncio.run(tools._server_read_command("service_logs", service="sparkbot-v2", lines=500))

    assert result == "ok"
    assert captured["timeout"] == 17
    commands = captured["commands"]
    assert commands == [
        ("service_logs", ["journalctl", "-u", "sparkbot-v2", "-n", "200", "--no-pager"])
    ]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only Get-EventLog path; Linux uses journalctl")
def test_server_read_command_service_logs_uses_allowed_service_windows(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_run_profile_commands(commands, timeout):
        captured["commands"] = commands
        captured["timeout"] = timeout
        return "ok"

    monkeypatch.setattr(tools, "_ALLOWED_LOCAL_SERVICES", {"sparkbot-v2"})
    monkeypatch.setattr(tools, "_SERVER_COMMAND_TIMEOUT_SECONDS", 17)
    monkeypatch.setattr(tools, "_run_profile_commands", fake_run_profile_commands)

    result = asyncio.run(tools._server_read_command("service_logs", service="sparkbot-v2", lines=500))

    assert result == "ok"
    label, argv = captured["commands"][0]
    assert label == "service_logs"
    assert argv[0] == "powershell"
    assert "Get-EventLog" in " ".join(argv)
    assert "sparkbot-v2" in " ".join(argv)


def test_unknown_profile_message_is_explicit_about_not_being_a_policy_denial() -> None:
    """v1.6.74 regression: the bot was narrating 'policy-blocked' when it
    actually hit this enum-validation rejection. The error text now says so
    explicitly, so the LLM should distinguish parameter validation from a
    Guardian policy decision.
    """
    commands, err = tools._ops_profile_commands(
        "Get-Date",
        service="",
        lines=50,
        allowed_services=set(),
    )
    assert commands is None
    assert err is not None
    assert "parameter validation error" in err
    assert "not a policy denial" in err
    assert "host_identity" in err
    assert "toolchain_versions" in err


def test_host_identity_profile_runs_without_service(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_run_profile_commands(commands, timeout):
        captured["commands"] = commands
        return "ok"

    monkeypatch.setattr(tools, "_run_profile_commands", fake_run_profile_commands)

    result = asyncio.run(tools._server_read_command("host_identity"))

    assert result == "ok"
    labels = [label for label, _ in captured["commands"]]
    assert "hostname" in labels
    assert "current_user" in labels
    assert "current_time" in labels


def test_toolchain_versions_profile_probes_each_tool(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_run_profile_commands(commands, timeout):
        captured["commands"] = commands
        return "ok"

    monkeypatch.setattr(tools, "_run_profile_commands", fake_run_profile_commands)

    result = asyncio.run(tools._server_read_command("toolchain_versions"))

    assert result == "ok"
    labels = [label for label, _ in captured["commands"]]
    for tool_label in ("python", "git", "node", "docker"):
        assert tool_label in labels


def test_new_profiles_listed_in_allowed_set() -> None:
    assert "host_identity" in tools._SERVER_READ_COMMANDS
    assert "toolchain_versions" in tools._SERVER_READ_COMMANDS
