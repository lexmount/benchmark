"""Run the unchanged product inside an OSWorld guest; no evaluator data is read."""
from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def engine_metadata() -> dict:
    import browser_use
    import lexmount_browser_agent

    packages = {}
    for name in ("lexmount-browser-agent", "browser-use", "browser-harness", "pydantic-ai-slim"):
        packages[name] = importlib.metadata.version(name)
    if packages["browser-use"] != "1.0.4":
        raise RuntimeError("The frozen product requires browser-use==1.0.4")
    paths = {
        "product_runner": Path(lexmount_browser_agent.__file__).parent / "runner.py",
        "product_config": Path(lexmount_browser_agent.__file__).parent / "config.py",
        "engine_service": Path(browser_use.__file__).parent / "agent/service.py",
        "engine_repl_worker": Path(browser_use.__file__).parent / "repl/worker.py",
        "engine_repl_session": Path(browser_use.__file__).parent / "repl/session.py",
    }
    return {
        "python": sys.version,
        "executable": sys.executable,
        "packages": packages,
        "sources": {
            name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for name, path in paths.items()
        },
        "uid": os.getuid(),
        "home": str(Path.home()),
        "cwd": str(Path.cwd()),
    }


def redact(value, secrets: list[str]):
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, dict):
        return {key: redact(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    return value


async def probe(job: dict, root: Path) -> dict:
    from browser_use import Browser

    metadata = engine_metadata()
    probe_file = root / "file-probe.txt"
    probe_file.write_text("OSWorld guest filesystem probe\n")
    if probe_file.read_text() != "OSWorld guest filesystem probe\n":
        raise RuntimeError("Guest file round-trip failed")
    probe_file.unlink()
    browser = Browser(cdp_url=job["cdp_url"])
    try:
        await browser.start()
        metadata["browser_attached"] = True
    finally:
        # An external CDP Browser.stop() detaches its daemon, not the guest Chrome.
        await browser.stop()
    return {"status": "passed", "file_roundtrip": True, "metadata": metadata}


async def actor(job: dict, root: Path) -> dict:
    from lexmount_browser_agent.config import AgentConfig
    from lexmount_browser_agent.runner import run_task

    metadata = engine_metadata()
    environment_context = (
        "\n\nOSWorld task environment:\n"
        "You are running inside the task's Ubuntu virtual machine, sharing its files and original "
        "Chrome profile. Task inputs remain at their original paths. Save deliverables at the exact "
        "paths requested in the task; your product workspace is only a separate scratch directory.\n"
        f"The initial desktop screenshot is available at {root / 'initial.png'}.\n"
        "Keep all constraints in the original instruction, including any specified application, "
        "terminal or GUI operation. Python access does not waive those requirements. Use only "
        "task-visible inputs; do not seek evaluator code or reference answers. Do not reset the VM "
        "or stop its existing Chrome browser.\n"
    )
    instruction = job["instruction"]
    prompt = instruction + environment_context
    config = AgentConfig(**(job["actor_config"] | {"cdp_url": job["cdp_url"]}))
    result = await run_task(prompt, config, root / "actor-output")
    return {
        "schema_version": 1,
        "status": "finished",
        "instruction_sha256": hashlib.sha256(instruction.encode()).hexdigest(),
        "appended_environment_context": environment_context,
        "effective_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "metadata": metadata,
        "result": result,
    }


def main() -> int:
    job_path = Path(sys.argv[1]).resolve()
    job = json.loads(job_path.read_text())
    root = Path(job["guest_root"])
    secrets = [str(job.get("actor_config", {}).get(key, "")) for key in ("api_key", "model_proxy")]
    # Bootstrap already holds the configuration in memory; do not leave model credentials
    # in the filesystem while the model is allowed to inspect task files.
    job_path.unlink(missing_ok=True)
    destination = root / ("probe-result.json" if job["kind"] == "probe" else "actor-result.json")
    started = time.time()
    try:
        result = asyncio.run(probe(job, root) if job["kind"] == "probe" else actor(job, root))
        result["elapsed_seconds"] = time.time() - started
        atomic_json(destination, redact(result, secrets))
        return 0
    except BaseException as error:
        atomic_json(destination, redact({
            "schema_version": 1,
            "status": "error",
            "error_type": type(error).__name__,
            "error": str(error),
            "elapsed_seconds": time.time() - started,
        }, secrets))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
