"""Execute one public BU-filter task using the selected product's native API.

Observation recording is adapted from the existing 5090 worker_impl. This
module does not load dataset answers. It does not provide an OS security sandbox.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import sys
import time
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch


POLICY = (
    "Evaluation on public websites. If a site shows an access denial, CAPTCHA, region or login restriction, record the blocker. "
    "Stop requests to that blocked source. Use independent permitted public sources or continue independent requirements. "
    "Do not change identity or routes to regain access: do not hide browser automation flags, spoof a blocked browser identity, "
    "clear or modify challenge cookies, override DNS/IP/Host, probe origins or virtual hosts, or open another browser. "
    "Do not use third-party page-fetch proxies, translation proxies, CAPTCHA solvers or private endpoints to retrieve blocked content. "
    "An independent index or archive that already contains public material is a source; a service that fetches a blocked page on your behalf is a proxy. "
    "Use only this task workspace for local data, its attached browser, and authorized public content. Never access benchmark/evaluator materials, other tasks or system credentials. "
    "Do not contact people, send email, sign third parties up, place real orders or pay; stop before final submission and describe the observed state."
)


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def public_task(path):
    task = read(path)
    if set(task) != {"id", "instruction", "start_url"}:
        raise ValueError("Actor task must contain exactly id, instruction and start_url")
    if not isinstance(task["id"], str) or not task["id"]:
        raise ValueError("Task id is missing")
    if not isinstance(task["instruction"], str) or not task["instruction"].strip():
        raise ValueError("Task instruction is missing")
    if task["start_url"] is not None and not isinstance(task["start_url"], str):
        raise ValueError("start_url must be text or null")
    return task


def model_config(settings, credentials):
    """Override only the frozen evaluation parameters, preserving product defaults."""
    agent = settings["agent"]
    if agent["model"] != "deepseek-v4.1-flash" or agent["reasoning_effort"] != "high":
        raise ValueError("BU-filter requires deepseek-v4.1-flash high")
    if agent["mode"] != "ultrafast" or agent["max_steps"] != 300 or agent["timeout_seconds"] != 3600:
        raise ValueError("BU-filter requires ultrafast, 300 turns and 3600 seconds")
    result = {k: credentials[k] for k in ("api_key", "base_url")}
    result.update({k: agent[k] for k in ("model", "reasoning_effort", "mode", "max_steps", "timeout_seconds")})
    result["max_context_chars"] = agent.get("max_context_chars")
    return result


def configure_source(settings):
    project = Path(settings["product_source"]).resolve()
    source = project / "src"
    package = source / "lexmount_browser_agent"
    if not (package / "__init__.py").is_file():
        raise ValueError("product_source must contain src/lexmount_browser_agent")
    sys.path.insert(0, str(source))
    engine = package / "engine"
    if (engine / "browser_use/__init__.py").is_file():
        sys.path.insert(0, str(engine))
    return project


def runtime_provenance(project):
    import browser_use
    import lexmount_browser_agent

    package = Path(lexmount_browser_agent.__file__).resolve().parent
    if package != project / "src/lexmount_browser_agent":
        raise RuntimeError("Imported product does not match product_source")
    files = {
        str(p.relative_to(project)): digest(p)
        for p in sorted((project / "src").rglob("*.py"))
        if "__pycache__" not in p.parts
    }
    for name in ("pyproject.toml", "uv.lock"):
        if (project / name).is_file():
            files[name] = digest(project / name)
    engine = Path(browser_use.__file__).resolve().parent
    return {
        "python_executable": sys.executable,
        "product_source": str(project),
        "launcher_source": str(package),
        "engine_source": str(engine),
        "engine_version": version("browser-use"),
        "product_files_sha256": files,
        "engine_files_sha256": {
            str(p.relative_to(engine)): digest(p)
            for p in sorted(engine.rglob("*.py"))
            if "__pycache__" not in p.parts
        },
        "package_versions": {
            name: version(name)
            for name in ("browser-use", "browser-harness", "pydantic-ai-slim", "pydantic", "openai", "httpx", "cdp-use")
        },
        "engine_core_sha256": {
            name: digest(engine / name)
            for name in ("agent/loop.py", "agent/service.py", "repl/worker.py", "agent/prompt.py")
        },
    }


def validate_runtime(actual, expected):
    """Reject environment drift from the controller's frozen preflight proof."""
    if not isinstance(expected, dict) or set(expected) != {"version", "files_sha256", "package_versions"}:
        raise ValueError("Normal evaluation requires expected_engine from the frozen preflight")
    pairs = {
        "version": actual["engine_version"],
        "files_sha256": actual["engine_files_sha256"],
        "package_versions": actual["package_versions"],
    }
    for name, value in pairs.items():
        if expected[name] != value:
            raise RuntimeError("Engine environment changed since preflight: " + name)


