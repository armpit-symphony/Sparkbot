import asyncio

from app.api.routes.chat import tools


def test_server_manage_service_rejects_unapproved_service(monkeypatch) -> None:
    monkeypatch.setattr(tools, "_ALLOWED_LOCAL_SERVICES", {"sparkbot-v2"})

    result = asyncio.run(tools._server_manage_service("nginx", "restart"))

    assert "Service is not allowed" in result


def test_ssh_read_command_requires_configured_hosts(monkeypatch) -> None:
    monkeypatch.setattr(tools, "_ALLOWED_SSH_HOSTS", set())

    result = asyncio.run(tools._ssh_read_command("office-pc", "system_overview"))

    assert "SSH access is not configured" in result


def test_server_read_command_service_logs_uses_allowed_service(monkeypatch) -> None:
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
