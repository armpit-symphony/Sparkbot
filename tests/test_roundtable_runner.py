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
    return {"id": "00000000-0000-0000-0000-000000000001", "claim_token": "secret-claim", "attempt": 1,
            "room": {"id": "room-1", "name": "Pilot"},
            "trigger": {"id": "message-1", "sender_name": "Phil", "content": "@atlas explain the pilot"},
            "context": [], "limits": {"max_reply_chars": 8000, "lease_seconds": 600}}


class FakeStore:
    def __init__(self, allowed=True):
        self.events = []
        self.allowed = allowed

    def audit(self, event, job_id=""):
        self.events.append(event)

    def reserve(self):
        return self.allowed


class FakeClient:
    def __init__(self):
        self.calls = []
        self.message = None
        self.posts = 0

    def next_job(self):
        return sample_job()

    def job_action(self, job, action, **fields):
        self.calls.append((action, fields))
        if action == "complete":
            if self.message is None:
                self.posts += 1
                self.message = {"id": "reply", "content": fields["content"]}
            return {"job": {"status": "done"}, "message": self.message}
        return {"job": {"status": "claimed"}}


class FakeAdapter:
    def __init__(self, effect=None):
        self.runs = 0
        self.effect = effect

    def run(self, prompt, checkpoint):
        self.runs += 1
        checkpoint()
        return self.effect() if self.effect else "Pilot reply"