class Observer:
    """Existing after_tool screenshot/receipt capture, without evaluator imports."""

    def __init__(self, browser, folder, daemon_request):
        self.browser, self.folder, self.daemon_request = browser, Path(folder), daemon_request
        self.frames = []
        write(self.folder / "frames.json", self.frames)

    def capture(self, number):
        started = time.monotonic()
        frame = {"step_num": number, "screenshot_file": None}
        try:
            if not self.browser.name:
                raise RuntimeError("No active browser daemon")

            def cdp(method, **params):
                reply = self.daemon_request(
                    self.browser.name, {"method": method, "params": params},
                    timeout=20 if method == "Page.captureScreenshot" else 5,
                )
                if "error" in reply:
                    raise RuntimeError(str(reply["error"]))
                return reply.get("result", {})

            before = cdp("Page.getFrameTree")["frameTree"]["frame"]
            shot = cdp("Page.captureScreenshot", format="png", captureBeyondViewport=False)
            after = cdp("Page.getFrameTree")["frameTree"]["frame"]
            if any(before.get(k) != after.get(k) for k in ("id", "url", "loaderId")):
                raise RuntimeError("Document changed during screenshot capture")
            path = self.folder / "screenshots" / f"{number:04d}.png"
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(base64.b64decode(shot["data"], validate=True))
            frame.update(
                screenshot_file=str(path.relative_to(self.folder)), url=after.get("url"),
                sha256=digest(path), captured_at=time.time(),
                tabs=[{k: t.get(k) for k in ("targetId", "url", "title")}
                      for t in cdp("Target.getTargets").get("targetInfos", []) if t.get("type") == "page"],
            )
        except Exception as error:
            frame["capture_error"] = f"{type(error).__name__}: {error}"
        finally:
            frame["capture_seconds"] = time.monotonic() - started
        return frame

    async def after_tool(self, name, args, result):
        if name != "python":
            return
        started = time.monotonic()
        frame = await asyncio.to_thread(self.capture, len(self.frames) + 1)
        output_file = result.get("output_file")
        output = Path(output_file).read_text(errors="replace") if output_file and Path(output_file).is_file() else result.get("output", "")
        frame.update(
            action="python " + args["code"],
            response=output + "\nObserved tabs: " + json.dumps(frame.get("tabs", [])),
            tool_error=result.get("error"), native_stats=result.get("stats"),
        )
        frame["recording_seconds"] = time.monotonic() - started
        self.frames.append(frame)
        write(self.folder / "frames.json", self.frames)
        (self.folder / "steps.jsonl").write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in self.frames))


