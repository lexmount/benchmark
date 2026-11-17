"""Independent-source restaurant reference and retained-file rejudge contracts."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import restaurant_reference_repair as reference
import repair_restaurant_reference as correction

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font
    HAVE_XLSX = True
except ImportError:
    HAVE_XLSX = False


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class RestaurantOptionsTests(unittest.TestCase):
    def test_only_last_website_cell_changes_and_input_is_immutable(self):
        original = deepcopy(reference.ORIGINAL_OPTIONS)
        result = reference.repair_options(original)
        self.assertEqual(original, reference.ORIGINAL_OPTIONS)
        old = original["rules"][0]["rules"]
        new = result["rules"][0]["rules"]
        self.assertEqual(old[:3], new[:3])
        self.assertTrue(new[1]["preserve_numeric_tokens"])
        self.assertEqual(new[1]["type"], "exact_match")
        self.assertEqual(new[3:], [{"range": ["D1:D5"], "type": "domain_match"}, {"range": ["D6"], "type": "exact_match"}])
        result["rules"][0]["rules"][1]["ignore_chars"] = "anything"
        self.assertEqual(original, reference.ORIGINAL_OPTIONS)

    def test_options_drift_is_rejected(self):
        for change in (lambda r: r[1].pop("preserve_numeric_tokens"),
                       lambda r: r[1].update(type="includes"),
                       lambda r: r[3].update(range=["D1:D5"])):
            options = deepcopy(reference.ORIGINAL_OPTIONS)
            change(options["rules"][0]["rules"])
            with self.assertRaises(ValueError):
                reference.repair_options(options)


class PinnedRestaurantMetricTests(unittest.TestCase):
    def test_non_git_archive_checks_content_without_a_git_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "archive/desktop_env/evaluators/metrics/table.py"
            path.parent.mkdir(parents=True)
            content = b"# an archived fixed upstream metric\n"
            path.write_bytes(content)
            checksum = hashlib.sha256(content).hexdigest()
            blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
            with mock.patch.object(correction, "METRIC_SHA256", checksum), \
                    mock.patch.object(correction, "METRIC_GIT_BLOB_SHA1", blob), \
                    mock.patch.object(subprocess, "run", side_effect=AssertionError("Git is unavailable")):
                self.assertFalse((Path(temporary) / ".git").exists())
                self.assertEqual(correction.verify_original_metric_source(path), {"sha256": checksum, "git_blob_sha1": blob})
                path.write_bytes(content + b"# mutation\n")
                with self.assertRaises(ValueError):
                    correction.verify_original_metric_source(path)

    def test_both_audited_digests_are_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "table.py"
            content = b"# fixed upstream metric\n"
            path.write_bytes(content)
            checksum = hashlib.sha256(content).hexdigest()
            blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
            for sha256, oid in ((checksum, "0" * 40), ("0" * 64, blob)):
                with mock.patch.object(correction, "METRIC_SHA256", sha256), mock.patch.object(correction, "METRIC_GIT_BLOB_SHA1", oid), self.assertRaises(ValueError):
                    correction.verify_original_metric_source(path)


@unittest.skipUnless(HAVE_XLSX, "Requires the official host's openpyxl dependency")
class RestaurantRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.snapshots = self.base / "snapshots"
        self.snapshots.mkdir()
        self.sources = []
        for row, (stem, name, observed, _, _) in enumerate(reference.SOURCES, 2):
            data = {"name": observed, "url": "https://www.google.com/maps/place/" + stem,
                "observation_kind": "independent_live_Google_Maps_DOM", "observed_at_utc": "2026-11-17T14:00:00Z",
                "address": "Address: Building %d, 301-310 Example Rd, Hong Kong " % row,
                "phone": "Phone: +852 2820 858%d " % row,
                "website": None if row == 6 else "https://restaurant%d.example/" % row,
                "permanently_closed": row == 6,
                "info_buttons": [] if row == 6 else [{"id": "authority", "href": "https://restaurant%d.example/" % row}]}
            put(self.snapshots / (stem + ".json"), data)
            png = self.snapshots / (stem + ".png")
            png.write_bytes(b"independent screenshot " + stem.encode())
            self.sources.append((stem, name, observed, reference.sha(self.snapshots / (stem + ".json")), reference.sha(png)))
        self.template = self.base / "old-reference.xlsx"
        book = Workbook()
        sheet = book.active
        sheet.title = "Sheet1"
        sheet.append(reference.HEADERS)
        for row, source in enumerate(self.sources, 2):
            sheet.append([source[1], "Historical address", None, "http://historical.example/"])
            sheet.cell(row, 4).hyperlink = "http://historical.example/"
        sheet["A1"].font = Font(bold=True)
        book.save(self.template)
        for module, key, value in ((reference, "SOURCES", tuple(self.sources)),
                                  (reference, "ORIGINAL_GOLD_SHA256", reference.sha(self.template)),
                                  (correction, "ORIGINAL_GOLD_SHA256", reference.sha(self.template))):
            patch = mock.patch.object(module, key, value)
            patch.start()
            self.addCleanup(patch.stop)

    def build(self):
        output = self.base / "built"
        provenance = reference.build_reference(self.template, self.snapshots, output)
        return output, provenance

    def test_reference_uses_only_independent_sources_preserves_template_and_null(self):
        before = self.template.read_bytes()
        output, provenance = self.build()
        current = load_workbook(output / "current-reference.xlsx")["Sheet1"]
        self.assertEqual(self.template.read_bytes(), before)
        self.assertEqual(tuple(current.cell(1, n).value for n in range(1, 5)), reference.HEADERS)
        self.assertEqual([current.cell(n, 1).value for n in range(2, 7)], [s[1] for s in self.sources])
        self.assertEqual(current["B4"].value, "Building 4, 301-310 Example Rd, Hong Kong")
        self.assertEqual(current["C4"].value, "+852 2820 8584")
        self.assertIsNone(current["D6"].value)
        self.assertIsNone(current["D6"].hyperlink)
        self.assertEqual(current["D2"].hyperlink.target, "https://restaurant2.example/")
        self.assertTrue(current["A1"].font.bold)
        self.assertEqual(provenance, reference.verify_reference(self.template, output))
        self.assertEqual(sorted(p.name for p in (output / "sources").iterdir()), sorted(s[0] + ".json" for s in self.sources))
        self.assertFalse(list(output.rglob("*.png")))

    def test_mutated_snapshot_or_screenshot_rejected_before_reference_creation(self):
        for filename in ("MingPavilion.json", "Niras.png"):
            path = self.snapshots / filename
            data = path.read_bytes()
            path.write_bytes(data + b" changed")
            with self.assertRaises(ValueError):
                reference.build_reference(self.template, self.snapshots, self.base / "rejected")
            self.assertFalse((self.base / "rejected").exists())
            path.write_bytes(data)

    def test_missing_website_requires_closed_listing_without_authority(self):
        path = self.snapshots / "Niras.json"
        for updates in ({"permanently_closed": False}, {"website": "https://arbitrary.example/"},
                        {"info_buttons": [{"id": "authority", "href": "https://old.example/"}]}):
            data = json.loads(path.read_text())
            data.update(updates)
            put(path, data)
            sources = list(self.sources)
            sources[-1] = (*sources[-1][:3], reference.sha(path), sources[-1][4])
            with mock.patch.object(reference, "SOURCES", tuple(sources)), self.assertRaises(ValueError):
                reference.source_records(self.snapshots)

    def test_reference_tamper_rejected_even_with_new_self_declared_hash(self):
        output, _ = self.build()
        path = output / "current-reference.xlsx"
        book = load_workbook(path)
        book["Sheet1"]["A5"] = "Another restaurant"
        book.save(path)
        proof = json.loads((output / "provenance.json").read_text())
        proof["reference_sha256"] = reference.sha(path)
        put(output / "provenance.json", proof)
        with self.assertRaises(ValueError):
            reference.verify_reference(self.template, output)

    def run_fixture(self, score=.75, *, wrong_metric=False, mutate=None):
        self.run = self.base / "run"
        self.run.mkdir()
        self.metadata = {"harness_root": str(ROOT), "osworld_root": str(self.base / "upstream"),
                         "upstream_commit": reference.UPSTREAM_COMMIT}
        put(self.run / "run.json", self.metadata)
        self.receipt = self.run / "tasks" / reference.TASK_ID / "receipt.json"
        self.original_receipt = {"task_id": reference.TASK_ID, "task_sha256": reference.TASK_SHA256,
            "status": "scored", "score": 0., "actor_status": "completed", "official_terminal_action": "DONE",
            "owned_vm_closed": True, "owned_container_removal_verified": True, "evidence_errors": []}
        put(self.receipt, self.original_receipt)
        cache = self.receipt.parent / "official-cache" / reference.TASK_ID
        cache.mkdir(parents=True)
        self.actual, self.old = cache / "MUST_VISIT.xlsx", cache / "MUST_VISIT-gt.xlsx"
        self.actual.write_bytes(b"retained original official getter bytes")
        self.old.write_bytes(self.template.read_bytes())
        self.metric_path = Path(self.metadata["osworld_root"]) / correction.METRIC_RELATIVE
        self.metric_path.parent.mkdir(parents=True)
        source = self.base / "foreign.py" if wrong_metric else self.metric_path
        source.write_text("def compare_table(actual, expected, **options):\n    calls.append((actual, expected, options))\n    if mutate: mutate()\n    return score\n")
        if wrong_metric:
            self.metric_path.write_text("# correct frozen metric source\n")
        self.calls = []
        namespace = {"calls": self.calls, "score": score, "mutate": mutate}
        exec(compile(source.read_text(), str(source), "exec"), namespace)
        module = types.ModuleType("desktop_env.evaluators.metrics.table")
        module.compare_table = namespace["compare_table"]
        patches = [mock.patch.object(correction, "load", return_value=types.SimpleNamespace(verify_run=lambda run: self.metadata)),
            mock.patch.object(correction, "ACTUAL_SHA256", correction.sha(self.actual)),
            mock.patch.object(correction, "METRIC_SHA256", correction.sha(self.metric_path)),
            mock.patch.object(correction, "METRIC_GIT_BLOB_SHA1", hashlib.sha1(b"blob " + str(self.metric_path.stat().st_size).encode() + b"\0" + self.metric_path.read_bytes()).hexdigest()),
            mock.patch.dict(sys.modules, {module.__name__: module})]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        return self.base / "correction"

    def test_original_metric_call_preserves_actual_and_float_score_and_can_verify(self):
        output = self.run_fixture()
        original = {p: p.read_bytes() for p in (self.receipt, self.actual, self.old)}
        record = correction.repair(self.run, self.snapshots, output)
        self.assertEqual(record["status"], "corrected")
        self.assertEqual(record["score"], .75)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0], str(self.actual))
        self.assertEqual(self.calls[0][2], reference.repair_options(reference.ORIGINAL_OPTIONS))
        for path, data in original.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertEqual(correction.verify_correction(self.run, output / "correction.json"), record)

    def test_invalid_metric_score_or_exception_never_becomes_zero(self):
        for value in (True, float("nan"), "1", -1, 2):
            with self.subTest(value=value):
                # Each fixture runs in its own temporary instance.
                case = RestaurantRecoveryTests(methodName="runTest")
                case.setUp()
                try:
                    output = case.run_fixture(value)
                    record = correction.repair(case.run, case.snapshots, output)
                    self.assertEqual(record["status"], "repair_error")
                    self.assertIsNone(record["score"])
                finally:
                    case.doCleanups()

    def test_foreign_metric_rejected_without_comparison(self):
        output = self.run_fixture(wrong_metric=True)
        result = correction.repair(self.run, self.snapshots, output)
        self.assertEqual(result["status"], "repair_error")
        self.assertIsNone(result["score"])
        self.assertFalse(self.calls)

    def test_non_git_inputs_pass_but_archived_source_mutation_is_rejected(self):
        self.run_fixture()
        self.assertFalse((Path(self.metadata["osworld_root"]) / ".git").exists())
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("Git is unavailable")):
            values = correction.inputs(self.run)
            self.assertEqual(values[5], self.metric_path)
            self.metric_path.write_bytes(self.metric_path.read_bytes() + b"# changed\n")
            with self.assertRaises(ValueError):
                correction.inputs(self.run)

    def test_concurrent_original_replacement_invalidates_score(self):
        output = self.run_fixture(mutate=lambda: self.actual.write_bytes(b"replaced"))
        result = correction.repair(self.run, self.snapshots, output)
        self.assertEqual(result["status"], "repair_error")
        self.assertIsNone(result["score"])

    def test_legal_original_fail_or_technical_error_not_eligible(self):
        self.run_fixture()
        for updates in ({"official_terminal_action": "FAIL"}, {"score": True},
                        {"status": "evaluation_error", "score": None}, {"score": 1}):
            put(self.receipt, {**self.original_receipt, **updates})
            with self.assertRaises(ValueError):
                correction.inputs(self.run)

    def test_correction_declared_path_option_and_source_tampering_rejected(self):
        output = self.run_fixture()
        original = correction.repair(self.run, self.snapshots, output)
        path = output / "correction.json"
        for updates in ({"original_actual": str(self.template)}, {"score": True},
                        {"reference": str(self.template)}, {"repaired_options": reference.ORIGINAL_OPTIONS},
                        {"repair_sources_sha256": {}}):
            put(path, {**original, **updates})
            with self.assertRaises(ValueError):
                correction.verify_correction(self.run, path)


if __name__ == "__main__":
    unittest.main()
