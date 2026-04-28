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


def _run_setup(args: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=ROOT,
        env=merged_env,
        text=True,
        capture_output=True,
        check=False,
    )


def _run_start(args: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env.update(env)
    return subprocess.run(
        ["bash", str(START_SCRIPT), *args],
        cwd=ROOT,
        env=merged_env,
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


def test_hidden_input_prompt_warns_user_and_keeps_secret_out_of_output(tmp_path: Path) -> None:
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
    )

    assert result.returncode != 0
    assert "Input will be hidden. Paste/type your key, then press Enter." in result.stderr


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
        input="sk-visible-input\n\n\n\n\n\n\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Input will be hidden" not in result.stderr
    assert "OPENAI_API_KEY=sk-visible-input" in env_file.read_text()


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


def test_start_script_passes_setup_args_through(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "docker",
        """#!/usr/bin/env sh
if [ "$1" = "info" ]; then exit 0; fi
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


def test_compose_local_uses_legacy_compatible_env_file_syntax() -> None:
    content = LOCAL_COMPOSE.read_text()

    assert "required: false" not in content
    assert "path: .env.local" not in content
    assert "env_file:\n      - .env.local" in content


def test_start_script_prefers_docker_compose_v2_path(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log_file = tmp_path / "compose.log"
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env sh
echo "$@" >> "{log_file}"
if [ "$1" = "info" ]; then exit 0; fi
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