def offline_model():
    """Scripted responses for a real-browser integration check; never contacts an API."""
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    html = '<title>BU-filter offline probe</title><input id="name"><button onclick="document.getElementById(\'receipt\').textContent=\'Saved \'+document.getElementById(\'name\').value">Save</button><p id="receipt">Waiting</p>'
    from urllib.parse import quote
    url = "data:text/html," + quote(html)
    code = (
        f"goto_url({url!r})\nwait_for_element('#name')\n"
        "observed = js(\"document.getElementById('name').value='fixture'; document.querySelector('button').click(); return document.getElementById('receipt').textContent\")\n"
        "assert observed == 'Saved fixture', observed\nprint(observed)"
    )
    calls = 0

    def respond(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            return ModelResponse(parts=[ToolCallPart("python", {"code": code})])
        if "Saved fixture" not in str(messages):
            raise AssertionError("Real browser result was not returned to the scripted model")
        return ModelResponse(parts=[ToolCallPart("finish", {"result": "Offline browser submission verified.", "success": True})])

    return FunctionModel(respond)


async def run(folder, settings, *, offline_smoke=False):
    folder = Path(folder).resolve()
    if (folder / "execution.json").exists() or (folder / "agent").exists():
        raise FileExistsError("Preserve the existing Actor execution; choose a new run directory")
    task = public_task(folder / "task.json")
    if not offline_smoke:
        from dataset import actor_task
        task = actor_task(task)
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
    os.environ.setdefault("BH_TELEMETRY", "0")
    project = configure_source(settings)
    runtime = runtime_provenance(project)
    if not offline_smoke:
        validate_runtime(runtime, settings.get("expected_engine"))
    write(folder / "runtime-provenance.json", runtime)
    if offline_smoke:
        credentials = {"api_key": "offline-fixture-key", "base_url": "http://127.0.0.1:1/v1"}
    elif settings["credentials_file"] == "-":
        credentials = json.load(sys.stdin)
    else:
        credentials = read(settings["credentials_file"])
    config_values = model_config(settings, credentials)
    from browser_use import Browser
    from browser_use.agent import loop, service
    from browser_use.browser.browser import _daemon_request
    from lexmount_browser_agent import AgentConfig, run_task
    from lexmount_browser_agent.records import Records
    from vendor.billing import record_billing
    from vendor.viewport import FixedViewport

    config = AgentConfig(**config_values)
    browser = Browser("chromium", headless=True, executable_path=settings["browser_executable"])
    observer = Observer(browser, folder, _daemon_request)
    original_session, original_start, original_response = service.Session, Browser.start, Records.response
    viewport = None
    if settings.get("viewport", {"width": 1440, "height": 900}) != {"width": 1440, "height": 900}:
        raise ValueError("The retained evaluation viewport is 1440 by 900")

    def observed_session(*args, **kwargs):
        return original_session(*args, **kwargs, after_tool=observer.after_tool)

    async def start_with_viewport(current_browser):
        nonlocal viewport
        result = await original_start(current_browser)
        if viewport is None:
            viewport = FixedViewport(current_browser, folder / "viewport.json")
        await viewport.start()
        return result

    async def billing_response(current_records, response):
        await original_response(current_records, response)
        receipt = response.request.extensions.get("lexmount_request")
        if receipt is not None:
            record_billing(current_records.root, receipt[0], response)

    instruction = task["instruction"]
    if task["start_url"]:
        instruction += "\nStarting page: " + task["start_url"]
    try:
        with patch.object(service, "Session", observed_session), patch.object(Browser, "start", start_with_viewport), \
                patch.object(loop, "SYSTEM_PROMPT", loop.SYSTEM_PROMPT + "\n\n" + POLICY), \
                patch.object(Records, "response", billing_response):
            extra = {"model": offline_model()} if offline_smoke else {}
            result = await run_task(instruction, config, folder / "agent", browser=browser, **extra)
        result["independent_capture_seconds"] = sum(f["capture_seconds"] for f in observer.frames)
        result["solver_wall_excluding_capture_seconds"] = max(0, result["wall_seconds"] - result["independent_capture_seconds"])
        result["capture_timing_note"] = "Wall time includes capture; subtraction is only a timing breakdown."
        text = result["text"]
        steps = observer.frames + ([{"step_num": len(observer.frames) + 1, "action": "final_response", "response": text, "final": True}] if text else [])
        (folder / "steps.jsonl").write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in steps))
        (folder / "final_response.txt").write_text(text)
        write(folder / "execution.json", result)
        write(folder / "recording.json", {
            "step_unit": "native_python_cell", "cells": len(observer.frames),
            "screenshots": sum(bool(f.get("screenshot_file")) for f in observer.frames),
            "capture_errors": [f["capture_error"] for f in observer.frames if f.get("capture_error")],
            "budget_unit": "model_turns", "actor_task_fields": ["id", "instruction", "start_url"],
            "observer_loads_judge_dataset": False, "os_sandbox_provided": False,
            "offline_smoke": offline_smoke,
            "independent_capture_seconds": result["independent_capture_seconds"],
            "note": "One Python cell can execute multiple browser actions; Actor input contains no reference answer.",
        })
        return result
    finally:
        try:
            if viewport and viewport.client:
                await viewport.close()
        except Exception as error:
            print("viewport cleanup failed", type(error).__name__, flush=True)
        await browser.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", required=True, type=Path)
    parser.add_argument("--settings", required=True, type=Path)
    parser.add_argument("--offline-smoke", action="store_true", help="Real Chrome with scripted model responses; zero API calls")
    args = parser.parse_args()
    if not args.folder.is_absolute() or not args.settings.is_absolute():
        parser.error("folder and settings must be absolute paths")
    asyncio.run(run(args.folder, read(args.settings), offline_smoke=args.offline_smoke))


if __name__ == "__main__":
    main()
