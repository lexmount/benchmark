"""Recover original file bytes and metric calls; never start a VM/model/network."""
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import types
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import repair_file_evaluation as repair

try:
    ET.fromstring("<document/>")
    XML_AVAILABLE = True
except ImportError:
    XML_AVAILABLE = False


BIB = b"@article{one,\n title = {Actual paper},\n year = {2024},\n}\n"


def docx(titles=3):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        paragraphs = ''.join('<w:p><w:r><w:t>Title: Paper %d</w:t></w:r></w:p>' % i for i in range(titles))
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + paragraphs + '</w:body></w:document>')
    return stream.getvalue()


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class FileRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.run = self.base / "run"
        self.run.mkdir()
        self.meta = {"harness_root": str(ROOT), "osworld_root": str(self.base / "upstream"),
                     "agent_commit": "a" * 40, "upstream_commit": "5123bfdbbc34b947bcffcff564abc62d0ab7072d"}
        put(self.run / "run.json", self.meta)
        self.tasks = {i: json.loads((ROOT / "data/tasks/multi_apps" / (i + ".json")).read_text()) for i in repair.TASKS}
        self.receipts = {}
        for identifier, task in self.tasks.items():
            path = self.run / "tasks" / identifier / "receipt.json"
            put(path, {"task_id": identifier,
                "task_sha256": repair.sha(ROOT / "data/tasks/multi_apps" / (identifier + ".json")),
                "status": "evaluation_error", "score": None, "actor_status": "completed",
                "official_terminal_action": "DONE", "owned_vm_closed": True,
                "owned_container_removal_verified": True,
                "error_type": "SSLError" if identifier == repair.BIB_TASK else "RuntimeError",
                "error": "huggingface.co SSL unexpected EOF" if identifier == repair.BIB_TASK else "Postconfig setup failed"})
            self.receipts[identifier] = path
        self.cached = self.receipts[repair.BIB_TASK].parent / "official-cache" / repair.BIB_TASK / "references.bib"
        self.cached.parent.mkdir(parents=True)
        self.cached.write_bytes(BIB)
        self.control = mock.patch.object(repair, "load", return_value=types.SimpleNamespace(verify_run=lambda run: self.meta))
        self.control.start()
        self.addCleanup(self.control.stop)
        self.metric_calls = []

    def reference(self, task_id, data=None):
        suffix = repair.TASKS[task_id][2]
        path = self.base / (task_id + suffix)
        path.write_bytes(data if data is not None else (BIB if suffix == ".bib" else docx()))
        provenance = {"source_url": self.tasks[task_id]["evaluator"]["expected"]["path"],
            "http_status": 200, "https_verification": repair.TLS_POLICY,
            "final_url_without_query": "https://huggingface.co/api/resolve-cache/datasets/xlangai/ubuntu_osworld_file_cache/" + "e" * 40 + "/reference",
            "bytes": path.stat().st_size, "sha256": repair.sha(path)}
        proof = self.base / (task_id + "-reference.json")
        put(proof, provenance)
        return path, proof

    def metric(self, task_id, value=.625, wrong_source=False, mutate=None):
        module_name, function_name, _ = repair.TASKS[task_id]
        source = Path(self.meta["osworld_root"]) / ("desktop_env/evaluators/metrics/" + module_name + ".py")
        if wrong_source:
            source = self.base / "wrong-checkout" / (module_name + ".py")
        source.parent.mkdir(parents=True, exist_ok=True)
        code = 'def ' + function_name + '(actual, expected, **options):\n    calls.append((actual, expected, options))\n    if mutate is not None: mutate()\n    return value\n'
        source.write_text(code)
        namespace = {"calls": self.metric_calls, "value": value, "mutate": mutate}
        exec(compile(code, str(source), "exec"), namespace)
        module = types.ModuleType("desktop_env.evaluators.metrics." + module_name)
        setattr(module, function_name, namespace[function_name])
        return mock.patch.dict(sys.modules, {module.__name__: module})

    def snapshot(self, *, later_mutation=False):
        task_id = repair.DOCX_TASK
        data = docx()
        destination = self.tasks[task_id]["evaluator"]["result"]["path"]
        checksum = repair.digest(data)
        verification = json.dumps({"deliverable": destination, "sha256": checksum, "size_bytes": len(data)}).encode()
        arguments = [
            {"code": "desk=" + repr(destination) + "; shutil.copy2('new_doc.docx', desk)"},
            {"code": "desk=" + repr(destination) + "; print(hashlib.sha256(open(desk,'rb').read()).hexdigest())"},
            {"code": "desk=" + repr(destination) + "; save_workspace_verification_of_last_hash()"},
            {"success": True},
        ]
        outputs = [["new hash " + checksum + " matches scratch: True"], ["hash now: " + checksum], ["saved verification.json"], ["Final result processed."]]
        messages = []
        records = []
        for index, (args, observations) in enumerate(zip(arguments, outputs), 1):
            tool = "python" if index <= 3 else "finish"
            if later_mutation and index == 4:
                tool, args = "python", {"code": "open(" + repr(destination) + ",'wb').write(b'changed')"}
            call_id = "call-" + str(index)
            messages += [{"parts": [{"part_kind": "tool-call", "tool_name": tool, "tool_call_id": call_id, "args": args}]},
                         {"parts": [{"part_kind": "tool-return", "tool_call_id": call_id, "content": observations}]}]
            if index <= 3:
                records.append({"step": index, "tool": tool, "call_id": call_id, "args": args, "observations": observations})
        raw_messages = json.dumps(messages).encode()
        archive_path = self.receipts[task_id].parent / "actor-output.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            for name, content in [("actor-output/messages.json", raw_messages),
                                  ("actor-output/workspace/new_doc.docx", data),
                                  ("actor-output/workspace/verification.json", verification)]:
                info = tarfile.TarInfo(name)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        evidence = {"task_id": task_id, "run": str(self.run), "product_commit": self.meta["agent_commit"],
            "upstream_commit": self.meta["upstream_commit"], "receipt_sha256": repair.sha(self.receipts[task_id]),
            "original_status": "evaluation_error", "original_score": None, "actual_VM_path": destination,
            "binding_kind": "recorded_copy_and_last_known_actual_file_hash_matches_preserved_workspace_bytes",
            "actor_archive_sha256": repair.sha(archive_path),
            "candidate_member": "actor-output/workspace/new_doc.docx", "candidate_sha256": checksum,
            "candidate_bytes": len(data), "messages_member_sha256": repair.digest(raw_messages),
            "verification_member": "actor-output/workspace/verification.json",
            "verification_member_sha256": repair.digest(verification), "tool_records": records}
        path = self.base / "actual-evidence.json"
        put(path, evidence)
        return path, data

    def test_bib_recovery_calls_the_frozen_metric_with_unchanged_options_and_original_bytes(self):
        reference, provenance = self.reference(repair.BIB_TASK)
        originals = {p: p.read_bytes() for p in (self.run / "run.json", self.receipts[repair.BIB_TASK], self.cached)}
        output = self.base / "correction"
        with self.metric(repair.BIB_TASK):
            result = repair.repair(self.run, repair.BIB_TASK, output, reference=reference, reference_provenance=provenance)
        self.assertEqual(result["status"], "corrected")
        self.assertEqual(result["score"], .625)
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["vm_starts"], 0)
        self.assertEqual(Path(self.metric_calls[0][0]).read_bytes(), BIB)
        self.assertEqual(self.metric_calls[0][2], self.tasks[repair.BIB_TASK]["evaluator"]["options"])
        self.assertEqual({p: p.read_bytes() for p in originals}, originals)
        self.assertEqual(repair.verify_correction(self.run, output / "correction.json")["score"], .625)
        with self.assertRaises(FileExistsError):
            repair.repair(self.run, repair.BIB_TASK, output, reference=reference, reference_provenance=provenance)

    @unittest.skipUnless(XML_AVAILABLE, "Existing Python XML parser unavailable; run with the documented Python3.12")
    def test_docx_uses_byte_identical_archived_snapshot_and_discloses_its_getter_boundary(self):
        evidence, data = self.snapshot()
        reference, provenance = self.reference(repair.DOCX_TASK)
        with self.metric(repair.DOCX_TASK, .9731):
            result = repair.repair(self.run, repair.DOCX_TASK, self.base / "docx-correction", evidence, reference, provenance)
        self.assertEqual(result["status"], "corrected")
        self.assertEqual(result["score"], .9731)
        self.assertEqual(Path(result["actual"]).read_bytes(), data)
        self.assertEqual(result["input_kind"], "archived_byte_identical_last_known_desktop_snapshot")
        self.assertIn("Not a retained vm_file", result["actual_source"]["boundary"])
        self.assertEqual(self.metric_calls[0][2], self.tasks[repair.DOCX_TASK]["evaluator"]["options"])
        repair.verify_correction(self.run, Path(result["actual"]).parent / "correction.json")

    @unittest.skipUnless(XML_AVAILABLE, "Existing Python XML parser unavailable; run with Python3.12")
    def test_snapshot_wrong_hash_or_subsequent_mutation_is_rejected_before_scoring(self):
        evidence, _ = self.snapshot()
        record = repair.read(evidence)
        record["candidate_sha256"] = "0" * 64
        put(evidence, record)
        with self.assertRaisesRegex(ValueError, "evidence bytes"):
            repair.inputs(self.run, repair.DOCX_TASK, evidence)
        evidence, _ = self.snapshot(later_mutation=True)
        with self.assertRaisesRegex(ValueError, "mutation tool"):
            repair.inputs(self.run, repair.DOCX_TASK, evidence)

    def test_invalid_reference_tls_origin_hash_or_format_never_produces_zero(self):
        reference, provenance = self.reference(repair.BIB_TASK)
        valid = repair.read(provenance)
        changes = [{"http_status": 404}, {"https_verification": "verification disabled"},
                   {"source_url": "https://example.com/other.bib"}, {"sha256": "0" * 64},
                   {"final_url_without_query": "https://huggingface.co.evil.example/reference"}]
        for index, change in enumerate(changes):
            with self.subTest(change=change), self.metric(repair.BIB_TASK):
                put(provenance, valid | change)
                result = repair.repair(self.run, repair.BIB_TASK, self.base / ("bad" + str(index)), reference=reference, reference_provenance=provenance)
                self.assertEqual(result["status"], "repair_error")
                self.assertIsNone(result["score"])
        self.assertEqual(self.metric_calls, [])
        reference.write_bytes(b"<html>Access denied</html>")
        put(provenance, valid | {"bytes": reference.stat().st_size, "sha256": repair.sha(reference)})
        result = repair.repair(self.run, repair.BIB_TASK, self.base / "bad-format", reference=reference, reference_provenance=provenance)
        self.assertIsNone(result["score"])

    def test_download_or_metric_failure_is_unscored_and_original_failure_is_preserved(self):
        before = self.receipts[repair.BIB_TASK].read_bytes()
        with mock.patch.object(repair, "download_reference", side_effect=OSError("TLS transport failed")):
            result = repair.repair(self.run, repair.BIB_TASK, self.base / "download-failed")
        self.assertIsNone(result["score"])
        self.assertEqual(result["error_type"], "OSError")
        reference, provenance = self.reference(repair.BIB_TASK)
        for index, invalid in enumerate((True, "1", float("nan"), float("inf"), -1, 2)):
            with self.subTest(invalid=invalid), self.metric(repair.BIB_TASK, invalid):
                result = repair.repair(self.run, repair.BIB_TASK, self.base / ("invalid-score" + str(index)), reference=reference, reference_provenance=provenance)
                self.assertIsNone(result["score"])
        self.assertEqual(self.receipts[repair.BIB_TASK].read_bytes(), before)

    def test_foreign_metric_and_concurrent_original_replacement_invalidate_score(self):
        reference, provenance = self.reference(repair.BIB_TASK)
        with self.metric(repair.BIB_TASK, wrong_source=True):
            result = repair.repair(self.run, repair.BIB_TASK, self.base / "wrong-metric", reference=reference, reference_provenance=provenance)
        self.assertIsNone(result["score"])
        self.assertEqual(self.metric_calls, [])
        with self.metric(repair.BIB_TASK, mutate=lambda: self.cached.write_bytes(BIB.replace(b"2024", b"2023"))):
            result = repair.repair(self.run, repair.BIB_TASK, self.base / "changed-original", reference=reference, reference_provenance=provenance)
        self.assertIsNone(result["score"])

    def test_a_legal_scored_failure_or_unrelated_task_is_not_eligible_for_recovery(self):
        path = self.receipts[repair.BIB_TASK]
        original = repair.read(path)
        for change in [{"status": "scored", "score": 0.0}, {"official_terminal_action": "FAIL"},
                       {"actor_status": "error"}, {"owned_vm_closed": False}]:
            put(path, original | change)
            with self.assertRaises(ValueError):
                repair.inputs(self.run, repair.BIB_TASK)
        with self.assertRaisesRegex(ValueError, "two audited"):
            repair.inputs(self.run, "not-in-scope")

    def test_correction_binding_rejects_modified_source_score_options_and_reference(self):
        reference, provenance = self.reference(repair.BIB_TASK)
        output = self.base / "sealed"
        with self.metric(repair.BIB_TASK):
            record = repair.repair(self.run, repair.BIB_TASK, output, reference=reference, reference_provenance=provenance)
        for change in [{"score": True}, {"score": float("nan")}, {"model_calls": False},
                       {"repair_sources_sha256": {}}, {"task_sha256": "0" * 64}, {"options": {}}]:
            put(output / "correction.json", record | change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                repair.verify_correction(self.run, output / "correction.json")
        put(output / "correction.json", record)
        Path(record["reference"]).write_bytes(BIB.replace(b"2024", b"2023"))
        with self.assertRaises(ValueError):
            repair.verify_correction(self.run, output / "correction.json")


class DownloadPolicyTests(unittest.TestCase):
    def test_default_verified_tls_is_used_and_signed_query_is_not_exported(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = BIB
        response.geturl.return_value = "https://huggingface.co/api/resolve-cache/ref?secret=signed-download-token"
        response.headers = {"Content-Type": "text/plain", "ETag": '"reference-etag"'}
        opener = mock.Mock()
        opener.open.return_value = response
        with tempfile.TemporaryDirectory() as temporary, \
                mock.patch.object(repair.urllib.request, "build_opener", return_value=opener) as build:
            path = Path(temporary) / "reference.bib"
            result = repair.download_reference("https://huggingface.co/datasets/original/resolve/main/reference.bib", path)
        https_handler = build.call_args.args[1]
        self.assertEqual(https_handler._context.verify_mode, repair.ssl.CERT_REQUIRED)
        self.assertTrue(https_handler._context.check_hostname)
        self.assertNotIn("signed-download-token", json.dumps(result))
        self.assertEqual(result["https_verification"], repair.TLS_POLICY)

    def test_redirect_downgrade_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "downgrade"):
            repair.VerifiedRedirects().redirect_request(None, None, 302, "Found", {}, "http://huggingface.co/reference")


if __name__ == "__main__":
    unittest.main()
