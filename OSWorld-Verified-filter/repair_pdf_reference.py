#!/usr/bin/env python3
"""Repair the confirmed e1e75309 reference, preserving the original Actor and receipt.

Requires the documented OSWorld host environment. No model is called. Run only
after reserving a VM slot; this command does not alter a live scheduler.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import inspect
import json
import math
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
TASK_ID = "e1e75309-3ddb-4d09-92ec-de869c928143"
PLACEHOLDER_SHA256 = "f246a0043abad99c6fe9964c6dbd54b20a506bdd2720b0bf7b14a21f9bc4aa61"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inputs(run_dir):
    control = load(ROOT / "evaluate.py", "reference_repair_control")
    metadata = control.verify_run(run_dir)
    manifest = read(Path(metadata["harness_root"]) / "data/manifest.json")
    item = next(t for t in manifest["tasks"] if t["task_id"] == TASK_ID)
    source = Path(metadata["harness_root"]) / item["task_path"]
    task = read(source)
    evaluator = task["evaluator"]
    if (evaluator["func"] != "compare_pdfs"
            or evaluator["result"]["type"] != "vm_file"
            or evaluator["expected"]["type"] != "pdf_from_url"
            or evaluator.get("postconfig") or evaluator.get("options")):
        raise ValueError("This repair only supports the audited original PDF task")
    folder = run_dir / "tasks" / TASK_ID
    receipt_path = folder / "receipt.json"
    receipt = read(receipt_path)
    if (receipt.get("status") != "scored" or type(receipt.get("score")) not in (int, float)
            or receipt.get("score") != 0
            or receipt.get("task_id") != TASK_ID
            or receipt.get("task_sha256") != item["sha256"]
            or receipt.get("official_terminal_action") == "FAIL"):
        raise ValueError("Expected the preserved, non-FAIL, original scored-zero receipt")
    cache = folder / "official-cache" / TASK_ID
    actual = cache / evaluator["result"]["dest"]
    gold = cache / evaluator["expected"]["dest"]
    if sha(gold) != PLACEHOLDER_SHA256:
        raise ValueError("Original reference is not the confirmed invalid placeholder; no rejudge")
    return metadata, task, receipt_path, actual, gold


def repair(run_dir, output):
    from reference_repair import get_pdf_from_url, validate_pdf

    run_dir, output = Path(run_dir).resolve(), Path(output).resolve()
    metadata, task, original, actual, invalid = inputs(run_dir)
    # All identity and corruption checks precede VM creation or output creation.
    actual_info = validate_pdf(actual)
    binding = {"run_metadata_sha256": sha(run_dir / "run.json"),
               "original_receipt": str(original), "original_receipt_sha256": sha(original),
               "original_actual": str(actual), "original_actual_sha256": sha(actual),
               "invalid_reference": str(invalid), "invalid_reference_sha256": sha(invalid)}
    output.mkdir(parents=True, exist_ok=False)
    for name in ("reference_repair.py", "repair_pdf_reference.py"):
        shutil.copyfile(ROOT / name, output / name)
    receipt = {"schema_version": 1, "task_id": TASK_ID,
               "run_dir": str(run_dir), "status": "reference_unavailable", "score": None,
               "original_score": read(original)["score"], "model_calls": 0,
               "actor_rerun": False, "task_sha256": sha(Path(metadata["harness_root"]) /
                   next(t["task_path"] for t in read(Path(metadata["harness_root"]) /
                        "data/manifest.json")["tasks"] if t["task_id"] == TASK_ID)),
               "started_at": datetime.now(timezone.utc).isoformat(),
               "binding": binding, "actual_pdf": actual_info, "evidence_errors": [],
               "repair_sources_sha256": {n: sha(output / n) for n in
                   ("reference_repair.py", "repair_pdf_reference.py")}}
    bridge = load(Path(metadata["harness_root"]) / "runtime.py", "reference_repair_frozen_runtime")
    try:
        # Reuse the frozen VM ownership/cleanup bridge and the original task setup.
        # There is no product bootstrap, Actor import, private model file or LLM.
        with bridge._environment(metadata, output, receipt) as env:
            env.reset(task_config=task)
            receipt["cdp"] = bridge._ensure_cdp(env, metadata)
            reference = Path(get_pdf_from_url(env, task["evaluator"]["expected"]))
            receipt["reference"] = str(reference)
            receipt["reference_pdf"] = validate_pdf(reference)
            receipt["reference_sha256"] = sha(reference)
            from desktop_env.evaluators.metrics.chrome import compare_pdfs
            metric_path = Path(metadata["osworld_root"]) / "desktop_env/evaluators/metrics/chrome.py"
            if Path(inspect.getsourcefile(compare_pdfs)).resolve() != metric_path.resolve():
                raise ValueError("Imported metric does not come from this run's frozen checkout")
            value = compare_pdfs(str(actual), str(reference))
            if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("The unchanged official compare_pdfs returned an invalid score")
            receipt.update(status="corrected", score=float(value), metric="compare_pdfs",
                           metric_source_sha256=sha(metric_path))
    except Exception as error:
        receipt.update(status="reference_unavailable", score=None,
                       error_type=type(error).__name__, error=str(error))
    # Identity checks also protect against an accidental replacement during repair.
    for path_key, hash_key in (("original_receipt", "original_receipt_sha256"),
                               ("original_actual", "original_actual_sha256"),
                               ("invalid_reference", "invalid_reference_sha256")):
        if sha(binding[path_key]) != binding[hash_key]:
            receipt.update(status="repair_error", score=None,
                           error="An original artifact changed during repair")
    if receipt.get("owned_vm_closed") is not True or receipt["evidence_errors"]:
        receipt.update(status="repair_error", score=None)
    receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_new(output / "correction.json", receipt)
    return receipt


def verify_correction(run_dir, path):
    value = read(path)
    binding = value["binding"]
    if (value.get("status") != "corrected" or value.get("task_id") != TASK_ID
            or value.get("actor_rerun") is not False or value.get("model_calls") != 0
            or value.get("owned_vm_closed") is not True or value.get("evidence_errors")
            or Path(value["run_dir"]).resolve() != run_dir.resolve()
            or binding["run_metadata_sha256"] != sha(run_dir / "run.json")):
        raise ValueError("Correction does not bind this run and a clean model-free repair")
    for key in ("original_receipt", "original_actual", "invalid_reference"):
        if sha(binding[key]) != binding[key + "_sha256"]:
            raise ValueError("Correction input changed: " + key)
    metadata = read(run_dir / "run.json")
    _, _, original, actual, invalid = inputs(run_dir)
    for key, expected in (("original_receipt", original), ("original_actual", actual),
                          ("invalid_reference", invalid)):
        if Path(binding[key]).resolve() != expected.resolve():
            raise ValueError("Correction refers to another original artifact: " + key)
    if binding["invalid_reference_sha256"] != PLACEHOLDER_SHA256:
        raise ValueError("Correction is not for the confirmed invalid reference")
    if sha(value["reference"]) != value["reference_sha256"]:
        raise ValueError("Corrected reference changed")
    for name, checksum in value["repair_sources_sha256"].items():
        if sha(Path(path).parent / name) != checksum:
            raise ValueError("Archived repair source changed")
    metric = Path(metadata["osworld_root"]) / "desktop_env/evaluators/metrics/chrome.py"
    if sha(metric) != value["metric_source_sha256"]:
        raise ValueError("Official comparison source changed")
    score = value.get("score")
    if type(score) not in (float, int) or not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("Correction contains an invalid score")
    return value


def report(run_dir, correction=None):
    """Expose raw and repaired scores separately; never turn unavailable into zero."""
    control = load(ROOT / "evaluate.py", "reference_repair_report_control")
    run_dir = Path(run_dir).resolve()
    raw = control.report(run_dir)
    rows = [dict(r) for r in raw["tasks"]]
    row = next(r for r in rows if r["task_id"] == TASK_ID)
    metadata = read(run_dir / "run.json")
    manifest = read(Path(metadata["harness_root"]) / "data/manifest.json")
    item = next(t for t in manifest["tasks"] if t["task_id"] == TASK_ID)
    task = read(Path(metadata["harness_root"]) / item["task_path"])
    reference = run_dir / "tasks" / TASK_ID / "official-cache" / TASK_ID / task["evaluator"]["expected"]["dest"]
    if row["status"] == "scored" and reference.exists() and sha(reference) == PLACEHOLDER_SHA256:
        row.update(status="reference_unavailable", score=None, original_score=row["score"])
    if correction:
        fixed = verify_correction(run_dir, Path(correction))
        row.update(status="corrected", score=fixed["score"], original_score=fixed["original_score"],
                   correction=str(Path(correction).resolve()), correction_sha256=sha(correction))
    scores = [r["score"] for r in rows if r["status"] in {"scored", "corrected"}]
    return {"run_dir": str(run_dir), "task_count": 76,
            "scoring_version": "official-5123 + pdf-reference-v1" if correction else "official-5123 + invalid-reference-audit",
            "raw_official": raw, "valid_scored": len(scores),
            "corrected_tasks": sum(r["status"] == "corrected" for r in rows),
            "status_counts": dict(Counter(r["status"] for r in rows)),
            "score_sum": sum(scores), "full_76_mean": sum(scores) / 76 if len(scores) == 76 else None,
            "tasks": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fix = sub.add_parser("repair")
    fix.add_argument("--run-dir", required=True, type=Path)
    fix.add_argument("--output", required=True, type=Path)
    summary = sub.add_parser("report")
    summary.add_argument("--run-dir", required=True, type=Path)
    summary.add_argument("--correction", type=Path)
    args = parser.parse_args()
    value = repair(args.run_dir, args.output) if args.command == "repair" else report(args.run_dir, args.correction)
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))
    return 1 if value.get("status") in {"reference_unavailable", "repair_error"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
