"""A technical correction never overwrites an Actor result or hides coverage."""
import importlib.util
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pdf_correction_tests", ROOT / "repair_pdf_reference.py")
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class CorrectionReportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.run = Path(temp.name)
        manifest = json.loads((ROOT / "data/manifest.json").read_text())
        self.item = next(t for t in manifest["tasks"] if t["task_id"] == repair.TASK_ID)
        write(self.run / "run.json", {"agent_commit": "a" * 40,
              "upstream_commit": "5123bfdbbc34b947bcffcff564abc62d0ab7072d",
              "harness_root": str(ROOT), "osworld_root": str(self.run / "upstream")})
        self.original = self.run / "tasks" / repair.TASK_ID / "receipt.json"
        write(self.original, {"status": "scored", "score": 0.0, "task_id": repair.TASK_ID,
                             "task_sha256": self.item["sha256"]})
        task = json.loads((ROOT / self.item["task_path"]).read_text())
        self.gold = self.original.parent / "official-cache" / repair.TASK_ID / task["evaluator"]["expected"]["dest"]
        self.gold.parent.mkdir(parents=True)
        self.gold.write_bytes(b"%PDF-1.4\n%EOF\n")
        self.before = self.original.read_bytes()

    def test_broken_reference_zero_is_preserved_raw_but_unscored_in_audited_report(self):
        result = repair.report(self.run)
        self.assertEqual(result["raw_official"]["valid_scored_tasks"], 1)
        self.assertEqual(result["valid_scored"], 0)
        self.assertEqual(result["status_counts"]["reference_unavailable"], 1)
        self.assertIsNone(result["full_76_mean"])
        self.assertEqual(result["task_count"], 76)
        self.assertEqual(self.original.read_bytes(), self.before)

    def test_repaired_fraction_is_not_rounded_and_never_claimed_as_full_76(self):
        correction = self.run / "correction.json"
        correction.write_text("{}")
        with patch.object(repair, "verify_correction", return_value={"score": .973,
                                                                   "original_score": 0.0}):
            result = repair.report(self.run, correction)
        self.assertEqual(result["valid_scored"], 1)
        self.assertEqual(result["corrected_tasks"], 1)
        self.assertEqual(result["score_sum"], .973)
        self.assertIsNone(result["full_76_mean"])
        self.assertEqual(self.original.read_bytes(), self.before)

    def test_invalid_correction_stops_report_instead_of_silently_using_its_score(self):
        correction = self.run / "wrong.json"
        write(correction, {"binding": {}, "status": "corrected", "task_id": "wrong"})
        with self.assertRaises(ValueError):
            repair.report(self.run, correction)

    def test_new_correction_cannot_overwrite_existing_receipt(self):
        with self.assertRaises(FileExistsError):
            repair.write_new(self.original, {"score": 1})
        self.assertEqual(self.original.read_bytes(), self.before)


