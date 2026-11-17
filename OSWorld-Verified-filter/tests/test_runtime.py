"""Exercise guest/bootstrap boundaries without starting a process or VM."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load(name: str):
    spec = importlib.util.spec_from_file_location("osworld_filter_test_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bootstrap = load("guest_bootstrap")
guest_actor = load("guest_actor")
runtime = load("runtime")


class GuestBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.key = "test-private-model-key-8715"
        uv_bytes = b"fake Linux uv bytes for offline tests"
        bundle = self.root / "runtime-bundle.tar.gz"
        with tarfile.open(bundle, "w:gz") as archive:
            for name, raw in {"uv": uv_bytes, "guest_actor.py": b"# frozen actor\n",
                              "product/pyproject.toml": b"[project]\nname='test'\n"}.items():
                member = tarfile.TarInfo(name)
                member.size = len(raw)
                archive.addfile(member, io.BytesIO(raw))
        self.job_path = self.root / "job.json"
        self.job = {
            "kind": "actor", "guest_root": str(self.root),
            "bundle_sha256": bootstrap.digest(bundle),
            "uv_binary_sha256": hashlib.sha256(uv_bytes).hexdigest(),
            "guest_python": "3.12.13", "bootstrap_timeout_seconds": 30,
            "actor_grace_seconds": 10,
            "actor_config": {"api_key": self.key, "timeout_seconds": 60},
        }
        self.job_path.write_text(json.dumps(self.job))

    def invoke(self, side_effect):
        with mock.patch.object(sys, "argv", ["guest_bootstrap.py", str(self.job_path)]), \
                mock.patch.object(bootstrap, "run_child", side_effect=side_effect) as child, \
                mock.patch.object(bootstrap.os, "umask"):
            result = bootstrap.main()
        state = json.loads((self.root / "bootstrap-state.json").read_text())
        return result, state, child

    def test_install_failure_is_failed_bootstrap_not_an_actor_rejection(self):
        result, state, child = self.invoke([9])
        self.assertEqual(result, 1)
        self.assertEqual(child.call_count, 1)
        self.assertEqual(state["stage"], "failed")
        self.assertIn("uv sync failed", state["error"])
        self.assertFalse((self.root / "actor-result.json").exists())
        self.assertFalse(self.job_path.exists())

    def test_actor_process_timeout_remains_a_technical_failure(self):
        result, state, child = self.invoke([0, subprocess.TimeoutExpired("actor", 70)])
        self.assertEqual(result, 1)
        self.assertEqual(child.call_count, 2)
        self.assertEqual(state["stage"], "failed")
        self.assertEqual(state["error_type"], "TimeoutExpired")
        self.assertNotIn("agent_success", state)
        self.assertNotIn("score", state)

    def test_product_install_uses_frozen_lock_without_credentials_in_argv_or_env(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": self.key, "OPENAI_MODEL": "private"}):
            result, state, child = self.invoke([0, 0])
        self.assertEqual(result, 0)
        self.assertEqual(state["stage"], "finished")
        install = child.call_args_list[0]
        self.assertIn("--frozen", install.args[0])
        self.assertIn("--no-dev", install.args[0])
        self.assertNotIn(self.key, repr(child.call_args_list))
        self.assertNotIn("OPENAI_API_KEY", install.kwargs["environment"])
        self.assertNotIn("OPENAI_MODEL", install.kwargs["environment"])

    def test_wrong_uploaded_bundle_is_rejected_before_install(self):
        (self.root / "runtime-bundle.tar.gz").write_bytes(b"corrupt upload")
        result, state, child = self.invoke([])
        self.assertEqual(result, 1)
        self.assertEqual(child.call_count, 0)
        self.assertEqual(state["stage"], "failed")
        self.assertIn("digest mismatch", state["error"])

    def test_public_archive_excludes_job_product_cache_and_redacts_logs(self):
        (self.root / "install.log").write_text("error " + self.key)
        output = self.root / "actor-output"
        output.mkdir()
        (output / "result.json").write_text(json.dumps({"error": self.key}))
        (self.root / "product").mkdir()
        (self.root / "product/private.txt").write_text(self.key)
        (self.root / "uv-cache").mkdir()
        (self.root / "uv-cache/private.txt").write_text(self.key)
        archive = bootstrap.archive_public_output(self.root, [self.key])
        with tarfile.open(archive) as stream:
            names = stream.getnames()
            self.assertFalse(any(name.startswith(("job.json", "product", "uv-cache")) for name in names))
            for member in stream.getmembers():
                if member.isfile():
                    self.assertNotIn(self.key.encode(), stream.extractfile(member).read())
        self.assertIn("[REDACTED]", (self.root / "install.log").read_text())

    def test_runtime_archive_cannot_escape_guest_root_or_install_symlinks(self):
        for name, link in [("../outside", False), ("safe/link", True)]:
            with self.subTest(name=name):
                archive = self.root / "unsafe.tar.gz"
                with tarfile.open(archive, "w:gz") as stream:
                    member = tarfile.TarInfo(name)
                    if link:
                        member.type = tarfile.SYMTYPE
                        member.linkname = "/etc/passwd"
                        stream.addfile(member)
                    else:
                        member.size = 1
                        stream.addfile(member, io.BytesIO(b"x"))
                with self.assertRaisesRegex(RuntimeError, "Unsafe runtime bundle member"):
                    bootstrap.unpack(archive, self.root / "extracted")


class GuestActorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.key = "test-private-key-from-actor-0953"
        self.job_path = self.root / "job.json"
        self.job = {"kind": "actor", "guest_root": str(self.root), "instruction": "Read the task file.",
                    "actor_config": {"api_key": self.key}, "cdp_url": "http://127.0.0.1:9222"}
        self.job_path.write_text(json.dumps(self.job))

    def test_actor_removes_private_job_before_product_can_read_task_files(self):
        async def actor(job, root):
            self.assertFalse(self.job_path.exists())
            self.assertEqual(job["actor_config"]["api_key"], self.key)
            return {"status": "finished", "result": {"status": "completed", "agent_success": True}}

        with mock.patch.object(sys, "argv", ["guest_actor.py", str(self.job_path)]), \
                mock.patch.object(guest_actor, "actor", actor):
            result = guest_actor.main()
        self.assertEqual(result, 0)
        self.assertEqual(json.loads((self.root / "actor-result.json").read_text())["status"], "finished")

    def test_unhandled_product_crash_is_an_error_not_agent_success_false(self):
        async def crash(job, root):
            raise RuntimeError("model transport crash: " + self.key)

        with mock.patch.object(sys, "argv", ["guest_actor.py", str(self.job_path)]), \
                mock.patch.object(guest_actor, "actor", crash):
            result = guest_actor.main()
        self.assertEqual(result, 1)
        path = self.root / "actor-result.json"
        raw = path.read_text()
        self.assertNotIn(self.key, raw)
        value = json.loads(raw)
        self.assertEqual(value["status"], "error")
        self.assertEqual(value["error_type"], "RuntimeError")
        self.assertNotIn("agent_success", value)
        self.assertNotIn("score", value)

    def test_effective_prompt_audit_keeps_original_instruction_hash(self):
        import asyncio
        captured = {}

        class Config:
            def __init__(self, **values):
                captured["config"] = values

        async def run_task(prompt, config, output):
            captured.update(prompt=prompt, output=output)
            return {"status": "completed", "agent_success": False}

        config_module = types.ModuleType("lexmount_browser_agent.config")
        config_module.AgentConfig = Config
        runner_module = types.ModuleType("lexmount_browser_agent.runner")
        runner_module.run_task = run_task
        with mock.patch.dict(sys.modules, {"lexmount_browser_agent.config": config_module,
                                           "lexmount_browser_agent.runner": runner_module}), \
                mock.patch.object(guest_actor, "engine_metadata", return_value={"packages": {}}):
            result = asyncio.run(guest_actor.actor(self.job, self.root))
        self.assertEqual(result["status"], "finished")
        self.assertFalse(result["result"]["agent_success"])
        self.assertEqual(result["instruction_sha256"],
                         hashlib.sha256(self.job["instruction"].encode()).hexdigest())
        self.assertEqual(result["effective_prompt_sha256"],
                         hashlib.sha256(captured["prompt"].encode()).hexdigest())
        self.assertTrue(captured["prompt"].startswith(self.job["instruction"]))
        self.assertEqual(captured["config"]["cdp_url"], self.job["cdp_url"])
        self.assertEqual(captured["output"], self.root / "actor-output")


class OfficialOutcomeTests(unittest.TestCase):
    @staticmethod
    def actor(status="completed", success=True):
        return {"status": "finished", "result": {"status": status, "agent_success": success}}

    def test_only_completed_explicit_false_maps_to_official_infeasible_fail(self):
        for status, success, terminal in [("completed", False, "FAIL"), ("completed", True, "DONE"),
                                          ("completed", None, None), ("timeout", False, None),
                                          ("max_steps", False, None)]:
            with self.subTest(status=status, success=success):
                env = mock.Mock()
                env.evaluate.return_value = 0.375
                receipt = {"score": None}
                runtime._finish_task(env, self.actor(status, success), receipt)
                if terminal is None:
                    env.step.assert_not_called()
                else:
                    env.step.assert_called_once_with(terminal, 0)
                env.evaluate.assert_called_once_with()
                self.assertEqual(receipt["official_terminal_action"], terminal)
                self.assertEqual(receipt["status"], "scored")
                self.assertEqual(receipt["score"], 0.375)

    def test_timeout_and_budget_stop_cannot_earn_infeasible_credit_by_false_flag(self):
        class InfeasibleEnv:
            def __init__(self):
                self.actions = []
            def step(self, action, pause):
                self.actions.append(action)
            def evaluate(self):
                return 1 if self.actions and self.actions[-1] == "FAIL" else 0

        for status in ("timeout", "max_steps"):
            with self.subTest(status=status):
                env, receipt = InfeasibleEnv(), {}
                runtime._finish_task(env, self.actor(status, False), receipt)
                self.assertEqual(env.actions, [])
                self.assertEqual(receipt["score"], 0.0)

    def test_ordinary_actor_error_or_unfinished_process_is_not_sent_to_grader(self):
        for actor in [self.actor("error", False), {"status": "error", "result": {}},
                      {"status": "finished"}, {"status": "starting"}]:
            with self.subTest(actor=actor):
                env, receipt = mock.Mock(), {"score": None}
                with self.assertRaises(RuntimeError):
                    runtime._finish_task(env, actor, receipt)
                env.step.assert_not_called()
                env.evaluate.assert_not_called()
                self.assertIsNone(receipt["score"])

    def test_evaluator_crash_leaves_no_score(self):
        env, receipt = mock.Mock(), {"score": None}
        env.evaluate.side_effect = RuntimeError("Reference unavailable")
        with self.assertRaisesRegex(RuntimeError, "Reference unavailable"):
            runtime._finish_task(env, self.actor(), receipt)
        self.assertIsNone(receipt["score"])
        self.assertNotEqual(receipt.get("status"), "scored")

    def test_invalid_grader_values_cannot_be_coerced_into_valid_scores(self):
        for value in [True, False, "0.5", None, float("nan"), float("inf"), -0.1, 1.1]:
            with self.subTest(value=value):
                env, receipt = mock.Mock(), {"score": None}
                env.evaluate.return_value = value
                with self.assertRaises((RuntimeError, ValueError, TypeError)):
                    runtime._finish_task(env, self.actor(), receipt)
                self.assertIsNone(receipt["score"])
                self.assertNotEqual(receipt.get("status"), "scored")


class HostRunFailureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run_dir = Path(self.temp.name)
        self.item = json.loads((ROOT / "data/manifest.json").read_text())["tasks"][0]
        self.key = "test-host-secret-67619"
        self.metadata = {"task_count": 76, "upstream_commit": runtime.UPSTREAM_COMMIT,
                         "harness_root": str(ROOT), "guest_root": "/tmp/lexmount-test-owned-guest",
                         "config": json.loads((ROOT / "config.json").read_text())}
        (self.run_dir / "run.json").write_text(json.dumps(self.metadata))
        (self.run_dir / "probe.json").write_text(json.dumps({
            "status": "passed", "run_metadata_sha256": runtime._digest(self.run_dir / "run.json")}))
        self.private = self.run_dir / "private-model.json"
        self.private.write_text(json.dumps({"base_url": "https://model.invalid/v1", "api_key": self.key}))
        self.folder = self.run_dir / "tasks" / self.item["task_id"]
        self.env = mock.Mock()
        self.env.evaluate.return_value = 0.625
        self.env.controller.end_recording.side_effect = lambda path: Path(path).write_bytes(b"fake video")

    def invoke(self, *, reset_error=None, cdp_error=None, state=None, actor=None, wait_error=None):
        if reset_error is not None:
            self.env.reset.side_effect = reset_error

        @contextmanager
        def environment(metadata, folder, receipt):
            try:
                yield self.env
            finally:
                receipt["owned_vm_closed"] = True

        with mock.patch.object(runtime, "_environment", environment) as context, \
                mock.patch.object(runtime, "_save_screenshot"), \
                mock.patch.object(runtime, "_ensure_cdp", side_effect=cdp_error,
                                  return_value={"endpoint": "http://127.0.0.1:9222"}), \
                mock.patch.object(runtime, "_launch_job", return_value=1234) as launch, \
                mock.patch.object(runtime, "_wait_job", side_effect=wait_error,
                                  return_value=state or {"stage": "finished", "phase": "actor"}) as wait, \
                mock.patch.object(runtime, "_collect", return_value=actor or {
                    "status": "finished", "result": {"status": "completed", "agent_success": True}}):
            summary = runtime.run_tasks(self.run_dir, self.private, [self.item["task_id"]])
        receipt = json.loads((self.folder / "receipt.json").read_text())
        return summary, receipt, launch, wait

    def assert_private_key_not_in_evidence(self):
        for path in self.folder.rglob("*"):
            if path.is_file():
                self.assertNotIn(self.key.encode(), path.read_bytes(), str(path))

    def test_setup_failure_is_unscored_and_never_starts_actor(self):
        summary, receipt, launch, _ = self.invoke(reset_error=RuntimeError("setup: " + self.key))
        self.assertEqual(summary["invalid"], 1)
        self.assertEqual(receipt["status"], "setup_error")
        self.assertIsNone(receipt["score"])
        launch.assert_not_called()
        self.env.evaluate.assert_not_called()
        self.assert_private_key_not_in_evidence()

    def test_install_failure_is_unscored_not_fail_action(self):
        summary, receipt, _, _ = self.invoke(state={"stage": "failed"}, actor={"status": "error"})
        self.assertEqual(summary["invalid"], 1)
        self.assertEqual(receipt["status"], "bootstrap_error")
        self.assertIsNone(receipt["score"])
        self.env.step.assert_not_called()
        self.env.evaluate.assert_not_called()

    def test_outer_timeout_is_unscored_not_infeasible_success(self):
        _, receipt, _, _ = self.invoke(wait_error=TimeoutError("guest timeout " + self.key))
        self.assertEqual(receipt["status"], "transport_error")
        self.assertIsNone(receipt["score"])
        self.env.step.assert_not_called()
        self.env.evaluate.assert_not_called()
        self.assert_private_key_not_in_evidence()

    def test_native_actor_crash_remains_unscored(self):
        _, receipt, _, _ = self.invoke(actor={
            "status": "finished", "result": {"status": "error", "agent_success": False}})
        self.assertEqual(receipt["status"], "actor_error")
        self.assertIsNone(receipt["score"])
        self.env.step.assert_not_called()
        self.env.evaluate.assert_not_called()

    def test_official_evaluation_failure_is_a_technical_error(self):
        self.env.evaluate.side_effect = RuntimeError("reference read failed " + self.key)
        _, receipt, _, _ = self.invoke()
        self.assertEqual(receipt["status"], "evaluation_error")
        self.assertIsNone(receipt["score"])
        self.assert_private_key_not_in_evidence()

    def test_successful_round_uses_original_float_grader_and_closes_owned_vm(self):
        summary, receipt, _, _ = self.invoke()
        self.assertEqual(summary["scored"], 1)
        self.assertEqual(receipt["status"], "scored")
        self.assertEqual(receipt["score"], 0.625)
        self.assertTrue(receipt["owned_vm_closed"])
        self.assertEqual(receipt["task_sha256"], self.item["sha256"])
        self.env.reset.assert_called_once()
        self.env.evaluate.assert_called_once()

    def test_resume_preserves_existing_legal_or_technical_receipt_without_rejudge(self):
        self.folder.mkdir(parents=True)
        path = self.folder / "receipt.json"
        for status in ("scored", "evaluation_error", "interrupted"):
            with self.subTest(status=status):
                value = {"task_id": self.item["task_id"], "status": status, "score": 0.125 if status == "scored" else None}
                path.write_text(json.dumps(value))
                before = path.read_bytes()
                summary, receipt, launch, wait = self.invoke()
                self.assertEqual(summary["skipped_existing"], 1)
                self.assertEqual(path.read_bytes(), before)
                launch.assert_not_called()
                wait.assert_not_called()
        self.env.reset.assert_not_called()

    def test_interrupted_attempt_is_preserved_and_not_silently_retried(self):
        self.folder.mkdir(parents=True)
        previous = self.folder / "events.jsonl"
        previous.write_text('previous partial trajectory\n')
        summary, receipt, launch, _ = self.invoke()
        self.assertEqual(summary["invalid"], 1)
        self.assertEqual(receipt["status"], "interrupted")
        self.assertIsNone(receipt["score"])
        self.assertEqual(previous.read_text(), 'previous partial trajectory\n')
        launch.assert_not_called()
        self.env.reset.assert_not_called()

    def test_task_byte_hash_mismatch_is_rejected_before_vm_or_actor(self):
        original_digest = runtime._digest
        task_path = ROOT / self.item["task_path"]
        def digest(path):
            return "f" * 64 if Path(path) == task_path else original_digest(path)
        with mock.patch.object(runtime, "_digest", side_effect=digest):
            _, receipt, launch, _ = self.invoke()
        self.assertEqual(receipt["status"], "setup_error")
        self.assertIsNone(receipt["score"])
        self.assertIn("hash mismatch", receipt["error"])
        self.env.reset.assert_not_called()
        launch.assert_not_called()

    def test_transport_diagnostic_is_redacted_at_the_public_receipt_boundary(self):
        _, receipt, launch, _ = self.invoke(cdp_error=RuntimeError("guest diagnostic: " + self.key))
        self.assertIsNone(receipt["score"])
        self.assertIn("[REDACTED]", receipt["error"])
        launch.assert_not_called()
        self.assert_private_key_not_in_evidence()


class GuestTransportTests(unittest.TestCase):
    def test_failed_command_is_not_mistaken_for_success(self):
        private_key = "test-transport-secret-06128"
        response = mock.Mock()
        response.json.return_value = {"status": "error", "returncode": 9,
                                      "error": private_key, "stderr": private_key}
        requests = types.ModuleType("requests")
        requests.post = mock.Mock(return_value=response)
        env = types.SimpleNamespace(controller=types.SimpleNamespace(http_server="http://127.0.0.1:5000"))
        with mock.patch.dict(sys.modules, {"requests": requests}):
            with self.assertRaises(RuntimeError) as caught:
                runtime._execute(env, "print('task-visible command')")
        self.assertIn("exit=9", str(caught.exception))
        self.assertEqual(requests.post.call_count, 1)
        self.assertFalse(requests.post.call_args.kwargs["allow_redirects"])

    def test_lost_launch_response_is_not_automatically_replayed(self):
        requests = types.ModuleType("requests")
        requests.post = mock.Mock(side_effect=TimeoutError("response lost after guest may have executed"))
        env = types.SimpleNamespace(controller=types.SimpleNamespace(http_server="http://127.0.0.1:5000"))
        with mock.patch.dict(sys.modules, {"requests": requests}):
            with self.assertRaises(TimeoutError):
                runtime._execute(env, "start_actor_once()")
        self.assertEqual(requests.post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
