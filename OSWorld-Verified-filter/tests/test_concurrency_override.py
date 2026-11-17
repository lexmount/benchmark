"""Exercise the takeover controller without starting processes, VMs or models."""
from __future__ import annotations

import importlib.util
import json
import multiprocessing
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


override = load("osworld_override_contract", "concurrency_override.py")
runtime = load("osworld_override_runtime_contract", "runtime.py")


class LegacyIdentityTests(unittest.TestCase):
    def test_dead_worker_reserves_its_slot_until_cleanup_is_verified_even_with_invalid_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            worker = {"pid": 100, "start_ticks": "12", "task_id": "a"}
            task = folder / "tasks" / "a"
            task.mkdir(parents=True)
            with mock.patch.object(override, "identity", return_value=None):
                for contents in (None, '{"status":', '[]', '{"owned_vm_closed":false}'):
                    with self.subTest(contents=contents):
                        receipt = task / "receipt.json"
                        if contents is not None:
                            receipt.write_text(contents)
                        elif receipt.exists():
                            receipt.unlink()
                        self.assertEqual(override.pending_legacy_workers([worker], folder), [worker])
                (task / "worker-cleanup.json").write_text('{"verified_absent":true}')
                self.assertEqual(override.pending_legacy_workers([worker], folder), [])
                with mock.patch.object(override, "identity", return_value={"pid": 100, "start_ticks": "12"}):
                    self.assertEqual(override.pending_legacy_workers([worker], folder), [worker])

    def test_reused_pid_and_dead_pid_are_not_counted_as_original_workers(self):
        workers = [{"pid": 100, "start_ticks": "12", "task_id": "a"},
                   {"pid": 101, "start_ticks": "13", "task_id": "b"},
                   {"pid": 102, "start_ticks": "14", "task_id": "c"}]
        identities = {100: {"pid": 100, "start_ticks": "12"},
                      101: {"pid": 101, "start_ticks": "999"}, 102: None}
        with mock.patch.object(override, "identity", side_effect=identities.get):
            self.assertEqual(override.live_legacy_workers(workers), workers[:1])

    def test_old_pause_event_is_insufficient_and_new_ack_precedes_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary).resolve()
            (folder / "runtime.lock").write_text(json.dumps({"pid": 700,
                "hostname": override.socket.gethostname(), "worker_pids": [701]}))
            events = folder / "events.jsonl"
            events.write_text(json.dumps({"event": "worker_started", "pid": 701, "task_id": "original-task"}) +
                              '\n' + json.dumps({"event": "dispatch_paused"}) + '\n')
            observed, waits = [], []
            real_path = Path

            def path(value):
                if str(value) == "/proc/700/cmdline":
                    return types.SimpleNamespace(read_bytes=lambda: ("python evaluate.py run --run-dir " + str(folder)).encode())
                return real_path(value)

            def sleep(seconds):
                waits.append(seconds)
                with events.open("a") as stream:
                    stream.write(json.dumps({"event": "dispatch_paused"}) + '\n')

            with mock.patch.object(override, "Path", side_effect=path), \
                    mock.patch.object(override, "identity", side_effect=lambda pid: {"pid": pid, "start_ticks": str(pid)}), \
                    mock.patch.object(override.os, "kill", side_effect=lambda pid, sig: observed.append(("signal", pid, sig))), \
                    mock.patch.object(override.time, "sleep", side_effect=sleep):
                result = override.stop_old_dispatcher(folder, lambda name, **kw: observed.append((name, kw)))
            self.assertEqual(waits, [.25])
            self.assertEqual(observed[0], ("signal", 700, override.signal.SIGINT))
            self.assertEqual(result, [{"pid": 701, "start_ticks": "701", "task_id": "original-task",
                                      "owner_identity": {"pid": 700, "start_ticks": "700"}}])
            self.assertEqual(observed[-1][0], "old_dispatch_paused")

    def test_no_acknowledgement_refuses_takeover(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary).resolve()
            (folder / "runtime.lock").write_text(json.dumps({"pid": 700,
                "hostname": override.socket.gethostname(), "worker_pids": []}))
            (folder / "events.jsonl").write_text("")
            real_path = Path
            def path(value):
                if str(value) == "/proc/700/cmdline":
                    return types.SimpleNamespace(read_bytes=lambda: ("evaluate.py run " + str(folder)).encode())
                return real_path(value)
            with mock.patch.object(override, "identity", return_value={"pid": 700, "start_ticks": "12"}), \
                    mock.patch.object(override, "Path", side_effect=path), \
                    mock.patch.object(override.os, "kill") as kill, \
                    mock.patch.object(override.time, "monotonic", side_effect=[0, 41]):
                with self.assertRaisesRegex(RuntimeError, "acknowledge"):
                    override.stop_old_dispatcher(folder, lambda *args, **kwargs: None)
            kill.assert_called_once_with(700, override.signal.SIGINT)

    def test_worker_imports_and_calls_the_frozen_runtime_at_the_recorded_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            harness = folder / "frozen"
            harness.mkdir()
            (harness / "runtime.py").write_text(
                "import json\nfrom pathlib import Path\n"
                "def _worker_entry(run_dir, task_id, model_config):\n"
                "    Path(run_dir, 'called.json').write_text(json.dumps([run_dir, task_id, model_config]))\n")
            (folder / "run.json").write_text(json.dumps({"harness_root": str(harness)}))
            with mock.patch.dict(sys.modules):
                sys.modules.pop("runtime", None)
                with mock.patch.object(sys, "path", list(sys.path)):
                    override.task_worker(str(folder), "task-id", "/private/model.json")
                    self.assertEqual(Path(sys.modules["runtime"].__file__).parent, harness)
            self.assertEqual(json.loads((folder / "called.json").read_text()),
                             [str(folder), "task-id", "/private/model.json"])

    def test_canonical_worker_is_spawn_picklable_and_imports_frozen_stub_in_fresh_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            harness = folder / "frozen"
            harness.mkdir()
            (harness / "runtime.py").write_text(
                "import json, os\nfrom pathlib import Path\n"
                "def _worker_entry(run_dir, task_id, model_config):\n"
                "    Path(run_dir, 'spawn-called.json').write_text(json.dumps({\n"
                "        'args': [run_dir, task_id, model_config], 'pid': os.getpid(),\n"
                "        'source': __file__}))\n")
            (folder / "run.json").write_text(json.dumps({"harness_root": str(harness)}))
            with mock.patch.object(sys, "path", [str(ROOT), *sys.path]), mock.patch.dict(sys.modules):
                sys.modules.pop("concurrency_override", None)
                canonical = importlib.import_module("concurrency_override")
                process = multiprocessing.get_context("spawn").Process(target=canonical.task_worker,
                    args=(str(folder), "task-id", "/private/model.json"))
                process.start()
                try:
                    process.join(timeout=10)
                    self.assertFalse(process.is_alive(), "The isolated runtime stub did not finish")
                    self.assertEqual(process.exitcode, 0)
                finally:
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=5)
            result = json.loads((folder / "spawn-called.json").read_text())
            self.assertEqual(result["args"], [str(folder), "task-id", "/private/model.json"])
            self.assertEqual(Path(result["source"]).resolve(), (harness / "runtime.py").resolve())
            self.assertNotEqual(result["pid"], override.os.getpid())


class OverrideDispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.tasks = json.loads((ROOT / "data/manifest.json").read_text())["tasks"]
        self.by_id = {t["task_id"]: t for t in self.tasks}
        self.metadata = {"task_count": 76, "upstream_commit": runtime.UPSTREAM_COMMIT,
            "harness_root": str(ROOT), "guest_root": "/tmp/lexmount-override-test",
            "config": json.loads((ROOT / "config.json").read_text())}
        self.metadata["config"]["runtime"]["concurrency"] = 4
        (self.folder / "run.json").write_text(json.dumps(self.metadata))
        (self.folder / "probe.json").write_text(json.dumps({"status": "passed",
            "run_metadata_sha256": runtime._digest(self.folder / "run.json")}))
        self.private = self.folder / "private-model.json"
        self.key = "private-override-key-must-not-be-serialized-6137"
        self.private.write_text(json.dumps({"api_key": self.key}))
        self.legacy = [{"pid": 81000 + n, "start_ticks": str(20 + n), "task_id": self.tasks[n]["task_id"]}
                       for n in range(4)]
        for worker in self.legacy:
            (self.folder / "tasks" / worker["task_id"]).mkdir(parents=True)
        self.legacy_live = True
        self.processes, self.admissions, self.handlers = [], [], []
        self.total_max, self.waits = 0, 0
        self.deny_first = self.pause_first = self.fail_one = False
        self.paused_ack = False
        self.existing_id = self.tasks[4]["task_id"]
        self.original_receipt = b'{"status":"scored", "score":0.125, "owned_vm_closed":true}\n'
        old = self.folder / "tasks" / self.existing_id
        old.mkdir(parents=True)
        (old / "receipt.json").write_bytes(self.original_receipt)
        owner = self

        class Process:
            def __init__(self, *, target, args, name):
                self.target, self.args, self.name = target, args, name
                self.task_id, self.pid, self.exitcode, self.alive = args[1], None, None, False
                owner.processes.append(self)

            def start(self):
                owner.assertTrue(owner.paused_ack, "A new VM was dispatched before the old dispatcher acknowledged pause")
                self.pid, self.alive = 90000 + len(owner.processes), True
                owner.total_max = max(owner.total_max, sum(p.alive for p in owner.processes) +
                                      (len(owner.legacy) if owner.legacy_live else 0))

            def is_alive(self):
                return self.alive

            def finish(self):
                if not self.alive:
                    return
                self.alive = False
                self.exitcode = -9 if owner.fail_one and self is owner.processes[0] else 0
                if self.exitcode == 0:
                    runtime._write_json(owner.folder / "tasks" / self.task_id / "receipt.json", {
                        "task_id": self.task_id, "task_sha256": owner.by_id[self.task_id]["sha256"],
                        "status": "scored", "score": .375, "owned_vm_closed": True}, exclusive=True)

            def join(self):
                self.finish()

        self.context = types.SimpleNamespace(Process=Process)

    def sleep(self, seconds):
        self.waits += 1
        if self.pause_first and self.waits == 1:
            self.handlers[0](override.signal.SIGINT, None)
        for process in self.processes:
            process.finish()
        if self.legacy_live:
            for worker in self.legacy:
                runtime._write_json(self.folder / "tasks" / worker["task_id"] / "receipt.json", {
                    "task_id": worker["task_id"], "status": "scored", "score": .75,
                    "owned_vm_closed": True}, exclusive=True)
            self.legacy_live = False

    def admission(self, total, settings):
        self.admissions.append(total)
        return {"admitted": not (self.deny_first and len(self.admissions) == 1), "in_flight": total,
                "mem_available_gib": 100, "required_memory_gib": 12 + 6 * (total + 1),
                "load_average_1m": 1, "max_load_average": 24}

    def invoke(self, *, stop_error=False):
        real_spec = importlib.util.spec_from_file_location("override_control", ROOT / "evaluate.py")
        owner = self

        class Loader:
            def create_module(self, spec):
                return None
            def exec_module(self, module):
                module.verify_run = lambda folder: owner.metadata

        real_spec.loader = Loader()

        def stop(folder, event):
            if stop_error:
                raise RuntimeError("No acknowledgement")
            self.paused_ack = True
            return self.legacy

        def signal(number, handler):
            self.handlers.append(handler)
            return "original-signal-handler"

        args = types.SimpleNamespace(run_dir=self.folder, model_config=self.private, concurrency=12)
        with mock.patch.object(override.importlib.util, "spec_from_file_location", return_value=real_spec), \
                mock.patch.object(override, "frozen_runtime", return_value=(runtime, self.metadata)), \
                mock.patch.object(override, "stop_old_dispatcher", side_effect=stop), \
                mock.patch.object(override, "live_legacy_workers", side_effect=lambda legacy: legacy if self.legacy_live else []), \
                mock.patch.object(override.multiprocessing, "get_context", return_value=self.context) as context, \
                mock.patch.object(override.signal, "signal", side_effect=signal), \
                mock.patch.object(override.time, "sleep", side_effect=self.sleep), \
                mock.patch.object(runtime, "_actor_settings"), \
                mock.patch.object(runtime, "_resource_admission", side_effect=self.admission), \
                mock.patch.object(runtime, "_cleanup_dead_worker", return_value={"verified_absent": True}):
            result = override.run(args)
        context.assert_called_once_with("spawn")
        return result

    def test_inherited_four_plus_new_eight_obey_total_twelve_and_execute_the_other_tasks_once(self):
        result = self.invoke()
        self.assertEqual(result["status"], "completed")
        ids = [p.task_id for p in self.processes]
        excluded = {self.existing_id, *(w["task_id"] for w in self.legacy)}
        self.assertEqual(ids, [t["task_id"] for t in self.tasks if t["task_id"] not in excluded])
        self.assertEqual(len(ids), 71)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(self.total_max, 12)
        self.assertEqual(self.admissions[:8], list(range(4, 12)))
        self.assertEqual((self.folder / "tasks" / self.existing_id / "receipt.json").read_bytes(), self.original_receipt)
        self.assertFalse((self.folder / "concurrency-override.lock").exists())
        for process in self.processes:
            self.assertIs(process.target, override.task_worker)
            self.assertEqual(process.args, (str(self.folder), process.task_id, str(self.private)))
            self.assertNotIn(self.key, repr(process.args))
        for path in (self.folder / "control-overrides").rglob("*.json*"):
            self.assertNotIn(self.key, path.read_text())

    def test_old_dispatcher_without_ack_cannot_launch_a_new_worker(self):
        with self.assertRaisesRegex(RuntimeError, "acknowledgement"):
            self.invoke(stop_error=True)
        self.assertEqual(self.processes, [])
        self.assertFalse((self.folder / "concurrency-override.lock").exists())

    def test_admission_denial_waits_without_dispatch_and_rechecks_total_after_legacy_finishes(self):
        self.deny_first = True
        result = self.invoke()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.admissions[:2], [4, 0])
        self.assertEqual(self.total_max, 12)

    def test_failed_completed_batch_prevents_replacement_and_keeps_failure_unscored(self):
        self.fail_one = True
        result = self.invoke()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stop_reason"], "worker_or_cleanup_failure")
        self.assertEqual(len(self.processes), 8)
        failure = json.loads((self.folder / "tasks" / self.processes[0].task_id / "receipt.json").read_text())
        self.assertEqual(failure["status"], "interrupted")
        self.assertIsNone(failure["score"])
        self.assertEqual((self.folder / "tasks" / self.existing_id / "receipt.json").read_bytes(), self.original_receipt)

    def test_sigint_stops_new_dispatch_but_drains_all_legacy_and_new_workers(self):
        self.pause_first = True
        result = self.invoke()
        self.assertEqual(result["stop_reason"], "interrupted")
        self.assertEqual(len(self.processes), 8)
        self.assertTrue(all(not p.alive for p in self.processes))
        self.assertFalse(self.legacy_live)
        self.assertEqual(self.handlers[-1], "original-signal-handler")

    def test_mismatched_probe_metadata_hash_refuses_takeover_before_any_worker(self):
        (self.folder / "probe.json").write_text(json.dumps({"status": "passed", "run_metadata_sha256": "0" * 64}))
        with self.assertRaisesRegex(RuntimeError, "probe"):
            self.invoke()
        self.assertEqual(self.processes, [])
        self.assertFalse((self.folder / "concurrency-override.lock").exists())

    def test_dead_legacy_owner_and_workers_are_cleaned_and_recorded_without_new_dispatch_or_zero_score(self):
        self.legacy_live = False
        for worker in self.legacy:
            worker["owner_identity"] = {"pid": 80000, "start_ticks": "1"}
        with mock.patch.object(override, "identity", return_value=None):
            result = self.invoke()
        self.assertEqual(result["stop_reason"], "inherited_worker_failure")
        self.assertEqual(self.processes, [])
        for worker in self.legacy:
            receipt = json.loads((self.folder / "tasks" / worker["task_id"] / "receipt.json").read_text())
            self.assertEqual(receipt["status"], "interrupted")
            self.assertIsNone(receipt["score"])
            self.assertTrue(receipt["owned_container_removal_verified"])


if __name__ == "__main__":
    unittest.main()