class CorrectionIdentityTests(unittest.TestCase):
    """Use real task/evaluator paths; mock only the expensive frozen-run verification."""
    def setUp(self):
        CorrectionReportTests.setUp(self)
        self.metadata = json.loads((self.run / "run.json").read_text())
        self.task = json.loads((ROOT / self.item["task_path"]).read_text())
        self.actual = self.gold.parent / self.task["evaluator"]["result"]["dest"]
        self.actual.write_bytes(b"archived actor PDF fixture identity")
        self.metric = self.run / "upstream/desktop_env/evaluators/metrics/chrome.py"
        self.metric.parent.mkdir(parents=True)
        self.metric_code = "def compare_pdfs(actual, reference):\n    calls.append((actual, reference))\n    return 0.973\n"
        self.metric.write_text(self.metric_code)

    def control(self):
        return types.SimpleNamespace(verify_run=Mock(return_value=self.metadata))

    def packet(self):
        output = self.run / "correction-packet"
        output.mkdir(exist_ok=True)
        reference = output / "new-reference.pdf"
        reference.write_bytes(b"independent reference PDF fixture identity")
        for name in ("reference_repair.py", "repair_pdf_reference.py"):
            shutil.copyfile(ROOT / name, output / name)
        return output / "correction.json", {
            "status": "corrected", "task_id": repair.TASK_ID,
            "actor_rerun": False, "model_calls": 0, "owned_vm_closed": True,
            "evidence_errors": [], "run_dir": str(self.run),
            "binding": {"run_metadata_sha256": repair.sha(self.run / "run.json"),
                "original_receipt": str(self.original), "original_receipt_sha256": repair.sha(self.original),
                "original_actual": str(self.actual), "original_actual_sha256": repair.sha(self.actual),
                "invalid_reference": str(self.gold), "invalid_reference_sha256": repair.sha(self.gold)},
            "reference": str(reference), "reference_sha256": repair.sha(reference),
            "repair_sources_sha256": {name: repair.sha(output / name) for name in
                ("reference_repair.py", "repair_pdf_reference.py")},
            "metric_source_sha256": repair.sha(self.metric), "score": 0.973, "original_score": 0.0,
        }

    def test_original_boolean_or_non_numeric_zero_is_not_a_repairable_official_zero(self):
        original = json.loads(self.original.read_text())
        for value in (False, True, "0", None, float("nan"), float("inf")):
            with self.subTest(value=value):
                write(self.original, original | {"score": value})
                with patch.object(repair, "load", return_value=self.control()):
                    with self.assertRaisesRegex(ValueError, "original scored-zero receipt"):
                        repair.inputs(self.run)
        for value in (0, 0.0):
            with self.subTest(valid_zero=value):
                write(self.original, original | {"score": value})
                with patch.object(repair, "load", return_value=self.control()):
                    _, _, receipt, actual, invalid = repair.inputs(self.run)
                self.assertEqual(receipt, self.original)
                self.assertEqual(actual, self.actual)
                self.assertEqual(invalid, self.gold)

    def test_correction_with_consistent_real_artifact_paths_is_accepted(self):
        path, value = self.packet()
        write(path, value)
        with patch.object(repair, "load", return_value=self.control()):
            result = repair.verify_correction(self.run, path)
        self.assertEqual(result["score"], 0.973)

    def test_equal_bytes_at_another_path_cannot_be_bound_as_the_original_artifact(self):
        path, value = self.packet()
        for key in ("original_receipt", "original_actual", "invalid_reference"):
            with self.subTest(artifact=key):
                forged = deepcopy(value)
                alternate = self.run / "another-task" / (key + ".copy")
                alternate.parent.mkdir(exist_ok=True)
                alternate.write_bytes(Path(forged["binding"][key]).read_bytes())
                # Equal bytes and equal SHA deliberately pass content-integrity
                # checks; only the frozen evaluator-derived path can reject it.
                forged["binding"][key] = str(alternate)
                self.assertEqual(repair.sha(alternate), forged["binding"][key + "_sha256"])
                write(path, forged)
                with patch.object(repair, "load", return_value=self.control()):
                    with self.assertRaisesRegex(ValueError, "another original artifact"):
                        repair.verify_correction(self.run, path)

    def invoke_metric_binding(self, *, wrong_source):
        output = self.run / ("wrong-source-repair" if wrong_source else "correct-source-repair")
        reference = self.run / "generated-reference.pdf"
        reference.write_bytes(b"generated reference fixture identity")
        source = self.run / "other-checkout/chrome.py" if wrong_source else self.metric
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(self.metric_code)
        namespace = {"calls": []}
        exec(compile(self.metric_code, str(source), "exec"), namespace)
        metric_module = types.ModuleType("desktop_env.evaluators.metrics.chrome")
        metric_module.compare_pdfs = namespace["compare_pdfs"]
        reference_module = types.ModuleType("reference_repair")
        reference_module.get_pdf_from_url = Mock(return_value=str(reference))
        reference_module.validate_pdf = Mock(return_value={"pages": 1, "text_chars": 21})
        env = types.SimpleNamespace(reset=Mock())

        @contextmanager
        def environment(metadata, folder, receipt):
            try:
                yield env
            finally:
                receipt["owned_vm_closed"] = True

        bridge = types.SimpleNamespace(_environment=environment, _ensure_cdp=Mock(return_value={"port": 1337}))
        before = {path: path.read_bytes() for path in (self.original, self.actual, self.gold)}
        with patch.dict(sys.modules, {"reference_repair": reference_module,
                                      "desktop_env.evaluators.metrics.chrome": metric_module}), \
                patch.object(repair, "inputs", return_value=(self.metadata, self.task, self.original, self.actual, self.gold)), \
                patch.object(repair, "load", return_value=bridge):
            result = repair.repair(self.run, output)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        env.reset.assert_called_once_with(task_config=self.task)
        return result, namespace["calls"]

    def test_repair_calls_the_actual_metric_from_the_frozen_checkout(self):
        result, calls = self.invoke_metric_binding(wrong_source=False)
        self.assertEqual(result["status"], "corrected")
        self.assertEqual(result["score"], 0.973)
        self.assertEqual(result["metric_source_sha256"], repair.sha(self.metric))
        self.assertEqual(len(calls), 1)
        self.assertEqual(Path(calls[0][0]).resolve(), self.actual.resolve())
        self.assertEqual(Path(calls[0][1]).resolve(), (self.run / "generated-reference.pdf").resolve())

    def test_metric_imported_from_another_checkout_is_rejected_before_calling_it(self):
        result, calls = self.invoke_metric_binding(wrong_source=True)
        self.assertEqual(result["status"], "reference_unavailable")
        self.assertIsNone(result["score"])
        self.assertIn("Imported metric does not come from", result["error"])
        self.assertEqual(calls, [])


