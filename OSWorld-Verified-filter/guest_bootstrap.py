"""Install the frozen product in a private guest directory and invoke its entrypoint."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tarfile
import time


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def unpack(archive: Path, root: Path) -> None:
    with tarfile.open(archive, "r:gz") as source:
        for member in source.getmembers():
            destination = (root / member.name).resolve()
            if not destination.is_relative_to(root.resolve()) or member.issym() or member.islnk():
                raise RuntimeError("Unsafe runtime bundle member")
            if not (member.isfile() or member.isdir()):
                raise RuntimeError("Unsupported runtime bundle member")
        source.extractall(root)


def run_child(command: list[str], *, root: Path, environment: dict, timeout: float, log_name: str) -> int:
    with (root / log_name).open("ab") as log:
        process = subprocess.Popen(command, cwd=root, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            return process.wait(timeout=timeout)
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


def archive_public_output(root: Path, secrets: list[str]) -> Path:
    # Explicit allowlist: job.json, uv cache, Python installation and product source
    # never enter the host evidence archive.
    names = ("actor-output", "actor-result.json", "probe-result.json", "bootstrap.log",
             "install.log", "actor.log", "initial.png", "cdp.json")
    for name in names:
        path = root / name
        candidates = path.rglob("*") if path.is_dir() else [path]
        for item in candidates:
            if not item.is_file() or item.is_symlink():
                continue
            if item.suffix.lower() not in (".json", ".jsonl", ".log", ".txt", ".md", ".xml", ".html"):
                continue
            raw = item.read_bytes()
            clean = raw
            for secret in secrets:
                if secret:
                    clean = clean.replace(secret.encode(), b"[REDACTED]")
            if clean != raw:
                item.write_bytes(clean)
    archive = root / "actor-output.tar.gz"
    with tarfile.open(archive, "w:gz", dereference=False) as target:
        for name in names:
            path = root / name
            if path.exists() and not path.is_symlink():
                target.add(path, arcname=name, recursive=True,
                           filter=lambda member: None if member.issym() or member.islnk() else member)
    return archive


def main() -> int:
    os.umask(0o077)
    job_path = Path(sys.argv[1]).resolve()
    job = json.loads(job_path.read_text())
    root = Path(job["guest_root"]).resolve()
    state_path = root / "bootstrap-state.json"
    state = {"schema_version": 1, "kind": job["kind"], "pid": os.getpid(),
             "started_at_epoch": time.time(), "stage": "starting"}
    secrets = [str(job.get("actor_config", {}).get(key, "")) for key in ("api_key", "model_proxy")]
    exit_code = 1
    try:
        atomic_json(state_path, state)
        bundle = root / "runtime-bundle.tar.gz"
        if digest(bundle) != job["bundle_sha256"]:
            raise RuntimeError("Uploaded runtime bundle digest mismatch")
        unpack(bundle, root)
        uv = root / "uv"
        if digest(uv) != job["uv_binary_sha256"]:
            raise RuntimeError("Uploaded uv binary digest mismatch")
        uv.chmod(0o700)
        environment = os.environ.copy()
        environment.update({"UV_CACHE_DIR": str(root / "uv-cache"),
                            "UV_PYTHON_INSTALL_DIR": str(root / "python"),
                            "UV_NO_PROGRESS": "1", "UV_LINK_MODE": "copy",
                            "ANONYMIZED_TELEMETRY": "false", "PYTHONUNBUFFERED": "1"})
        # Credentials are passed only in the private job file, never to uv or argv.
        for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"):
            environment.pop(key, None)
        state.update(stage="installing", phase="install", phase_started_at_epoch=time.time())
        atomic_json(state_path, state)
        returncode = run_child([str(uv), "sync", "--frozen", "--no-dev", "--python",
                                job["guest_python"], "--project", str(root / "product")],
                               root=root, environment=environment,
                               timeout=job["bootstrap_timeout_seconds"], log_name="install.log")
        if returncode:
            raise RuntimeError(f"uv sync failed with exit code {returncode}; see install.log")
        state.update(stage="running", phase=job["kind"], phase_started_at_epoch=time.time())
        atomic_json(state_path, state)
        command = [str(root / "product/.venv/bin/python"), str(root / "guest_actor.py"), str(job_path)]
        timeout = (300 if job["kind"] == "probe" else
                   job["actor_config"]["timeout_seconds"] + job["actor_grace_seconds"])
        returncode = run_child(command, root=root, environment=environment,
                               timeout=timeout, log_name="actor.log")
        state.update(stage="finished" if returncode == 0 else "failed", returncode=returncode)
        exit_code = 0 if returncode == 0 else 1
    except BaseException as error:
        message = str(error)
        for secret in secrets:
            if secret:
                message = message.replace(secret, "[REDACTED]")
        state.update(stage="failed", error_type=type(error).__name__, error=message)
    finally:
        job_path.unlink(missing_ok=True)
        try:
            archive = archive_public_output(root, secrets)
            state["artifact_path"] = str(archive)
        except Exception as error:
            state["artifact_error"] = type(error).__name__ + ": " + str(error)
        state["finished_at_epoch"] = time.time()
        atomic_json(state_path, state)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
