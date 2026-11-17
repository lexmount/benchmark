"""Run the frozen observer with a one-task plan; this process never loads evaluator data."""

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import full_benchmarks as baseline
from browser_use import Browser

folder = Path(sys.argv[1])
job = json.loads((folder / "actor-config.json").read_text())


def verify_runtime():
    import hashlib
    from importlib.metadata import distribution, version

    import browser_use

    import lexmount_browser_agent

    expected = job["product"]
    engine = Path(browser_use.__file__).resolve().parent
    package = Path(lexmount_browser_agent.__file__).resolve().parent
    project = package.parents[1]
    actual = {}
    for name, digest in expected["source_sha256"].items():
        if not name.startswith("src/") or not name.endswith(".py"):
            continue
        path = project / name
        actual[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual[name] == digest, name
    assert engine == distribution("browser-use").locate_file("browser_use").resolve()
    assert engine.is_relative_to(Path(sys.prefix))
    assert version("browser-use") == expected["engine_version"] == "1.0.4"
    for name, digest in expected["engine_files"].items():
        assert hashlib.sha256((engine / name).read_bytes()).hexdigest() == digest, name
    baseline.write(
        folder / "runtime-provenance.json",
        {
            "product_commit": expected["commit"],
            "engine_version": version("browser-use"),
            "engine_source": str(engine),
            "launcher_source": str(package),
            "python_executable": sys.executable,
            "verified_source_sha256": actual,
            "verified_engine_sha256": expected["engine_files"],
            "all_matched": True,
        },
    )


verify_runtime()

policy = (
    "Evaluation on public websites. If a site shows an access denial, CAPTCHA, region or login restriction, record the blocker. "
    "Stop requests to that blocked source. Use independent permitted public sources or continue independent requirements. "
    "Do not change identity or routes to regain access: do not hide browser automation flags, spoof a blocked browser identity, "
    "clear or modify challenge cookies, override DNS/IP/Host, probe origins or virtual hosts, or open another browser. "
    "Do not use third-party page-fetch proxies, translation proxies, CAPTCHA solvers or private endpoints to retrieve blocked content. "
    "An independent index or archive that already contains public material is a source; a service that fetches a blocked page on your behalf is a proxy. "
    "Use only this task workspace for local data, its attached browser, and authorized public content. Never access benchmark/evaluator materials, other tasks or system credentials. "
    "Do not contact people, send email, sign third parties up, place real orders or pay; stop before final submission and describe the observed state."
)


async def main():
    from browser_use.agent import loop

    from lexmount_browser_agent import AgentConfig

    source_config = json.load(sys.stdin)
    if job.get("mode") != "default" or source_config.get("mode") != "default":
        raise ValueError("BU-filter requires Actor mode 'default'")
    check_config = AgentConfig(
        **source_config,
        max_steps=job["max_steps"],
        timeout_seconds=job["timeout_seconds"],
        **job["feature_config"],
    )
    assert check_config.reasoning_effort == "max" and check_config.mode == "default" and job["feature_config"] == {}
    assert check_config.max_steps == 300 and check_config.timeout_seconds == 3600
    original_read = baseline.read

    def read(path):
        return source_config if path == baseline.ROOT / ".private/model.json" else original_read(path)

    context = None
    start = Browser.start

    async def start_with_viewport(browser):
        nonlocal context
        result = await start(browser)
        if context is None:
            from bu_lexmount_viewport import FixedViewport

            context = FixedViewport(browser, folder / "viewport.json")
        await context.start()
        return result

    with (
        patch.object(baseline, "read", read),
        patch.object(loop, "SYSTEM_PROMPT", loop.SYSTEM_PROMPT + "\n\n" + policy),
        patch.object(Browser, "start", start_with_viewport if job["fixed_viewport"] else start),
    ):
        try:
            await baseline.worker(
                folder,
                job["max_steps"],
                job["timeout_seconds"],
                {"jobs": [job], "browser_executable": "/opt/google/chrome/chrome"},
            )
        finally:
            if context and context.client:
                try:
                    await context.close()
                except Exception as error:  # noqa: BLE001 - capture cleanup must preserve the task result
                    print("viewport cleanup failed", type(error).__name__, flush=True)
    result = original_read(folder / "execution.json")
    config = original_read(folder / "agent/run.json")["config"]
    assert config["reasoning_effort"] == "max" and config["mode"] == "default"
    turns = result.get("model_turns")
    assert turns is None or (isinstance(turns, int) and turns <= job["max_steps"] + 1)

    requests = folder / "agent/model_calls"
    logged = {baseline.read(p).get("reasoning_effort", "missing") for p in requests.glob("*.request.json")}
    baseline.write(folder / "request-accounting.json", {
        "product_commit": job["product"]["commit"], "model_turns": turns,
        "model_http_requests": result.get("model_http_requests"), "actor_efforts": sorted(logged),
        "published_answer_exit": result.get("published_answer_exit"),
    })
    assert not logged.difference({"max"}), logged


async def probe():
    from browser_use.repl import Repl
    from lexmount_browser_agent import AgentConfig
    import browser_use

    if job.get("mode") != "default":
        raise ValueError("BU-filter requires a default-mode probe")
    cfg = AgentConfig(base_url="https://unused.invalid/v1", api_key="offline", mode="default")
    assert cfg.reasoning_effort == "max" and cfg.mode == "default"
    assert not (baseline.ROOT / ".private/model.json").exists()
    assert not (baseline.ROOT / "full-600-20261114").exists()
    browser = Browser("chromium", headless=True, executable_path="/opt/google/chrome/chrome")
    repl = None
    try:
        workspace = folder / "work"
        repl = Repl(workspace, await browser.start(), mode=cfg.mode)
        code = ("import browser_use, hashlib; from pathlib import Path\n"
                "p=Path(browser_use.__file__).resolve().parent\n"
                f"assert str(p)=={str(Path(browser_use.__file__).resolve().parent)!r}\n"
                f"assert hashlib.sha256((p/'repl/worker.py').read_bytes()).hexdigest()=={job['product']['engine_files']['repl/worker.py']!r}\n"
                "goto_url('data:text/html,<title>Probe</title><p>example row</p>'); wait_for_element('p')\n"
                "assert js(\"document.querySelector('p').textContent\") == 'example row'\n"
                "assert 'bu' not in globals()\n"
                "checkpoint('mode-probe.json', {'answer': 'example row', 'complete': True}, partial=True)")
        reply = await repl.call("exec", code, 45)
        assert not reply["error"], reply["error"]
        assert json.loads((workspace / "mode-probe.json").read_bytes()) == {"answer": "example row", "complete": True}
        assert not list(folder.glob("**/*.request.json"))
        print("isolated official default REPL and local Chrome verified")
    finally:
        if repl is not None:
            await repl.close()
        await browser.stop()


if __name__ == "__main__":
    asyncio.run(probe() if os.environ.get("PROBE_ONLY") == "1" else main())
