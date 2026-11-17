#!/usr/bin/env python3
"""Frozen 76-task data checks, run preparation and original-OSWorld dispatch.

Only probe/run import the separately installed official VM dependencies.
verify/prepare/report use the Python standard library and never call a model.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import uuid

ROOT = Path(__file__).resolve().parent
UPSTREAM = "5123bfdbbc34b947bcffcff564abc62d0ab7072d"
MANIFEST_SHA256 = "a00d470d1ce25eb31a29a394b019a191c159bd23c91a92a8d5a4580de7597e2d"
COUNTS = {"web": 25, "browser_file": 27, "local_file": 24}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def check(condition, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify(root: Path = ROOT, upstream: Path | None = None) -> dict:
    path = root / "data/manifest.json"
    check(digest(path) == MANIFEST_SHA256, "The approved 76-task manifest changed")
    manifest = read_json(path)
    check(manifest["upstream"]["commit"] == UPSTREAM, "Wrong upstream revision")
    tasks = manifest["tasks"]
    check(len(tasks) == manifest["task_count"] == 76, "Expected exactly 76 tasks")
    check(Counter(t["category"] for t in tasks) == COUNTS, "Wrong category counts")
    check(len({t["task_id"] for t in tasks}) == 76, "Duplicate task IDs")
    original = read_json(root / "data/upstream/test_all.json")
    nogdrive = read_json(root / "data/upstream/test_nogdrive.json")
    check(sum(map(len, original.values())) == 368, "Wrong source manifest")
    check(sum(map(len, nogdrive.values())) == 360, "Wrong no-Drive source manifest")
    google = {i for d, ids in original.items() for i in ids if i not in nogdrive[d]}
    exclusions = read_json(root / "data/exclusions.json")
    check({t["task_id"] for t in exclusions["excluded"]} == google, "Wrong Drive exclusions")
    check(len(google) == 8 and exclusions["candidate_count"] == 84, "Wrong selection provenance")
    order = {(d, i): n for n, (d, i) in enumerate(
        (d, i) for d, ids in original.items() for i in ids)}
    positions = []
    for ordinal, item in enumerate(tasks, 1):
        task_id, domain = item["task_id"], item["source_domain"]
        expected_path = f"data/tasks/{domain}/{task_id}.json"
        check(item["ordinal"] == ordinal and item["task_path"] == expected_path, "Wrong index or path")
        check(task_id not in google and task_id in original[domain], "Invalid selected ID")
        check(original[domain].index(task_id) + 1 == item["source_ordinal"], "Wrong original ordinal")
        positions.append(order[domain, task_id])
        raw = root / expected_path
        check(digest(raw) == item["sha256"], f"Task bytes changed: {task_id}")
        task = read_json(raw)
        check(task["id"] == task_id, "ID differs from filename")
        check(hashlib.sha256(task["instruction"].encode()).hexdigest() == item["instruction_sha256"],
              f"Instruction changed: {task_id}")
        if upstream is not None:
            source = upstream / "evaluation_examples/examples" / domain / (task_id + ".json")
            check(digest(source) == item["sha256"], f"Different upstream task: {task_id}")
    check(positions == sorted(positions), "Official relative order changed")
    check(len(list((root / "data/tasks").rglob("*.json"))) == 76, "Extra/missing raw task file")
    return {"status": "passed", "task_count": 76, "category_counts": COUNTS,
            "manifest_sha256": MANIFEST_SHA256, "upstream_commit": UPSTREAM,
            "compared_with_upstream": upstream is not None, "model_calls": 0}


def git(source: Path, *args: str, binary=False):
    return subprocess.check_output(["git", "-C", str(source), *args], text=not binary).strip()


def archive_git(source: Path, commit: str, target: Path, paths: list[str] | None = None) -> None:
    command = ["git", "-C", str(source), "archive", "--format=tar", commit, *(paths or [])]
    archive = subprocess.check_output(command)
    target.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        for member in stream.getmembers():
            # Archives here contain source files only. Never follow repository symlinks.
            check(not member.issym() and not member.islnk(), "Source archive contains a symlink")
            check(member.isdir() or member.isfile(), "Unsupported archive member")
            check((target / member.name).resolve().is_relative_to(target.resolve()), "Unsafe archive path")
        stream.extractall(target)


def file_inventory(base: Path) -> dict[str, str]:
    return {str(p.relative_to(base)): digest(p) for p in sorted(base.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def clean_commit(source: Path, expected: str | None = None) -> str:
    commit = git(source, "rev-parse", "HEAD")
    check(expected is None or commit == expected, f"Unexpected commit in {source}")
    check(not git(source, "status", "--porcelain", "--untracked-files=no"), f"Tracked changes in {source}")
    return commit


def prepare(args) -> dict:
    upstream, product = args.osworld_root.resolve(), args.agent_source.resolve()
    clean_commit(upstream, UPSTREAM)
    commit = clean_commit(product, args.agent_commit)
    verify(upstream=upstream)
    uv = args.uv_binary.resolve()
    with uv.open("rb") as stream:
        check(stream.read(4) == b"\x7fELF", "Pass the 5090 Linux uv executable, not a macOS binary")
    uv_version = subprocess.check_output([str(uv), "--version"], text=True, timeout=10).strip()
    check(uv_version.startswith("uv "), "Pass the actual uv binary, not the snap launcher")
    vm = args.vm_image.resolve()
    check(vm.is_file(), "VM image does not exist")
    config = read_json(ROOT / "config.json")
    folder = args.run_dir.resolve()
    folder.mkdir(parents=True, exist_ok=False, mode=0o700)
    archive_git(upstream, UPSTREAM, folder / "upstream")
    archive_git(product, commit, folder / "product-source", ["src", "pyproject.toml", "uv.lock"])
    shutil.copytree(ROOT, folder / "harness", ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc", ".private", ".venv", "results", "*.log"))
    bundle = folder / "runtime-bundle.tar.gz"
    with tarfile.open(bundle, "w:gz") as stream:
        stream.add(folder / "product-source", arcname="product")
        stream.add(uv, arcname="uv")
        for name in ("guest_bootstrap.py", "guest_actor.py"):
            stream.add(folder / "harness" / name, arcname=name)
    # Deliberately hash the QCOW2 itself once; a ZIP receipt is not its checksum.
    vm_sha = digest(vm)
    stat = vm.stat()
    try:
        benchmark_commit = git(ROOT, "rev-parse", "HEAD")
    except subprocess.SubprocessError:
        benchmark_commit = None
    record = {"schema_version": 1, "benchmark": "OSWorld-Verified-filter", "task_count": 76,
              "benchmark_commit": benchmark_commit,
              "created_at": now(), "upstream_commit": UPSTREAM, "agent_commit": commit,
              "config": config, "osworld_root": str(folder / "upstream"),
              "harness_root": str(folder / "harness"), "bundle_path": str(bundle),
              "bundle_sha256": digest(bundle), "uv_binary_sha256": digest(uv),
              "uv_version": uv_version,
              "vm_image": str(vm), "vm_image_sha256": vm_sha,
              "vm_image_size": stat.st_size, "vm_image_mtime_ns": stat.st_mtime_ns,
              "guest_root": "/tmp/lexmount-osworld-" + uuid.uuid4().hex,
              "protocol": config["protocol"], "prepared_by": str(ROOT)}
    write_json(folder / "run.json", record)
    write_json(folder / "frozen-files.json", {
        "run.json": digest(folder / "run.json"),
        "runtime-bundle.tar.gz": digest(bundle),
        **{"harness/" + k: v for k, v in file_inventory(folder / "harness").items()},
        **{"upstream/" + k: v for k, v in file_inventory(folder / "upstream").items()},
        **{"product-source/" + k: v for k, v in file_inventory(folder / "product-source").items()}})
    return {"status": "prepared", "run_dir": str(folder), "agent_commit": commit,
            "task_count": 76, "vm_image_sha256": vm_sha, "model_calls": 0}


def verify_run(folder: Path) -> dict:
    folder = folder.resolve()
    for name, checksum in read_json(folder / "frozen-files.json").items():
        check(digest(folder / name) == checksum, f"Frozen file changed: {name}")
    record = read_json(folder / "run.json")
    check(record["upstream_commit"] == UPSTREAM and record["task_count"] == 76, "Wrong frozen run")
    stat = Path(record["vm_image"]).stat()
    check((stat.st_size, stat.st_mtime_ns) == (record["vm_image_size"], record["vm_image_mtime_ns"]),
          "VM image changed after prepare; do not resume with a different image")
    verify(Path(record["harness_root"]), Path(record["osworld_root"]))
    return record


def report(folder: Path) -> dict:
    record = read_json(folder / "run.json")
    verify(Path(record["harness_root"]))
    if (folder / "frozen-files.json").exists():
        for name, checksum in read_json(folder / "frozen-files.json").items():
            if name == "run.json" or name.startswith("harness/"):
                check(digest(folder / name) == checksum, f"Frozen report input changed: {name}")
    manifest = read_json(Path(record["harness_root"]) / "data/manifest.json")
    rows, scores, errors = [], [], Counter()
    for item in manifest["tasks"]:
        path = folder / "tasks" / item["task_id"] / "receipt.json"
        try:
            receipt = read_json(path) if path.exists() else {"status": "missing", "score": None}
        except (ValueError, OSError):
            receipt = {"status": "invalid_receipt", "score": None}
        if not isinstance(receipt, dict):
            receipt = {"status": "invalid_receipt", "score": None}
        score = receipt.get("score")
        legal = (receipt.get("status") == "scored" and type(score) in (float, int)
                 and math.isfinite(score) and 0 <= score <= 1
                 and receipt.get("task_id") == item["task_id"]
                 and receipt.get("task_sha256") == item["sha256"])
        status = receipt.get("status", "invalid_receipt")
        if status == "scored" and not legal:
            status = "invalid_receipt"
        if legal:
            scores.append(float(score))
        else:
            errors[status] += 1
        rows.append({"ordinal": item["ordinal"], "task_id": item["task_id"],
                     "category": item["category"], "status": status,
                     "score": float(score) if legal else None})
    complete = len(scores) == 76
    return {"benchmark": "OSWorld-Verified-filter", "agent_commit": record["agent_commit"],
            "upstream_commit": record["upstream_commit"], "fixed_denominator": 76,
            "valid_scored_tasks": len(scores), "unscored_tasks": 76 - len(scores),
            "complete": complete, "score_sum": sum(scores),
            "full_76_mean_score": sum(scores) / 76 if complete else None,
            "observed_mean_score": sum(scores) / len(scores) if scores else None,
            "fully_successful_tasks": sum(s == 1 for s in scores),
            "full_76_success_rate": sum(s == 1 for s in scores) / 76 if complete else None,
            "unscored_statuses": dict(errors), "tasks": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("verify", help="Offline exact-data verification")
    command.add_argument("--upstream", type=Path)
    command = commands.add_parser("prepare", help="Freeze source, runtime and the 76-task plan; no model")
    command.add_argument("--osworld-root", type=Path, required=True)
    command.add_argument("--agent-source", type=Path, required=True)
    command.add_argument("--agent-commit", required=True, help="Full product commit")
    command.add_argument("--uv-binary", type=Path, required=True)
    command.add_argument("--vm-image", type=Path, required=True)
    command.add_argument("--run-dir", type=Path, required=True)
    for name in ("probe", "run", "report"):
        command = commands.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)
        if name == "run":
            command.add_argument("--model-config", type=Path, required=True)
            command.add_argument("--task-id", action="append", help="Smoke subset; full report still uses 76")
    args = parser.parse_args()
    try:
        if args.command == "verify":
            result = verify(upstream=args.upstream)
        elif args.command == "prepare":
            result = prepare(args)
        elif args.command == "report":
            result = report(args.run_dir.resolve())
        else:
            run_dir = args.run_dir.resolve()
            record = verify_run(run_dir)
            # Execute the frozen bridge, even if the caller later updates this checkout.
            sys.path.insert(0, record["harness_root"])
            from runtime import probe, run_tasks
            if args.command == "probe":
                result = probe(run_dir)
            else:
                check(read_json(run_dir / "probe.json").get("status") == "passed", "A passing probe is required")
                result = run_tasks(run_dir, args.model_config.resolve(), args.task_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") not in {"failed", "error"} else 1
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
