#!/usr/bin/env python3
"""Retire daily BU-100 entry points; default is a read-only plan.

Run on 5090 only after the self-contained BU-filter package passes its free checks.
This is an operator migration tool, not an evaluator. It never starts a model.
"""
from __future__ import annotations

import argparse
import copy
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import time
from datetime import datetime, timezone

BU_NAMES = {"bu_v1", "bu_bench_v1", "BU_Bench_V1", "bu-lexmount"}
DIRECT = [f"benchmark/{n}" for n in ("bu_bench_v1", "bu_bench_v1_1", "bu_bench_v1_1_fork", "bu-lexmount")]
COMPAT = ["benchmark/bu_bench_v1/upstream/BU_Bench_V1.enc", "benchmark/bu_bench_v1/upstream/judge.py"]
MIXED = ["tmp/bu103-core-20261113", "tmp/bu103-helpers-20261114", "tmp/bu103-reliability-20261113"]
SHARED_RUNS = {"tmp/bu-0x-5090-local-bu100-20261112": "Legacy Python path imported by the mixed evaluation module"}
CANDIDATES = [f"tmp/{n}" for n in (
    "bu-0x-5090-local-bu100-20261112", "bu-colleague-interrupted23-retest-1115",
    "bu-colleague-native-reproduction-1115", "bu-colleague-native-reproduction-1115-early-aborted",
    "bu-pure-5090-local-bu100-20261112", "cae-5090-bu100-20261112",
    "cae-5090-local-bu100-20261112", "cae-native-5090-local-bu100-20261112",
    "cae-program-gpt61sol-local-5090-bu100-20261115", "codex-main-bu5-20261110",
)]
CANDIDATES += ["tmp/bu103-helpers-20261114/" + n for n in (
    "bu-budget-delivery-e2ed37d-1115", "bu-df93e28-failed28-300steps-20261116",
    "bu-fresh-delivery-93cf652-1115", "bu-projected-evidence-bcdb196-1115",
    "bu-research-f476c6b-1115", "bu-verified-review-df93e28-1115",
)]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_manifest(root: Path) -> dict:
    result = {}
    for base, directories, files in os.walk(root, followlinks=False):
        for name in list(directories):
            p = Path(base) / name
            if p.is_symlink():
                result[str(p.relative_to(root))] = {"link": os.readlink(p)}
                directories.remove(name)
        for name in files:
            p = Path(base) / name
            if p.is_symlink():
                result[str(p.relative_to(root))] = {"link": os.readlink(p)}
            elif p.is_file():
                result[str(p.relative_to(root))] = {"sha256": digest(p), "bytes": p.stat().st_size}
            else:
                raise RuntimeError(f"Special file prevents verified backup: {p}")
    return result


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")
    temp.replace(path)


def exchange_directories(left: Path, right: Path) -> None:
    """Atomic Linux exchange keeps OD's shared source paths continuously readable."""
    libc = ctypes.CDLL(None, use_errno=True)
    call = getattr(libc, "renameat2", None)
    if call is None:
        raise RuntimeError("Atomic directory exchange is unavailable; leave legacy files in place")
    call.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    call.restype = ctypes.c_int
    if call(-100, os.fsencode(left), -100, os.fsencode(right), 2):
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number))


def processes() -> list[dict]:
    rows = []
    for p in Path("/proc").iterdir():
        if not p.name.isdigit() or int(p.name) == os.getpid():
            continue
        try:
            cwd = Path(os.readlink(p / "cwd"))
            cmd = [(v.decode(errors="replace")) for v in (p / "cmdline").read_bytes().split(b"\0") if v]
            fields = (p / "stat").read_text().rsplit(")", 1)[1].split()
            exe = os.readlink(p / "exe")
            rows.append({"pid": int(p.name), "cwd": str(cwd), "start_ticks": int(fields[19]),
                         "state": fields[0], "exe": exe,
                         "scripts": [v for v in cmd if v.endswith((".py", ".sh")) and len(v) < 300]})
        except (OSError, PermissionError, ValueError):
            continue
    return rows


