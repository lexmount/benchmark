"""Evaluation adapters only. Product code is installed from the delivered local build."""
from __future__ import annotations
import argparse, asyncio, base64, hashlib, importlib.util, json, os, shutil, signal, sys, time
from pathlib import Path

ROOT = Path(os.environ.get("LEXMOUNT_EVAL_ROOT", Path(__file__).resolve().parent.parent))
EVAL = ROOT.parents[1]
PYTHON = ROOT / "envs/baseline/bin/python"
LEGACY_PYTHON = EVAL / "tmp/bu-0x-5090-local-bu100-20261112/.venv/bin/python"
BU = EVAL / "benchmark/bu_bench_v1/upstream"
OD = EVAL / "benchmark/odysseys_eval/upstream/odysseys"
SOURCES = [BU / "BU_Bench_V1.enc", BU / "judge.py",
           OD / "data/odysseys.json", OD / "scripts/python/run_full_trajectory_per_rubric.py"]

def read(path):
    return json.loads(Path(path).read_text())

def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def verify():
    actual = {str(p.relative_to(EVAL)): digest(p) for p in SOURCES}
    assert actual == read(ROOT / "sources.json"), "Pinned benchmark sources changed"

def tasks(suite):
    verify()
    if suite == "bu_v1":
        from cryptography.fernet import Fernet
        key = base64.urlsafe_b64encode(hashlib.sha256(b"BU_Bench_V1").digest())
        data = json.loads(Fernet(key).decrypt(base64.b64decode((BU / "BU_Bench_V1.enc").read_bytes())))
        rows = data["tasks"] if isinstance(data, dict) else data
        assert len(rows) == 100
        return [{"id": str(t["task_id"]), "instruction": t["confirmed_task"], "start_url": None,
                 "answer": t.get("answer")} for t in rows]
    rows = read(OD / "data/odysseys.json")
    assert len(rows) == 200
    return [{"id": str(t["task_id"]), "instruction": t["confirmed_task"], "start_url": t["website"],
             "level": t["level"], "rubrics": [{"id": k, **v} for k, v in t["rubrics"].items()]} for t in rows]