class RunnerTests(unittest.TestCase):
    def test_cancelled_claim_preflight_never_spends_model_run(self):
        runner = self.make_runner()
        def cancelled(*args, **kwargs):
            raise rt.RoundtableError("cancelled", 409)
        runner.client.job_action = cancelled
        runner.run(once=True)
        self.assertEqual(runner.adapter.runs, 0)

    def test_interrupt_during_completion_does_not_release_job(self):
        runner = self.make_runner()
        original = runner.client.job_action
        def action(job, action, **fields):
            result = original(job, action, **fields)
            if action == "complete":
                raise KeyboardInterrupt()
            return result
        runner.client.job_action = action
        with self.assertRaises(KeyboardInterrupt):
            runner.run()
        self.assertEqual(runner.client.posts, 1)
        self.assertNotIn("fail", [a for a, _ in runner.client.calls])

    def test_access_revocation_stops_runner(self):
        runner = self.make_runner()
        def denied(*args, **kwargs):
            raise rt.RoundtableError("revoked", 403)
        runner.client.job_action = denied
        with self.assertRaises(rt.RoundtableError):
            runner.run()
        self.assertEqual(runner.adapter.runs, 0)

    def test_invalid_limits_rejected_without_auth(self):
        with patch.object(rt, "Session") as session, \
             patch.object(rt.sys, "stderr", new_callable=io.StringIO):
            self.assertEqual(rt.main(["run", "--runs-per-hour", "100"]), 1)
            session.assert_not_called()

    def make_runner(self, client=None, adapter=None, store=None, **kwargs):
        return rt.Runner(client or FakeClient(), adapter or FakeAdapter(),
                         store or FakeStore(), "Atlas", sleep=lambda _: None, **kwargs)

    def test_once_signs_and_completes_without_direct_post(self):
        runner = self.make_runner()
        runner.run(once=True)
        self.assertEqual(runner.client.posts, 1)
        self.assertIn("Signed: Atlas", runner.client.message["content"])
        self.assertEqual(runner.adapter.runs, 1)
        self.assertEqual(runner.store.events[-1], "runner_stopped")

    def test_lost_ack_retries_same_completion_without_rerun(self):
        client = FakeClient()
        original = client.job_action
        first = True
        def action(job, action, **fields):
            nonlocal first
            result = original(job, action, **fields)
            if action == "complete" and first:
                first = False
                raise OSError("lost acknowledgement")
            return result
        client.job_action = action
        runner = self.make_runner(client=client)
        runner.run(once=True)
        self.assertEqual(client.posts, 1)
        self.assertEqual(runner.adapter.runs, 1)
        completions = [fields for action, fields in client.calls if action == "complete"]
        self.assertEqual(len(completions), 2)
        self.assertEqual(completions[0], completions[1])

    def test_unacknowledged_completion_stops_without_fail_or_rerun(self):
        client = FakeClient()
        original = client.job_action
        def action(job, action, **fields):
            result = original(job, action, **fields)
            if action == "complete":
                raise OSError("connection lost")
            return result
        client.job_action = action
        runner = self.make_runner(client=client)
        with self.assertRaises(rt.CompletionUncertain):
            runner.run()
        self.assertEqual(client.posts, 1)
        self.assertNotIn("fail", [a for a, _ in client.calls])
        self.assertEqual(runner.adapter.runs, 1)

    def test_pause_heartbeat_stops_without_completion(self):
        client = FakeClient()
        original = client.job_action
        def action(job, action, **fields):
            if action == "heartbeat" and fields["note"] == "working":
                raise rt.RoundtableError("cancelled", 409)
            return original(job, action, **fields)
        client.job_action = action
        clock = iter([0, 61])
        runner = self.make_runner(client=client, clock=lambda: next(clock))
        runner.run(once=True)
        self.assertEqual(client.posts, 0)
        self.assertIn("claim_lost_or_cancelled", runner.store.events)

    def test_ctrl_c_requests_retry_before_completion(self):
        def interrupt():
            raise KeyboardInterrupt()
        runner = self.make_runner(adapter=FakeAdapter(interrupt))
        with self.assertRaises(KeyboardInterrupt):
            runner.run()
        self.assertEqual(runner.client.calls[-1], ("fail", {"error": "runner_interrupted", "retry": True}))

    def test_local_cap_never_invokes_model(self):
        runner = self.make_runner(store=FakeStore(False))
        runner.run(once=True)
        self.assertEqual(runner.adapter.runs, 0)
        self.assertEqual(runner.client.calls[-1][1]["error"], "local_hourly_cap")

    def test_reply_bound_includes_signature(self):
        runner = self.make_runner(adapter=FakeAdapter(lambda: "x" * 9000))
        runner.run(once=True)
        self.assertEqual(len(runner.client.message["content"]), 8000)

    def test_adapter_error_is_generic_in_fail(self):
        def error():
            raise rt.RoundtableError("secret-claim")
        runner = self.make_runner(adapter=FakeAdapter(error))
        runner.run(once=True)
        self.assertNotIn("secret-claim", json.dumps(runner.client.calls))
        self.assertEqual(runner.client.posts, 0)

    def test_invalid_job_cannot_launch(self):
        runner = self.make_runner()
        job = sample_job()
        job["id"] = "../../escape"
        with self.assertRaises(rt.RoundtableError):
            runner.process(job)
        self.assertEqual(runner.adapter.runs, 0)

    def test_no_job_does_not_launch(self):
        runner = self.make_runner()
        runner.client.next_job = lambda: None
        runner.run(once=True)
        self.assertEqual(runner.adapter.runs, 0)

    def test_poll_errors_are_bounded(self):
        runner = self.make_runner()
        def offline():
            raise OSError("offline")
        runner.client.next_job = offline
        with self.assertRaises(rt.RoundtableError):
            runner.run()
        self.assertEqual(runner.store.events.count("poll_retry"), 4)

    def test_job_api_uses_claim_token_and_25_second_poll(self):
        calls = []
        def transport(method, url, body, headers):
            calls.append((method, url, body))
            if url.endswith("/token"):
                return 200, {"access_token": "seat-token"}
            if "/next?" in url:
                return 204, None
            return 200, {"job": {"status": "claimed"}}
        client = rt.Client("https://example.invalid", "seat-key", transport)
        self.assertIsNone(client.next_job())
        client.job_action(sample_job(), "heartbeat", note="working")
        self.assertTrue(calls[1][1].endswith("/seats/jobs/next?wait=25"))
        self.assertEqual(calls[-1][2], {"claim_token": "secret-claim", "note": "working"})


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

    def test_context_bound_preserves_trigger_and_drops_oldest(self):
        job = sample_job()
        job["context"] = [{"content": "a" * 8000}] * 30
        prompt = rt.runner_prompt(job, "Atlas")
        self.assertLess(len(prompt.encode("utf-8")), 65000)
        self.assertIn("@atlas explain the pilot", prompt)
        job["trigger"]["content"] = "x" * 8001
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
