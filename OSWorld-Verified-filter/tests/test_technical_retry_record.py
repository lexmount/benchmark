"""Technical retries preserve unknown originals and require the same frozen Actor."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import technical_retry_record as retry


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def inventory(path):
    return {str(p.relative_to(path)): retry.sha(p) for p in path.rglob("*") if p.is_file()}


class TechnicalRetryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.old, self.new = self.root / "old", self.root / "new"
        self.actor = {"model": "deepseek-v4.1-flash", "reasoning_effort": "max", "mode": "default",
                      "max_steps": 300, "timeout_seconds": 3600, "request_timeout_seconds": 120}
        self.make_run(self.old, False, "a")
        self.make_run(self.new, True, "b")
        self.checked = []
        def verify_run(path):
            self.checked.append(path)
            for name, expected in retry.read(path / "frozen-files.json").items():
                if retry.sha(path / name) != expected:
                    raise ValueError("Frozen file changed")
            return retry.read(path / "run.json")
        self.control = types.SimpleNamespace(verify_run=verify_run, file_inventory=inventory)
        self.patch = mock.patch.object(retry, "load_control", return_value=self.control)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def bundle(self, path, *, content=b"same runtime", mtime=0):
        with tarfile.open(path, "w:gz") as archive:
            member = tarfile.TarInfo("guest_actor.py")
            member.size, member.mode, member.mtime = len(content), 0o644, mtime
            archive.addfile(member, io.BytesIO(content))

    def actor_archive(self, run, public):
        path = run / "tasks" / retry.TASK_ID / "actor-output.tar.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(public).encode()
        with tarfile.open(path, "w:gz") as archive:
            member = tarfile.TarInfo("actor-output/run.json")
            member.size = len(raw)
            archive.addfile(member, io.BytesIO(raw))

    def freeze(self, run):
        files = {"run.json": retry.sha(run / "run.json"),
                 "runtime-bundle.tar.gz": retry.sha(run / "runtime-bundle.tar.gz")}
        for prefix in ("harness", "upstream", "product-source"):
            files.update({prefix + "/" + name: value for name, value in inventory(run / prefix).items()})
        put(run / "frozen-files.json", files)

    def make_run(self, run, success, digit):
        run.mkdir()
        guest = "/tmp/lexmount-osworld-" + digit * 32
        task = {"instruction": 'Change all "text" to "test".'}
        task_path = run / "harness/data/tasks/vs_code" / (retry.TASK_ID + ".json")
        put(task_path, task)
        item = {"task_id": retry.TASK_ID, "task_path": str(task_path.relative_to(run / "harness")),
                "sha256": retry.sha(task_path)}
        put(run / "harness/data/manifest.json", {"tasks": [item]})
        for name in retry.REQUIRED_SOURCE_FILES - {"harness/data/manifest.json"}:
            path = run / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("same source " + name)
        for name in ("runner.py", "config.py"):
            path = run / "product-source/src/lexmount_browser_agent" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixed product " + name)
        self.bundle(run / "runtime-bundle.tar.gz", mtime=1 if success else 0)
        metadata = {"schema_version": 1, "upstream_commit": "u" * 40, "agent_commit": "p" * 40,
            "benchmark_commit": "h" * 40, "task_count": 76, "config": {"actor": deepcopy(self.actor)},
            "harness_root": str(run / "harness"), "osworld_root": str(run / "upstream"),
            "bundle_path": str(run / "runtime-bundle.tar.gz"),
            "bundle_sha256": retry.sha(run / "runtime-bundle.tar.gz"),
            "guest_root": guest, "created_at": "new" if success else "old", "vm_image_sha256": "v" * 64}
        put(run / "run.json", metadata)
        packages = {"lexmount-browser-agent": "0.2.0", "browser-use": "1.0.4", "browser-harness": "0.1.13", "pydantic-ai-slim": "2.66.0"}
        sources = {name: {"path": guest + "/product/" + name, "sha256": "c" * 64}
                   for name in ("engine_service", "engine_repl_worker", "engine_repl_session")}
        for key, name in (("product_runner", "runner.py"), ("product_config", "config.py")):
            sources[key] = {"path": guest + "/product/src/lexmount_browser_agent/" + name,
                "sha256": retry.sha(run / "product-source/src/lexmount_browser_agent" / name)}
        engine = {"python": "3.12.13", "packages": packages, "sources": sources, "uid": 1000, "home": "/home/user"}
        context = "\nOriginal VM input. Screenshot " + guest + "/initial.png\n"
        public = {"task": task["instruction"] + context, "config": deepcopy(self.actor) | {"browser": "cdp"},
                  "versions": packages, "model_override": None}
        self.actor_archive(run, public)
        native = {"status": "completed" if success else "error", "agent_success": True if success else None,
            "error": None if success else "ModelRequestRejectedError: status_code: 400 [Temporary multimodal download failure]",
            "model_turns": 10 if success else 5, "model_http_requests": 10 if success else 5, "wall_seconds": 100.0}
        actor = {"status": "finished", "metadata": engine, "result": native,
            "instruction_sha256": hashlib.sha256(task["instruction"].encode()).hexdigest(),
            "appended_environment_context": context,
            "effective_prompt_sha256": hashlib.sha256(public["task"].encode()).hexdigest()}
        put(run / "tasks" / retry.TASK_ID / "actor-result.json", actor)
        receipt = {"task_id": retry.TASK_ID, "task_sha256": item["sha256"],
            "status": "scored" if success else "actor_error", "score": 1.0 if success else None,
            "actor_status": native["status"], "agent_success": native["agent_success"],
            "official_terminal_action": "DONE" if success else None, "budget": deepcopy(self.actor),
            "owned_vm_closed": True, "owned_container_removal_verified": True, "evidence_errors": [],
            "started_at": "2026-11-17T14:00:00+00:00" if success else "2026-11-17T13:00:00+00:00",
            "finished_at": "2026-11-17T14:02:00+00:00" if success else "2026-11-17T13:02:00+00:00"}
        put(run / "tasks" / retry.TASK_ID / "receipt.json", receipt)
        probe = {"status": "passed", "run_metadata_sha256": retry.sha(run / "run.json"),
            "owned_vm_closed": True, "owned_container_removal_verified": True, "evidence_errors": [],
            "product_probe": {"status": "passed", "file_roundtrip": True, "metadata": engine}}
        put(run / "probe.json", probe)
        self.freeze(run)

    def change(self, run, filename, mutate):
        path = run / filename
        value = retry.read(path)
        mutate(value)
        put(path, value)

    @property
    def receipt(self):
        return "tasks/" + retry.TASK_ID + "/receipt.json"

    def create(self):
        return retry.create_record(self.old, self.new, self.root / "record.json")

    def test_roundtrip_checks_two_frozen_runs_and_preserves_unknown_original(self):
        old_hash = retry.sha(self.old / self.receipt)
        record = self.create()
        self.assertIsNone(record["original_score"])
        self.assertTrue(record["actor_rerun"])
        self.assertFalse(record["original_output_rejudged"])
        self.assertEqual(record["score"], 1)
        self.assertEqual(retry.verify_record(self.old, self.root / "record.json"), record)
        self.assertEqual(retry.sha(self.old / self.receipt), old_hash)
        self.assertIn(self.old, self.checked)
        self.assertIn(self.new, self.checked)

    def test_legal_original_zero_must_not_be_retried(self):
        self.change(self.old, self.receipt, lambda r: r.update(status="scored", score=0.0))
        with self.assertRaises(ValueError): self.create()

    def test_unrelated_actor_error_is_refused(self):
        self.change(self.old, "tasks/" + retry.TASK_ID + "/actor-result.json", lambda a: a["result"].update(error="authentication failed"))
        with self.assertRaises(ValueError): self.create()

    def test_cross_run_probe_is_refused(self):
        self.change(self.new, "probe.json", lambda p: p.update(run_metadata_sha256=retry.sha(self.old / "run.json")))
        with self.assertRaises(ValueError): self.create()

    def test_different_actual_actor_config_is_refused(self):
        path = self.new / "tasks" / retry.TASK_ID / "actor-output.tar.gz"
        public, _ = retry._public_actor_run(path)
        public["config"]["request_timeout_seconds"] = 999
        self.actor_archive(self.new, public)
        with self.assertRaises(ValueError): self.create()

    def test_model_override_is_refused(self):
        public, _ = retry._public_actor_run(self.new / "tasks" / retry.TASK_ID / "actor-output.tar.gz")
        public["model_override"] = "another-model"
        self.actor_archive(self.new, public)
        with self.assertRaises(ValueError): self.create()

    def test_rehashed_different_harness_is_refused(self):
        (self.new / "harness/runtime.py").write_text("changed code")
        self.freeze(self.new)
        with self.assertRaises(ValueError): self.create()

    def test_different_bundle_content_is_refused_even_when_rehashed(self):
        self.bundle(self.new / "runtime-bundle.tar.gz", content=b"different runtime")
        self.freeze(self.new)
        with self.assertRaises(ValueError): self.create()

    def test_changed_receipt_after_create_is_refused(self):
        self.create()
        self.change(self.new, self.receipt, lambda r: r.update(score=.5))
        with self.assertRaises(ValueError): retry.verify_record(self.old, self.root / "record.json")

    def test_same_run_is_refused(self):
        with self.assertRaises(ValueError): retry.create_record(self.old, self.old, self.root / "record.json")

    def test_original_receipt_cannot_be_output(self):
        with self.assertRaises(ValueError): retry.create_record(self.old, self.new, self.old / self.receipt)

    def test_record_is_never_overwritten(self):
        self.create()
        with self.assertRaises(FileExistsError): self.create()

    def test_boolean_retry_score_is_not_numeric(self):
        self.change(self.new, self.receipt, lambda r: r.update(score=True))
        with self.assertRaises(ValueError): self.create()

    def test_a_legal_failed_new_attempt_is_recorded_without_forcing_success(self):
        self.change(self.new, self.receipt, lambda r: r.update(score=0.0, agent_success=False, official_terminal_action="FAIL"))
        self.change(self.new, "tasks/" + retry.TASK_ID + "/actor-result.json", lambda a: a["result"].update(agent_success=False))
        self.assertEqual(self.create()["score"], 0)

    def test_retry_before_original_error_is_refused(self):
        self.change(self.new, self.receipt, lambda r: r.update(started_at="2026-11-17T12:00:00+00:00"))
        with self.assertRaises(ValueError): self.create()


class AuditedBundlePermissionTests(unittest.TestCase):
    def entry(self, mode):
        return {"type": "file", "mode": mode, "size": 5569,
                "sha256": retry.AUDITED_GUEST_ACTOR_SHA256}

    def test_only_audited_group_write_difference_is_accepted_and_disclosed(self):
        for before, after in ((0o644, 0o664), (0o664, 0o644)):
            with self.subTest(before=before, after=after):
                old = {"guest_actor.py": self.entry(before)}
                new = {"guest_actor.py": self.entry(after)}
                saved = deepcopy((old, new))
                normalized, changes = retry.compare_bundle_inventories(old, new)
                self.assertEqual(normalized["guest_actor.py"]["mode"], 0o644)
                self.assertEqual(changes[0]["original_mode"], before)
                self.assertEqual(changes[0]["retry_mode"], after)
                self.assertEqual(changes[0]["unchanged_sha256"], retry.AUDITED_GUEST_ACTOR_SHA256)
                self.assertEqual((old, new), saved)

    def test_no_difference_does_not_claim_a_permission_exception(self):
        value = {"guest_actor.py": self.entry(0o644)}
        _, changes = retry.compare_bundle_inventories(value, deepcopy(value))
        self.assertEqual(changes, [])

    def test_executable_setuid_world_writable_or_other_permissions_are_rejected(self):
        for mode in (0o744, 0o666, 0o4644, 0o640, 0o660, 0o764):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                retry.compare_bundle_inventories({"guest_actor.py": self.entry(0o644)},
                                                {"guest_actor.py": self.entry(mode)})

    def test_the_same_mode_change_for_any_other_path_is_rejected(self):
        for name in ("guest_bootstrap.py", "product/guest_actor.py", "uv"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                retry.compare_bundle_inventories({name: self.entry(0o644)}, {name: self.entry(0o664)})

    def test_changed_content_size_or_type_is_rejected(self):
        for changes in ({"sha256": "0" * 64}, {"size": 5570}, {"type": "directory"}):
            after = self.entry(0o664) | changes
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                retry.compare_bundle_inventories({"guest_actor.py": self.entry(0o644)},
                                                {"guest_actor.py": after})

    def test_changed_path_inventory_is_rejected(self):
        with self.assertRaises(ValueError):
            retry.compare_bundle_inventories({"guest_actor.py": self.entry(0o644)}, {})


if __name__ == "__main__":
    unittest.main()
