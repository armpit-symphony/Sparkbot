from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "sparkbot-setup.sh"
START_SCRIPT = ROOT / "scripts" / "sparkbot-start.sh"
LOCAL_COMPOSE = ROOT / "compose.local.yml"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run_setup(
    args: list[str],
    *,
    env: dict[str, str],
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=ROOT,
        env=merged_env,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def _run_start(
    args: list[str],
    *,
    env: dict[str, str],
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    for key in (
        "SPARKBOT_FRONTEND_BIND_HOST",
        "SPARKBOT_FRONTEND_PORT",
        "SPARKBOT_PASSPHRASE",
        "SPARKBOT_AUTH_DISABLED",
        "VITE_V1_LOCAL_MODE",
    ):
        if key not in env:
            merged_env.pop(key, None)
    merged_env.update(env)
    if "SPARKBOT_COMPOSE_ENV_FILE" not in merged_env and "SPARKBOT_ENV_FILE" in merged_env:
        merged_env["SPARKBOT_COMPOSE_ENV_FILE"] = str(Path(merged_env["SPARKBOT_ENV_FILE"]).with_name(".env"))
    return subprocess.run(
        ["bash", str(START_SCRIPT), *args],
        cwd=ROOT,
        env=merged_env,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def _template(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "PROJECT_NAME=Sparkbot",
                "SPARKBOT_PASSPHRASE=sparkbot-local",
                "OPENAI_API_KEY=",
                "ANTHROPIC_API_KEY=",
                "GOOGLE_API_KEY=",
                "GROQ_API_KEY=",
                "MINIMAX_API_KEY=",
                "OPENROUTER_API_KEY=",
                "SPARKBOT_DEFAULT_PROVIDER=openai",
                "SPARKBOT_MODEL=gpt-5-mini",
                "SPARKBOT_HEAVY_HITTER_MODEL=gpt-5-mini",
                "SPARKBOT_LOCAL_MODEL=",
                "",
            ]
        )
    )


def test_compose_detection_prefers_docker_compose_v2(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "docker",
        '#!/usr/bin/env sh\n[ "$1" = "compose" ] && [ "$2" = "version" ] && exit 0\nexit 1\n',
    )

    result = _run_setup(
        ["--print-compose-command"],
        env={"PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "docker compose"


def test_compose_detection_falls_back_to_legacy_binary(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "docker", "#!/usr/bin/env sh\nexit 1\n")
    _write_executable(fake_bin / "docker-compose", "#!/usr/bin/env sh\nexit 0\n")

    result = _run_setup(
        ["--print-compose-command"],
        env={"PATH": f"{fake_bin}:/usr/bin:/bin"},
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "docker-compose"


def test_compose_detection_missing_docker_prints_clear_error(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "cat", "#!/bin/sh\n/bin/cat \"$@\"\n")

    result = subprocess.run(
        [
            "/bin/bash",
            "-c",
            'source "$1"; PATH="$2"; sparkbot_detect_compose',
            "bash",
            str(SCRIPT),
            str(fake_bin),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Docker Compose was not found" in result.stderr


def test_check_config_fails_without_provider_or_ollama(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.local"
    _template(env_file)

    result = _run_setup(
        ["--check-config"],
        env={"SPARKBOT_ENV_FILE": str(env_file)},
    )

    assert result.returncode != 0


def test_check_config_ignores_placeholder_provider_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.local"
    _template(env_file)
    env_file.write_text(env_file.read_text().replace("OPENAI_API_KEY=", "OPENAI_API_KEY=REPLACE_WITH_OPENAI_KEY"))

    result = _run_setup(
        ["--check-config"],
        env={"SPARKBOT_ENV_FILE": str(env_file)},
    )

    assert result.returncode != 0


def test_noninteractive_setup_creates_env_and_does_not_echo_secret(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "docker",
        '#!/usr/bin/env sh\n[ "$1" = "compose" ] && [ "$2" = "version" ] && exit 0\nexit 1\n',
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_setup(
        ["--non-interactive"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "OPENAI_API_KEY": "sk-test-secret",
        },
    )

    assert result.returncode == 0
    content = env_file.read_text()
    assert "OPENAI_API_KEY=sk-test-secret" in content
    assert "SECRET_KEY=" in content
    assert "DATABASE_TYPE=postgresql" in content
    assert "POSTGRES_SERVER=db" in content
    assert "POSTGRES_PORT=5432" in content
    assert "POSTGRES_DB=sparkbot" in content
    assert "POSTGRES_USER=sparkbot" in content
    assert "POSTGRES_PASSWORD=sparkbot-local" in content
    assert "SPARKBOT_FRONTEND_PORT=3000" in content
    assert "SPARKBOT_FRONTEND_BIND_HOST=127.0.0.1" in content
    assert "SPARKBOT_MODEL=gpt-5-mini" in content
    assert "sk-test-secret" not in result.stdout
    assert "sk-test-secret" not in result.stderr


def test_noninteractive_setup_preserves_existing_provider_value(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "docker",
        '#!/usr/bin/env sh\n[ "$1" = "compose" ] && [ "$2" = "version" ] && exit 0\nexit 1\n',
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)
    env_file.write_text(template.read_text().replace("OPENAI_API_KEY=", "OPENAI_API_KEY=sk-existing"))

    result = _run_setup(
        ["--non-interactive"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "OPENAI_API_KEY": "sk-new",
        },
    )

    assert result.returncode == 0
    content = env_file.read_text()
    assert "OPENAI_API_KEY=sk-existing" in content
    assert "sk-new" not in content


def test_provider_prompt_is_visible_by_default_and_keeps_secret_out_of_output(tmp_path: Path) -> None:
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_setup(
        [],
        env={
            "SPARKBOT_SETUP_SKIP_COMPOSE_CHECK": "1",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
        },
        input_text="sk-visible-default\n\n\n\n\n\n\n\n\n",
    )

    assert result.returncode == 0
    assert "Your key will be visible while typing in this terminal session." in result.stderr
    assert "Input will be hidden" not in result.stderr
    assert "OPENAI_API_KEY=sk-visible-default" in env_file.read_text()
    assert "sk-visible-default" not in result.stdout
    assert "sk-visible-default" not in result.stderr


def test_show_input_path_accepts_typed_provider_key(tmp_path: Path) -> None:
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = subprocess.run(
        ["bash", str(SCRIPT), "--show-input"],
        cwd=ROOT,
        env={
            **os.environ,
            "SPARKBOT_SETUP_SKIP_COMPOSE_CHECK": "1",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
        },
        input="sk-visible-input\n\n\n\n\n\n\n\n\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Input will be hidden" not in result.stderr
    assert "OPENAI_API_KEY=sk-visible-input" in env_file.read_text()


def test_hide_input_path_accepts_typed_provider_key(tmp_path: Path) -> None:
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_setup(
        ["--hide-input"],
        env={
            "SPARKBOT_SETUP_SKIP_COMPOSE_CHECK": "1",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
        },
        input_text="sk-hidden-provider\n\n\n\n\n\n\n\n\n",
    )

    assert result.returncode == 0
    assert "Input will be hidden. Paste/type your key, then press Enter." in result.stderr
    assert "Your key will be visible" not in result.stderr
    assert "OPENAI_API_KEY=sk-hidden-provider" in env_file.read_text()
    assert "sk-hidden-provider" not in result.stdout
    assert "sk-hidden-provider" not in result.stderr


def test_ssh_environment_uses_visible_provider_prompt(tmp_path: Path) -> None:
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_setup(
        [],
        env={
            "SPARKBOT_SETUP_SKIP_COMPOSE_CHECK": "1",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "SSH_CONNECTION": "203.0.113.5 55555 203.0.113.10 22",
        },
        input_text="sk-ssh-visible\n\n\n\n\n\n\n\n\n",
    )

    assert result.returncode == 0
    assert "SSH session detected. Provider key input will be visible so paste works reliably." in result.stderr
    assert "Your key will be visible while typing in this terminal session." in result.stderr
    assert "Input will be hidden" not in result.stderr
    assert "OPENAI_API_KEY=sk-ssh-visible" in env_file.read_text()
    assert "sk-ssh-visible" not in result.stdout
    assert "sk-ssh-visible" not in result.stderr


def test_from_env_imports_exported_provider_key_without_echoing_secret(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "docker",
        '#!/usr/bin/env sh\n[ "$1" = "compose" ] && [ "$2" = "version" ] && exit 0\nexit 1\n',
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_setup(
        ["--from-env"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "OPENAI_API_KEY": "sk-from-env",
        },
    )

    assert result.returncode == 0
    content = env_file.read_text()
    assert "OPENAI_API_KEY=sk-from-env" in content
    assert "sk-from-env" not in result.stdout
    assert "sk-from-env" not in result.stderr


def test_direct_provider_key_argument_writes_key_without_echoing_secret(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "docker",
        '#!/usr/bin/env sh\n[ "$1" = "compose" ] && [ "$2" = "version" ] && exit 0\nexit 1\n',
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_setup(
        ["--openrouter-key", "sk-or-direct"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
        },
    )

    assert result.returncode == 0
    content = env_file.read_text()
    assert "OPENROUTER_API_KEY=sk-or-direct" in content
    assert "SPARKBOT_MODEL=openrouter/openai/gpt-4o-mini" in content
    assert "sk-or-direct" not in result.stdout
    assert "sk-or-direct" not in result.stderr


def test_minimax_provider_key_argument_writes_key_and_model(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "docker",
        '#!/usr/bin/env sh\n[ "$1" = "compose" ] && [ "$2" = "version" ] && exit 0\nexit 1\n',
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_setup(
        ["--minimax-key", "minimax-direct"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
        },
    )

    assert result.returncode == 0
    content = env_file.read_text()
    assert "MINIMAX_API_KEY=minimax-direct" in content
    assert "SPARKBOT_MODEL=minimax/MiniMax-M2.5" in content
    assert "minimax-direct" not in result.stdout
    assert "minimax-direct" not in result.stderr


def test_start_script_passes_setup_args_through(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "docker",
        """#!/usr/bin/env sh
if [ "$1" = "info" ]; then exit 0; fi
if [ "$1" = "buildx" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ]; then exit 0; fi
exit 1
""",
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        ["--openai-key", "sk-start-direct"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
        },
    )

    assert result.returncode == 0
    assert "Running Sparkbot setup with requested options." in result.stdout
    assert "OPENAI_API_KEY=sk-start-direct" in env_file.read_text()
    assert "sk-start-direct" not in result.stdout
    assert "sk-start-direct" not in result.stderr


def test_start_script_selects_next_frontend_port_when_default_is_busy(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    compose_log = tmp_path / "compose.log"
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env sh
if [ "$1" = "info" ]; then exit 0; fi
if [ "$1" = "buildx" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ]; then echo "$@" >> "{compose_log}"; echo "SPARKBOT_FRONTEND_PORT=${{SPARKBOT_FRONTEND_PORT:-}}" >> "{compose_log}"; echo "SPARKBOT_FRONTEND_BIND_HOST=${{SPARKBOT_FRONTEND_BIND_HOST:-}}" >> "{compose_log}"; exit 0; fi
exit 1
""",
    )
    _write_executable(
        fake_bin / "ss",
        """#!/usr/bin/env sh
echo "State Recv-Q Send-Q Local Address:Port Peer Address:Port"
echo "LISTEN 0 128 127.0.0.1:3000 0.0.0.0:*"
exit 0
""",
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        ["--openai-key", "sk-port-busy"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
        },
    )

    assert result.returncode == 0
    assert "Port 3000 is already in use. Using 3001" in result.stderr
    assert "SPARKBOT_FRONTEND_PORT=3001" in env_file.read_text()
    assert "Web UI: http://localhost:3001" in result.stdout
    assert "SPARKBOT_FRONTEND_PORT=3001" in compose_log.read_text()
    assert "SPARKBOT_FRONTEND_BIND_HOST=127.0.0.1" in compose_log.read_text()


def test_start_script_respects_custom_frontend_port(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    compose_log = tmp_path / "compose.log"
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env sh
if [ "$1" = "info" ]; then exit 0; fi
if [ "$1" = "buildx" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ]; then echo "$@" >> "{compose_log}"; echo "SPARKBOT_FRONTEND_PORT=${{SPARKBOT_FRONTEND_PORT:-}}" >> "{compose_log}"; echo "SPARKBOT_FRONTEND_BIND_HOST=${{SPARKBOT_FRONTEND_BIND_HOST:-}}" >> "{compose_log}"; exit 0; fi
exit 1
""",
    )
    _write_executable(
        fake_bin / "ss",
        """#!/usr/bin/env sh
echo "State Recv-Q Send-Q Local Address:Port Peer Address:Port"
exit 0
""",
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        ["--openai-key", "sk-custom-port"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "SPARKBOT_FRONTEND_PORT": "3100",
        },
    )

    assert result.returncode == 0
    assert "SPARKBOT_FRONTEND_PORT=3100" in env_file.read_text()
    assert "Web UI: http://localhost:3100" in result.stdout
    assert "SPARKBOT_FRONTEND_PORT=3100" in compose_log.read_text()
    assert "SPARKBOT_FRONTEND_BIND_HOST=127.0.0.1" in compose_log.read_text()


def test_start_script_local_mode_binds_loopback_and_syncs_compose_env(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    compose_log = tmp_path / "compose.log"
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env sh
if [ "$1" = "info" ]; then exit 0; fi
if [ "$1" = "buildx" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ]; then echo "$@" >> "{compose_log}"; echo "SPARKBOT_FRONTEND_PORT=${{SPARKBOT_FRONTEND_PORT:-}}" >> "{compose_log}"; echo "SPARKBOT_FRONTEND_BIND_HOST=${{SPARKBOT_FRONTEND_BIND_HOST:-}}" >> "{compose_log}"; exit 0; fi
exit 1
""",
    )
    _write_executable(
        fake_bin / "ss",
        """#!/usr/bin/env sh
echo "State Recv-Q Send-Q Local Address:Port Peer Address:Port"
exit 0
""",
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    compose_env = tmp_path / ".env"
    _template(template)

    result = _run_start(
        ["--local", "--openai-key", "sk-local-mode"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "SPARKBOT_COMPOSE_ENV_FILE": str(compose_env),
        },
    )

    assert result.returncode == 0
    assert "Bind host: 127.0.0.1" in result.stdout
    assert "Web UI: http://localhost:3000" in result.stdout
    assert "SPARKBOT_FRONTEND_BIND_HOST=127.0.0.1" in env_file.read_text()
    assert "SPARKBOT_FRONTEND_PORT=3000" in compose_env.read_text()
    assert "SPARKBOT_FRONTEND_BIND_HOST=127.0.0.1" in compose_env.read_text()
    assert "VITE_V1_LOCAL_MODE=true" in compose_env.read_text()
    assert "V1_LOCAL_MODE=true" in env_file.read_text()
    assert "SPARKBOT_FRONTEND_BIND_HOST=127.0.0.1" in compose_log.read_text()
    assert "up --build -d" in compose_log.read_text()


def test_start_script_server_mode_with_default_passphrase_fails_before_startup(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    compose_log = tmp_path / "compose.log"
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env sh
if [ "$1" = "info" ]; then exit 0; fi
if [ "$1" = "buildx" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ]; then echo "$@" >> "{compose_log}"; exit 0; fi
exit 1
""",
    )
    _write_executable(
        fake_bin / "ss",
        """#!/usr/bin/env sh
echo "State Recv-Q Send-Q Local Address:Port Peer Address:Port"
exit 0
""",
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        ["--server", "--openai-key", "sk-server-default-passphrase"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
        },
    )

    assert result.returncode != 0
    assert "Server mode requires authentication" in result.stderr
    assert "SPARKBOT_PASSPHRASE is missing, blank, too short, a placeholder, or a default value." in result.stderr
    assert not compose_log.exists()


def test_start_script_server_mode_with_missing_passphrase_fails_before_startup(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    compose_log = tmp_path / "compose.log"
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env sh
if [ "$1" = "info" ]; then exit 0; fi
if [ "$1" = "buildx" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ]; then echo "$@" >> "{compose_log}"; exit 0; fi
exit 1
""",
    )
    _write_executable(
        fake_bin / "ss",
        """#!/usr/bin/env sh
echo "State Recv-Q Send-Q Local Address:Port Peer Address:Port"
exit 0
""",
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)
    template.write_text(template.read_text().replace("SPARKBOT_PASSPHRASE=sparkbot-local", "SPARKBOT_PASSPHRASE="))

    result = _run_start(
        ["--server", "--openai-key", "sk-server-missing-passphrase"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
        },
    )

    assert result.returncode != 0
    assert "Server mode requires authentication" in result.stderr
    assert not compose_log.exists()


def test_start_script_server_mode_show_input_prompts_for_passphrase(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    compose_log = tmp_path / "compose.log"
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env sh
if [ "$1" = "info" ]; then exit 0; fi
if [ "$1" = "buildx" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ]; then echo "$@" >> "{compose_log}"; exit 0; fi
exit 1
""",
    )
    _write_executable(
        fake_bin / "ss",
        """#!/usr/bin/env sh
echo "State Recv-Q Send-Q Local Address:Port Peer Address:Port"
exit 0
""",
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        ["--server", "--show-input", "--openai-key", "sk-server-prompt"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "SPARKBOT_PUBLIC_HOST": "203.0.113.30",
        },
        input_text="server-passphrase-123\nserver-passphrase-123\n",
    )

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "Create Sparkbot server passphrase:" in combined
    assert "Confirm server passphrase:" in combined
    assert "server-passphrase-123" not in result.stdout
    assert "server-passphrase-123" not in result.stderr
    assert "SPARKBOT_PASSPHRASE=server-passphrase-123" in env_file.read_text()
    assert "V1_LOCAL_MODE=false" in env_file.read_text()
    assert compose_log.exists()


def test_start_script_server_mode_show_passphrase_input_prompts_visibly(tmp_path: Path) -> None:
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        [
            "--server",
            "--dry-run-setup",
            "--show-passphrase-input",
            "--openai-key",
            "sk-server-visible-passphrase",
        ],
        env={
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "SPARKBOT_PUBLIC_HOST": "203.0.113.32",
        },
        input_text="visible-server-passphrase\nvisible-server-passphrase\n",
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Your passphrase will be visible while typing in this terminal session." in result.stderr
    assert "Hidden input did not work" not in combined
    assert "Dry-run setup complete. Docker was not started." in result.stdout
    assert "Server passphrase saved." in result.stderr
    assert "SPARKBOT_PASSPHRASE=visible-server-passphrase" in env_file.read_text()
    assert "visible-server-passphrase" not in result.stdout
    assert "visible-server-passphrase" not in result.stderr


def test_start_script_server_mode_ssh_passphrase_uses_visible_fallback(tmp_path: Path) -> None:
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        ["--server", "--dry-run-setup", "--openai-key", "sk-server-ssh-passphrase"],
        env={
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "SPARKBOT_PUBLIC_HOST": "203.0.113.33",
            "SSH_CONNECTION": "203.0.113.5 55555 203.0.113.10 22",
        },
        input_text="ssh-server-passphrase\nssh-server-passphrase\n",
    )

    assert result.returncode == 0
    assert "Hidden input did not work in this terminal. Switching to visible input." in result.stderr
    assert "Your passphrase will be visible while typing in this terminal session." in result.stderr
    assert "Server passphrase saved." in result.stderr
    assert "SPARKBOT_PASSPHRASE=ssh-server-passphrase" in env_file.read_text()
    assert "ssh-server-passphrase" not in result.stdout
    assert "ssh-server-passphrase" not in result.stderr


def test_start_script_server_mode_from_env_accepts_passphrase(tmp_path: Path) -> None:
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        ["--server", "--dry-run-setup", "--from-env"],
        env={
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "SPARKBOT_PUBLIC_HOST": "203.0.113.34",
            "OPENAI_API_KEY": "sk-from-env-server",
            "SPARKBOT_PASSPHRASE": "from-env-server-passphrase",
        },
    )

    assert result.returncode == 0
    assert "Create Sparkbot server passphrase" not in result.stderr
    content = env_file.read_text()
    assert "OPENAI_API_KEY=sk-from-env-server" in content
    assert "SPARKBOT_PASSPHRASE=from-env-server-passphrase" in content
    assert "from-env-server-passphrase" not in result.stdout
    assert "from-env-server-passphrase" not in result.stderr


def test_start_script_server_mode_direct_passphrase_argument(tmp_path: Path) -> None:
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        [
            "--server",
            "--dry-run-setup",
            "--openai-key",
            "sk-direct-passphrase",
            "--passphrase",
            "direct-server-passphrase",
        ],
        env={
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "SPARKBOT_PUBLIC_HOST": "203.0.113.35",
        },
    )

    assert result.returncode == 0
    assert "Create Sparkbot server passphrase" not in result.stderr
    assert "SPARKBOT_PASSPHRASE=direct-server-passphrase" in env_file.read_text()
    assert "direct-server-passphrase" not in result.stdout
    assert "direct-server-passphrase" not in result.stderr


def test_start_script_server_mode_passphrase_mismatch_retries(tmp_path: Path) -> None:
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        [
            "--server",
            "--dry-run-setup",
            "--show-passphrase-input",
            "--openai-key",
            "sk-mismatch-passphrase",
        ],
        env={
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "SPARKBOT_PUBLIC_HOST": "203.0.113.36",
        },
        input_text=(
            "first-server-passphrase\n"
            "second-server-passphrase\n"
            "matched-server-passphrase\n"
            "matched-server-passphrase\n"
        ),
    )

    assert result.returncode == 0
    assert "Passphrases did not match." in result.stderr
    assert "first-server-passphrase" not in env_file.read_text()
    assert "SPARKBOT_PASSPHRASE=matched-server-passphrase" in env_file.read_text()
    assert "matched-server-passphrase" not in result.stdout
    assert "matched-server-passphrase" not in result.stderr


def test_start_script_server_mode_rejects_weak_prompted_passphrase_then_accepts_valid(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    compose_log = tmp_path / "compose.log"
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env sh
if [ "$1" = "info" ]; then exit 0; fi
if [ "$1" = "buildx" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ]; then echo "$@" >> "{compose_log}"; exit 0; fi
exit 1
""",
    )
    _write_executable(
        fake_bin / "ss",
        """#!/usr/bin/env sh
echo "State Recv-Q Send-Q Local Address:Port Peer Address:Port"
exit 0
""",
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        ["--server", "--show-input", "--openai-key", "sk-server-retry"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "SPARKBOT_PUBLIC_HOST": "203.0.113.31",
        },
        input_text=(
            "replace-with-a-long-private-passphrase\n"
            "replace-with-a-long-private-passphrase\n"
            "valid-server-passphrase\n"
            "valid-server-passphrase\n"
        ),
    )

    assert result.returncode == 0
    assert "Passphrase cannot be a default or placeholder." in result.stderr
    assert "replace-with-a-long-private-passphrase" not in env_file.read_text()
    assert "SPARKBOT_PASSPHRASE=valid-server-passphrase" in env_file.read_text()
    assert compose_log.exists()


def test_start_script_rejects_weak_direct_passphrase_without_logging_value(tmp_path: Path) -> None:
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        [
            "--server",
            "--dry-run-setup",
            "--openai-key",
            "sk-weak-direct-passphrase",
            "--passphrase",
            "sparkbot",
        ],
        env={
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "SPARKBOT_PUBLIC_HOST": "203.0.113.37",
        },
    )

    assert result.returncode != 0
    assert "Passphrase cannot be a default or placeholder." in result.stderr
    assert "SPARKBOT_PASSPHRASE=sparkbot" not in env_file.read_text().splitlines()


def test_start_script_server_mode_rejects_short_prompted_passphrase(tmp_path: Path) -> None:
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        [
            "--server",
            "--dry-run-setup",
            "--show-passphrase-input",
            "--openai-key",
            "sk-short-passphrase",
        ],
        env={
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "SPARKBOT_PUBLIC_HOST": "203.0.113.38",
        },
        input_text=(
            "short\n"
            "short\n"
            "valid-after-short-passphrase\n"
            "valid-after-short-passphrase\n"
        ),
    )

    assert result.returncode == 0
    assert "Passphrase is too short. Use at least 12 characters." in result.stderr
    assert "SPARKBOT_PASSPHRASE=valid-after-short-passphrase" in env_file.read_text()


def test_start_script_server_mode_rejects_empty_prompted_passphrase(tmp_path: Path) -> None:
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        [
            "--server",
            "--dry-run-setup",
            "--show-passphrase-input",
            "--openai-key",
            "sk-empty-passphrase",
        ],
        env={
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "SPARKBOT_PUBLIC_HOST": "203.0.113.39",
        },
        input_text=(
            "\n"
            "\n"
            "valid-after-empty-passphrase\n"
            "valid-after-empty-passphrase\n"
        ),
    )

    assert result.returncode == 0
    assert "Passphrase cannot be empty." in result.stderr
    assert "SPARKBOT_PASSPHRASE=valid-after-empty-passphrase" in env_file.read_text()


def test_start_script_server_mode_max_passphrase_retries_exits_cleanly(tmp_path: Path) -> None:
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        [
            "--server",
            "--dry-run-setup",
            "--show-passphrase-input",
            "--openai-key",
            "sk-max-retry-passphrase",
        ],
        env={
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "SPARKBOT_PUBLIC_HOST": "203.0.113.41",
        },
        input_text=("short\nshort\n" * 5),
    )

    assert result.returncode != 0
    assert result.stderr.count("Passphrase is too short. Use at least 12 characters.") == 5
    assert "Too many invalid passphrase attempts. Rerun setup to try again." in result.stderr
    assert "SPARKBOT_PASSPHRASE=short" not in env_file.read_text().splitlines()


def test_start_script_server_mode_refuses_disabled_auth(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    compose_log = tmp_path / "compose.log"
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env sh
if [ "$1" = "info" ]; then exit 0; fi
if [ "$1" = "buildx" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ]; then echo "$@" >> "{compose_log}"; exit 0; fi
exit 1
""",
    )
    _write_executable(
        fake_bin / "ss",
        """#!/usr/bin/env sh
echo "State Recv-Q Send-Q Local Address:Port Peer Address:Port"
exit 0
""",
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        ["--server", "--openai-key", "sk-server-auth-disabled"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "SPARKBOT_PASSPHRASE": "valid-server-passphrase",
            "SPARKBOT_AUTH_DISABLED": "true",
        },
    )

    assert result.returncode != 0
    assert "Server mode refuses to start because auth is disabled." in result.stderr
    assert not compose_log.exists()


def test_start_script_server_mode_binds_publicly_and_prints_detected_url(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    compose_log = tmp_path / "compose.log"
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env sh
if [ "$1" = "info" ]; then exit 0; fi
if [ "$1" = "buildx" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ]; then echo "$@" >> "{compose_log}"; echo "SPARKBOT_FRONTEND_PORT=${{SPARKBOT_FRONTEND_PORT:-}}" >> "{compose_log}"; echo "SPARKBOT_FRONTEND_BIND_HOST=${{SPARKBOT_FRONTEND_BIND_HOST:-}}" >> "{compose_log}"; exit 0; fi
exit 1
""",
    )
    _write_executable(
        fake_bin / "ss",
        """#!/usr/bin/env sh
echo "State Recv-Q Send-Q Local Address:Port Peer Address:Port"
echo "LISTEN 0 128 127.0.0.1:3000 0.0.0.0:*"
exit 0
""",
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    compose_env = tmp_path / ".env"
    _template(template)

    result = _run_start(
        ["--server", "--openai-key", "sk-server-mode"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "SPARKBOT_COMPOSE_ENV_FILE": str(compose_env),
            "SPARKBOT_PUBLIC_HOST": "203.0.113.10",
            "SPARKBOT_PASSPHRASE": "valid-server-passphrase",
        },
    )

    assert result.returncode == 0
    assert "Port 3000 is already in use. Using 3001" in result.stderr
    assert "Bind host: 0.0.0.0" in result.stdout
    assert "Detected public IP: 203.0.113.10" in result.stdout
    assert "Open Sparkbot:\nhttp://203.0.113.10:3001" in result.stdout
    assert "Security warning:" in result.stdout
    assert "valid-server-passphrase" not in result.stdout
    assert "valid-server-passphrase" not in result.stderr
    assert "SPARKBOT_FRONTEND_BIND_HOST=0.0.0.0" in env_file.read_text()
    assert "SPARKBOT_PASSPHRASE=valid-server-passphrase" in env_file.read_text()
    assert "V1_LOCAL_MODE=false" in env_file.read_text()
    assert "SPARKBOT_FRONTEND_PORT=3001" in compose_env.read_text()
    assert "SPARKBOT_FRONTEND_BIND_HOST=0.0.0.0" in compose_env.read_text()
    assert "VITE_V1_LOCAL_MODE=false" in compose_env.read_text()
    assert "SPARKBOT_FRONTEND_BIND_HOST=0.0.0.0" in compose_log.read_text()


def test_start_script_preserves_existing_bind_mode_and_port(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    compose_log = tmp_path / "compose.log"
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env sh
if [ "$1" = "info" ]; then exit 0; fi
if [ "$1" = "buildx" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ]; then echo "$@" >> "{compose_log}"; echo "SPARKBOT_FRONTEND_PORT=${{SPARKBOT_FRONTEND_PORT:-}}" >> "{compose_log}"; echo "SPARKBOT_FRONTEND_BIND_HOST=${{SPARKBOT_FRONTEND_BIND_HOST:-}}" >> "{compose_log}"; exit 0; fi
exit 1
""",
    )
    _write_executable(
        fake_bin / "ss",
        """#!/usr/bin/env sh
echo "State Recv-Q Send-Q Local Address:Port Peer Address:Port"
exit 0
""",
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)
    env_file.write_text(
        template.read_text()
        .replace("OPENAI_API_KEY=", "OPENAI_API_KEY=sk-existing")
        .replace("SPARKBOT_PASSPHRASE=sparkbot-local", "SPARKBOT_PASSPHRASE=existing-server-passphrase")
        + "\nSPARKBOT_FRONTEND_PORT=3105\nSPARKBOT_FRONTEND_BIND_HOST=0.0.0.0\n"
    )

    result = _run_start(
        [],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "SPARKBOT_PUBLIC_HOST": "203.0.113.20",
        },
    )

    assert result.returncode == 0
    assert "Running Sparkbot setup with requested options." not in result.stdout
    assert "Bind host: 0.0.0.0" in result.stdout
    assert "Open Sparkbot:\nhttp://203.0.113.20:3105" in result.stdout
    assert "SPARKBOT_FRONTEND_PORT=3105" in env_file.read_text()
    assert "SPARKBOT_FRONTEND_BIND_HOST=0.0.0.0" in env_file.read_text()
    assert "SPARKBOT_PASSPHRASE=existing-server-passphrase" in env_file.read_text()
    assert "SPARKBOT_FRONTEND_PORT=3105" in compose_log.read_text()
    assert "SPARKBOT_FRONTEND_BIND_HOST=0.0.0.0" in compose_log.read_text()


def test_complete_server_first_run_reaches_docker_startup_without_manual_env_edits(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    compose_log = tmp_path / "compose.log"
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env sh
if [ "$1" = "info" ]; then exit 0; fi
if [ "$1" = "buildx" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ]; then echo "$@" >> "{compose_log}"; exit 0; fi
exit 1
""",
    )
    _write_executable(
        fake_bin / "ss",
        """#!/usr/bin/env sh
echo "State Recv-Q Send-Q Local Address:Port Peer Address:Port"
exit 0
""",
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    compose_env = tmp_path / ".env"
    _template(template)

    result = _run_start(
        ["--server"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
            "SPARKBOT_COMPOSE_ENV_FILE": str(compose_env),
            "SPARKBOT_PUBLIC_HOST": "203.0.113.40",
            "SSH_CONNECTION": "203.0.113.5 55555 203.0.113.10 22",
        },
        input_text=(
            "sk-full-first-run\n"
            "\n"
            "\n"
            "\n"
            "\n"
            "\n"
            "n\n"
            "\n"
            "full-server-passphrase\n"
            "full-server-passphrase\n"
        ),
    )

    assert result.returncode == 0
    assert "Sparkbot setup" in result.stdout
    assert "Hidden input did not work in this terminal. Switching to visible input." in result.stderr
    assert "Starting Sparkbot in the background" in result.stdout
    assert "Open Sparkbot:\nhttp://203.0.113.40:3000" in result.stdout
    assert "compose.local.yml up --build -d" in compose_log.read_text()
    content = env_file.read_text()
    assert "OPENAI_API_KEY=sk-full-first-run" in content
    assert "SPARKBOT_PASSPHRASE=full-server-passphrase" in content
    assert "SPARKBOT_FRONTEND_BIND_HOST=0.0.0.0" in content
    assert "V1_LOCAL_MODE=false" in content
    assert "full-server-passphrase" not in result.stdout
    assert "full-server-passphrase" not in result.stderr


def test_compose_local_uses_legacy_compatible_env_file_syntax() -> None:
    content = LOCAL_COMPOSE.read_text()

    assert "required: false" not in content
    assert "path: .env.local" not in content
    assert "env_file:\n      - .env.local" in content
    assert '"${SPARKBOT_FRONTEND_BIND_HOST:-127.0.0.1}:${SPARKBOT_FRONTEND_PORT:-3000}:80"' in content
    assert "VITE_V1_LOCAL_MODE=${VITE_V1_LOCAL_MODE:-false}" in content
    assert "OPENAI_API_KEY=${OPENAI_API_KEY:-}" not in content
    assert "SPARKBOT_PASSPHRASE=${SPARKBOT_PASSPHRASE:-sparkbot-local}" not in content


def test_start_script_has_no_hidden_only_passphrase_prompt() -> None:
    content = START_SCRIPT.read_text()

    assert "--show-passphrase-input" in content
    assert "Hidden input did not work in this terminal. Switching to visible input." in content
    assert "read -r -s value" in content
    assert "read_passphrase_visible" in content


def test_compose_local_prestart_waits_for_database_health() -> None:
    content = LOCAL_COMPOSE.read_text()

    assert "prestart:" in content
    assert "db:\n        condition: service_healthy" in content
    assert "command: bash scripts/prestart.sh" in content


def test_start_script_prefers_docker_compose_v2_path(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log_file = tmp_path / "compose.log"
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env sh
echo "$@" >> "{log_file}"
if [ "$1" = "info" ]; then exit 0; fi
if [ "$1" = "buildx" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ] && [ "$2" = "version" ]; then exit 0; fi
if [ "$1" = "compose" ]; then exit 0; fi
exit 1
""",
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        ["--openai-key", "sk-v2-start"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
        },
    )

    assert result.returncode == 0
    assert "Using legacy docker-compose compatibility mode" not in result.stdout
    assert "compose -f compose.local.yml up --build" in log_file.read_text()


def test_start_script_prints_legacy_mode_and_uses_docker_compose(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log_file = tmp_path / "compose.log"
    _write_executable(
        fake_bin / "docker",
        "#!/usr/bin/env sh\n[ \"$1\" = \"info\" ] && exit 0\n[ \"$1\" = \"buildx\" ] && [ \"$2\" = \"version\" ] && exit 0\nexit 1\n",
    )
    _write_executable(
        fake_bin / "docker-compose",
        f"""#!/usr/bin/env sh
echo "$@" >> "{log_file}"
exit 0
""",
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        ["--openai-key", "sk-v1-start"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
        },
    )

    assert result.returncode == 0
    assert "Using legacy docker-compose compatibility mode" in result.stdout
    assert "-f compose.local.yml up --build" in log_file.read_text()


def test_start_script_legacy_compose_without_buildx_fails_before_raw_buildkit_error(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log_file = tmp_path / "compose.log"
    _write_executable(
        fake_bin / "docker",
        "#!/usr/bin/env sh\n[ \"$1\" = \"info\" ] && exit 0\nexit 1\n",
    )
    _write_executable(
        fake_bin / "docker-compose",
        f"""#!/usr/bin/env sh
echo "$@" >> "{log_file}"
exit 0
""",
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        ["--openai-key", "sk-no-buildx"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
        },
    )

    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "Using legacy docker-compose compatibility mode" in result.stdout
    assert "Docker buildx is missing or not working." in result.stderr
    assert "docker-buildx-plugin docker-compose-plugin" in result.stderr
    assert "BuildKit is enabled but the buildx component is missing or broken" not in combined
    assert not log_file.exists()


def test_start_script_install_docker_plugins_then_prefers_modern_compose(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    installed_marker = tmp_path / "plugins-installed"
    compose_log = tmp_path / "compose.log"
    sudo_log = tmp_path / "sudo.log"
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env sh
if [ "$1" = "info" ]; then exit 0; fi
if [ "$1" = "buildx" ] && [ "$2" = "version" ] && [ -f "{installed_marker}" ]; then exit 0; fi
if [ "$1" = "compose" ] && [ "$2" = "version" ] && [ -f "{installed_marker}" ]; then exit 0; fi
if [ "$1" = "compose" ] && [ -f "{installed_marker}" ]; then echo "$@" >> "{compose_log}"; exit 0; fi
exit 1
""",
    )
    _write_executable(
        fake_bin / "docker-compose",
        f"""#!/usr/bin/env sh
echo "$@" >> "{compose_log}"
exit 0
""",
    )
    _write_executable(
        fake_bin / "sudo",
        f"""#!/usr/bin/env sh
echo "$@" >> "{sudo_log}"
touch "{installed_marker}"
exit 0
""",
    )
    template = tmp_path / ".env.local.example"
    env_file = tmp_path / ".env.local"
    _template(template)

    result = _run_start(
        ["--install-docker-plugins", "--openai-key", "sk-install-path"],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPARKBOT_ENV_FILE": str(env_file),
            "SPARKBOT_ENV_TEMPLATE": str(template),
        },
    )

    assert result.returncode == 0
    assert "Installing Docker Compose v2 and buildx plugins with apt..." in result.stdout
    assert "apt update" in sudo_log.read_text()
    assert "apt install docker-buildx-plugin docker-compose-plugin -y" in sudo_log.read_text()
    assert "Using legacy docker-compose compatibility mode" not in result.stdout
    assert "compose -f compose.local.yml up --build" in compose_log.read_text()
