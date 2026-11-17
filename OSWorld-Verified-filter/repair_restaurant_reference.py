#!/usr/bin/env python3
"""Rejudge one retained restaurant workbook with an independent Maps reference.

An explicit custom reference correction, with no VM, Actor, model or network.
The original task, zero receipt, actual workbook and historical Gold stay intact.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib
import inspect
import math
from pathlib import Path
import shutil
import sys

from repair_pdf_reference import load, read, sha, write_new
from restaurant_reference_repair import (ACTUAL_SHA256, KIND, ORIGINAL_GOLD_SHA256,
    ORIGINAL_OPTIONS, TASK_ID, TASK_SHA256, UPSTREAM_COMMIT, build_reference,
    repair_options, verify_reference)

ROOT = Path(__file__).resolve().parent
SOURCE_NAMES = ("restaurant_reference_repair.py", "repair_restaurant_reference.py", "repair_pdf_reference.py")
METRIC_RELATIVE = "desktop_env/evaluators/metrics/table.py"
METRIC_SHA256 = "9a17d8945a4d67c50947ae8ff79197de7506ed313507f2d8764cfb104b543346"
METRIC_GIT_BLOB_SHA1 = "c9f5bf24ddeb1823f9701bbef8049257c5bf892d"


def verify_original_metric_source(path):
    """Check the audited 5123 blob without requiring .git in a frozen archive."""
    content = Path(path).read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
    if checksum != METRIC_SHA256 or blob != METRIC_GIT_BLOB_SHA1:
        raise ValueError("Official comparison content differs from the audited fixed upstream Git blob")
    return {"sha256": checksum, "git_blob_sha1": blob}


def inputs(run_dir):
    run_dir = Path(run_dir).resolve()
    metadata = load(ROOT / "evaluate.py", "restaurant_repair_control").verify_run(run_dir)
    if metadata["upstream_commit"] != UPSTREAM_COMMIT:
        raise ValueError("Only the audited frozen OSWorld revision is supported")
    manifest = read(Path(metadata["harness_root"]) / "data/manifest.json")
    matches = [t for t in manifest["tasks"] if t["task_id"] == TASK_ID]
    if len(matches) != 1:
        raise ValueError("Restaurant task is absent or duplicated in the frozen manifest")
    item = matches[0]
    task_path = Path(metadata["harness_root"]) / item["task_path"]
    task = read(task_path)
    evaluator = task["evaluator"]
    expected_url = "https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/" + TASK_ID + "/MUST_VISIT_gold.xlsx"
    if (sha(task_path) != TASK_SHA256 or item["sha256"] != TASK_SHA256
            or task.get("id") != TASK_ID or evaluator["func"] != "compare_table"
            or evaluator["result"] != {"type": "vm_file", "path": "/home/user/Desktop/MUST_VISIT.xlsx", "dest": "MUST_VISIT.xlsx"}
            or evaluator["expected"] != {"type": "cloud_file", "path": expected_url, "dest": "MUST_VISIT-gt.xlsx"}):
        raise ValueError("Original restaurant task/getter/metric identity changed")
    repaired = repair_options(evaluator["options"])
    receipt_path = run_dir / "tasks" / TASK_ID / "receipt.json"
    receipt = read(receipt_path)
    if (receipt.get("task_id") != TASK_ID or receipt.get("task_sha256") != TASK_SHA256
            or receipt.get("status") != "scored" or type(receipt.get("score")) not in (int, float)
            or receipt["score"] != 0 or receipt.get("actor_status") != "completed"
            or receipt.get("official_terminal_action") != "DONE"
            or receipt.get("owned_vm_closed") is not True or receipt.get("owned_container_removal_verified") is not True
            or receipt.get("evidence_errors")):
        raise ValueError("Expected the original clean completed/DONE scored-zero receipt")
    cache = receipt_path.parent / "official-cache" / TASK_ID
    actual, old_gold = cache / evaluator["result"]["dest"], cache / evaluator["expected"]["dest"]
    if sha(actual) != ACTUAL_SHA256 or sha(old_gold) != ORIGINAL_GOLD_SHA256:
        raise ValueError("The retained original official getter files differ from the audited bytes")
    metric_path = Path(metadata["osworld_root"]) / METRIC_RELATIVE
    verify_original_metric_source(metric_path)
    return metadata, task_path, receipt_path, actual, old_gold, metric_path, repaired


def _binding(run_dir, values):
    _, task_path, original, actual, old_gold, metric_path, _ = values
    return {"run_metadata_sha256": sha(run_dir / "run.json"), "task_path": str(task_path),
        "task_sha256": sha(task_path), "original_receipt": str(original), "original_receipt_sha256": sha(original),
        "original_actual": str(actual), "original_actual_sha256": sha(actual),
        "original_reference": str(old_gold), "original_reference_sha256": sha(old_gold),
        "metric_source_sha256": sha(metric_path),
        "metric_source_git_blob_sha1": verify_original_metric_source(metric_path)["git_blob_sha1"]}


def repair(run_dir, snapshot_dir, output):
    run_dir, snapshot_dir, output = (Path(p).resolve() for p in (run_dir, snapshot_dir, output))
    values = inputs(run_dir)
    metadata, _, _, actual, old_gold, metric_path, repaired = values
    binding = _binding(run_dir, values)
    # Never write inside the original/frozen inputs, even if output is a new folder.
    if any(output.is_relative_to(run_dir / part) for part in ("tasks", "harness", "upstream", "product-source")):
        raise ValueError("Correction output must be separate from original/frozen artifacts")
    output.mkdir(parents=True, exist_ok=False)
    for name in SOURCE_NAMES:
        shutil.copyfile(ROOT / name, output / name)
    record = {"schema_version": 1, "kind": KIND, "task_id": TASK_ID, "run_dir": str(run_dir),
        "created_at": datetime.now(timezone.utc).isoformat(), "status": "repair_error", "score": None,
        "original_status": "scored", "original_score": 0.0, "original_score_unchanged": True,
        "custom_reference_update": True, "unmodified_official_scoring": False,
        "actor_rerun": False, "model_calls": 0, "vm_starts": 0, "getter_replayed": False,
        "input_kind": "retained_original_postconfig_vm_file", "upstream_commit": UPSTREAM_COMMIT,
        **binding, "metric": "compare_table", "original_options": deepcopy(ORIGINAL_OPTIONS),
        "repaired_options": deepcopy(repaired), "reference": str(output / "reference/current-reference.xlsx"),
        "reference_provenance": str(output / "reference/provenance.json"),
        "repair_sources_sha256": {name: sha(output / name) for name in SOURCE_NAMES}, "evidence_errors": [],
        "boundary": "Reference B/C/D fields come from five independently captured current Google Maps listings, never the Actor workbook. Original comparison and address/numeric rules are unchanged. Only this task's D6 uses existing exact_match for the independently absent Niras website."}
    try:
        build_reference(old_gold, snapshot_dir, output / "reference")
        record.update(reference_sha256=sha(record["reference"]),
            reference_provenance_sha256=sha(record["reference_provenance"]))
        sys.path.insert(0, metadata["osworld_root"])
        metric = importlib.import_module("desktop_env.evaluators.metrics.table").compare_table
        if Path(inspect.getsourcefile(metric)).resolve() != metric_path.resolve():
            raise ValueError("Imported comparison is not from this run's frozen checkout")
        # The original task has already saved via postconfig; these are its
        # preserved getter bytes. No getter, postconfig or setup is replayed.
        value = metric(str(actual), record["reference"], **deepcopy(repaired))
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Unchanged official comparison returned an invalid score")
        if _binding(run_dir, inputs(run_dir)) != binding:
            raise ValueError("Original inputs or metric source changed during correction")
        verify_reference(old_gold, output / "reference")
        record.update(status="corrected", score=float(value))
    except Exception as error:
        record.update(status="repair_error", score=None, error_type=type(error).__name__, error=str(error))
    record["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_new(output / "correction.json", record)
    return record


def verify_correction(run_dir, path):
    run_dir, path = Path(run_dir).resolve(), Path(path).resolve()
    record = read(path)
    if (record.get("kind") != KIND or record.get("task_id") != TASK_ID
            or record.get("status") != "corrected" or Path(record["run_dir"]).resolve() != run_dir
            or record.get("original_status") != "scored" or type(record.get("original_score")) not in (float, int)
            or record["original_score"] != 0 or record.get("original_score_unchanged") is not True
            or record.get("custom_reference_update") is not True or record.get("unmodified_official_scoring") is not False
            or record.get("actor_rerun") is not False or record.get("getter_replayed") is not False
            or any(type(record.get(k)) is not int or record[k] != 0 for k in ("vm_starts", "model_calls"))
            or record.get("input_kind") != "retained_original_postconfig_vm_file" or record.get("evidence_errors")
            or record.get("upstream_commit") != UPSTREAM_COMMIT or record.get("metric") != "compare_table"):
        raise ValueError("Correction identity/execution boundary changed")
    values = inputs(run_dir)
    for key, value in _binding(run_dir, values).items():
        if record.get(key) != value:
            raise ValueError("Original correction input binding changed: " + key)
    if (record.get("original_options") != ORIGINAL_OPTIONS or record.get("repaired_options") != values[-1]
            or record.get("reference") != str(path.parent / "reference/current-reference.xlsx")
            or record.get("reference_provenance") != str(path.parent / "reference/provenance.json")
            or sha(record["reference"]) != record.get("reference_sha256")
            or sha(record["reference_provenance"]) != record.get("reference_provenance_sha256")
            or set(record.get("repair_sources_sha256", {})) != set(SOURCE_NAMES)):
        raise ValueError("Correction options/reference/source inventory changed")
    for name in SOURCE_NAMES:
        if sha(path.parent / name) != record["repair_sources_sha256"][name] or sha(ROOT / name) != record["repair_sources_sha256"][name]:
            raise ValueError("Archived or executing correction source changed")
    verify_reference(values[4], path.parent / "reference")
    value = record.get("score")
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Invalid corrected comparison score")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = repair(args.run_dir, args.snapshot_dir, args.output)
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["status"] == "corrected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
