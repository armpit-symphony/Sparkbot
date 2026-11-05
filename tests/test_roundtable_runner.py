"""Offline runner checks: python -m unittest discover -s tests -p test_roundtable_runner.py."""
import importlib.util
import json
import io
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("rt", Path(__file__).resolve().parents[1] / "sparkbot-roundtable.py")
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)


def sample_job():
    return {"id": "job-1", "claim_token": "secret-claim", "attempt": 1,
            "room": {"id": "room-1", "name": "Pilot"},
            "trigger": {"id": "message-1", "sender_name": "Phil", "content": "@atlas explain the pilot"},
            "context": [], "limits": {"max_reply_chars": 8000, "lease_seconds": 600}}


class AdapterTests(unittest.TestCase):
    def test_quota_survives_restart_and_clock_rollback(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"ROUNDTABLE_HOME": d}):
            with rt.RunnerStore("atlas", 1) as store:
                self.assertTrue(store.reserve(10000))
                self.assertFalse(store.reserve(9000))
            with rt.RunnerStore("atlas", 1) as store:
                self.assertFalse(store.reserve(10001))
                self.assertTrue(store.reserve(13601))

    def test_corrupt_quota_fails_closed(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"ROUNDTABLE_HOME": d}):
            with rt.RunnerStore("atlas") as store:
                Path(str(store.base) + ".json").write_text("broken")
                with self.assertRaises(rt.RoundtableError):
                    store.reserve()

    def test_single_runner_lock_released_on_exit(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"ROUNDTABLE_HOME": d}):
            with rt.RunnerStore("atlas"):
                with self.assertRaises(rt.RoundtableError):
                    with rt.RunnerStore("atlas"):
                        pass
            with rt.RunnerStore("atlas"):
                pass

    def test_dry_run_never_loads_credentials_or_launches_process(self):
        with patch.object(rt, "Session") as session, patch.object(rt.subprocess, "Popen") as proc, \
             patch.object(rt.sys, "stdout", new_callable=io.StringIO) as output:
            self.assertEqual(rt.main(["run", "--profile", "atlas", "--dry-run"]), 0)
            data = json.loads(output.getvalue())
            self.assertEqual(data["model_calls"], 0)
            self.assertEqual(data["network_calls"], 0)
            session.assert_not_called()
            proc.assert_not_called()

    def run_fake(self, code, checkpoint=lambda: None, timeout=3):
        original_run = rt.subprocess.run
        def run(*args, **kwargs):
            if args[0][-1] == "--help":
                return rt.subprocess.CompletedProcess(args[0], 0, b"--ignore-user-config", b"")
            return original_run(*args, **kwargs)
        def command(executable, directory, output):
            return [sys.executable, "-c", code, output]
        with patch.object(rt, "codex_executable", return_value=sys.executable), \
             patch.object(rt, "codex_command", side_effect=command), \
             patch.object(rt.subprocess, "run", side_effect=run):
            return rt.CodexAdapter(timeout).run("offline sample", checkpoint)

    def test_real_subprocess_returns_final_file(self):
        result = self.run_fake("import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('hello', encoding='utf-8')")
        self.assertEqual(result, "hello")

    def test_timeout_terminates_subprocess(self):
        with self.assertRaisesRegex(rt.RoundtableError, "timeout"):
            self.run_fake("import time; time.sleep(30)", timeout=0.1)

    def test_lost_claim_terminates_subprocess(self):
        def revoked():
            raise rt.RoundtableError("claim cancelled", 409)
        with self.assertRaisesRegex(rt.RoundtableError, "cancelled"):
            self.run_fake("import time; time.sleep(30)", checkpoint=revoked)

    def test_empty_reply_is_not_published(self):
        with self.assertRaisesRegex(rt.RoundtableError, "empty"):
            self.run_fake("import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('')")

    def test_nonzero_exit_does_not_leak_stderr(self):
        with self.assertRaises(rt.RoundtableError) as error:
            self.run_fake("import sys; print('secret-claim',file=sys.stderr); sys.exit(1)")
        self.assertNotIn("secret-claim", str(error.exception))

    def test_prompt_does_not_pass_claim_or_credentials(self):
        job = sample_job()
        job["key"] = "secret-seat"
        prompt = rt.runner_prompt(job, "Atlas")
        self.assertNotIn("secret-claim", prompt)
        self.assertNotIn("secret-seat", prompt)
        self.assertIn("@atlas explain", prompt)
        self.assertIn("does not\nenable execution", prompt)

    def test_context_bound_rejects_oversize(self):
        job = sample_job()
        job["context"] = [{"content": "a" * 8000}] * 30
        with self.assertRaises(rt.RoundtableError):
            rt.runner_prompt(job, "Atlas")

    def test_environment_excludes_secrets_and_session_inheritance(self):
        with patch.dict(os.environ, {"PATH": "bin", "SPARKBOT_SEAT_KEY": "secret",
                                    "OPENAI_API_KEY": "secret", "CODEX_THREAD_ID": "parent",
                                    "CODEX_HOME": "existing-auth"}, clear=True):
            self.assertEqual(rt.runner_environment(), {"PATH": "bin", "CODEX_HOME": "existing-auth"})

    def test_command_is_noninteractive_and_isolated(self):
        cmd = rt.codex_command("codex", "empty", "out")
        for flag in ("--ignore-user-config", "--ignore-rules", "--ephemeral", "read-only",
                     'approval_policy="never"', 'forced_login_method="chatgpt"', 'mcp_servers={}'):
            self.assertIn(flag, cmd)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", cmd)
        for feature in ("apps", "hooks", "plugins", "shell_tool", "multi_agent"):
            self.assertEqual(cmd[cmd.index(feature) - 1], "--disable")
        self.assertEqual(cmd[-1], "-")

    def test_windows_shim_is_not_executed_as_shell(self):
        with tempfile.TemporaryDirectory() as d:
            shim = Path(d) / "codex.cmd"
            native = Path(d) / "node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x/bin/codex.exe"
            native.parent.mkdir(parents=True)
            native.touch()
            with patch.object(rt.shutil, "which", return_value=str(shim)):
                self.assertEqual(rt.codex_executable(), str(native))

    def test_unsupported_cli_fails_before_launch(self):
        with patch.object(rt, "codex_executable", return_value="codex"), \
             patch.object(rt.subprocess, "run") as probe, \
             patch.object(rt.subprocess, "Popen") as launch:
            probe.return_value.returncode = 0
            probe.return_value.stdout = b"old help"
            with self.assertRaises(rt.RoundtableError):
                rt.CodexAdapter().run("prompt", lambda: None)
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