async def worker(folder, max_steps, timeout, plan):
    # This process receives only instruction/start URL. It never loads task answers or rubrics.
    from browser_use import Browser
    from browser_use.agent import service
    from browser_use.browser.browser import _daemon_request
    from lexmount_browser_agent import AgentConfig, run_task
    task = read(folder / "task.json")
    cfg = read(ROOT / ".private/model.json")
    assert cfg["model"] == "deepseek-v4.1-flash" and cfg.get("reasoning_effort", "high") == "high"
    job = next(j for j in plan["jobs"] if Path(j["source_folder"]).resolve() == folder)
    config = AgentConfig(**cfg, max_steps=max_steps, timeout_seconds=timeout, **job["feature_config"])
    browser = Browser("chromium", headless=True, executable_path=plan["browser_executable"])
    frames = []
    write(folder / "frames.json", frames)
    original_session = service.Session
    def capture(number):
        capture_started = time.monotonic()
        frame = {"step_num": number, "screenshot_file": None}
        try:
            if not browser.name:
                raise RuntimeError("No active browser daemon")
            def cdp(method, **params):
                reply = _daemon_request(browser.name, {"method": method, "params": params}, timeout=20 if method == "Page.captureScreenshot" else 5)
                if "error" in reply:
                    raise RuntimeError(str(reply["error"]))
                return reply.get("result", {})
            before = cdp("Page.getFrameTree")["frameTree"]["frame"]
            shot = cdp("Page.captureScreenshot", format="png", captureBeyondViewport=False)
            after = cdp("Page.getFrameTree")["frameTree"]["frame"]
            if any(before.get(k) != after.get(k) for k in ("id", "url", "loaderId")):
                raise RuntimeError("Document changed during screenshot capture")
            path = folder / "screenshots" / f"{number:04d}.png"
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(base64.b64decode(shot["data"], validate=True))
            frame.update(screenshot_file=str(path.relative_to(folder)), url=after.get("url"),
                         sha256=digest(path), captured_at=time.time(),
                         tabs=[{k: t.get(k) for k in ("targetId", "url", "title")} for t in
                               cdp("Target.getTargets").get("targetInfos", []) if t.get("type") == "page"])
        except Exception as exc:
            frame["capture_error"] = f"{type(exc).__name__}: {exc}"
        finally:
            frame["capture_seconds"] = time.monotonic() - capture_started
        return frame
    async def after_tool(name, args, result):
        if name != "python":
            return
        recording_started = time.monotonic()
        frame = await asyncio.to_thread(capture, len(frames) + 1)
        output_file = result.get("output_file")
        output = Path(output_file).read_text(errors="replace") if output_file and Path(output_file).exists() else result.get("output", "")
        frame.update(action="python " + args["code"], response=output + "\nObserved tabs: " + json.dumps(frame.get("tabs", [])),
                     tool_error=result.get("error"), native_stats=result.get("stats"))
        frame["recording_seconds"] = time.monotonic() - recording_started
        frames.append(frame)
        write(folder / "frames.json", frames)
        (folder / "steps.jsonl").write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in frames))
    def observed_session(*args, **kwargs):
        return original_session(*args, **kwargs, after_tool=after_tool)
    service.Session = observed_session
    instruction = task["instruction"]
    if task.get("start_url"):
        instruction += "\nStarting page: " + task["start_url"]
    try:
        result = await run_task(instruction, config, folder / "agent", browser=browser)
        result["independent_capture_seconds"] = sum(f["capture_seconds"] for f in frames)
        result["solver_wall_excluding_capture_seconds"] = max(0, result["wall_seconds"] - result["independent_capture_seconds"])
        result["capture_timing_note"] = "Wall time includes capture; subtraction is only a timing breakdown."
        text = result["text"]
        steps = frames + ([{"step_num": len(frames) + 1, "action": "final_response", "response": text, "final": True}] if text else [])
        (folder / "steps.jsonl").write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in steps))
        (folder / "final_response.txt").write_text(text)
        write(folder / "execution.json", result)
        write(folder / "recording.json", {"step_unit": "native_python_cell", "cells": len(frames),
              "screenshots": sum(bool(f.get("screenshot_file")) for f in frames),
              "capture_errors": [f["capture_error"] for f in frames if f.get("capture_error")],
              "solver_received_rubrics": False, "budget_unit": "model_turns",
              "independent_capture_seconds": result["independent_capture_seconds"],
              "note": "One code cell can execute multiple browser actions; these counts are not GUI-action counts."})
    finally:
        service.Session = original_session
        await browser.stop()

def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

async def child(command, log, timeout, env=None):
    process = await asyncio.create_subprocess_exec(*map(str, command), stdin=asyncio.subprocess.DEVNULL,
        stdout=log, stderr=asyncio.subprocess.STDOUT, start_new_session=True, env=env)
    command_list = list(map(str, command))
    if "--folder" in command_list:
        flag = "--destination" if "--destination" in command_list else "--folder"
        output = Path(command_list[command_list.index(flag) + 1])
        output.mkdir(parents=True, exist_ok=True)
        write(output / ("worker-dispatch.json" if "worker" in command_list else "judge-dispatch.json"),
              {"pid": process.pid, "started_at": time.time(), "command": command_list})
    try:
        return await asyncio.wait_for(process.wait(), timeout)
    except (TimeoutError, asyncio.CancelledError) as exc:
        if process.returncode is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(process.wait(), 20)
            except TimeoutError:
                os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
        if isinstance(exc, asyncio.CancelledError):
            raise
        return 124


