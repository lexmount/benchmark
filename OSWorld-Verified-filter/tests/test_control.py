"""Offline acceptance checks for the frozen task set and honest result coverage.

Run: python3 -m unittest discover -s OSWorld-Verified-filter/tests -v
No model, VM, browser, network or non-standard-library dependency is used.
"""
from __future__ import annotations

from collections import Counter
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("osworld_filter_control", ROOT / "evaluate.py")
control = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class FrozenTaskSetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "data", self.root / "data")
        self.manifest = control.read_json(self.root / "data/manifest.json")

    def test_approved_set_has_76_original_tasks_in_official_relative_order(self):
        result = control.verify(self.root)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["model_calls"], 0)
        tasks = self.manifest["tasks"]
        self.assertEqual(len(tasks), 76)
        self.assertEqual(Counter(t["category"] for t in tasks),
                         {"web": 25, "browser_file": 27, "local_file": 24})
        original = control.read_json(self.root / "data/upstream/test_all.json")
        official_ids = [(domain, ident) for domain, ids in original.items() for ident in ids]
        positions = [official_ids.index((t["source_domain"], t["task_id"])) for t in tasks]
        self.assertEqual(positions, sorted(set(positions)))
        for t in tasks:
            self.assertEqual(original[t["source_domain"]][t["source_ordinal"] - 1], t["task_id"])

    def test_exact_eight_drive_exclusions_do_not_exclude_colab_by_url_substring(self):
        original = control.read_json(self.root / "data/upstream/test_all.json")
        without_drive = control.read_json(self.root / "data/upstream/test_nogdrive.json")
        all_ids = {ident for ids in original.values() for ident in ids}
        nogdrive_ids = {ident for ids in without_drive.values() for ident in ids}
        official_excluded = all_ids - nogdrive_ids
        self.assertEqual(len(official_excluded), 8)
        selected = {t["task_id"] for t in self.manifest["tasks"]}
        self.assertFalse(selected & official_excluded)
        # A Colab /drive/ link is not one of the eight Google Drive workflow tasks.
        self.assertIn("dd60633f-2c72-42ba-8547-6f2c8cb0fdb0", selected)
        exclusions = control.read_json(self.root / "data/exclusions.json")
        self.assertEqual(exclusions["candidate_count"], 84)
        self.assertEqual({x["task_id"] for x in exclusions["excluded"]}, official_excluded)

    def test_even_semantically_identical_raw_task_reformatting_is_rejected(self):
        task = self.root / self.manifest["tasks"][0]["task_path"]
        task.write_bytes(task.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Task bytes changed"):
            control.verify(self.root)

    def test_instruction_rewrite_is_rejected(self):
        task = self.root / self.manifest["tasks"][0]["task_path"]
        value = control.read_json(task)
        value["instruction"] += " Also accept a different output path."
        write_json(task, value)
        with self.assertRaisesRegex(ValueError, "Task bytes changed"):
            control.verify(self.root)

    def test_extra_task_is_rejected_instead_of_changing_denominator(self):
        write_json(self.root / "data/tasks/chrome/extra.json", {"id": "extra"})
        with self.assertRaisesRegex(ValueError, "Extra/missing raw task file"):
            control.verify(self.root)

    def test_manifest_reordering_is_not_accepted_even_when_json_is_valid(self):
        self.manifest["tasks"][0], self.manifest["tasks"][1] = (
            self.manifest["tasks"][1], self.manifest["tasks"][0])
        write_json(self.root / "data/manifest.json", self.manifest)
        with self.assertRaisesRegex(ValueError, "approved 76-task manifest changed"):
            control.verify(self.root)

    def test_drive_exclusion_list_cannot_be_silently_expanded_or_reduced(self):
        path = self.root / "data/exclusions.json"
        exclusions = control.read_json(path)
        exclusions["excluded"].pop()
        write_json(path, exclusions)
        with self.assertRaisesRegex(ValueError, "Wrong Drive exclusions"):
            control.verify(self.root)


class ResultCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run_dir = Path(self.temp.name)
        self.tasks = control.read_json(ROOT / "data/manifest.json")["tasks"]
        write_json(self.run_dir / "run.json", {
            "agent_commit": "a" * 40,
            "upstream_commit": control.UPSTREAM,
            "harness_root": str(ROOT),
        })

    def receipt(self, n: int, **changes):
        item = self.tasks[n]
        value = {"status": "scored", "score": 1.0,
                 "task_id": item["task_id"], "task_sha256": item["sha256"]}
        value.update(changes)
        write_json(self.run_dir / "tasks" / item["task_id"] / "receipt.json", value)

    def test_missing_receipts_are_unscored_not_zero_scores(self):
        result = control.report(self.run_dir)
        self.assertEqual(result["fixed_denominator"], 76)
        self.assertEqual(result["valid_scored_tasks"], 0)
        self.assertEqual(result["unscored_tasks"], 76)
        self.assertIsNone(result["observed_mean_score"])
        self.assertIsNone(result["full_76_mean_score"])
        self.assertIsNone(result["full_76_success_rate"])
        self.assertFalse(result["complete"])
        self.assertEqual(result["unscored_statuses"], {"missing": 76})
        self.assertTrue(all(t["score"] is None for t in result["tasks"]))

    def test_partial_float_score_is_preserved_without_claiming_a_full_run(self):
        self.receipt(0, score=0.73125)
        self.receipt(1, score=0)
        result = control.report(self.run_dir)
        self.assertEqual(result["valid_scored_tasks"], 2)
        self.assertEqual(result["unscored_tasks"], 74)
        self.assertAlmostEqual(result["score_sum"], 0.73125)
        self.assertAlmostEqual(result["observed_mean_score"], 0.365625)
        self.assertIsNone(result["full_76_mean_score"])
        self.assertIsNone(result["full_76_success_rate"])
        self.assertFalse(result["complete"])

    def test_only_complete_valid_coverage_has_a_full_76_score(self):
        for n in range(76):
            self.receipt(n, score=0.5 if n == 0 else 1.0)
        result = control.report(self.run_dir)
        self.assertTrue(result["complete"])
        self.assertEqual(result["valid_scored_tasks"], 76)
        self.assertEqual(result["unscored_tasks"], 0)
        self.assertEqual(result["score_sum"], 75.5)
        self.assertAlmostEqual(result["full_76_mean_score"], 75.5 / 76)
        self.assertEqual(result["fully_successful_tasks"], 75)
        self.assertAlmostEqual(result["full_76_success_rate"], 75 / 76)

    def test_boolean_nonfinite_out_of_range_and_non_numeric_scores_are_invalid(self):
        values = [True, False, float("nan"), float("inf"), -0.01, 1.01, "1", None]
        for n, value in enumerate(values):
            self.receipt(n, score=value)
        result = control.report(self.run_dir)
        self.assertEqual(result["valid_scored_tasks"], 0)
        self.assertEqual(result["unscored_statuses"]["invalid_receipt"], len(values))
        self.assertTrue(all(result["tasks"][n]["score"] is None for n in range(len(values))))

    def test_a_different_task_id_or_source_hash_cannot_contribute_a_score(self):
        self.receipt(0, task_sha256="f" * 64)
        self.receipt(1, task_id=self.tasks[0]["task_id"])
        result = control.report(self.run_dir)
        self.assertEqual(result["valid_scored_tasks"], 0)
        self.assertEqual(result["unscored_statuses"]["invalid_receipt"], 2)

    def test_setup_actor_and_evaluator_errors_never_become_legitimate_zero_scores(self):
        statuses = ["setup_error", "bootstrap_error", "actor_timeout", "actor_error", "evaluation_error"]
        for n, status in enumerate(statuses):
            self.receipt(n, status=status, score=0)
        result = control.report(self.run_dir)
        self.assertEqual(result["valid_scored_tasks"], 0)
        self.assertIsNone(result["observed_mean_score"])
        for n, status in enumerate(statuses):
            self.assertEqual(result["unscored_statuses"][status], 1)
            self.assertIsNone(result["tasks"][n]["score"])

    def test_report_is_read_only_and_does_not_overwrite_an_existing_receipt(self):
        self.receipt(0, score=0.125)
        path = self.run_dir / "tasks" / self.tasks[0]["task_id"] / "receipt.json"
        before = path.read_bytes()
        first = control.report(self.run_dir)
        second = control.report(self.run_dir)
        self.assertEqual(first, second)
        self.assertEqual(path.read_bytes(), before)

    def test_malformed_or_non_object_json_is_unscored_instead_of_a_complete_score(self):
        path = self.run_dir / "tasks" / self.tasks[0]["task_id"] / "receipt.json"
        path.parent.mkdir(parents=True)
        for content in ['{"score":', '[]', 'null', '"scored"']:
            with self.subTest(content=content):
                path.write_text(content)
                result = control.report(self.run_dir)
                self.assertFalse(result["complete"])
                self.assertEqual(result["valid_scored_tasks"], 0)
                self.assertEqual(result["unscored_statuses"]["invalid_receipt"], 1)
                self.assertIsNone(result["tasks"][0]["score"])

    def test_modified_frozen_run_identity_is_rejected_by_report(self):
        path = self.run_dir / "run.json"
        write_json(self.run_dir / "frozen-files.json", {"run.json": control.digest(path)})
        record = control.read_json(path)
        record["agent_commit"] = "b" * 40
        write_json(path, record)
        with self.assertRaisesRegex(ValueError, "Frozen report input changed"):
            control.report(self.run_dir)


if __name__ == "__main__":
    unittest.main()
