"""Tests for the original df93 controller reuse. No model/browser calls."""
from __future__ import annotations

import ast
import asyncio
from contextlib import redirect_stdout
import copy
import importlib.util
import io
import json
from pathlib import Path
import signal
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import strict_runtime
from dataset import actor_task, load_tasks

TASKS = load_tasks()
COMMIT = "df93e28b9aa1013523f39391dd4cb8a269dae585"


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def fixture(parent, completed=()):
    run = Path(parent) / "run"
    run.mkdir()
    settings = {"agent_python": str(run / "product/.venv/bin/python"),
                "judge_python": str(Path(parent) / "judge-venv/bin/python")}
    write(run / "settings.json", settings)
    write(run / "support/.private/model.json", {"model": "deepseek-v4.1-flash",
          "reasoning_effort": "max", "mode": "ultrafast", "api_key": "offline-fixture-key"})
    write(run / "support/previous-capacity/pause-bu-priority.json", {"in_flight": []})
    jobs = []
    for task in TASKS:
        folder = run / "runs/bu_v1" / task["id"]
        write(folder / "task.json", actor_task(task))
        write(folder / "actor-config.json", {"source_folder": str(folder), "max_steps": 300,
              "timeout_seconds": 3600, "fixed_viewport": True,
              "feature_config": {"preparation_fraction": 0.0, "track_task_progress": False,
                                 "public_source_lookup": True, "review_answer": True}})
        jobs.append({"arm": "candidate", "suite": "bu_v1", "task_id": task["id"],
                     "ordinal": task["ordinal"], "source_folder": str(folder),
                     "judge_folder": str(run / "judges/bu_v1" / task["id"]),
                     "task_input_sha256": strict_runtime.hashlib.sha256((folder / "task.json").read_bytes()).hexdigest(),
                     "actor_config_sha256": strict_runtime.hashlib.sha256((folder / "actor-config.json").read_bytes()).hexdigest()})
    plan = {"product_commit": COMMIT, "file_sha256": {}, "jobs": jobs,
            "feature_config": {}, "agent_reasoning": "max"}
    write(run / "plan.json", plan)
    write(run / "probe-passed.json", {"product_commit": COMMIT, "model_requests": 0})
    for index in completed:
        job = jobs[index]
        write(Path(job["source_folder"]) / "execution.json", {"status": "completed"})
        write(Path(job["judge_folder"]) / "judge-bu_v1.json", {"status": "judged", "score": 0})
    with patch.object(strict_runtime, "_install_environment"):
        namespace = strict_runtime.load_runtime(run)
    # Deterministic admission information; all other Path operations remain real.
    def path(value):
        if str(value) == "/proc/meminfo":
            return SimpleNamespace(read_text=lambda: "MemAvailable: 6291456 kB\n")
        return Path(value)
    namespace["Path"] = path
    return run, plan, namespace