async def judge(folder, suite, task, destination):
    """Rejudge immutable execution evidence; each protocol owns a new destination."""
    verify()
    from evidence_adapter import prepare, verify_originals
    from evidence_ranges import VERSION
    import httpx
    from openai import AsyncOpenAI, APIConnectionError, APIStatusError
    from openai.types.chat import ChatCompletion
    from types import SimpleNamespace
    import copy, re

    destination.mkdir(parents=True, exist_ok=True)
    grade_file = destination / ("judge-" + suite + ".json")
    if grade_file.exists() and read(grade_file).get("status") == "judged":
        existing = read(grade_file)
        assert existing["reasoning_effort"] == "low" and existing["evidence_version"] == VERSION
        verify_originals(read(destination / "evidence-manifest.json"))
        return existing
    trace, evidence = prepare(folder, suite, destination)
    cfg = read(ROOT / ".private/model.json")
    calls = len(list((destination / "model_calls").glob("*.request.json")))
    official = module_at("official_" + suite, BU / "judge.py" if suite == "bu_v1" else OD / "scripts/python/run_full_trajectory_per_rubric.py")

    async def request(req):
        nonlocal calls
        calls += 1
        req.extensions["receipt"] = calls
        req.extensions["started"] = time.monotonic()
        write(destination / "model_calls" / f"{calls:04d}.request.json", json.loads(req.content))

    async def response(resp):
        body = await resp.aread()
        try:
            value = json.loads(body)
        except ValueError:
            value = {"unparsed_response": body.decode(errors="replace")}
        number = resp.request.extensions["receipt"]
        write(destination / "model_calls" / f"{number:04d}.response.json", value)
        write(destination / "model_calls" / f"{number:04d}.transport.json",
              {"status": resp.status_code, "seconds": time.monotonic() - resp.request.extensions["started"]})

    def validate(response):
        if not response.choices or response.choices[0].finish_reason != "stop":
            raise ValueError("Judge response is incomplete")
        text = response.choices[0].message.content or ""
        if suite == "bu_v1":
            official.JudgementResult.model_validate_json(text)
        elif not re.search(r"Thoughts:\s*\S", text) or not re.search(r"Status:\s*[\"']?(success|failure)[\"']?", text, re.I):
            raise ValueError("Judge response has no valid Thoughts/Status verdict")

    async with httpx.AsyncClient(timeout=600, event_hooks={"request": [request], "response": [response]}) as http:
        client = AsyncOpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"], http_client=http, max_retries=2, timeout=600)

        async def create(**kwargs):
            kwargs = copy.deepcopy(kwargs)
            kwargs["reasoning_effort"] = "low"
            kwargs["extra_body"] = {"allowed_openai_params": ["reasoning_effort"]}
            if "max_completion_tokens" in kwargs:
                kwargs["max_tokens"] = kwargs.pop("max_completion_tokens")
            kwargs["max_tokens"] = 16384
            key = hashlib.sha256(json.dumps(kwargs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            cache = destination / "validated_responses" / (key + ".json")
            attempts_path = destination / "attempts" / (key + ".json")
            if cache.exists():
                result = ChatCompletion.model_validate(read(cache))
                validate(result)
                return result
            attempts = read(attempts_path) if attempts_path.exists() else []
            if len(attempts) >= 2:
                raise RuntimeError("Identical judge request already exhausted its two permitted attempts")
            while len(attempts) < 2:
                row = {"request_sha256": key, "attempt": len(attempts) + 1, "started_at": time.time()}
                attempts.append(row)
                write(attempts_path, attempts)
                try:
                    result = await client.chat.completions.create(**kwargs)
                    validate(result)
                    row.update(status="valid", ended_at=time.time())
                    write(attempts_path, attempts)
                    write(cache, result.model_dump(mode="json"))
                    return result
                except Exception as exc:
                    row.update(status="invalid_or_transport_error", error_type=type(exc).__name__, ended_at=time.time())
                    write(attempts_path, attempts)
                    retryable = isinstance(exc, (ValueError, APIConnectionError)) or (
                        isinstance(exc, APIStatusError) and (exc.status_code == 429 or exc.status_code >= 500)
                    )
                    if not retryable or len(attempts) >= 2:
                        raise
                    await asyncio.sleep(300 if isinstance(exc, (APIConnectionError, APIStatusError)) else 1)
            raise RuntimeError("Judge attempt budget exhausted")

        try:
            if suite == "bu_v1":
                messages = official.construct_judge_messages(
                    task=task["instruction"], ground_truth=task.get("answer"), **trace)
                response = await create(model=cfg["model"], max_tokens=8192,
                    messages=[m.model_dump(exclude_none=True) for m in messages],
                    response_format={"type": "json_object"})
                verdict = official.JudgementResult.model_validate_json(response.choices[0].message.content)
                result = {"status": "judged", "score": int(verdict.verdict), "judgement": verdict.model_dump()}
            else:
                proxy = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
                result = await official.evaluate_run(
                    destination, proxy, "openai", cfg["model"],
                    {task["id"]: {"task": task["instruction"], "rubrics": task["rubrics"]}},
                    max_images=0, max_steps=None)
                bad = (result.get("error") and result["error"] != "Empty trajectory - no steps recorded.") or any(
                    r["final_reasoning"].startswith("Error judging rubric") for r in result.get("rubric_results", []))
                result["status"] = "judge_error" if bad else "judged"
            verify_originals(evidence)
            result.update(
                judge_model=cfg["model"], reasoning_effort="low", evidence_version=VERSION,
                source_folder=str(folder), official_sources=read(ROOT / "sources.json"),
                reference_judge_model_changed=True, judge_http_requests=calls,
            )
        except Exception as exc:
            result = {
                "status": "judge_error", "error": str(exc).replace(cfg["api_key"], "[REDACTED]"),
                "judge_model": cfg["model"], "reasoning_effort": "low", "evidence_version": VERSION,
                "source_folder": str(folder), "judge_http_requests": calls,
            }
        write(grade_file, result)
        return result



def verify_bundle(plan):
    verify()
    for name, expected in plan["frozen_files"].items():
        if digest(name) != expected:
            raise RuntimeError("Frozen evaluation source changed: " + name)


def event(run, name, **fields):
    with (run / "events.jsonl").open("a") as stream:
        stream.write(json.dumps({"event": name, "at": time.time(), **fields}) + "\n")


def summarize_campaign(plan):
    groups = {}
    for kind in ("baseline", "candidate", "all"):
        groups[kind] = {}
        for suite in ("bu_v1", "odysseys"):
            jobs = [j for j in plan["jobs"] if j["suite"] == suite and (kind == "all" or j["variant"] == kind)]
            grades, missing = [], []
            for job in jobs:
                path = Path(job["judge_folder"]) / ("judge-" + suite + ".json")
                if path.exists() and read(path).get("status") == "judged":
                    grades.append(read(path))
                else:
                    missing.append(job["id"])
            row = {"requested": len(jobs), "graded": len(grades), "ungraded_ids": missing, "complete": not missing}
            if suite == "bu_v1":
                row["passed"] = sum(g["score"] for g in grades)
                row["success_rate"] = row["passed"] / len(grades) if grades and not missing else None
            else:
                scores = [s for g in grades for s in g.get("rubric_scores", {}).values()]
                row.update(rubrics_passed=sum(scores), rubrics_graded=len(scores),
                    task_mean=sum(g["average_rubric_score"] for g in grades) / len(grades) if grades and not missing else None,
                    rubric_mean=sum(scores) / len(scores) if scores and not missing else None,
                    perfect_tasks=sum(g["perfect"] for g in grades),
                    perfect_rate=sum(g["perfect"] for g in grades) / len(grades) if grades and not missing else None)
            groups[kind][suite] = row
    write(Path(plan["run"]) / "summary.json", {"updated_at": time.time(), "groups": groups})
    return groups


async def campaign(plan, phase):
    """Independent pools: execution completion releases its slot before grading."""
    verify_bundle(plan)
    run = Path(plan["run"])
    selected = [j for j in plan["jobs"] if phase == "all" or j["stage"] == phase]
    execution_slots = asyncio.Semaphore(plan["execution_concurrency"])
    judge_slots = asyncio.Semaphore(plan["judge_concurrency"])
    active = {"execution": 0, "judge": 0}
    stopped = False
    progress_path = run / "progress.json"
    progress = read(progress_path) if progress_path.exists() else {}
    event(run, "controller_started", pid=os.getpid(), phase=phase, selected=len(selected))

    def external_actors():
        other = read(Path(plan["external_actor_progress"]))
        return sum(v["status"] == "execution_started" for v in other.values())

    def state(job, status, **extra):
        progress[job["variant"] + "/" + job["suite"] + "/" + job["id"]] = {"kind": job["kind"], "status": status, "at": time.time(), **extra}
        write(progress_path, progress)
        event(run, status, variant=job["variant"], suite=job["suite"], task=job["id"], active=dict(active), **extra)

    async def grade_one(job):
        async with judge_slots:
            # The first controller owns its four judge slots until its bounded stage ends.
            # Waiting is outside actor slots; running actors keep replenishing immediately.
            while not Path(plan["external_controller_complete"]).exists():
                await asyncio.sleep(0.5)
            verify_bundle(plan)
            active["judge"] += 1
            state(job, "judge_started")
            folder = Path(job["judge_folder"])
            folder.mkdir(parents=True, exist_ok=True)
            try:
                with (folder / ("judge-" + str(time.time_ns()) + ".log")).open("xb") as log:
                    code = await child(
                        [LEGACY_PYTHON if job["suite"] == "bu_v1" else PYTHON,
                         plan["adapter"], "judge", "--folder", job["source_folder"],
                         "--destination", folder, "--suite", job["suite"], "--task-id", job["id"],
                         "--plan", run / "plan.json"],
                        log, 14400, env={**os.environ, "LEXMOUNT_EVAL_ROOT": str(ROOT)})
                if code:
                    write(folder / "judge-process-error.json", {"exit_code": code})
                path = folder / ("judge-" + job["suite"] + ".json")
                status = read(path).get("status") if path.exists() else "judge_error"
            finally:
                active["judge"] -= 1
            state(job, status)
            summarize_campaign(plan)

    async def one(job):
        nonlocal stopped
        try:
            folder = Path(job["source_folder"])
            if job["kind"] == "new":
                async with execution_slots:
                    # First-stage actors were all dispatched already, so their count only decreases.
                    # No await occurs between this admission check and incrementing our active count.
                    while active["execution"] + external_actors() >= plan["execution_concurrency"]:
                        await asyncio.sleep(0.5)
                    if stopped:
                        state(job, "not_dispatched_source_failure")
                        return
                    verify_bundle(plan)
                    if (folder / "execution.json").exists():
                        state(job, "existing_execution_preserved")
                    elif folder.exists():
                        state(job, "existing_incomplete_attempt_preserved")
                        return
                    else:
                        task = next(t for t in tasks(job["suite"]) if t["id"] == job["id"])
                        folder.mkdir(parents=True, exist_ok=False)
                        write(folder / "task.json", {k: task[k] for k in ("id", "instruction", "start_url")})
                        active["execution"] += 1
                        state(job, "execution_started")
                        try:
                            with (folder / "worker.log").open("xb") as log:
                                code = await child(
                                    [job["python"], plan["adapter"], "worker", "--folder", folder,
                                     "--max-steps", job["max_steps"], "--timeout", job["timeout_seconds"],
                                     "--plan", run / "plan.json"],
                                    log, job["timeout_seconds"] + 300,
                                    env={**os.environ, "PYTHONPATH": plan["product_source"],
                                         "LEXMOUNT_EVAL_ROOT": str(ROOT)})
                            write(folder / "worker-completion.json", {"exit_code": code, "finished_at": time.time()})
                            if code or not (folder / "execution.json").exists():
                                write(folder / "worker-error.json", {"exit_code": code})
                        finally:
                            active["execution"] -= 1
                        state(job, "execution_finished", exit_code=code)
                # This await is intentionally outside execution_slots.
                if not (folder / "execution.json").exists():
                    state(job, "execution_error")
                    return
            state(job, "judge_queued")
            await grade_one(job)
        except Exception as exc:
            stopped = True
            state(job, "controller_error", error_type=type(exc).__name__, message=str(exc)[:500])

    await asyncio.gather(*(one(job) for job in selected))
    groups = summarize_campaign(plan)
    write(run / ("complete-" + phase + ".json"), {"finished_at": time.time(), "active": active, "groups": groups})
    event(run, "controller_finished", phase=phase, active=active)
    print(json.dumps(groups), flush=True)


def main():
    import fcntl
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["worker", "judge", "campaign", "summary"])
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--folder", type=Path)
    p.add_argument("--destination", type=Path)
    p.add_argument("--suite", choices=["bu_v1", "odysseys"])
    p.add_argument("--task-id")
    p.add_argument("--max-steps", type=int, default=100)
    p.add_argument("--timeout", type=float, default=3600)
    p.add_argument("--phase", choices=["targeted", "all"], default="all")
    args = p.parse_args()
    plan = read(args.plan)
    verify_bundle(plan)
    if args.command == "worker":
        asyncio.run(worker(args.folder.resolve(), args.max_steps, args.timeout, plan))
    elif args.command == "judge":
        task = next(t for t in tasks(args.suite) if t["id"] == args.task_id)
        print(json.dumps(asyncio.run(judge(args.folder.resolve(), args.suite, task, args.destination.resolve()))))
    elif args.command == "summary":
        print(json.dumps(summarize_campaign(plan)))
    else:
        with (Path(plan["run"]) / "controller.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            asyncio.run(campaign(plan, args.phase))


if __name__ == "__main__":
    main()
