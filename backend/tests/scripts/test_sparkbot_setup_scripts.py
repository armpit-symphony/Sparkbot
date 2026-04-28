from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "sparkbot-setup.sh"


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