class SourceIdentityTests(unittest.TestCase):
    def test_controller_changes_only_count_and_actor_profile_checks(self):
        original = ast.parse(strict_runtime.REFERENCE.read_text())
        originals = {node.name: node for node in original.body
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        extracted, audit = strict_runtime._extracted_module()
        self.assertEqual([node.name for node in extracted.body], list(strict_runtime.FUNCTIONS))
        self.assertEqual(len(audit["approved_ast_changes"]), 3)
        self.assertEqual(audit["approved_ast_changes"][0]["before"], 100)
        self.assertEqual(audit["approved_ast_changes"][0]["after"], 88)
        for node in extracted.body:
            expected = copy.deepcopy(originals[node.name])
            if node.name == "run":
                outer = next(item for item in expected.body if isinstance(item, ast.Assert)
                             and "len(plan['jobs']) == 100" in ast.unparse(item))
                count = next(item for item in ast.walk(outer) if isinstance(item, ast.Constant) and item.value == 100)
                count.value = 88
                for statement in expected.body:
                    if not isinstance(statement, ast.Assert):
                        continue
                    expression = ast.unparse(statement.test)
                    if expression == "public_config.get('reasoning_effort', 'high') == 'high'":
                        statement.test = ast.parse("public_config['reasoning_effort'] == 'max'", mode="eval").body
                    elif expression == "plan['review_answer'] and plan['request_budget_includes_answer_review']":
                        statement.test = ast.parse("plan['feature_config'] == {} and plan['agent_reasoning'] == 'max'", mode="eval").body
            self.assertEqual(ast.dump(node, include_attributes=False), ast.dump(expected, include_attributes=False))
        self.assertTrue(all(value["unchanged"] for name, value in audit["functions"].items() if name != "run"))

    def test_inner_one_capacity_and_event_functions_are_unmodified(self):
        original = next(node for node in ast.parse(strict_runtime.REFERENCE.read_text()).body
                        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run")
        extracted, _ = strict_runtime._extracted_module()
        runtime = next(node for node in extracted.body if node.name == "run")
        nested = lambda node: {item.name: ast.dump(item, include_attributes=False) for item in node.body
                               if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertEqual(set(nested(original)), {"inherited", "wait_capacity", "event", "one"})
        self.assertEqual(nested(runtime), nested(original))

    def test_changed_reference_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            changed = Path(temp) / "df93-run.py.txt"
            changed.write_bytes(strict_runtime.REFERENCE.read_bytes() + b"\n# changed\n")
            with patch.object(strict_runtime, "REFERENCE", changed), self.assertRaises(ValueError):
                strict_runtime.source_audit()

    def test_runtime_paths_and_venv_binding_are_exact(self):
        with tempfile.TemporaryDirectory() as temp:
            run, plan, _ = fixture(temp)
            with patch.object(strict_runtime, "_install_environment") as install:
                namespace = strict_runtime.load_runtime(run)
            self.assertEqual(namespace["RUN"], run)
            self.assertEqual(namespace["ROOT"], run / "support")
            self.assertEqual(namespace["PRODUCT"], run / "product")
            self.assertEqual(namespace["ENV"], run / "product/.venv")
            self.assertEqual(namespace["CODE"], run / "frozen/harness/legacy/code")
            self.assertEqual(namespace["SOURCE"], run / "product/src")
            self.assertEqual(namespace["DEPENDENCIES"], namespace["CODE"])
            self.assertEqual(namespace["OLD"], run / "support/previous-capacity")
            self.assertEqual(namespace["COMMIT"], plan["product_commit"])
            self.assertEqual(namespace["__file__"], str(run / "driver/run.py"))
            install.assert_called_once_with(run, run / "support", namespace["CODE"], namespace["LEGACY"])
            self.assertNotIn("prepare", namespace)


class OriginalBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_dynamic_32_actor_4_judge_pools_preserve_original_flow(self):
        with tempfile.TemporaryDirectory() as temp:
            run, plan, namespace = fixture(temp)
            first = plan["jobs"][0]["task_id"]
            jobs = {job["task_id"]: job for job in plan["jobs"]}
            release_actor = asyncio.Event()
            release_judges = asyncio.Event()
            short_actors_done = asyncio.Event()
            all_actors_done = asyncio.Event()
            active = {"actor": 0, "judge": 0}
            peak = {"actor": 0, "judge": 0}
            finished = []
            judged = []
            timeouts = {"actor": set(), "judge": set()}

            async def invoke(command, log_path, timeout, stdin=None):
                role = "judge" if len(command) > 2 and command[2] == "judge" else "actor"
                task_id = command[-1] if role == "judge" else Path(command[-1]).name
                job = jobs[task_id]
                active[role] += 1
                peak[role] = max(peak[role], active[role])
                timeouts[role].add(timeout)
                try:
                    if role == "actor":
                        self.assertIsInstance(stdin, bytes)
                        if task_id == first:
                            await release_actor.wait()
                        else:
                            await asyncio.sleep(0)
                        write(Path(job["source_folder"]) / "execution.json", {"status": "completed"})
                        finished.append(task_id)
                        if len([item for item in finished if item != first]) == 86:
                            short_actors_done.set()
                        if len(finished) == 88:
                            all_actors_done.set()
                    else:
                        self.assertIsNone(stdin)
                        self.assertEqual(command[0], str(namespace["LEGACY"]))
                        self.assertEqual(command[1], namespace["__file__"])
                        await release_judges.wait()
                        await asyncio.sleep(0)
                        write(Path(job["judge_folder"]) / "judge-bu_v1.json", {"status": "judged", "score": 0})
                        judged.append(task_id)
                finally:
                    active[role] -= 1
                return 0

            namespace["invoke"] = invoke
            with redirect_stdout(io.StringIO()):
                campaign = asyncio.create_task(namespace["run"]())
                try:
                    await asyncio.wait_for(short_actors_done.wait(), 5)
                    self.assertNotIn(first, finished)
                    self.assertEqual(judged, [])
                    release_actor.set()
                    await asyncio.wait_for(all_actors_done.wait(), 5)
                    self.assertEqual(judged, [])
                    self.assertEqual(peak, {"actor": 32, "judge": 4})
                finally:
                    release_actor.set()
                    release_judges.set()
                    await asyncio.wait_for(campaign, 5)
            self.assertEqual(timeouts, {"actor": {3900}, "judge": {14400}})
            self.assertTrue((run / "complete-all.json").is_file())
            self.assertEqual(len(judged), 88)

    async def test_original_six_gib_memory_admission_and_point75_poll(self):
        with tempfile.TemporaryDirectory() as temp:
            run, plan, namespace = fixture(temp, range(1, 88))
            memory = {"available_kib": 5 * 1048576}
            sleeps = []
            real_sleep = asyncio.sleep
            def path(value):
                if str(value) == "/proc/meminfo":
                    return SimpleNamespace(read_text=lambda: f"MemAvailable: {memory['available_kib']} kB\n")
                return Path(value)
            async def sleep(seconds):
                sleeps.append(seconds)
                memory["available_kib"] = 6 * 1048576
                await real_sleep(0)
            async def invoke(command, log_path, timeout, stdin=None):
                self.assertGreaterEqual(memory["available_kib"], 6 * 1048576)
                job = plan["jobs"][0]
                if stdin:
                    write(Path(job["source_folder"]) / "execution.json", {"status": "completed"})
                else:
                    write(Path(job["judge_folder"]) / "judge-bu_v1.json", {"status": "judged", "score": 0})
                return 0
            namespace["Path"] = path
            namespace["asyncio"] = SimpleNamespace(Semaphore=asyncio.Semaphore, gather=asyncio.gather, sleep=sleep)
            namespace["invoke"] = invoke
            with redirect_stdout(io.StringIO()):
                await namespace["run"]()
            self.assertEqual(sleeps, [0.75])

    async def test_any_existing_packet_is_preserved_even_if_judge_error(self):
        with tempfile.TemporaryDirectory() as temp:
            run, plan, namespace = fixture(temp, range(88))
            packet = Path(plan["jobs"][0]["judge_folder"]) / "judge-bu_v1.json"
            write(packet, {"status": "judge_error", "score": None})
            original = packet.read_bytes()
            invoke = AsyncMock(side_effect=AssertionError("Existing original packet must be preserved"))
            namespace["invoke"] = invoke
            with redirect_stdout(io.StringIO()):
                await namespace["run"]()
            invoke.assert_not_awaited()
            self.assertEqual(packet.read_bytes(), original)
            self.assertTrue((run / "complete-all.json").is_file())

    async def test_original_interrupted_agent_dir_is_not_rerun_and_completion_asserts(self):
        with tempfile.TemporaryDirectory() as temp:
            run, plan, namespace = fixture(temp, range(1, 88))
            folder = Path(plan["jobs"][0]["source_folder"])
            (folder / "agent").mkdir()
            invoke = AsyncMock(side_effect=AssertionError("Original interrupted Actor must not rerun"))
            namespace["invoke"] = invoke
            with redirect_stdout(io.StringIO()), self.assertRaisesRegex(AssertionError, "missing receipts"):
                await namespace["run"]()
            invoke.assert_not_awaited()
            self.assertFalse((run / "complete-all.json").exists())
            events = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines()]
            self.assertTrue(any(row["status"] == "interrupted_actor_preserved" for row in events))

    async def test_original_invoke_timeout_uses_term_five_seconds_then_kill(self):
        with tempfile.TemporaryDirectory() as temp:
            _, _, namespace = fixture(temp)
            waits = []
            wait_calls = 0
            async def communicate(stdin):
                self.assertEqual(stdin, b"offline-stdin")
                raise TimeoutError
            async def wait():
                nonlocal wait_calls
                wait_calls += 1
                if wait_calls == 1:
                    raise TimeoutError
                return -9
            process = SimpleNamespace(pid=12345, communicate=communicate, wait=wait, returncode=-9)
            create = AsyncMock(return_value=process)
            async def wait_for(awaitable, timeout):
                waits.append(timeout)
                return await awaitable
            killpg = Mock()
            namespace["asyncio"] = SimpleNamespace(create_subprocess_exec=create,
                subprocess=asyncio.subprocess, wait_for=wait_for)
            namespace["os"] = SimpleNamespace(killpg=killpg)
            result = await namespace["invoke"](["offline-command"], Path(temp) / "log" / "worker.log", 3900, b"offline-stdin")
            self.assertEqual(result, 124)
            self.assertEqual(waits, [3900, 5])
            self.assertEqual(killpg.call_args_list[0].args, (12345, signal.SIGTERM))
            self.assertEqual(killpg.call_args_list[1].args, (12345, signal.SIGKILL))
            self.assertTrue(create.call_args.kwargs["start_new_session"])
            self.assertEqual(create.call_args.kwargs["stdin"], asyncio.subprocess.PIPE)


if __name__ == "__main__":
    unittest.main()
