import asyncio
import sys

import pytest

from app.api.routes.chat import tools


def _write_fake_proc(
    root,
    pid: int,
    *,
    name: str,
    cmd: str,
    ppid: int = 1,
    uid: int = 1000,
    rss_kb: int = 1024,
) -> None:
    proc_dir = root / str(pid)
    proc_dir.mkdir(parents=True)
    proc_dir.joinpath("cmdline").write_bytes(cmd.encode("utf-8").replace(b" ", b"\x00"))
    proc_dir.joinpath("status").write_text(
        "\n".join(
            [
                f"Name:\t{name}",
                "State:\tS (sleeping)",
                f"PPid:\t{ppid}",
                f"Uid:\t{uid}\t{uid}\t{uid}\t{uid}",
                f"VmRSS:\t{rss_kb} kB",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


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
        captured["timeout"] = timeout
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
        captured["timeout"] = timeout
        return "ok"

    monkeypatch.setattr(tools, "_run_profile_commands", fake_run_profile_commands)

    result = asyncio.run(tools._server_read_command("toolchain_versions"))

    assert result == "ok"
    labels = [label for label, _ in captured["commands"]]
    for tool_label in ("python", "git", "node", "docker"):
        assert tool_label in labels


def test_bot_health_profile_uses_internal_host_inspection(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_run_profile_commands(commands, timeout):
        captured["commands"] = commands
        captured["timeout"] = timeout
        return "ok"

    monkeypatch.setattr(tools, "_run_profile_commands", fake_run_profile_commands)

    result = asyncio.run(tools._server_read_command("bot_health", query="kalshi"))

    assert result == "ok"
    assert captured["commands"] == [("bot_health", ["__sparkbot_internal__", "bot_health", "kalshi"])]


def test_process_search_reports_missing_host_proc_without_policy_language(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(tools, "_HOST_PROC_ROOT", tmp_path / "proc")

    result = asyncio.run(tools._server_read_command("process_search", query="sparkbot"))

    assert "Host process table is not mounted" in result
    assert "policy" not in result.lower()


def test_scheduled_jobs_reads_mounted_cron_files(monkeypatch, tmp_path) -> None:
    cron_dir = tmp_path / "cron.d"
    cron_dir.mkdir()
    (cron_dir / "sparkbot").write_text("*/5 * * * * sparkbot /srv/sparkbot/jobs/health_check.py >> /tmp/sparkbot.log 2>&1\n")
    monkeypatch.setattr(tools, "_HOST_CRON_ROOTS", [cron_dir])

    result = asyncio.run(tools._server_read_command("scheduled_jobs", query="sparkbot"))

    assert "Scheduled jobs matching 'sparkbot': 1" in result
    assert "health_check.py" in result


def test_process_snapshot_uses_mounted_host_proc(monkeypatch, tmp_path) -> None:
    proc_root = tmp_path / "proc"
    _write_fake_proc(
        proc_root,
        225970,
        name="node",
        cmd="/usr/bin/node /srv/sparkbot-ui/dist/server.js gateway --port 18789",
    )
    _write_fake_proc(
        proc_root,
        1268686,
        name="python",
        cmd="/usr/bin/python /srv/example-worker/worker.py --api-port 18212",
    )
    monkeypatch.setattr(tools, "_HOST_PROC_ROOT", proc_root)
    monkeypatch.setattr(tools.sys, "platform", "linux")

    result = asyncio.run(tools._server_read_command("process_snapshot"))

    assert "Host process snapshot" in result
    assert "sparkbot-ui" in result
    assert "example-worker" in result
    assert "ps -eo" not in result


def test_network_listeners_uses_mounted_host_proc_net(monkeypatch, tmp_path) -> None:
    proc_root = tmp_path / "proc"
    _write_fake_proc(
        proc_root,
        225970,
        name="node",
        cmd="/usr/bin/node sparkbot gateway --port 18789",
    )
    fd_dir = proc_root / "225970" / "fd"
    fd_dir.mkdir()
    try:
        (fd_dir / "7").symlink_to("socket:[12345]")
        link_created = True
    except OSError:
        link_created = False
    net_dir = proc_root / "net"
    net_dir.mkdir()
    net_dir.joinpath("tcp").write_text(
        "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
        "   0: 0100007F:4965 00000000:0000 0A 00000000:00000000 00:00000000 00000000 1000 0 12345 1 0000000000000000 100 0 0 10 0\n",
        encoding="utf-8",
    )
    net_dir.joinpath("tcp6").write_text(
        "  sl  local_address                         remote_address                        st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tools, "_HOST_PROC_ROOT", proc_root)
    monkeypatch.setattr(tools.sys, "platform", "linux")

    result = asyncio.run(tools._server_read_command("network_listeners"))

    assert "Host TCP listeners" in result
    assert "127.0.0.1:18789" in result
    if link_created:
        assert "sparkbot" in result
    else:
        assert "(process unavailable)" in result


def test_host_full_audit_itemizes_known_workloads(monkeypatch, tmp_path) -> None:
    proc_root = tmp_path / "proc"
    _write_fake_proc(
        proc_root,
        225970,
        name="node",
        cmd="/usr/bin/node /srv/sparkbot-ui/dist/server.js gateway --port 18789",
    )
    _write_fake_proc(
        proc_root,
        1268686,
        name="postgres",
        cmd="/usr/lib/postgresql/bin/postgres -D /var/lib/postgresql/data",
    )
    (proc_root / "uptime").write_text("7200.00 100.00\n", encoding="utf-8")
    (proc_root / "meminfo").write_text(
        "MemTotal:        8192000 kB\nMemAvailable:    4096000 kB\nSwapTotal:       4096000 kB\nSwapFree:        4000000 kB\n",
        encoding="utf-8",
    )
    net_dir = proc_root / "net"
    net_dir.mkdir()
    net_dir.joinpath("tcp").write_text(
        "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n",
        encoding="utf-8",
    )
    net_dir.joinpath("tcp6").write_text(
        "  sl  local_address                         remote_address                        st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n",
        encoding="utf-8",
    )
    cron_dir = tmp_path / "cron.d"
    cron_dir.mkdir()
    cron_dir.joinpath("sparkbot").write_text("*/5 * * * * sparkbot /srv/sparkbot/jobs/health_check.py\n")
    monkeypatch.setattr(tools, "_HOST_PROC_ROOT", proc_root)
    monkeypatch.setattr(tools, "_HOST_CRON_ROOTS", [cron_dir])

    result = asyncio.run(tools._server_read_command("host_full_audit"))

    assert "Full host audit: read-only snapshot" in result
    assert "sparkbot: 1 process" in result
    assert "postgres: 1 process" in result
    assert "health_check.py" in result
    assert "coverage" in result.lower()


def test_new_profiles_listed_in_allowed_set() -> None:
    assert "host_identity" in tools._SERVER_READ_COMMANDS
    assert "toolchain_versions" in tools._SERVER_READ_COMMANDS
    assert "bot_health" in tools._SERVER_READ_COMMANDS
    assert "process_search" in tools._SERVER_READ_COMMANDS
    assert "scheduled_jobs" in tools._SERVER_READ_COMMANDS
    assert "runtime_context" in tools._SERVER_READ_COMMANDS
    assert "host_capabilities" in tools._SERVER_READ_COMMANDS
    assert "host_full_audit" in tools._SERVER_READ_COMMANDS
