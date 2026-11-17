#!/usr/bin/env python3
"""Build and verify portable managed Python + uv cache; never run an Agent or VM."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import signal
import shutil
import subprocess
import sys
import tarfile
import time
import uuid


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def checked(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def output(command: list[str], *, env: dict | None = None, cwd: Path | None = None) -> str:
    return subprocess.check_output(command, env=env, cwd=cwd, text=True).strip()


def extract_checked(stream: tarfile.TarFile, target: Path, *, roots: set[str] | None = None) -> int:
    members = stream.getmembers()
    for member in members:
        checked(member.isfile() or member.isdir(), "Archive contains a link or special file")
        path = Path(member.name)
        checked(not path.is_absolute() and ".." not in path.parts, "Unsafe archive member")
        checked((target / path).resolve().is_relative_to(target.resolve()), "Archive escapes its target")
        if roots is not None:
            checked(bool(path.parts) and path.parts[0] in roots, "Unexpected asset archive root")
    # The archive is inspected above, including symlinks, before extraction.
    stream.extractall(target)
    return len(members)


def archive_product(source: Path, commit: str, target: Path) -> None:
    target.mkdir()
    raw = subprocess.check_output([
        "git", "-C", str(source), "archive", commit, "src", "pyproject.toml", "uv.lock",
    ])
    with tarfile.open(fileobj=io.BytesIO(raw)) as stream:
        extract_checked(stream, target)


def run_logged(command: list[str], *, env: dict, cwd: Path, log: Path) -> float:
    started = time.monotonic()
    with log.open("xb") as destination:
        process = subprocess.Popen(command, env=env, cwd=cwd, stdout=destination,
                                   stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                   start_new_session=True)
        try:
            returncode = process.wait(timeout=3600)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            raise
    checked(returncode == 0, f"Command failed with exit {returncode}; inspect {log}")
    return time.monotonic() - started


IMPORT_PROBE = r"""
import importlib.metadata,json,ssl,sys
import browser_use,lexmount_browser_agent
from browser_use import Agent,Browser
from lexmount_browser_agent.config import AgentConfig
from lexmount_browser_agent.runner import run_task
print(json.dumps({'packages':{d.metadata['Name']:d.version for d in importlib.metadata.distributions()},
                 'python':sys.version,'base_prefix':sys.base_prefix,'executable':sys.executable,
                 'product_module':lexmount_browser_agent.__file__,
                 'engine_module':browser_use.__file__,'ssl':ssl.OPENSSL_VERSION}))
