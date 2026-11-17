"""Real DOCX extraction regressions using the unchanged official score functions."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import address_reference_repair as repair
import repair_address_reference as command

UPSTREAM = Path(os.environ.get("OSWORLD_UPSTREAM_DIR", "/tmp/osworld-corpus-5123"))
try:
    from docx import Document
    from docx.shared import Pt
    import rapidfuzz
    DEPS = (UPSTREAM / "desktop_env/evaluators/metrics/general.py").is_file()
except ImportError:
    DEPS = False


@unittest.skipUnless(DEPS, "Requires documented control dependencies and OSWORLD_UPSTREAM_DIR")
class AddressHeadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.official = repair.load_official_functions(UPSTREAM)
        task = json.loads((ROOT / "data/tasks/multi_apps" / (repair.TASK_ID + ".json")).read_text())
        cls.rules = task["evaluator"]["expected"]["rules"]
        cls.addresses = [g[0] for g in cls.rules["expected"][:6]]

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)

    def document(self, entries, *, heading=None, style="Normal", bold=True, title_size=14, body_size=12):
        doc = Document()
        if heading is not None:
            paragraph = doc.add_paragraph(heading, style=style)
            for run in paragraph.runs:
                run.bold, run.font.size = bold, Pt(title_size)
        for text in entries:
            paragraph = doc.add_paragraph(text)
            for run in paragraph.runs:
                run.font.size = Pt(body_size)
        path = self.folder / (str(len(list(self.folder.iterdir()))) + ".docx")
        doc.save(path)
        return path

    def scores(self, path):
        return (self.official["fuzzy_place_math"](str(path), self.rules),
                repair.score_document(str(path), self.rules, self.official))

    def test_normal_bold_larger_title_is_ignored_without_rewriting(self):
        path = self.document(self.addresses[:5], heading="深圳市福田区24小时自助签注机地址（5个）：")
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        old, (new, audit) = self.scores(path)
        self.assertEqual((old, new), (0, 1))
        self.assertEqual(audit["ignored_paragraphs"][0]["style"], "Normal")
        self.assertTrue(audit["ignored_paragraphs"][0]["larger_bold_title"])
        self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_title_style_is_supported_with_same_size_and_no_direct_bold(self):
        path = self.document(self.addresses[:5], heading="福田区自助签注机地址", style="Title", bold=False, title_size=12)
        self.assertEqual(self.scores(path)[1][0], 1)

    def test_six_real_addresses_still_fail_with_heading(self):
        path = self.document(self.addresses, heading="福田区自助签注机地址")
        self.assertEqual(self.scores(path)[1][0], 0)

    def test_six_real_addresses_are_never_relabelled_as_heading(self):
        path = self.document(self.addresses)
        old, (new, audit) = self.scores(path)
        self.assertEqual((old, new), (0, 0))
        self.assertEqual(audit["ignored_paragraphs"], [])

    def test_five_address_document_is_unchanged(self):
        path = self.document(self.addresses[:5])
        old, (new, audit) = self.scores(path)
        self.assertEqual((old, new), (1, 1))
        self.assertEqual(audit["ignored_paragraphs"], [])

    def test_duplicate_cannot_be_hidden_by_heading_repair(self):
        entries = [self.addresses[0], self.addresses[0], *self.addresses[2:5]]
        path = self.document(entries, heading="福田区自助签注机地址")
        self.assertEqual(self.scores(path)[1][0], 0)

    def test_partial_credit_formula_and_all_remaining_text_are_unchanged(self):
        entries = self.addresses[:5]
        entries[0] += "（每天24小时）"
        plain = self.document(entries)
        headed = self.document(entries, heading="福田区自助签注机地址")
        expected = self.official["fuzzy_place_math"](str(plain), self.rules)
        new, audit = repair.score_document(str(headed), self.rules, self.official)
        self.assertGreater(expected, 0)
        self.assertLess(expected, 1)
        self.assertEqual(new, expected)
        doc = Document(headed)
        view, _ = repair.prepare_address_scoring_view(doc, self.rules, self.official)
        self.assertEqual([p.text for p in view.paragraphs], entries)
        self.assertEqual(audit["remaining_nonempty_paragraphs"], 5)

    def test_unmatched_arbitrary_paragraph_is_not_dropped(self):
        for heading in ("以下信息尚未核实", "福田区自助签注机地址（某公园）"):
            with self.subTest(heading=heading):
                path = self.document(self.addresses[:5], heading=heading)
                _, (new, audit) = self.scores(path)
                self.assertEqual(new, 0)
                self.assertEqual(audit["ignored_paragraphs"], [])

    def test_heading_with_street_number_or_reference_identity_is_not_dropped(self):
        for heading in ("福田区自助签注机地址：正义街1号", "福田区自助签注机地址：某路999号"):
            with self.subTest(heading=heading):
                path = self.document(self.addresses[:5], heading=heading, style="Heading 1")
                self.assertEqual(self.scores(path)[1][1]["ignored_paragraphs"], [])

    def test_numbered_heading_is_not_dropped(self):
        path = self.document(self.addresses[:5], heading="1. 福田区自助签注机地址", style="Heading 1")
        self.assertEqual(self.scores(path)[1][1]["ignored_paragraphs"], [])

    def test_normal_same_size_or_not_all_bold_does_not_qualify(self):
        for bold, size in ((False, 14), (True, 12)):
            path = self.document(self.addresses[:5], heading="福田区自助签注机地址", bold=bold, title_size=size)
            self.assertEqual(self.scores(path)[1][1]["ignored_paragraphs"], [])

    def test_only_first_nonempty_paragraph_is_considered(self):
        path = self.document(["无关说明", *self.addresses[:5]], heading="福田区自助签注机地址")
        self.assertEqual(self.scores(path)[1][0], 0)
        path = self.document([self.addresses[0], "福田区自助签注机地址", *self.addresses[1:5]])
        self.assertEqual(self.scores(path)[1][1]["ignored_paragraphs"], [])

    def test_invalid_outer_count_and_missing_path_keep_original_zero(self):
        for count in (True, "5", 0, -1):
            rules = deepcopy(self.rules)
            rules["expected_entry_count"] = count
            self.assertEqual(repair.score_document("not-opened.docx", rules, self.official)[0], 0)
        self.assertEqual(repair.score_document(None, self.rules, self.official)[0], 0)

    def test_original_metric_identity_works_in_a_non_git_archive(self):
        archived = self.folder / "archive/desktop_env/evaluators/metrics/general.py"
        archived.parent.mkdir(parents=True)
        archived.write_bytes((UPSTREAM / "desktop_env/evaluators/metrics/general.py").read_bytes())
        self.assertFalse((self.folder / "archive/.git").exists())
        with mock.patch("subprocess.run", side_effect=AssertionError("No Git command is allowed")):
            identity = command.verify_original_metric_source(archived)
        self.assertEqual(identity["sha256"], command.METRIC_SHA256)
        self.assertEqual(identity["git_blob_sha1"], command.METRIC_GIT_BLOB_SHA1)

    def test_non_git_archive_still_rejects_any_metric_byte_change(self):
        archived = self.folder / "general.py"
        archived.write_bytes((UPSTREAM / "desktop_env/evaluators/metrics/general.py").read_bytes() + b"\n# changed\n")
        with self.assertRaises(ValueError):
            command.verify_original_metric_source(archived)


@unittest.skipUnless(DEPS, "Requires documented control dependencies and OSWORLD_UPSTREAM_DIR")
class AddressCorrectionTests(unittest.TestCase):
    """Exercise real metric/file I/O; isolate only the run identity preflight."""
    @classmethod
    def setUpClass(cls):
        AddressHeadingTests.setUpClass.__func__(cls)

    document = AddressHeadingTests.document

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.rules = deepcopy(type(self).rules)
        self.run = self.folder / "run"
        self.run.mkdir()
        (self.run / "run.json").write_text('{"fixture":"immutable"}')
        self.receipt = self.run / "receipt.json"
        self.receipt.write_text('{"status":"scored","score":0}')
        self.task = ROOT / "data/tasks/multi_apps" / (repair.TASK_ID + ".json")
        self.actual = self.document(self.addresses[:5], heading="福田区自助签注机地址")
        self.metric = UPSTREAM / "desktop_env/evaluators/metrics/general.py"
        self.metadata = {"osworld_root": str(UPSTREAM)}
        self.preflight = mock.patch.object(command, "inputs", return_value=(self.metadata,
            self.task, self.receipt, self.actual, self.metric, self.rules))
        self.inputs_mock = self.preflight.start()
        self.addCleanup(self.preflight.stop)

    def perform(self):
        output = self.folder / "correction"
        record = command.repair(self.run, output)
        return output, record

    def test_correction_roundtrip_preserves_all_original_files(self):
        paths = [self.run / "run.json", self.task, self.receipt, self.actual, self.metric]
        before = {p: command.sha(p) for p in paths}
        output, record = self.perform()
        self.assertEqual(record["score"], 1)
        self.assertEqual(record["original_score"], 0)
        self.assertFalse(record["actor_rerun"])
        self.assertEqual(record["model_calls"], 0)
        self.assertEqual(record["vm_starts"], 0)
        self.assertEqual(command.verify_correction(self.run, output / "correction.json"), record)
        self.assertEqual(before, {p: command.sha(p) for p in paths})

    def rewrite_record(self, output, record):
        (output / "correction.json").write_text(json.dumps(record, ensure_ascii=False))

    def test_changed_score_is_not_accepted(self):
        output, record = self.perform()
        record["score"] = .25
        self.rewrite_record(output, record)
        with self.assertRaises(ValueError):
            command.verify_correction(self.run, output / "correction.json")

    def test_changed_reference_rule_is_not_accepted(self):
        output, record = self.perform()
        record["original_expected_rule"]["expected_entry_count"] = 6
        self.rewrite_record(output, record)
        with self.assertRaises(ValueError):
            command.verify_correction(self.run, output / "correction.json")

    def test_changed_original_actual_is_not_accepted(self):
        output, _ = self.perform()
        self.actual.write_bytes(self.actual.read_bytes() + b"changed")
        with self.assertRaises(ValueError):
            command.verify_correction(self.run, output / "correction.json")

    def test_changed_archived_repair_source_is_not_accepted(self):
        output, _ = self.perform()
        source = output / "address_reference_repair.py"
        source.write_text(source.read_text() + "\n# changed\n")
        with self.assertRaises(ValueError):
            command.verify_correction(self.run, output / "correction.json")

    def test_changed_extraction_cannot_pass_with_rehashed_json(self):
        output, record = self.perform()
        target = output / "heading-extraction.json"
        extraction = json.loads(target.read_text())
        extraction["ignored_paragraphs"][0]["text"] = "different title"
        target.write_text(json.dumps(extraction))
        record["extraction_sha256"] = command.sha(target)
        self.rewrite_record(output, record)
        with self.assertRaises(ValueError):
            command.verify_correction(self.run, output / "correction.json")

    def test_boolean_score_is_not_numeric_original_zero(self):
        output, record = self.perform()
        record["original_score"] = False
        self.rewrite_record(output, record)
        with self.assertRaises(ValueError):
            command.verify_correction(self.run, output / "correction.json")

    def test_existing_output_is_never_overwritten(self):
        output = self.folder / "correction"
        output.mkdir()
        sentinel = output / "keep.txt"
        sentinel.write_text("preserved")
        with self.assertRaises(FileExistsError):
            command.repair(self.run, output)
        self.assertEqual(sentinel.read_text(), "preserved")

    def test_nonzero_original_or_no_heading_is_refused(self):
        self.actual = self.document(self.addresses[:5])
        self.inputs_mock.return_value = (self.metadata, self.task, self.receipt,
                                        self.actual, self.metric, self.rules)
        output = self.folder / "correction"
        with self.assertRaises(ValueError):
            command.repair(self.run, output)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
