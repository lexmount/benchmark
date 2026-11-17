#!/usr/bin/env python3
"""Rejudge the audited address heading parser issue, without a VM or Actor."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil

from address_reference_repair import (TASK_ID, UPSTREAM_COMMIT, load_official_functions,
                                      score_document, source_provenance)

ROOT = Path(__file__).resolve().parent
KIND = "task-scoped-address-heading-extraction-v1"
ACTUAL_SHA256 = "97d43e8505191d8e790890ee31c0735967566bba1b1d88e84c5383e9ea2e3447"
TASK_SHA256 = "22a705766872e96b937dd5a56f88b7909afa39bde28f99a5e6156b08c2ec04db"
METRIC_SHA256 = "da85cbad0241062f372455dd5ecb977ff780f018350910e9dbb506710d8f6284"
METRIC_GIT_BLOB_SHA1 = "ccacfcb5789de5527d25fd3c634605ef83a52ee4"
SOURCE_NAMES = ("address_reference_repair.py", "repair_address_reference.py")


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


def verify_original_metric_source(path):
    """Verify the audited Git blob without requiring .git in a prepared archive."""
    content = Path(path).read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
    if digest != METRIC_SHA256 or blob != METRIC_GIT_BLOB_SHA1:
        raise ValueError("Metric content differs from the audited fixed upstream Git blob")
    return {"sha256": digest, "git_blob_sha1": blob}


def inputs(run_dir):
    control = load(ROOT / "evaluate.py", "address_repair_control")
    metadata = control.verify_run(run_dir)
    if metadata["upstream_commit"] != UPSTREAM_COMMIT:
        raise ValueError("Only the audited frozen upstream revision is supported")
    manifest = read(Path(metadata["harness_root"]) / "data/manifest.json")
    item = next(t for t in manifest["tasks"] if t["task_id"] == TASK_ID)
    task_path = Path(metadata["harness_root"]) / item["task_path"]
    task = read(task_path)
    evaluator = task["evaluator"]
    if (sha(task_path) != TASK_SHA256 or item["sha256"] != TASK_SHA256
            or evaluator["func"] != "fuzzy_place_math"
            or evaluator["result"] != {"type": "vm_file", "path": "/home/user/Desktop/AllLocations.docx", "dest": "AllLocations.docx"}
            or evaluator["expected"]["type"] != "rule" or evaluator.get("options")):
        raise ValueError("Original address task/getter/options identity changed")
    rules = evaluator["expected"]["rules"]
    if type(rules.get("expected_entry_count")) is not int or rules["expected_entry_count"] != 5 or rules.get("require_distinct") is not True:
        raise ValueError("Original five-distinct-place rule changed")
    receipt_path = run_dir / "tasks" / TASK_ID / "receipt.json"
    receipt = read(receipt_path)
    if (receipt.get("task_id") != TASK_ID or receipt.get("task_sha256") != item["sha256"]
            or receipt.get("status") != "scored" or type(receipt.get("score")) not in (int, float)
            or receipt["score"] != 0 or receipt.get("official_terminal_action") != "DONE"
            or receipt.get("actor_status") != "completed" or receipt.get("owned_vm_closed") is not True
            or receipt.get("evidence_errors")):
        raise ValueError("Expected the clean original completed scored-zero receipt")
    actual = receipt_path.parent / "official-cache" / TASK_ID / evaluator["result"]["dest"]
    if actual.stat().st_size != 10737 or sha(actual) != ACTUAL_SHA256:
        raise ValueError("Original postconfig-saved official result differs from the audited DOCX")
    metric_path = Path(metadata["osworld_root"]) / "desktop_env/evaluators/metrics/general.py"
    verify_original_metric_source(metric_path)
    return metadata, task_path, receipt_path, actual, metric_path, rules


def repair(run_dir, output):
    run_dir, output = Path(run_dir).resolve(), Path(output).resolve()
    metadata, task_path, original, actual, metric_path, rules = inputs(run_dir)
    official = load_official_functions(metadata["osworld_root"])
    old = official["fuzzy_place_math"](str(actual), rules)
    value, extraction = score_document(str(actual), rules, official)
    if old != 0 or len(extraction["ignored_paragraphs"]) != 1:
        raise ValueError("Original zero and the single audited heading were not reproduced")
    if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Unchanged original helper returned an invalid continuous score")
    before = {"run_metadata": sha(run_dir / "run.json"), "task": sha(task_path),
              "original_receipt": sha(original), "original_actual": sha(actual),
              "metric_source": sha(metric_path)}
    output.mkdir(parents=True, exist_ok=False)
    for name in SOURCE_NAMES:
        shutil.copyfile(ROOT / name, output / name)
    write_new(output / "heading-extraction.json", extraction)
    record = {"schema_version": 1, "kind": KIND, "repair_label": "task-scoped heading extraction repair",
        "task_id": TASK_ID, "run_dir": str(run_dir), "status": "corrected",
        "created_at": datetime.now(timezone.utc).isoformat(), "original_score": 0.0,
        "original_metric_reproduced_score": float(old), "score": float(value),
        "actor_rerun": False, "model_calls": 0, "vm_starts": 0, "getter_replayed": False,
        "input_kind": "original_postconfig_official_vm_file", "upstream_commit": UPSTREAM_COMMIT,
        "run_metadata_sha256": before["run_metadata"], "task_path": str(task_path),
        "task_sha256": before["task"], "original_receipt": str(original),
        "original_receipt_sha256": before["original_receipt"], "original_actual": str(actual),
        "original_actual_sha256": before["original_actual"], "original_expected_rule": rules,
        "original_options": read(task_path)["evaluator"].get("options", {}),
        "metric": "fuzzy_place_math/_fuzzy_distinct_place_score",
        "metric_source_sha256": before["metric_source"],
        "metric_source_git_blob_sha1": METRIC_GIT_BLOB_SHA1,
        "outer_metric_checks_preserved": ["non-null existing original result path", "valid integer expected_entry_count", "originalDocumentloading", "require_distinct=True", "expected and identity_aliases unchanged"],
        "helper_boundary": "Only first-heading extraction differs. All remaining original Paragraph objects are passed to the unchanged upstream helper; no document is rewritten and no text, references, count, identity checks or fuzzy formula are normalized beyond upstream behavior.",
        "extraction": str(output / "heading-extraction.json"),
        "extraction_sha256": sha(output / "heading-extraction.json"),
        "repair_sources_sha256": {name: sha(output / name) for name in SOURCE_NAMES},
        "source_provenance": source_provenance(), "evidence_errors": []}
    if any(sha(path) != before[key] for key, path in (("run_metadata", run_dir / "run.json"),
            ("task", task_path), ("original_receipt", original), ("original_actual", actual), ("metric_source", metric_path))):
        raise ValueError("An original input changed during the read-only repair")
    write_new(output / "correction.json", record)
    return record


def verify_correction(run_dir, path):
    run_dir, path = Path(run_dir).resolve(), Path(path).resolve()
    record = read(path)
    metadata, task_path, receipt_path, actual, metric_path, rules = inputs(run_dir)
    if (record.get("kind") != KIND or record.get("task_id") != TASK_ID
            or record.get("status") != "corrected" or Path(record["run_dir"]).resolve() != run_dir
            or record.get("actor_rerun") is not False or record.get("getter_replayed") is not False
            or record.get("model_calls") != 0 or record.get("vm_starts") != 0
            or record.get("input_kind") != "original_postconfig_official_vm_file"
            or type(record.get("original_score")) not in (int, float)
            or record.get("original_score") != 0 or record.get("evidence_errors")
            or record.get("upstream_commit") != UPSTREAM_COMMIT
            or record.get("original_expected_rule") != rules
            or record.get("original_options") != read(task_path)["evaluator"].get("options", {})):
        raise ValueError("Correction identity, reference or declared boundaries changed")
    for key, expected in (("task_path", task_path), ("original_receipt", receipt_path), ("original_actual", actual)):
        hash_key = "task_sha256" if key == "task_path" else key + "_sha256"
        if Path(record[key]).resolve() != expected.resolve() or sha(expected) != record[hash_key]:
            raise ValueError("Correction input changed: " + key)
    if (sha(run_dir / "run.json") != record["run_metadata_sha256"]
            or sha(metric_path) != record["metric_source_sha256"]
            or record.get("metric_source_git_blob_sha1") != METRIC_GIT_BLOB_SHA1):
        raise ValueError("Frozen run or metric source changed")
    if set(record["repair_sources_sha256"]) != set(SOURCE_NAMES):
        raise ValueError("Correction has an unexpected repair source set")
    for name, digest in record["repair_sources_sha256"].items():
        if sha(path.parent / name) != digest or sha(ROOT / name) != digest:
            raise ValueError("Repair source changed: " + name)
    extraction = path.parent / "heading-extraction.json"
    if Path(record["extraction"]).resolve() != extraction.resolve() or sha(extraction) != record["extraction_sha256"]:
        raise ValueError("Heading extraction record changed")
    official = load_official_functions(metadata["osworld_root"])
    old = official["fuzzy_place_math"](str(actual), rules)
    value, observed = score_document(str(actual), rules, official)
    if (old != 0 or type(record.get("original_metric_reproduced_score")) not in (int, float)
            or record.get("original_metric_reproduced_score") != float(old)
            or observed != read(extraction) or len(observed["ignored_paragraphs"]) != 1
            or type(record.get("score")) not in (float, int) or not math.isfinite(record["score"])
            or not 0 <= record["score"] <= 1 or record["score"] != float(value)):
        raise ValueError("Correction does not reproduce the original helper result")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output", type=Path)
    group.add_argument("--verify", type=Path)
    args = parser.parse_args()
    result = (verify_correction(args.run_dir, args.verify) if args.verify
              else repair(args.run_dir, args.output))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