class FutureEnvironmentGetterHookTests(unittest.TestCase):
    def test_optional_hook_is_installed_before_constructor_and_reset_and_records_its_source_sha(self):
        # Reuse the existing fake upstream boundary, but run the actual new hook
        # and actual install_getter_patch against isolated getter exports.
        import test_runtime as contract
        getter_spec = importlib.util.spec_from_file_location("future_reference_getter", ROOT / "reference_repair.py")
        getter = importlib.util.module_from_spec(getter_spec)
        getter_spec.loader.exec_module(getter)
        lifecycle = contract.OwnedDockerLifecycleTests()
        for enabled in (False, True):
            with self.subTest(enabled=enabled), lifecycle.fake_upstream(remove_on_close=True) as data:
                metadata, folder, container, captured, lookups, instances = data
                if enabled:
                    metadata["config"]["scoring"] = {"reference_getter_repair": getter.REPAIR_VERSION}
                receipt = {"task_id": "sample-task", "evidence_errors": []}
                original_getter = lambda *args: "original"
                chrome = types.ModuleType("desktop_env.evaluators.getters.chrome")
                chrome.get_pdf_from_url = original_getter
                exports = types.ModuleType("desktop_env.evaluators.getters")
                exports.get_pdf_from_url = original_getter
                desktop_module = sys.modules["desktop_env.desktop_env"]
                original_env = desktop_module.DesktopEnv
                owner = self
                order = []

                def check():
                    expected = getter.get_pdf_from_url if enabled else original_getter
                    owner.assertIs(chrome.get_pdf_from_url, expected)
                    owner.assertIs(exports.get_pdf_from_url, expected)
                    if enabled:
                        owner.assertEqual(receipt["reference_getter_repair"]["repair_source_sha256"],
                                          repair.sha(ROOT / "reference_repair.py"))
                    else:
                        owner.assertNotIn("reference_getter_repair", receipt)

                class CheckedEnv(original_env):
                    def __init__(self, **kwargs):
                        check()
                        order.append("constructor")
                        super().__init__(**kwargs)
                    def reset(self):
                        check()
                        order.append("reset")

                with patch.dict(sys.modules, {"reference_repair": getter,
                    "desktop_env.evaluators.getters.chrome": chrome,
                    "desktop_env.evaluators.getters": exports}), \
                        patch.object(desktop_module, "DesktopEnv", CheckedEnv):
                    with contract.runtime._environment(metadata, folder, receipt) as env:
                        env.reset()
                self.assertEqual(order, ["constructor", "reset"])
                self.assertTrue(receipt["owned_vm_closed"])


if __name__ == "__main__":
    unittest.main()
