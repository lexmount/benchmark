"""Native browser-use assembly plus the upstream ExecutionResult adapter contract."""

import asyncio
import base64
import importlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from frameworks import ExecutionResult
from lexmount_v1_1.judging import estimate_cost
from lexmount_v1_1.storage import redact, write_new


@dataclass
class MeasuredExecutionResult(ExecutionResult):
    """Optional measurements; absent fields stay unknown rather than becoming zero."""

    metrics: dict = field(default_factory=dict)
    evidence_seconds: float = 0.0


class MeteredTransport(httpx.AsyncBaseTransport):
    def __init__(self, folder, rates):
        self.transport = httpx.AsyncHTTPTransport()
        self.folder = Path(folder)
        self.rates = rates
        self.calls = []

    async def handle_async_request(self, request):
        start = time.monotonic()
        number = len(self.calls) + 1
        call = {"number": number, "started": start}
        self.calls.append(call)
        try:
            # Request bodies and responses are private evidence, never committed.
            body = await request.aread()
            call["request"] = json.loads(redact(body.decode()))
            response = await self.transport.handle_async_request(request)
            raw = await response.aread()
            call["http_status"] = response.status_code
            try:
                call["response"] = json.loads(redact(raw.decode()))
            except (ValueError, UnicodeError):
                call["response_text"] = redact(raw.decode(errors="replace"))
            call["usage"] = (call.get("response") or {}).get("usage")
            call["estimated_cost_usd"] = estimate_cost(call["usage"], self.rates)
            return response
        except BaseException as exc:
            call["error"] = redact(f"{type(exc).__name__}: {exc}")
            raise
        finally:
            call["finished"] = time.monotonic()
            call["elapsed_seconds"] = call["finished"] - start
            write_new(self.folder / f"request-{number:04}.json", call)

    async def aclose(self):
        await self.transport.aclose()


def union_seconds(calls):
    intervals = sorted((c["started"], c["finished"]) for c in calls if "finished" in c)
    total, end = 0.0, float("-inf")
    for start, stop in intervals:
        total += max(0, stop - max(start, end))
        end = max(end, stop)
    return total


def usage_summary(calls):
    usages = [
        c["usage"]
        for c in calls
        if isinstance(c.get("usage"), dict)
        and all(
            type(c["usage"].get(k)) is int and c["usage"][k] >= 0
            for k in ("prompt_tokens", "completion_tokens")
        )
    ]
    total = {
        k: sum(u[k] for u in usages) for k in ("prompt_tokens", "completion_tokens")
    }
    total["total_tokens"] = total["prompt_tokens"] + total["completion_tokens"]
    caches = [
        (u.get("prompt_tokens_details") or {}).get(
            "cached_tokens", u.get("prompt_cache_hit_tokens")
        )
        for u in usages
    ]
    reasoning = [
        (u.get("completion_tokens_details") or {}).get("reasoning_tokens")
        for u in usages
    ]
    total["cached_input_tokens"] = (
        sum(caches) if caches and all(type(v) is int for v in caches) else None
    )
    total["reasoning_output_tokens"] = (
        sum(reasoning) if reasoning and all(type(v) is int for v in reasoning) else None
    )
    return {
        "reported": total if usages else None,
        "calls_with_usage": len(usages),
        "calls_without_usage": len(calls) - len(usages),
        "complete": len(usages) == len(calls) and bool(calls),
        "note": "cache is included in prompt_tokens; reasoning is included in completion_tokens; do not add them again",
    }


