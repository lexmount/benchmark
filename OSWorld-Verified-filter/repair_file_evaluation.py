#!/usr/bin/env python3
"""Recover two archived, technically interrupted pure-file evaluations.

No VM, Actor or model is started. The original task, options, metrics, receipt
and deliverables remain unchanged. The DOCX input is an archived byte-identical
last-known Desktop snapshot, not a retained official vm_file getter result.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import importlib
import inspect
import io
import json
import math
from pathlib import Path
import re
import shutil
import ssl
import sys
import tarfile
import urllib.request
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import zipfile

from repair_pdf_reference import load, read, sha, write_new

ROOT = Path(__file__).resolve().parent
KIND = "archived-file-evaluation-recovery-v1"
BIB_TASK = "df67aebb-fb3a-44fd-b75b-51b6012df509"
DOCX_TASK = "236833a3-5704-47fc-888c-4f298f09f799"
TASKS = {BIB_TASK: ("vscode", "compare_text_file", ".bib"),
         DOCX_TASK: ("docs", "compare_docx_paper_records", ".docx")}
SOURCES = ("repair_file_evaluation.py", "repair_pdf_reference.py")
TLS_POLICY = "default system certificate verification; no bypass"
MAX_FILE_BYTES = 20 * 1024 * 1024


def digest(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


def validate_file(data, suffix, *, reference=False, prefilled=0):
    """Validate the container/record format without replacing the metric."""
    if not data or len(data) > MAX_FILE_BYTES:
        raise ValueError("Empty or oversized evaluation file")
    if suffix == ".bib":
        text = data.decode("utf-8")
        if not text.lstrip().startswith("@") or "<html" in text[:500].lower():
            raise ValueError("Reference is not BibTeX text")
        entries = re.findall(r"(?m)^\s*@([A-Za-z]+)\s*\{[^,\n]+,", text)
        level = 0
        escaped = False
        for char in text:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
            elif char == "{":
                level += 1
            elif char == "}":
                level -= 1
                if level < 0:
                    raise ValueError("Unbalanced BibTeX")
        if not entries or level:
            raise ValueError("Incomplete BibTeX records")
        return {"bytes": len(data), "sha256": digest(data), "bibtex_entries": len(entries)}
    if suffix != ".docx":
        raise ValueError("Unsupported evaluation format")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = archive.infolist()
        if len(members) > 1000 or sum(m.file_size for m in members) > 60 * 1024 * 1024:
            raise ValueError("Oversized DOCX package")
        if archive.testzip() is not None:
            raise ValueError("Corrupt DOCX package")
        if "[Content_Types].xml" not in archive.namelist():
            raise ValueError("Missing DOCX content types")
        ET.fromstring(archive.read("[Content_Types].xml"))
        document = ET.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = ["".join(p.itertext()).strip() for p in document.findall(".//w:p", ns)]
    text = "\n".join(paragraphs)
    titles = len(re.findall(r"(?im)^title\s*:", text))
    if not titles or (reference and titles <= prefilled):
        raise ValueError("DOCX has no complete paper-record reference content")
    return {"bytes": len(data), "sha256": digest(data), "paper_titles": titles,
            "paragraphs": len(paragraphs)}


def _member(archive, name):
    item = archive.getmember(name)
    if not item.isfile():
        raise ValueError("Evidence member is not a regular file")
    stream = archive.extractfile(item)
    if stream is None:
        raise ValueError("Missing evidence member")
    return stream.read()


def _calls(messages):
    """Read executed public tool parts only; never export reasoning/binary data."""
    calls, by_id = [], {}
    for message in messages:
        for part in message.get("parts", []):
            kind = part.get("part_kind")
            if kind == "tool-call":
                args = part.get("args")
                if isinstance(args, str):
                    args = json.loads(args)
                row = {"step": len(calls) + 1, "tool": part.get("tool_name"),
                       "call_id": part.get("tool_call_id"), "args": args, "observations": []}
                calls.append(row)
                by_id[row["call_id"]] = row
            elif kind in ("tool-return", "retry-prompt"):
                row = by_id.get(part.get("tool_call_id"))
                if row is None:
                    continue
                content = part.get("content", [])
                if isinstance(content, (str, dict)):
                    content = [content]
                for value in content:
                    if isinstance(value, str):
                        row["observations"].append(value)
                    elif isinstance(value, dict) and "data" not in value:
                        for key in ("text", "content"):
                            if isinstance(value.get(key), str):
                                row["observations"].append(value[key])
    return calls


def _docx_snapshot(run_dir, metadata, task, receipt_path, evidence_path):
    evidence = read(evidence_path)
    archive_path = receipt_path.parent / "actor-output.tar.gz"
    if (evidence.get("task_id") != DOCX_TASK or Path(evidence["run"]).resolve() != run_dir
            or evidence.get("product_commit") != metadata["agent_commit"]
            or evidence.get("upstream_commit") != metadata["upstream_commit"]
            or evidence.get("receipt_sha256") != sha(receipt_path)
            or evidence.get("original_status") != "evaluation_error"
            or evidence.get("original_score") is not None
            or evidence.get("actual_VM_path") != task["evaluator"]["result"]["path"]
            or evidence.get("binding_kind") != "recorded_copy_and_last_known_actual_file_hash_matches_preserved_workspace_bytes"
            or evidence.get("actor_archive_sha256") != sha(archive_path)
            or evidence.get("candidate_member") != "actor-output/workspace/new_doc.docx"
            or evidence.get("verification_member") != "actor-output/workspace/verification.json"):
        raise ValueError("DOCX Desktop snapshot is not bound to this original run/task")
    with tarfile.open(archive_path, "r:gz") as archive:
        data = _member(archive, evidence["candidate_member"])
        messages = _member(archive, "actor-output/messages.json")
        verification = _member(archive, evidence["verification_member"])
    if (digest(data) != evidence["candidate_sha256"] or len(data) != evidence["candidate_bytes"]
            or digest(messages) != evidence["messages_member_sha256"]
            or digest(verification) != evidence["verification_member_sha256"]):
        raise ValueError("Archived DOCX evidence bytes changed")
    verified = json.loads(verification)
    if (verified.get("deliverable") != evidence["actual_VM_path"]
            or verified.get("sha256") != digest(data) or verified.get("size_bytes") != len(data)):
        raise ValueError("Final recorded Desktop hash differs from the preserved DOCX")
    calls = _calls(json.loads(messages))
    proof = evidence.get("tool_records", [])
    if len(proof) != 3:
        raise ValueError("Expected the audited copy and final hash observations")
    steps = [record.get("step") for record in proof]
    if any(type(n) is not int or not 1 <= n <= len(calls) for n in steps) or steps != sorted(set(steps)):
        raise ValueError("Invalid Desktop hash observation ordering")
    for record in proof:
        original = calls[record["step"] - 1]
        if any(record.get(key) != original.get(key) for key in ("tool", "call_id", "args", "observations")):
            raise ValueError("Desktop hash observation does not match the original tool record")
        if original["tool"] != "python" or evidence["actual_VM_path"] not in original["args"].get("code", ""):
            raise ValueError("Observation is not for the original Desktop deliverable")
    if (digest(data) not in "\n".join(proof[0]["observations"])
            or "matches scratch: True" not in "\n".join(proof[0]["observations"])
            or "hash now: " + digest(data) not in "\n".join(proof[1]["observations"])):
        raise ValueError("Copy/final hash observation does not confirm byte identity")
    later = calls[steps[-1]:]
    if not later or any(call["tool"] not in {"finish", "finish_from_repl"} for call in later):
        raise ValueError("A mutation tool follows the final Desktop snapshot")
    return data, {"kind": "archived_byte_identical_last_known_desktop_snapshot",
        "original_archive": str(archive_path), "original_archive_sha256": sha(archive_path),
        "archive_member": evidence["candidate_member"], "actual_VM_path": evidence["actual_VM_path"],
        "actual_sha256": digest(data), "evidence_sha256": sha(evidence_path),
        "evidence_steps": steps,
        "boundary": "Not a retained vm_file getter result. Archived workspace bytes match the recorded final Desktop hash; no subsequent mutation tool is recorded. Unrecorded background autosave cannot be excluded."}


def inputs(run_dir, task_id, actual_evidence=None):
    run_dir = Path(run_dir).resolve()
    if task_id not in TASKS:
        raise ValueError("Only the two audited file-evaluation failures are supported")
    if task_id == BIB_TASK and actual_evidence is not None:
        raise ValueError("The retained BibTeX getter input does not use archive snapshot evidence")
    metadata = load(ROOT / "evaluate.py", "file_recovery_control").verify_run(run_dir)
    item = next(t for t in read(Path(metadata["harness_root"]) / "data/manifest.json")["tasks"] if t["task_id"] == task_id)
    path = Path(metadata["harness_root"]) / item["task_path"]
    task = read(path)
    evaluator = task["evaluator"]
    if (sha(path) != item["sha256"] or evaluator["func"] != TASKS[task_id][1]
            or evaluator["result"]["type"] != "vm_file" or evaluator["expected"]["type"] != "cloud_file"
            or evaluator.get("postconfig")):
        raise ValueError("Original task/metric/options/postconfig identity changed")
    receipt_path = run_dir / "tasks" / task_id / "receipt.json"
    receipt = read(receipt_path)
    if (receipt.get("task_id") != task_id or receipt.get("task_sha256") != item["sha256"]
            or receipt.get("status") != "evaluation_error" or receipt.get("score") is not None
            or receipt.get("actor_status") != "completed" or receipt.get("official_terminal_action") != "DONE"
            or receipt.get("owned_vm_closed") is not True or receipt.get("owned_container_removal_verified") is not True):
        raise ValueError("Expected the original cleaned-up, completed/DONE unscored evaluation failure")
    if task_id == BIB_TASK:
        if receipt.get("error_type") != "SSLError" or "huggingface.co" not in receipt.get("error", ""):
            raise ValueError("This is not the audited reference-download TLS failure")
        actual = receipt_path.parent / "official-cache" / task_id / evaluator["result"]["dest"]
        data = actual.read_bytes()
        binding = {"kind": "retained_original_vm_file_getter", "original_actual": str(actual),
                   "original_actual_sha256": sha(actual), "actual_sha256": digest(data)}
    else:
        if receipt.get("error") != "Postconfig setup failed" or actual_evidence is None:
            raise ValueError("Expected the empty-postconfig network-gate failure and snapshot evidence")
        data, binding = _docx_snapshot(run_dir, metadata, task, receipt_path, Path(actual_evidence))
    validate_file(data, TASKS[task_id][2])
    return metadata, task, receipt_path, data, binding


class VerifiedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != "https":
            raise ValueError("Refusing a reference HTTP downgrade")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_reference(url, destination):
    context = ssl.create_default_context()
    opener = urllib.request.build_opener(VerifiedRedirects(), urllib.request.HTTPSHandler(context=context))
    request = urllib.request.Request(url, headers={"User-Agent": "Lexmount-OSWorld-file-evaluation-recovery"})
    with opener.open(request, timeout=60) as response:
        if response.status != 200 or urlsplit(response.geturl()).scheme != "https":
            raise ValueError("Reference download did not complete over verified HTTPS")
        data = response.read(MAX_FILE_BYTES + 1)
        final = urlsplit(response.geturl())
        provenance = {"source_url": url, "http_status": response.status,
            "content_type": response.headers.get("Content-Type"),
            "final_url_without_query": final._replace(query="", fragment="").geturl(),
            "etag": response.headers.get("ETag"), "bytes": len(data), "sha256": digest(data),
            "observed_at_utc": datetime.now(timezone.utc).isoformat(), "https_verification": TLS_POLICY}
    Path(destination).write_bytes(data)
    return provenance


def reference_info(task, reference, provenance):
    url = task["evaluator"]["expected"]["path"]
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "huggingface.co"
            or not parsed.path.startswith("/datasets/xlangai/ubuntu_osworld_file_cache/resolve/")):
        raise ValueError("Reference is not the original HF cache URL")
    final_host = urlsplit(provenance.get("final_url_without_query", "")).hostname or ""
    if (provenance.get("source_url") != url or type(provenance.get("http_status")) is not int
            or provenance["http_status"] != 200 or provenance.get("https_verification") != TLS_POLICY
            or urlsplit(provenance.get("final_url_without_query", "")).scheme != "https"
            or not (final_host == "huggingface.co" or final_host.endswith(".huggingface.co")
                    or final_host == "hf.co" or final_host.endswith(".hf.co"))
            or provenance.get("sha256") != sha(reference) or provenance.get("bytes") != Path(reference).stat().st_size):
        raise ValueError("Reference HTTP/TLS/source/hash provenance is invalid")
    return validate_file(Path(reference).read_bytes(), TASKS[task["id"]][2], reference=True,
                         prefilled=len(task["evaluator"].get("options", {}).get("prefilled_titles", [])))


def repair(run_dir, task_id, output, actual_evidence=None, reference=None, reference_provenance=None):
    run_dir, output = Path(run_dir).resolve(), Path(output).resolve()
    metadata, task, original, data, binding = inputs(run_dir, task_id, actual_evidence)
    output.mkdir(parents=True, exist_ok=False)
    for name in SOURCES:
        shutil.copyfile(ROOT / name, output / name)
    if actual_evidence is not None:
        shutil.copyfile(actual_evidence, output / "actual-evidence.json")
    suffix = TASKS[task_id][2]
    actual, gold = output / ("actual" + suffix), output / ("reference" + suffix)
    actual.write_bytes(data)
    record = {"schema_version": 1, "kind": KIND, "task_id": task_id, "run_dir": str(run_dir),
        "created_at": datetime.now(timezone.utc).isoformat(), "status": "repair_error", "score": None,
        "original_status": "evaluation_error", "original_score": None, "model_calls": 0, "vm_starts": 0,
        "actor_rerun": False, "getter_replayed": False, "input_kind": binding["kind"],
        "run_metadata_sha256": sha(run_dir / "run.json"), "task_sha256": sha(Path(metadata["harness_root"]) /
            next(t["task_path"] for t in read(Path(metadata["harness_root"]) / "data/manifest.json")["tasks"] if t["task_id"] == task_id)),
        "original_receipt": str(original), "original_receipt_sha256": sha(original),
        "actual": str(actual), "actual_sha256": sha(actual), "actual_source": binding,
        "actual_evidence": str(output / "actual-evidence.json") if actual_evidence is not None else None,
        "reference": str(gold), "reference_provenance": str(output / "reference-provenance.json"),
        "metric": task["evaluator"]["func"], "options": deepcopy(task["evaluator"].get("options", {})),
        "repair_sources_sha256": {name: sha(output / name) for name in SOURCES}, "evidence_errors": []}
    try:
        if reference is not None:
            if reference_provenance is None:
                raise ValueError("A provided reference needs its independent HTTPS provenance")
            shutil.copyfile(reference, gold)
            provenance = read(reference_provenance)
        else:
            provenance = download_reference(task["evaluator"]["expected"]["path"], gold)
        info = reference_info(task, gold, provenance)
        write_new(output / "reference-provenance.json", provenance)
        record.update(reference_sha256=sha(gold), reference_format=info,
                      reference_provenance_sha256=sha(output / "reference-provenance.json"))
        sys.path.insert(0, metadata["osworld_root"])
        module_name, metric_name, _ = TASKS[task_id]
        metric = getattr(importlib.import_module("desktop_env.evaluators.metrics." + module_name), metric_name)
        source = Path(metadata["osworld_root"]) / ("desktop_env/evaluators/metrics/" + module_name + ".py")
        if Path(inspect.getsourcefile(metric)).resolve() != source.resolve():
            raise ValueError("Imported metric does not come from this run's frozen checkout")
        metric_sha = sha(source)
        value = metric(str(actual), str(gold), **deepcopy(record["options"]))
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("The unchanged official metric returned an invalid score")
        if sha(source) != metric_sha:
            raise ValueError("Official comparison source changed during evaluation")
        record.update(status="corrected", score=float(value), metric_source_sha256=metric_sha)
    except Exception as error:
        record.update(status="repair_error", score=None, error_type=type(error).__name__, error=str(error))
    # Re-read the same original inputs: a concurrent replacement invalidates the score.
    try:
        _, _, checked_original, checked_data, checked_binding = inputs(run_dir, task_id, actual_evidence)
        if (sha(checked_original) != record["original_receipt_sha256"] or digest(checked_data) != digest(data)
                or checked_binding != binding):
            raise ValueError("An original artifact changed during repair")
    except Exception as error:
        record.update(status="repair_error", score=None, error_type=type(error).__name__, error=str(error))
    record["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_new(output / "correction.json", record)
    return record


def verify_correction(run_dir, path):
    run_dir, path = Path(run_dir).resolve(), Path(path).resolve()
    record = read(path)
    task_id = record.get("task_id")
    if (record.get("kind") != KIND or task_id not in TASKS or record.get("status") != "corrected"
            or Path(record["run_dir"]).resolve() != run_dir or record.get("original_score") is not None
            or record.get("original_status") != "evaluation_error" or record.get("actor_rerun") is not False
            or record.get("getter_replayed") is not False or record.get("evidence_errors")
            or any(type(record.get(k)) is not int or record[k] != 0 for k in ("model_calls", "vm_starts"))
            or record.get("run_metadata_sha256") != sha(run_dir / "run.json")):
        raise ValueError("Invalid file recovery identity or execution boundary")
    evidence = path.parent / "actual-evidence.json" if task_id == DOCX_TASK else None
    metadata, task, original, data, binding = inputs(run_dir, task_id, evidence)
    suffix = TASKS[task_id][2]
    if (record.get("original_receipt") != str(original) or record.get("original_receipt_sha256") != sha(original)
            or record.get("task_sha256") != read(original)["task_sha256"]
            or record.get("actual_source") != binding or record.get("input_kind") != binding["kind"]
            or record.get("actual_evidence") != (str(evidence) if evidence is not None else None)
            or record.get("actual") != str(path.parent / ("actual" + suffix))
            or sha(record["actual"]) != record.get("actual_sha256") or sha(record["actual"]) != digest(data)
            or record.get("reference") != str(path.parent / ("reference" + suffix))
            or sha(record["reference"]) != record.get("reference_sha256")
            or record.get("reference_provenance") != str(path.parent / "reference-provenance.json")
            or sha(record["reference_provenance"]) != record.get("reference_provenance_sha256")
            or record.get("options") != task["evaluator"].get("options", {})
            or record.get("metric") != task["evaluator"]["func"]
            or set(record.get("repair_sources_sha256", {})) != set(SOURCES)):
        raise ValueError("Original source bytes, options or correction artifacts changed")
    reference_info(task, record["reference"], read(record["reference_provenance"]))
    for name in SOURCES:
        if sha(path.parent / name) != record["repair_sources_sha256"][name]:
            raise ValueError("Archived recovery source changed")
    module_name = TASKS[task_id][0]
    metric_path = Path(metadata["osworld_root"]) / ("desktop_env/evaluators/metrics/" + module_name + ".py")
    if sha(metric_path) != record.get("metric_source_sha256"):
        raise ValueError("Original metric source changed")
    score = record.get("score")
    if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("Invalid technical file-recovery score")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--task-id", choices=TASKS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--actual-evidence", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--reference-provenance", type=Path)
    args = parser.parse_args()
    result = repair(args.run_dir, args.task_id, args.output, args.actual_evidence,
                    args.reference, args.reference_provenance)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["status"] == "corrected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
