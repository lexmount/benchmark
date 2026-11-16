"""BU-filter acceptance tests. No browser, API, or paid model call is used."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bu_filter_dataset", ROOT / "dataset.py")
dataset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dataset)
EXCLUDED_ORDINALS = {11, 34, 39, 41, 46, 57, 61, 70, 76, 81, 86, 92, 96}


class DatasetTests(unittest.TestCase):
    def test_exact_87_ids_and_original_ordinals(self):
        rows = dataset.load_tasks()
        self.assertEqual(len(rows), 87)
        self.assertEqual(len({row["id"] for row in rows}), 87)
        self.assertEqual([row["ordinal"] for row in rows], [n for n in range(1, 101) if n not in EXCLUDED_ORDINALS])
        self.assertFalse(dataset.EXCLUDED_IDS & {row["id"] for row in rows})
        self.assertEqual(next(row["id"] for row in rows if row["ordinal"] == 19), dataset.TASK_19_ID)

    def test_actor_never_receives_reference_answers(self):
        public = dataset.load_tasks()
        full = dataset.load_judge_tasks()
        self.assertEqual(sum(row["answer"] is not None for row in full), 37)
        for safe, private in zip(public, full, strict=True):
            self.assertEqual(set(safe), {"ordinal", "id", "instruction", "start_url"})
            actor = dataset.actor_task(private)
            self.assertEqual(set(actor), {"id", "instruction", "start_url"})
            self.assertEqual(actor["instruction"], safe["instruction"])

    def test_refuses_excluded_and_modified_actor_tasks(self):
        task = dataset.load_tasks()[0]
        with self.assertRaises(dataset.DatasetError):
            dataset.actor_task(dict(task, id=next(iter(dataset.EXCLUDED_IDS))))
        with self.assertRaises(dataset.DatasetError):
            dataset.actor_task(dict(task, instruction=task["instruction"] + " changed"))
        with self.assertRaises(dataset.DatasetError):
            dataset.actor_task(dict(task, start_url="https://changed.invalid"))

    def test_ciphertext_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "data"
            shutil.copytree(dataset.DATA_DIR, target)
            path = target / "BU_FILTER.enc"
            path.write_bytes(path.read_bytes() + b"changed")
            with patch.object(dataset, "DATA_DIR", target), self.assertRaises(dataset.DatasetError):
                dataset.load_tasks()

    def test_manifest_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "data"
            shutil.copytree(dataset.DATA_DIR, target)
            path = target / "manifest.json"
            manifest = json.loads(path.read_text())
            manifest["task_count"] = 86
            path.write_text(json.dumps(manifest))
            with patch.object(dataset, "DATA_DIR", target), self.assertRaises(dataset.DatasetError):
                dataset.validate_dataset()

    def test_exclusion_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "data"
            shutil.copytree(dataset.DATA_DIR, target)
            path = target / "exclusions.json"
            path.write_text("[]")
            with patch.object(dataset, "DATA_DIR", target), self.assertRaises(dataset.DatasetError):
                dataset.load_judge_tasks()

    def test_validation_report_contains_no_task_or_gold_text(self):
        report = dataset.validate_dataset()
        self.assertEqual((report["task_count"], report["excluded_count"]), (87, 13))
        self.assertTrue(report["task_19_retained"])
        self.assertNotIn("instruction", report)
        self.assertNotIn("answer", report)


if __name__ == "__main__":
    unittest.main()