async def browser_use_execute(instruction, config, folder):
    # The agent's prompts, tools, loop and completion policy remain upstream native.
    from browser_use import Agent, Browser
    from browser_use.llm import ChatOpenAI

    folder = Path(folder)
    transport = MeteredTransport(folder / "agent_llm", config.get("agent_rates"))
    client = httpx.AsyncClient(transport=transport)
    llm = ChatOpenAI(
        model=config["model"],
        api_key=os.environ[config["agent_key_env"]],
        base_url=config["agent_base_url"],
        http_client=client,
        reasoning_effort=config.get("agent_reasoning"),
        max_completion_tokens=config["agent_max_tokens"],
        max_retries=2,
        timeout=config["model_timeout"],
    )
    browser = Browser(
        headless=config["browser"] == "local_headless",
        executable_path=config.get("chrome_bin"),
        viewport={"width": 1440, "height": 900},
        window_size={"width": 1440, "height": 900},
        user_data_dir=str(folder / "browser_profile"),
        downloads_path=str(folder / "downloads"),
    )
    start = time.monotonic()
    init_seconds = 0.0
    run_seconds = 0.0
    cleanup_seconds = 0.0
    status = "completed"
    agent = None
    history = None
    execution_error = None
    cleanup_error = None
    run_start = None
    init_start = None
    try:
        init_start = time.monotonic()
        await asyncio.wait_for(
            browser.start(), timeout=min(120, config["task_timeout"])
        )
        init_seconds = time.monotonic() - init_start
        agent = Agent(
            task=instruction,
            llm=llm,
            browser=browser,
            use_judge=False,
            use_vision=config["use_vision"],
            save_conversation_path=str(folder / "conversation"),
            file_system_path=str(folder / "workspace"),
        )
        run_start = time.monotonic()
        try:
            history = await asyncio.wait_for(
                agent.run(max_steps=config["max_steps"]),
                timeout=max(1, config["task_timeout"] - init_seconds),
            )
        except TimeoutError:
            status = "budget_exhausted"
            history = agent.history
        finally:
            run_seconds = time.monotonic() - run_start
    except Exception as exc:  # noqa: BLE001 - keep partial evidence for all agent failures
        status = "execution_error"
        execution_error = redact(f"{type(exc).__name__}: {exc}")
        history = agent.history if agent is not None else None
        if init_start is not None and run_start is None:
            init_seconds = time.monotonic() - init_start
    finally:
        cleanup_start = time.monotonic()
        try:
            await asyncio.wait_for(browser.kill(), timeout=30)
        except Exception as exc:  # noqa: BLE001 - cleanup cannot mask the original error
            cleanup_error = redact(f"{type(exc).__name__}: {exc}")
        finally:
            await client.aclose()
            cleanup_seconds = time.monotonic() - cleanup_start
    agent_wall = time.monotonic() - start
    capture_start = time.monotonic()
    # Reuse native recorded screenshots; this packaging time is evaluator overhead.
    images = []
    import io

    from PIL import Image

    for filename in history.screenshot_paths() if history is not None else []:
        if filename and Path(filename).is_file():
            with Image.open(filename) as image:
                buf = io.BytesIO()
                image.save(buf, format="PNG")
                images.append(base64.b64encode(buf.getvalue()).decode())
    steps = history.agent_steps() if history is not None else []
    if status == "budget_exhausted":
        steps.append(
            "Harness: configured agent time budget exhausted; partial history preserved."
        )
    if execution_error:
        steps.append("Harness execution error (not an agent claim): " + execution_error)
    if cleanup_error:
        steps.append("Harness cleanup error after execution: " + cleanup_error)
    if history is not None:
        history.save_to_file(folder / "native_history.json")
    evidence_seconds = time.monotonic() - capture_start
    known_costs = [
        c["estimated_cost_usd"]
        for c in transport.calls
        if c.get("estimated_cost_usd") is not None
    ]
    cost = (
        sum(known_costs)
        if len(known_costs) == len(transport.calls) and transport.calls
        else None
    )
    model_seconds = union_seconds(transport.calls)
    action_count = (
        sum(len(h.result or []) for h in history.history) if history is not None else 0
    )
    step_count = history.number_of_steps() if history is not None else 0
    metrics = {
        "agent_wall_seconds": agent_wall,
        "initialization_seconds": init_seconds,
        "run_seconds": run_seconds,
        "cleanup_seconds": cleanup_seconds,
        "model_wait_seconds": model_seconds,
        "non_model_seconds": max(0, agent_wall - model_seconds),
        "timing_note": "non_model includes browser observation/action, orchestration and cleanup; no finer split measured",
        "policy_steps": step_count,
        "browser_action_results": action_count,
        "physical_model_requests": len(transport.calls),
        "usage": usage_summary(transport.calls),
        "estimated_cost_usd": cost,
        "known_cost_subtotal_usd": sum(known_costs) if known_costs else None,
        "cost_rates_usd_per_million_tokens": config.get("agent_rates"),
        "execution_status": status,
        "execution_error": execution_error,
        "cleanup_error": cleanup_error,
    }
    return MeasuredExecutionResult(
        final_result=(history.final_result() or "") if history is not None else "",
        steps=steps,
        screenshots_b64=images,
        num_steps=step_count,
        duration_seconds=agent_wall,
        cost=cost,
        metrics=metrics,
        evidence_seconds=evidence_seconds,
    )


async def execute(instruction, config, folder):
    if config.get("adapter"):
        module, name = config["adapter"].split(":", 1)
        function = getattr(importlib.import_module(module), name)
        # Deliberately no task dictionary, reference answer or judge context.
        return await asyncio.wait_for(
            function(instruction), timeout=config["task_timeout"]
        )
    return await browser_use_execute(instruction, config, folder)