def under(path: str | Path, folder: Path) -> bool:
    try:
        Path(path).relative_to(folder)
        return True
    except ValueError:
        return False


def users_of(folder: Path, rows: list[dict]) -> list[dict]:
    return [r for r in rows if under(r["cwd"], folder) or under(r["exe"], folder)
            or any(under(p, folder) for p in r["scripts"] if p.startswith("/"))]


def bu_only_plan(folder: Path) -> bool:
    p = folder / "plan.json"
    if not p.is_file():
        return False
    value = json.loads(p.read_text())
    jobs = value.get("jobs")
    return isinstance(jobs, list) and bool(jobs) and all(
        isinstance(j, dict) and j.get("suite", j.get("benchmark")) in BU_NAMES for j in jobs)


def bu_defaults(current: dict, new_entry: str) -> dict:
    """Retire only BU options, retaining concurrently configured benchmarks."""
    value = copy.deepcopy(current)
    value["schema_version"] = 1
    value["default_bu_benchmark"] = "bu-filter"
    benchmarks = value.setdefault("benchmarks", {})
    old_bu = {name.lower() for name in BU_NAMES} | {"bu_bench_v1_1", "bu_bench_v1_1_fork", "bu-bench"}
    for name in list(benchmarks):
        if name.lower() in old_bu:
            del benchmarks[name]
    benchmarks["bu-filter"] = {"task_count": 87, "max_steps": 300,
                               "timeout_seconds": 3600, "entry": new_entry}
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/data/wf/sxh/workspace/lexmount/exclusive-agent-eval"))
    parser.add_argument("--new-entry", type=Path, required=True, help="New entry relative to eval root, e.g. bu-filter/run.py")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--retire-run", action="append", default=[], choices=[p for p in CANDIDATES if p not in SHARED_RUNS],
                        help="Optional pure-BU run; operator must first rule out shared OD/OMW imports/env dependencies")
    parser.add_argument("--stop-confirmed-bu-processes", action="store_true",
                        help="SIGTERM only processes belonging to an explicitly selected pure-BU plan; never mixed controllers")
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    entry = root / args.new_entry
    if args.new_entry.is_absolute() or ".." in args.new_entry.parts or not entry.is_file():
        raise SystemExit("New BU-filter entry must exist inside the eval root")
    if not args.new_entry.parts or args.new_entry.parts[0] != "bu-filter":
        raise SystemExit("New entry must be inside bu-filter/")
    control_python = root / ".venvs/bu-filter-control/bin/python"
    if args.apply and (not control_python.is_file() or not os.access(control_python, os.X_OK)):
        raise SystemExit("BU-filter control environment is missing; finish setup before retiring legacy entries")
    archive = args.archive or root.parent / ".archives" / ("bu-before-filter-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    archive = archive.absolute()
    if under(archive, root) or archive.exists():
        raise SystemExit("Archive must be a new directory outside the daily eval root")
    selected = [r for r in DIRECT + args.retire_run if (root / r).exists()]
    for rel in args.retire_run:
        if not bu_only_plan(root / rel):
            raise SystemExit(f"Not a verified pure-BU job plan: {rel}")
    rows = processes()
    active = {rel: users_of(root / rel, rows) for rel in selected}
    plan = {"root": str(root), "archive": str(archive), "new_entry": str(args.new_entry), "retire": selected, "control_python": str(control_python), "control_environment_ready": control_python.is_file(),
            "active_under_selected": {k: v for k, v in active.items() if v},
            "retained_shared_compatibility_files": COMPAT, "retained_mixed_trees": MIXED,
            "optional_bu_only_candidates": [p for p in CANDIDATES if p not in SHARED_RUNS], "retained_shared_run_dependencies": SHARED_RUNS,
            "boundary": "Daily default and direct benchmark entry points only. Shared mixed frozen code remains for OD/OMW; same-UID/root can deliberately inspect archives."}
    if not args.apply:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return
    for rel, users in active.items():
        if not users:
            continue
        if rel not in args.retire_run or not args.stop_confirmed_bu_processes:
            raise SystemExit(f"Selected directory has live processes; refusing migration: {rel}")
        for row in users:
            current = next((p for p in processes() if p["pid"] == row["pid"]), None)
            if current is None:
                continue
            if current["start_ticks"] != row["start_ticks"] or not users_of(root / rel, [current]):
                raise SystemExit("Process identity changed; refusing to signal")
            os.kill(row["pid"], signal.SIGTERM)
        deadline = time.monotonic() + 10
        while users_of(root / rel, processes()) and time.monotonic() < deadline:
            time.sleep(0.2)
        if users_of(root / rel, processes()):
            raise SystemExit(f"Processes did not drain after SIGTERM; refusing migration: {rel}")
    # Preserve OD/OMW source verification hashes before retiring direct BU folders.
    compat_hashes = {rel: digest(root / rel) for rel in COMPAT}
    archive.mkdir(parents=True, mode=0o700)
    write_json(archive / "plan.json", plan)
    for name in ["defaults.json", "load_bu.py"]:
        p = root / "benchmark" / name
        if p.exists():
            q = archive / "previous-entry-config" / name
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, q)
    receipt = {"moved": [], "compatibility": {}, "complete": False}
    write_json(archive / "receipt.json", receipt)
    for rel in selected:
        source, backup, retired = root / rel, archive / "backup" / rel, archive / "retired" / rel
        if users_of(source, processes()):
            raise SystemExit(f"A process appeared during migration: {rel}")
        before = tree_manifest(source)
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, backup, symlinks=True)
        if tree_manifest(backup) != before or tree_manifest(source) != before:
            raise SystemExit(f"Backup verification/source stability failed: {rel}")
        write_json(archive / "hashes" / (rel.replace("/", "__") + ".json"), before)
        retired.parent.mkdir(parents=True, exist_ok=True)
        if rel == "benchmark/bu_bench_v1":
            stage = archive / "compat-staging"
            for shared, expected in compat_hashes.items():
                relative = Path(shared).relative_to(Path(rel))
                link = stage / relative
                target = archive / "backup" / shared
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(target)
                if digest(link) != expected:
                    raise SystemExit(f"Shared OD/OMW verification source changed: {shared}")
                receipt["compatibility"][shared] = {"sha256": expected, "target": str(target)}
            exchange_directories(source, stage)
            stage.rename(retired)
        else:
            source.rename(retired)
        receipt["moved"].append(rel)
        write_json(archive / "receipt.json", receipt)
    for rel, expected in compat_hashes.items():
        if digest(root / rel) != expected:
            raise SystemExit(f"Shared OD/OMW verification source changed after retirement: {rel}")
    defaults_file = root / "benchmark/defaults.json"
    current = json.loads(defaults_file.read_text()) if defaults_file.exists() else {}
    write_json(defaults_file, bu_defaults(current, str(args.new_entry)))
    wrapper = '''"""Daily BU entry: only BU-filter. Legacy BU data is retired."""\nimport argparse, os, sys\nfrom pathlib import Path\np=argparse.ArgumentParser(add_help=False);p.add_argument('--benchmark',default='bu-filter')\na,rest=p.parse_known_args()\nif a.benchmark.lower()!='bu-filter':raise SystemExit('Legacy BU benchmarks are retired. Use BU-filter (87 tasks).')\nroot=Path(__file__).resolve().parents[1]\nentry=root/%r\npython=root/'.venvs/bu-filter-control/bin/python'\nif not python.is_file():raise SystemExit('BU-filter control environment is missing. Run its setup instructions.')\nos.execv(str(python),[str(python),str(entry),*rest])\n''' % str(args.new_entry)
    (root / "benchmark/load_bu.py").write_text(wrapper)
    receipt["complete"] = True
    write_json(archive / "receipt.json", receipt)
    print(json.dumps({"archive": str(archive), "receipt": str(archive / "receipt.json"), "retired_count": len(receipt["moved"]), "daily_bu_entry": str(entry)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
