"""Run the real cap-four dispatcher against deterministic fake spawn processes.

No process, browser, VM, Docker daemon, model or network request is started.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock
import sys


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("osworld_parallel_contract", ROOT / "runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class ParallelDispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.manifest = json.loads((ROOT / "data/manifest.json").read_text())["tasks"]
        self.by_id = {item["task_id"]: item for item in self.manifest}
        self.metadata = {"task_count": 76, "upstream_commit": runtime.UPSTREAM_COMMIT,
            "harness_root": str(ROOT), "guest_root": "/tmp/lexmount-parallel-test",
            "config": json.loads((ROOT / "config.json").read_text())}
        self.metadata["config"]["runtime"]["concurrency"] = 4
        (self.folder / "run.json").write_text(json.dumps(self.metadata))
        (self.folder / "probe.json").write_text(json.dumps({"status": "passed",
            "run_metadata_sha256": runtime._digest(self.folder / "run.json")}))
        self.private = self.folder / "private-model.json"
        self.key = "private-spawn-key-never-an-argument-4901"
        self.private.write_text(json.dumps({"api_key": self.key, "base_url": "https://model.invalid/v1"}))
        self.processes, self.events, self.handlers = [], [], []
        self.max_alive, self.wait_calls, self.admission_calls = 0, 0, 0
        self.pause_on_first_wait = False
        self.failed_task = None
        self.deny_first_admission = False
        owner = self

        class Process:
            def __init__(self, *, target, args, name):
                self.target, self.args, self.name = target, args, name
                self.task_id = args[1]
                self.pid, self.exitcode, self._alive = None, None, False
                self.joined = 0
                owner.processes.append(self)
            def start(self):
                self.pid = 41000 + len(owner.processes)
                self.sentinel = "fake-sentinel-" + str(self.pid)
                self._alive = True
                owner.events.append(("started", self.task_id))
                owner.max_alive = max(owner.max_alive, sum(p._alive for p in owner.processes))
            def is_alive(self):
                return self._alive
            def finish(self):
                if not self._alive:
                    return
                self._alive = False
                self.exitcode = -9 if self.task_id == owner.failed_task else 0
                owner.events.append(("finished", self.task_id))
                if self.exitcode == 0:
                    item = owner.by_id[self.task_id]
                    runtime._write_json(owner.folder / "tasks" / self.task_id / "receipt.json", {
                        "task_id": self.task_id, "task_sha256": item["sha256"], "status": "scored",
                        "score": 0.625, "owned_vm_closed": True}, exclusive=True)
            def join(self):
                self.joined += 1
                self.finish()

        self.context = types.SimpleNamespace(Process=Process)

    def wait(self, sentinels, timeout):
        self.wait_calls += 1
        active = [p for p in self.processes if p._alive]
        self.assertEqual(set(sentinels), {p.sentinel for p in active})
        if self.pause_on_first_wait and self.wait_calls == 1:
            self.handlers[-1](runtime.signal.SIGINT, None)
            return []
        for process in active:
            process.finish()
        return list(sentinels)

    def admission(self, in_flight, settings):
        self.admission_calls += 1
        admitted = not (self.deny_first_admission and self.admission_calls == 1)
        self.events.append(("admission", admitted))
        return {"admitted": admitted, "mem_available_gib": 64, "required_memory_gib": 36,
                "in_flight": in_flight, "load_average_1m": 1, "max_load_average": 24}

    def dispatch(self, task_ids=None):
        def signal(number, handler):
            self.handlers.append(handler)
        with mock.patch.object(runtime.multiprocessing, "get_context", return_value=self.context) as context, \
                mock.patch.object(runtime, "wait_sentinels", side_effect=self.wait), \
                mock.patch.object(runtime, "_resource_admission", side_effect=self.admission), \
                mock.patch.object(runtime, "_cleanup_dead_worker", return_value={"verified_absent": True}) as cleanup, \
                mock.patch.object(runtime.signal, "getsignal", return_value="previous-sigint-handler"), \
                mock.patch.object(runtime.signal, "signal", side_effect=signal), \
                mock.patch.object(runtime.time, "sleep", side_effect=lambda seconds: self.events.append(("sleep", seconds))):
            result = runtime.run_tasks(self.folder, self.private, task_ids)
        context.assert_called_once_with("spawn")
        return result, cleanup

    def test_all_76_are_dispatched_once_with_at_most_four_in_flight_and_no_key_arguments(self):
        result, cleanup = self.dispatch()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["scored"], 76)
        self.assertEqual(result["invalid"], 0)
        self.assertEqual(self.max_alive, 4)
        ids = [p.task_id for p in self.processes]
        self.assertEqual(ids, [t["task_id"] for t in self.manifest])
        self.assertEqual(len(set(ids)), 76)
        for process in self.processes:
            self.assertEqual(process.target, runtime._worker_entry)
            self.assertEqual(len(process.args), 3)
            self.assertEqual(process.args, (str(self.folder), process.task_id, str(self.private)))
            self.assertNotIn(self.key, repr(process.args))
            self.assertGreaterEqual(process.joined, 1)
        cleanup.assert_not_called()
        self.assertFalse((self.folder / "runtime.lock").exists())

    def test_every_completed_slot_is_drained_before_a_failed_batch_can_be_replaced(self):
        selected = [t["task_id"] for t in self.manifest[:6]]
        self.failed_task = selected[1]
        result, cleanup = self.dispatch(selected)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stop_reason"], "worker_or_cleanup_failure")
        self.assertEqual(result["not_started"], 2)
        self.assertEqual([p.task_id for p in self.processes], selected[:4])
        self.assertEqual(result["scored"], 3)
        self.assertEqual(result["invalid"], 1)
        cleanup.assert_called_once()
        failure = json.loads((self.folder / "tasks" / self.failed_task / "receipt.json").read_text())
        self.assertEqual(failure["status"], "interrupted")
        self.assertEqual(failure["worker_exitcode"], -9)
        self.assertIsNone(failure["score"])

    def test_insufficient_resources_wait_without_starting_a_worker(self):
        self.deny_first_admission = True
        result, _ = self.dispatch([self.manifest[0]["task_id"]])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.events[0], ("admission", False))
        self.assertEqual(self.events[1], ("sleep", 10))
        self.assertEqual(self.events[2], ("admission", True))
        self.assertEqual(len(self.processes), 1)
        events = (self.folder / "events.jsonl").read_text()
        self.assertIn('"resource_wait"', events)
        self.assertNotIn(self.key, events)

    def test_sigint_pauses_dispatch_and_waits_for_owned_inflight_workers(self):
        self.pause_on_first_wait = True
        selected = [t["task_id"] for t in self.manifest[:6]]
        with self.assertRaises(KeyboardInterrupt):
            self.dispatch(selected)
        self.assertEqual([p.task_id for p in self.processes], selected[:4])
        self.assertTrue(all(not p._alive and p.joined >= 1 for p in self.processes))
        self.assertGreaterEqual(self.wait_calls, 2)
        self.assertEqual(self.handlers[-1], "previous-sigint-handler")
        self.assertFalse((self.folder / "runtime.lock").exists())
        self.assertTrue(all((self.folder / "tasks" / ident / "receipt.json").exists() for ident in selected[:4]))
        self.assertTrue(all(not (self.folder / "tasks" / ident).exists() for ident in selected[4:]))


class ResourceAdmissionTests(unittest.TestCase):
    def test_real_policy_reserves_memory_for_next_vm_and_current_host_load(self):
        settings = {"reserve_memory_gib": 12, "per_vm_admission_gib": 6, "max_load_average": 24}
        path = types.SimpleNamespace(read_text=lambda: "MemTotal: 123456789 kB\nMemAvailable: 20971520 kB\n")
        with mock.patch.object(runtime, "Path", return_value=path), \
                mock.patch.object(runtime.os, "getloadavg", return_value=(1, 1, 1)):
            self.assertTrue(runtime._resource_admission(0, settings)["admitted"])
            self.assertFalse(runtime._resource_admission(1, settings)["admitted"])
        path = types.SimpleNamespace(read_text=lambda: "MemAvailable: 104857600 kB\n")
        with mock.patch.object(runtime, "Path", return_value=path), \
                mock.patch.object(runtime.os, "getloadavg", return_value=(25, 1, 1)):
            self.assertFalse(runtime._resource_admission(0, settings)["admitted"])


class DeadWorkerCleanupTests(unittest.TestCase):
    def test_killed_writer_preserves_malformed_receipt_and_writes_unscored_sidecar(self):
        task = json.loads((ROOT / "data/manifest.json").read_text())["tasks"][0]
        for raw in (b'{"status":', b'[]'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as temporary:
                run_dir = Path(temporary)
                folder = run_dir / "tasks" / task["task_id"]
                folder.mkdir(parents=True)
                path = folder / "receipt.json"
                path.write_bytes(raw)
                process = types.SimpleNamespace(pid=1234, exitcode=-9, join=mock.Mock())
                metadata = {"harness_root": str(ROOT)}
                with mock.patch.object(runtime, "_cleanup_dead_worker", return_value={"verified_absent": True}) as cleanup:
                    result, failed = runtime._finished_process(run_dir, metadata, task["task_id"], process)
                self.assertTrue(failed)
                process.join.assert_called_once()
                cleanup.assert_called_once_with(metadata, folder, task["task_id"])
                self.assertEqual(path.read_bytes(), raw)
                self.assertEqual(result["status"], "interrupted")
                self.assertIsNone(result["score"])
                self.assertEqual(result["error_type"], "WorkerProcessError")
                self.assertEqual(result["task_sha256"], task["sha256"])
                self.assertTrue(result["owned_container_removal_verified"])
                self.assertEqual(json.loads((folder / "worker-failure.json").read_text())["status"], "interrupted")

    def test_exact_owned_ids_and_all_three_labels_are_required_before_deletion(self):
        for foreign_tracked in (False, True):
            with self.subTest(foreign_tracked=foreign_tracked), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                task_id = "task-uuid"
                metadata = {"guest_root": "/tmp/owned-run-uuid"}
                labels = {"lexmount-evaluation": "OSWorld-Verified-filter",
                          "lexmount-run": "owned-run-uuid", "lexmount-task": task_id}
                owned = types.SimpleNamespace(id="owned-container-id", labels=labels, removed=False)
                owned.remove = mock.Mock(side_effect=lambda **kwargs: setattr(owned, "removed", True))
                foreign = types.SimpleNamespace(id="other-task-container", labels=labels | {"lexmount-task": "another-task"})
                foreign.remove = mock.Mock()

                class NotFound(Exception):
                    pass

                def get(identifier):
                    if identifier == owned.id:
                        if owned.removed:
                            raise NotFound(identifier)
                        return owned
                    if identifier == foreign.id:
                        return foreign
                    raise AssertionError("An untracked container was accessed")

                def listing(**kwargs):
                    self.assertTrue(kwargs["all"])
                    self.assertEqual(set(kwargs["filters"]["label"]), {key + "=" + value for key, value in labels.items()})
                    return [] if owned.removed else [owned]

                ids = [owned.id] + ([foreign.id] if foreign_tracked else [])
                (folder / "owned-container.json").write_text(json.dumps({"owned_container_ids": ids}))
                client = types.SimpleNamespace(containers=types.SimpleNamespace(get=mock.Mock(side_effect=get),
                                                                                list=mock.Mock(side_effect=listing)))
                docker = types.ModuleType("docker")
                docker.from_env = lambda: client
                errors = types.ModuleType("docker.errors")
                errors.NotFound = NotFound
                with mock.patch.dict(sys.modules, {"docker": docker, "docker.errors": errors}):
                    result = runtime._cleanup_dead_worker(metadata, folder, task_id)
                owned.remove.assert_called_once_with(force=True, v=True)
                foreign.remove.assert_not_called()
                self.assertEqual(result["removed_ids"], [owned.id])
                self.assertEqual(result["verified_absent"], not foreign_tracked)
                if foreign_tracked:
                    self.assertEqual(result["unconfirmed_ids"], [foreign.id])
                self.assertTrue((folder / "worker-cleanup.json").exists())


if __name__ == "__main__":
    unittest.main()
