"""Claude adapter checks: python -m unittest discover -s tests -p test_roundtable_claude_adapter.py

Uses a fake `claude` executable (no network, no model, no login) that records
how it was launched, so the isolation flags and environment can be verified.
"""
import importlib.util
import json
import os
import stat
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("roundtable_claude", ROOT / "sparkbot-roundtable.py")
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)

FAKE_CLAUDE = textwrap.dedent(
    """\
    #!{python}
    import json, os, sys, time
    record = os.environ.get("FAKE_CLAUDE_RECORD") or "{record}"
    if sys.argv[1:] == ["--help"]:
        if "{mode}" == "oldcli":
            print("Usage: claude --print --model")
        else:
            print("Usage: claude --tools --strict-mcp-config --mcp-config --setting-sources --disable-slash-commands --no-session-persistence")
        sys.exit(0)
    prompt = sys.stdin.read()
    with open(record, "w") as f:
        json.dump({{"argv": sys.argv[1:], "env": sorted(os.environ), "cwd": os.getcwd(),
                   "prompt_len": len(prompt), "mcp": open(sys.argv[sys.argv.index("--mcp-config") + 1]).read()}}, f)
    mode = "{mode}"
    if mode == "sleep":
        time.sleep(30)
    if mode == "empty":
        sys.exit(0)
    if mode == "fail":
        sys.exit(3)
    print("Claude here: I read " + str(len(prompt)) + " chars of room data.")
    """
)


def make_fake(directory: Path, mode: str = "ok") -> tuple[Path, Path]:
    record = directory / "record.json"
    exe = directory / "claude"
    exe.write_text(FAKE_CLAUDE.format(python=sys.executable, record=record, mode=mode))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe, record


@unittest.skipIf(os.name == "nt", "fake executable uses a POSIX shebang")
class ClaudeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_adapter(self, mode="ok", timeout=20, checkpoint=lambda: None, extra_env=None):
        exe, record = make_fake(self.dir, mode)
        env = {"ANTHROPIC_API_KEY": "sk-should-not-leak", "SPARKBOT_SEAT_KEY": "rts_should_not_leak"}
        env.update(extra_env or {})
        with patch.object(rt, "claude_executable", return_value=str(exe)), patch.dict(os.environ, env):
            adapter = rt.ClaudeAdapter(timeout)
            prompt = rt.runner_prompt(rt.runner_sample_job(), "Meridian")
            result = adapter.run(prompt, checkpoint)
        return result, (json.loads(record.read_text()) if record.exists() else None)

    def test_registered(self):
        self.assertIs(rt.RUNNER_ADAPTERS["claude"], rt.ClaudeAdapter)

    def test_reply_and_isolation(self):
        reply, seen = self.run_adapter()
        self.assertTrue(reply.startswith("Claude here: I read"))
        argv = seen["argv"]
        self.assertIn("-p", argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "")
        self.assertIn("--strict-mcp-config", argv)
        self.assertEqual(json.loads(seen["mcp"]), {"mcpServers": {}})
        self.assertEqual(argv[argv.index("--setting-sources") + 1], "local")
        for flag in ("--disable-slash-commands", "--no-session-persistence"):
            self.assertIn(flag, argv)
        self.assertNotIn("--bare", argv)  # --bare would ignore the subscription login
        # Prompt goes through stdin, never argv.
        self.assertTrue(all("ROOM DATA" not in a for a in argv))
        self.assertGreater(seen["prompt_len"], 100)
        # No API key, no seat key in the agent's environment.
        self.assertNotIn("ANTHROPIC_API_KEY", seen["env"])
        self.assertNotIn("SPARKBOT_SEAT_KEY", seen["env"])
        # Fresh empty working directory, removed afterwards.
        self.assertIn("roundtable-run-", seen["cwd"])
        self.assertFalse(Path(seen["cwd"]).exists())

    def test_fail_closed_without_isolation_flags(self):
        with self.assertRaisesRegex(rt.RoundtableError, "isolation flags"):
            self.run_adapter(mode="oldcli")

    def test_timeout_kills_agent(self):
        start = time.monotonic()
        with self.assertRaisesRegex(rt.RoundtableError, "timeout"):
            self.run_adapter(mode="sleep", timeout=1)
        self.assertLess(time.monotonic() - start, 15)

    def test_checkpoint_cancel_stops_agent(self):
        calls = {"n": 0}

        def checkpoint():
            calls["n"] += 1
            if calls["n"] >= 3:
                raise rt.RoundtableError("cancelled", 409)

        start = time.monotonic()
        with self.assertRaises(rt.RoundtableError):
            self.run_adapter(mode="sleep", timeout=60, checkpoint=checkpoint)
        self.assertLess(time.monotonic() - start, 15)

    def test_empty_and_failed_runs_raise(self):
        with self.assertRaisesRegex(rt.RoundtableError, "empty"):
            self.run_adapter(mode="empty")
        with self.assertRaisesRegex(rt.RoundtableError, "Claude failed"):
            self.run_adapter(mode="fail")


class ClaudeExecutableTests(unittest.TestCase):
    def test_windows_npm_shim_resolves_to_native_binary(self):
        with tempfile.TemporaryDirectory() as d:
            shim = Path(d) / "claude.cmd"
            shim.write_text("@echo off")
            native = Path(d) / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
            native.parent.mkdir(parents=True)
            native.write_bytes(b"MZ")
            with patch.object(rt.shutil, "which", return_value=str(shim)):
                self.assertEqual(rt.claude_executable(), str(native))

    def test_missing_binary_raises(self):
        with tempfile.TemporaryDirectory() as d:
            shim = Path(d) / "claude.cmd"
            shim.write_text("@echo off")
            with patch.object(rt.shutil, "which", return_value=str(shim)):
                with self.assertRaises(rt.RoundtableError):
                    rt.claude_executable()
        with patch.object(rt.shutil, "which", return_value=None):
            with self.assertRaises(rt.RoundtableError):
                rt.claude_executable()


if __name__ == "__main__":
    unittest.main()
