#!/usr/bin/env python3
"""Bind one explicitly authorized provider-error Actor retry to its original run.

This only reads existing artifacts. It does not launch an Actor, VM, model,
getter or metric, and never replaces the original receipt or its null score.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path, PurePosixPath
import re
import tarfile

ROOT = Path(__file__).resolve().parent
TASK_ID = "0ed39f63-6049-43d4-ba4d-5fa2fe04a951"
KIND = "technical-actor-retry-v1"
AUDITED_GUEST_ACTOR_SHA256 = "fe884502cb86918a43b62062c50f595f36da1bf11eb66c8e813cbe6bd9f675b6"
DERIVED_METADATA = {"created_at", "osworld_root", "harness_root", "bundle_path",
                    "bundle_sha256", "guest_root", "prepared_by"}
REQUIRED_SOURCE_FILES = {"harness/runtime.py", "harness/guest_actor.py",
    "harness/guest_bootstrap.py", "harness/config.json", "harness/data/manifest.json",
    "upstream/desktop_env/desktop_env.py", "product-source/pyproject.toml", "product-source/uv.lock"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def load_control():
    spec = importlib.util.spec_from_file_location("technical_retry_control", ROOT / "evaluate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bundle_inventory(path):
    """Ignore compression/mtime, retaining exact content and permission metadata."""
    result = {}
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            key = str(name)
            if (name.is_absolute() or ".." in name.parts or key in result
                    or not (member.isfile() or member.isdir())):
                raise ValueError("Unsafe or duplicate retry bundle member")
            digest = None
            if member.isfile():
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError("Unreadable retry bundle member")
                hasher = hashlib.sha256()
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(block)
                digest = hasher.hexdigest()
            result[key] = {"type": "file" if member.isfile() else "directory",
                           "mode": member.mode, "size": member.size, "sha256": digest}
    return result


def compare_bundle_inventories(original, retried):
    """Disclose one audited group-write-bit difference; reject every other change."""
    if set(original) != set(retried):
        raise ValueError("Retry runtime bundle paths differ")
    normalized = {name: dict(value) for name, value in original.items()}
    differences = []
    for name, before in original.items():
        after = retried[name]
        if before == after:
            continue
        if (name != "guest_actor.py" or before.get("type") != "file" or after.get("type") != "file"
                or {before.get("mode"), after.get("mode")} != {0o644, 0o664}
                or before.get("size") != 5569 or after.get("size") != 5569
                or before.get("sha256") != AUDITED_GUEST_ACTOR_SHA256
                or after.get("sha256") != AUDITED_GUEST_ACTOR_SHA256
                or set(before) != {"type", "mode", "size", "sha256"}
                or set(after) != set(before)):
            raise ValueError("Retry runtime bundle content or an unapproved permission differs: " + name)
        normalized[name]["mode"] = 0o644
        differences.append({"member": name, "original_mode": before["mode"],
            "retry_mode": after["mode"], "original_mode_octal": oct(before["mode"]),
            "retry_mode_octal": oct(after["mode"]), "size": 5569,
            "unchanged_sha256": AUDITED_GUEST_ACTOR_SHA256,
            "allowed_difference": "Only the group-write bit0644<->0664 for the audited guest_actor.py bytes; no executable,setuid or world-write change."})
    return normalized, differences


def _frozen_sources(run, control):
    declared = read(run / "frozen-files.json")
    if not REQUIRED_SOURCE_FILES.issubset(declared):
        raise ValueError("Frozen source inventory is incomplete")
    sources = {}
    for prefix in ("harness", "upstream", "product-source"):
        actual = {prefix + "/" + key: value for key, value in control.file_inventory(run / prefix).items()}
        expected = {k: v for k, v in declared.items() if k.startswith(prefix + "/")}
        if actual != expected:
            raise ValueError("Frozen source inventory has missing/extra/changed files: " + prefix)
        sources.update(expected)
    if set(declared) != set(sources) | {"run.json", "runtime-bundle.tar.gz"}:
        raise ValueError("Unexpected frozen inventory entries")
    return sources


def _engine_signature(metadata, guest_root):
    sources = metadata.get("sources", {})
    required = {"product_runner", "product_config", "engine_service",
                "engine_repl_worker", "engine_repl_session"}
    if (not required.issubset(sources) or metadata.get("uid") != 1000
            or metadata.get("home") != "/home/user"):
        raise ValueError("Missing original engine identity/user evidence")
    for value in sources.values():
        if (not re.fullmatch(r"[0-9a-f]{64}", value.get("sha256", ""))
                or not value.get("path", "").startswith(guest_root + "/")):
            raise ValueError("Engine source evidence is not bound to this guest")
    return {"python": metadata["python"], "packages": metadata["packages"],
            "sources": {k: v["sha256"] for k, v in sources.items()},
            "uid": metadata["uid"], "home": metadata["home"]}


def _public_actor_run(path):
    with tarfile.open(path, "r:gz") as archive:
        matches = [m for m in archive.getmembers() if m.name == "actor-output/run.json"]
        if len(matches) != 1 or not matches[0].isfile() or matches[0].size > 128 * 1024:
            raise ValueError("Missing/ambiguous original public Actor run configuration")
        raw = archive.extractfile(matches[0]).read()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _run_inputs(run, control):
    metadata = control.verify_run(run)
    for key, suffix in (("harness_root", "harness"), ("osworld_root", "upstream"),
                        ("bundle_path", "runtime-bundle.tar.gz")):
        if Path(metadata[key]).resolve() != (run / suffix).resolve():
            raise ValueError("Frozen paths are not derived from their own run")
    guest = metadata["guest_root"]
    if not re.fullmatch(r"/tmp/lexmount-osworld-[0-9a-f]{32}", guest):
        raise ValueError("Unexpected guest-root identity")
    sources = _frozen_sources(run, control)
    manifest = read(Path(metadata["harness_root"]) / "data/manifest.json")
    items = [t for t in manifest["tasks"] if t["task_id"] == TASK_ID]
    if len(items) != 1:
        raise ValueError("Retry task is absent/duplicated in the frozen manifest")
    item = items[0]
    task_path = Path(metadata["harness_root"]) / item["task_path"]
    if sha(task_path) != item["sha256"]:
        raise ValueError("Original task bytes changed")
    instruction = read(task_path)["instruction"]
    folder = run / "tasks" / TASK_ID
    receipt_path = folder / "receipt.json"
    receipt = read(receipt_path)
    if (receipt.get("task_id") != TASK_ID or receipt.get("task_sha256") != item["sha256"]
            or receipt.get("budget") != metadata["config"]["actor"]
            or receipt.get("owned_vm_closed") is not True
            or receipt.get("owned_container_removal_verified") is not True
            or receipt.get("evidence_errors")):
        raise ValueError("Task receipt/budget/cleanup is not valid for this frozen run")
    actor_path = folder / "actor-result.json"
    actor = read(actor_path)
    native = actor.get("result", {})
    if (actor.get("status") != "finished" or native.get("status") != receipt.get("actor_status")
            or native.get("agent_success") != receipt.get("agent_success")):
        raise ValueError("Original native outcome and bridge receipt disagree")
    context = actor.get("appended_environment_context", "")
    if (actor.get("instruction_sha256") != hashlib.sha256(instruction.encode()).hexdigest()
            or actor.get("effective_prompt_sha256") != hashlib.sha256((instruction + context).encode()).hexdigest()
            or guest + "/initial.png" not in context):
        raise ValueError("Native Actor prompt is not bound to the original task and guest")
    public, public_hash = _public_actor_run(folder / "actor-output.tar.gz")
    if (public.get("task") != instruction + context
            or public.get("model_override") is not None):
        raise ValueError("Actor configuration used a different task or model override")
    for key, value in metadata["config"]["actor"].items():
        if public.get("config", {}).get(key) != value:
            raise ValueError("Actual Actor setting differs from the frozen budget: " + key)
    signature = _engine_signature(actor["metadata"], guest)
    if public.get("versions") != signature["packages"]:
        raise ValueError("Actual public/native package versions disagree")
    probe_path = run / "probe.json"
    probe = read(probe_path)
    product_probe = probe.get("product_probe", {})
    if (probe.get("status") != "passed" or probe.get("run_metadata_sha256") != sha(run / "run.json")
            or probe.get("owned_vm_closed") is not True or probe.get("owned_container_removal_verified") is not True
            or probe.get("evidence_errors") or product_probe.get("status") != "passed"
            or product_probe.get("file_roundtrip") is not True
            or _engine_signature(product_probe["metadata"], guest) != signature):
        raise ValueError("A model-free passing probe bound to this exact run is required")
    for name, key in (("product_runner", "product-source/src/lexmount_browser_agent/runner.py"),
                      ("product_config", "product-source/src/lexmount_browser_agent/config.py")):
        if sources.get(key) != signature["sources"][name]:
            raise ValueError("Native product source differs from the frozen product checkout")
    return {"metadata": metadata, "sources": sources, "item": item, "receipt": receipt,
        "actor": actor, "native": native, "public_config": public["config"],
        "normalized_context": context.replace(guest, "{GUEST_ROOT}"), "engine": signature,
        "binding": {"run_dir": str(run), "run_metadata_sha256": sha(run / "run.json"),
            "frozen_inventory_sha256": sha(run / "frozen-files.json"), "task_sha256": item["sha256"],
            "receipt": str(receipt_path), "receipt_sha256": sha(receipt_path),
            "actor_result_sha256": sha(actor_path), "actor_archive_sha256": sha(folder / "actor-output.tar.gz"),
            "public_actor_run_member_sha256": public_hash, "probe_sha256": sha(probe_path),
            "native_status": native.get("status"), "status": receipt.get("status"),
            "score": receipt.get("score"), "model_turns": native.get("model_turns"),
            "model_http_requests": native.get("model_http_requests"), "wall_seconds": native.get("wall_seconds")}}


def _snapshot(run_dir, retry_run_dir):
    run, retry = Path(run_dir).resolve(), Path(retry_run_dir).resolve()
    if run == retry:
        raise ValueError("The retry must be a separate run")
    control = load_control()
    old, new = _run_inputs(run, control), _run_inputs(retry, control)
    receipt, native = old["receipt"], old["native"]
    error = native.get("error", "")
    if (receipt.get("status") != "actor_error" or receipt.get("score") is not None
            or receipt.get("actor_status") != "error" or native.get("status") != "error"
            or receipt.get("official_terminal_action") is not None
            or "ModelRequestRejectedError" not in error or "status_code: 400" not in error
            or "Temporary multimodal download failure" not in error):
        raise ValueError("Only the audited provider-image error/null outcome can have a technical Actor retry")
    rr, rn = new["receipt"], new["native"]
    score = rr.get("score")
    if (rr.get("status") != "scored" or type(score) not in (int, float)
            or not math.isfinite(score) or not 0 <= score <= 1
            or rn.get("status") not in {"completed", "max_steps", "timeout"}):
        raise ValueError("Retry does not have a legal scored task outcome")
    expected_action = ("DONE" if rn.get("agent_success") is True else "FAIL"
                       if rn.get("agent_success") is False else None) if rn["status"] == "completed" else None
    if rr.get("official_terminal_action") != expected_action or (rn["status"] == "completed" and expected_action is None):
        raise ValueError("Retry terminal action disagrees with the frozen bridge protocol")
    if datetime.fromisoformat(rr["started_at"]) < datetime.fromisoformat(receipt["finished_at"]):
        raise ValueError("Retry predates the original technical failure")
    stable_old = {k: v for k, v in old["metadata"].items() if k not in DERIVED_METADATA}
    stable_new = {k: v for k, v in new["metadata"].items() if k not in DERIVED_METADATA}
    if (stable_old != stable_new or old["sources"] != new["sources"]
            or old["item"] != new["item"] or old["public_config"] != new["public_config"]
            or old["normalized_context"] != new["normalized_context"] or old["engine"] != new["engine"]):
        raise ValueError("Retry product/upstream/config/source/task/protocol differs from the original run")
    bundles = [bundle_inventory(x["metadata"]["bundle_path"]) for x in (old, new)]
    normalized_bundle, bundle_differences = compare_bundle_inventories(*bundles)
    return {"original": old["binding"], "retry": new["binding"],
        "agent_commit": old["metadata"]["agent_commit"], "upstream_commit": old["metadata"]["upstream_commit"],
        "benchmark_commit": old["metadata"]["benchmark_commit"],
        "actor_budget": old["metadata"]["config"]["actor"],
        "public_actor_config_sha256": canonical(old["public_config"]),
        "source_inventory_sha256": canonical(old["sources"]),
        "runtime_bundle_normalized_member_inventory_sha256": canonical(normalized_bundle),
        "runtime_bundle_original_member_inventory_sha256": canonical(bundles[0]),
        "runtime_bundle_retry_member_inventory_sha256": canonical(bundles[1]),
        "runtime_bundle_allowed_metadata_differences": bundle_differences,
        "bundle_permission_policy": "Exact member paths/content/types/sizes/modes except the disclosed0644<->0664 group-write bit on the audited5569byte guest_actor.py blob.",
        "engine_signature": old["engine"],
        "allowed_derived_metadata_differences": sorted(k for k in DERIVED_METADATA
            if old["metadata"].get(k) != new["metadata"].get(k))}


def create_record(run_dir, retry_run_dir, output_record):
    snapshot = _snapshot(run_dir, retry_run_dir)
    path = Path(output_record).resolve()
    for value in (snapshot["original"], snapshot["retry"]):
        run = Path(value["run_dir"])
        if any(path.is_relative_to(run / part) for part in ("tasks", "harness", "upstream", "product-source")) or path in {run / "run.json", run / "frozen-files.json", run / "probe.json", run / "runtime-bundle.tar.gz"}:
            raise ValueError("Retry record must not overwrite original/frozen artifacts")
    record = {"schema_version": 1, "kind": KIND, "task_id": TASK_ID,
        "run_dir": str(Path(run_dir).resolve()), "retry_run_dir": str(Path(retry_run_dir).resolve()),
        "created_at": datetime.now(timezone.utc).isoformat(), "actor_rerun": True,
        "original_score": None, "score": float(snapshot["retry"]["score"]),
        "status": "technical_retry_recorded", "original_receipt_unchanged": True,
        "original_output_rejudged": False, "snapshot": snapshot,
        "verifier_sha256": sha(Path(__file__)),
        "boundary": "A separately authorized new Actor attempt after a provider image-download error; not a regrade of the original output and not a retry of a legal original zero."}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return record


def verify_record(run_dir, record_path, retry_run_dir=None):
    record = read(record_path)
    if (record.get("kind") != KIND or record.get("task_id") != TASK_ID
            or record.get("actor_rerun") is not True or record.get("original_score") is not None
            or record.get("original_output_rejudged") is not False
            or record.get("original_receipt_unchanged") is not True
            or record.get("status") != "technical_retry_recorded"
            or Path(record["run_dir"]).resolve() != Path(run_dir).resolve()
            or record.get("verifier_sha256") != sha(Path(__file__))
            or retry_run_dir is not None and Path(record["retry_run_dir"]).resolve() != Path(retry_run_dir).resolve()):
        raise ValueError("Technical Actor retry record identity/boundary changed")
    snapshot = _snapshot(run_dir, record["retry_run_dir"])
    if (record.get("snapshot") != snapshot or type(record.get("score")) not in (int, float)
            or record["score"] != snapshot["retry"]["score"]):
        raise ValueError("Original or retry artifact/configuration changed")
    return record


create = create_record
verify = verify_record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--run-dir", required=True, type=Path)
    create.add_argument("--retry-run-dir", required=True, type=Path)
    create.add_argument("--output", required=True, type=Path)
    verify = sub.add_parser("verify")
    verify.add_argument("--run-dir", required=True, type=Path)
    verify.add_argument("--record", required=True, type=Path)
    args = parser.parse_args()
    value = (create_record(args.run_dir, args.retry_run_dir, args.output)
             if args.command == "create" else verify_record(args.run_dir, args.record))
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