"""


def import_probe(project: Path, python_root: Path, env: dict) -> dict:
    data = json.loads(output([str(project / ".venv/bin/python"), "-c", IMPORT_PROBE], env=env, cwd=project))
    checked(Path(data["base_prefix"]).resolve().is_relative_to(python_root.resolve()),
            "The environment used a Python outside the staged managed installation")
    checked(Path(data["product_module"]).resolve().is_relative_to((project / "src").resolve()),
            "The editable product import points outside its fresh source directory")
    return data


def environment(cache: Path, python_root: Path, *, offline: bool) -> dict:
    value = os.environ.copy()
    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"):
        value.pop(key, None)
    value.update({"UV_CACHE_DIR": str(cache), "UV_PYTHON_INSTALL_DIR": str(python_root),
                  "UV_LINK_MODE": "copy", "UV_PYTHON_PREFERENCE": "only-managed",
                  "UV_PYTHON_DOWNLOADS": "never", "UV_NO_PROGRESS": "1",
                  "ANONYMIZED_TELEMETRY": "false"})
    if offline:
        value["UV_OFFLINE"] = "1"
    else:
        value.pop("UV_OFFLINE", None)
    return value


def build(args) -> dict:
    checked(platform.system() == "Linux" and platform.machine() in ("x86_64", "AMD64"),
            "Build these assets on x86_64 Linux, matching the OSWorld guest")
    source = args.agent_source.resolve()
    work = args.work_dir.resolve()
    uv = args.uv_binary.resolve()
    python_source = args.python_installation.resolve()
    checked(not work.is_relative_to(source) and not source.is_relative_to(work),
            "Keep the asset work directory separate from the product checkout")
    checked(not work.is_relative_to(python_source) and not python_source.is_relative_to(work),
            "Keep the asset work directory separate from the managed Python source")
    checked(uv.is_file() and uv.read_bytes()[:4] == b"\x7fELF", "Pass the actual Linux uv ELF")
    uv_version = output([str(uv), "--version"])
    checked(uv_version.startswith("uv "), "The supplied executable is not uv")
    commit = output(["git", "-C", str(source), "rev-parse", "HEAD"])
    checked(not output(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"]),
            "The product has tracked modifications")
    checked((source / "uv.lock").is_file(), "The product lockfile is missing")
    expected_python = "Python " + args.python_version
    checked(python_source.name.startswith("cpython-" + args.python_version + "-"),
            "Pass the named uv managed CPython installation directory")
    original_binary = python_source / "bin" / ("python" + ".".join(args.python_version.split(".")[:2]))
    checked(original_binary.is_file() and output([str(original_binary), "--version"]) == expected_python,
            "The managed Python source does not match the requested exact version")
    work.mkdir(parents=True, exist_ok=True)
    lock = work / "build-runtime-assets.lock"
    with lock.open("x") as stream:
        json.dump({"pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat()}, stream)
    try:
        final_archive, pending = work / "runtime-assets.tar.gz", work / "runtime-assets.pending.tar.gz"
        record_path = work / "runtime-assets.json"
        checked(not any(p.exists() for p in (final_archive, pending, record_path)),
                "Asset output already exists; preserve it and use a new work directory")
        payload = work / "payload"
        python_root, cache = payload / "python", payload / "uv-cache"
        python_root.mkdir(parents=True, exist_ok=True)
        cache.mkdir(parents=True, exist_ok=True)
        staged = python_root / python_source.name
        copied_binary = staged / "bin" / original_binary.name
        if not staged.exists():
            shutil.copytree(python_source, staged, symlinks=True)
        checked(copied_binary.is_file() and sha256(copied_binary) == sha256(original_binary),
                "Previously staged Python differs from its source")
        checked(output([str(copied_binary), "--version"]) == expected_python,
                "Copied managed Python does not execute at its new path")
        warm_project = work / ("warm-product-" + uuid.uuid4().hex[:12])
        archive_product(source, commit, warm_project)
        warm_env = environment(cache, python_root, offline=False)
        warm_env["UV_PROJECT_ENVIRONMENT"] = str(warm_project / ".venv")
        warm_command = [str(uv), "sync", "--frozen", "--no-dev", "--python", args.python_version,
                        "--project", str(warm_project)]
        warm_log = work / ("runtime-assets-warm-" + uuid.uuid4().hex[:8] + ".log")
        warm_seconds = run_logged(warm_command, env=warm_env, cwd=warm_project, log=warm_log)
        warm_import = import_probe(warm_project, python_root, warm_env)
        checked(not list(payload.rglob("pyvenv.cfg")), "A virtual environment entered the portable payload")
        internal_links = 0
        for directory, dirs, files in os.walk(payload, followlinks=False):
            for name in dirs + files:
                path = Path(directory) / name
                if path.is_symlink():
                    checked(path.resolve(strict=True).is_relative_to(payload.resolve()),
                            f"Asset symlink escapes the payload: {path}")
                    internal_links += 1
        pack_started = time.monotonic()
        with tarfile.open(pending, "w:gz", dereference=True, compresslevel=3) as stream:
            for name in ("python", "uv-cache"):
                stream.add(payload / name, arcname=name)
        pack_seconds = time.monotonic() - pack_started
        test = work / ("relocation-test-" + uuid.uuid4().hex[:12])
        test.mkdir()
        with tarfile.open(pending, "r:gz") as stream:
            members = extract_checked(stream, test, roots={"python", "uv-cache"})
        relocated_project = test / "product"
        archive_product(source, commit, relocated_project)
        offline_env = environment(test / "uv-cache", test / "python", offline=True)
        offline_env["UV_PROJECT_ENVIRONMENT"] = str(relocated_project / ".venv")
        offline_command = [str(uv), "sync", "--frozen", "--no-dev", "--python", args.python_version,
                           "--offline", "--project", str(relocated_project)]
        offline_log = work / ("runtime-assets-offline-" + uuid.uuid4().hex[:8] + ".log")
        offline_seconds = run_logged(offline_command, env=offline_env, cwd=relocated_project, log=offline_log)
        relocated_import = import_probe(relocated_project, test / "python", offline_env)
        checked(warm_import["packages"] == relocated_import["packages"], "Offline package versions changed")
        checked_packages = subprocess.run(
            [str(uv), "pip", "check", "--python", str(relocated_project / ".venv/bin/python")],
            env=offline_env, cwd=relocated_project, text=True, capture_output=True, check=True)
        pip_check = checked_packages.stdout + checked_packages.stderr
        checked(not output(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"]),
                "Product tracked files changed while building the assets")
        pending.rename(final_archive)
        record = {"schema_version": 1, "status": "passed", "created_at": datetime.now(timezone.utc).isoformat(),
                  "scope": "Host-only asset build and relocated offline sync/import; no VM or model calls",
                  "product_commit": commit, "agent_source": str(source),
                  "uv_lock_sha256": sha256(source / "uv.lock"),
                  "pyproject_sha256": sha256(source / "pyproject.toml"),
                  "python_version": args.python_version, "python_installation_source": str(python_source),
                  "python_source_binary_sha256": sha256(original_binary),
                  "python_staged_binary_sha256": sha256(copied_binary),
                  "uv_binary": str(uv), "uv_version": uv_version, "uv_binary_sha256": sha256(uv),
                  "archive_path": str(final_archive), "archive_sha256": sha256(final_archive),
                  "archive_bytes": final_archive.stat().st_size, "archive_top_level": ["python", "uv-cache"],
                  "archive_links": 0, "tar_member_count": members,
                  "internal_symlinks_dereferenced": internal_links,
                  "warm_command": warm_command, "warm_seconds": warm_seconds, "warm_log": str(warm_log),
                  "pack_seconds": pack_seconds, "offline_command": offline_command,
                  "offline_sync_seconds": offline_seconds, "offline_log": str(offline_log),
                  "offline_environment": {key: offline_env[key] for key in
                      ("UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "UV_LINK_MODE", "UV_PYTHON_PREFERENCE",
                       "UV_PYTHON_DOWNLOADS", "UV_OFFLINE")},
                  "offline_import": relocated_import, "pip_check_output": pip_check,
                  "package_count": len(relocated_import["packages"]),
                  "warm_and_relocated_packages_equal": True, "product_tracked_clean": True,
                  "vm_started": False, "model_calls": 0,
                  "limits": ["The runtime must separately verify this archive inside its original guest.",
                             "Rebuild after changing the lockfile, Python, platform or uv version."]}
        with record_path.open("x") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        return record
    finally:
        lock.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-source", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--uv-binary", type=Path, required=True)
    parser.add_argument("--python-installation", type=Path, required=True)
    parser.add_argument("--python-version", default="3.12.13")
    try:
        result = build(parser.parse_args())
        print(json.dumps({key: value for key, value in result.items() if key != "offline_import"},
                         ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
