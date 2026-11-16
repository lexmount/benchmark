"""Grade one BU-filter execution using the pinned official V1 binary judge.

The existing native-evidence v3 adapter and 5090 transport/recovery policy are
retained. Valid failures are never rejudged to seek a passing result.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import importlib
import json
import sys
import time
from pathlib import Path

VENDOR = Path(__file__).resolve().parent / "vendor"
sys.path.insert(0, str(VENDOR))
from evidence_adapter import prepare, verify_originals
from evidence_ranges import VERSION
from billing import record_billing


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


def redact(value, key):
    if isinstance(value, str):
        return value.replace(key, "[REDACTED]") if key else value
    if isinstance(value, list):
        return [redact(x, key) for x in value]
    if isinstance(value, dict):
        return {k: redact(v, key) for k, v in value.items()}
    return value


def selected_task(task_id):
    """The only dataset entry point is the fixed BU-filter allowlist."""
    from dataset import load_judge_tasks

    tasks = load_judge_tasks()
    if isinstance(tasks, dict):
        tasks = tasks.get("tasks", list(tasks.values()))
    matching = [t for t in tasks if str(t.get("id", t.get("task_id"))) == task_id]
    if len(matching) != 1:
        raise ValueError("Task is not uniquely present in the BU-filter dataset")
    task = matching[0]
    return {"id": task_id, "instruction": task["instruction"], "start_url": task.get("start_url"), "answer": task.get("answer")}


def is_content_refusal(text):
    text = str(text).lower()
    return any(s in text for s in (
        "data_inspection_failed", "inappropriate content", "content_filter",
        "content policy violation", "content policy is not allowed",
    ))


def validate_settings(settings):
    judge = settings["judge"]
    expected = {"model": "deepseek-v4.1-flash", "reasoning_effort": "low", "max_tokens": 16384,
                "timeout_seconds": 600, "sdk_retries": 2, "logical_attempts": 2,
                "refusal_fallback_model": "gpt-6.1-sol"}
    if any(judge.get(key) != value for key, value in expected.items()):
        raise ValueError("Judge parameters differ from the retained 5090 evaluation protocol")
    return judge


def validate_completion(completion, official):
    if not completion.choices or completion.choices[0].finish_reason != "stop":
        raise ValueError("Judge response is incomplete")
    return official.JudgementResult.model_validate_json(completion.choices[0].message.content or "")


async def request_with_recovery(client, kwargs, destination, official, *, attempts_limit=2, sleep=asyncio.sleep):
    """Retain the old identical-request cache and two-attempt logical budget."""
    from openai import APIConnectionError, APIStatusError
    from openai.types.chat import ChatCompletion

    destination = Path(destination)
    key = hashlib.sha256(json.dumps(kwargs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    cache = destination / "validated_responses" / (key + ".json")
    attempts_path = destination / "attempts" / (key + ".json")
    if cache.exists():
        result = ChatCompletion.model_validate(read(cache))
        validate_completion(result, official)
        return result
    attempts = read(attempts_path) if attempts_path.exists() else []
    if len(attempts) >= attempts_limit:
        raise RuntimeError("Identical judge request already exhausted its two permitted attempts")
    while len(attempts) < attempts_limit:
        row = {"request_sha256": key, "attempt": len(attempts) + 1, "started_at": time.time()}
        attempts.append(row)
        write(attempts_path, attempts)
        try:
            result = await client.chat.completions.create(**copy.deepcopy(kwargs))
            validate_completion(result, official)
            row.update(status="valid", ended_at=time.time())
            write(attempts_path, attempts)
            write(cache, result.model_dump(mode="json"))
            return result
        except Exception as error:
            row.update(status="invalid_or_transport_error", error_type=type(error).__name__, ended_at=time.time())
            write(attempts_path, attempts)
            retryable = isinstance(error, (ValueError, APIConnectionError)) or (
                isinstance(error, APIStatusError) and (error.status_code == 429 or error.status_code >= 500)
            )
            if not retryable or len(attempts) >= attempts_limit:
                raise
            await sleep(300 if isinstance(error, (APIConnectionError, APIStatusError)) else 1)
    raise RuntimeError("Judge attempt budget exhausted")


async def judge_model(folder, task, destination, settings, credentials, *, model_name):
    import httpx
    from openai import AsyncOpenAI

    official = importlib.import_module("official_judge")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    grade_file = destination / "judge-bu_v1.json"
    if grade_file.exists() and read(grade_file).get("status") == "judged":
        existing = read(grade_file)
        if existing.get("judge_model") != model_name or existing.get("evidence_version") != VERSION:
            raise ValueError("Existing grade belongs to another judge protocol")
        verify_originals(read(destination / "evidence-manifest.json"))
        return existing
    trace, evidence = prepare(folder, "bu_v1", destination)
    calls = len(list((destination / "model_calls").glob("*.request.json")))
    api_key = credentials["api_key"]

    async def request(req):
        nonlocal calls
        calls += 1
        req.extensions["receipt"] = calls
        req.extensions["started"] = time.monotonic()
        write(destination / "model_calls" / f"{calls:04d}.request.json", redact(json.loads(req.content), api_key))

    async def response(resp):
        body = await resp.aread()
        try:
            value = json.loads(body)
        except ValueError:
            value = {"unparsed_response": body.decode(errors="replace")}
        number = resp.request.extensions["receipt"]
        write(destination / "model_calls" / f"{number:04d}.response.json", redact(value, api_key))
        record_billing(destination, number, resp)
        write(destination / "model_calls" / f"{number:04d}.transport.json",
              {"status": resp.status_code, "seconds": time.monotonic() - resp.request.extensions["started"]})

    try:
        messages = official.construct_judge_messages(task=task["instruction"], ground_truth=task.get("answer"), **trace)
        kwargs = {
            "model": model_name, "reasoning_effort": "low",
            "extra_body": {"allowed_openai_params": ["reasoning_effort"]},
            "messages": [m.model_dump(exclude_none=True) for m in messages],
            "response_format": {"type": "json_object"},
        }
        kwargs["max_completion_tokens" if model_name == "gpt-6.1-sol" else "max_tokens"] = 16384
        # Official BU V1 emits at most 10 unique screenshots, below the fallback gateway's 50-image cap.
        async with httpx.AsyncClient(timeout=600, event_hooks={"request": [request], "response": [response]}) as http:
            client = AsyncOpenAI(api_key=api_key, base_url=credentials["base_url"],
                                 http_client=http, max_retries=2, timeout=600)
            completion = await request_with_recovery(client, kwargs, destination, official)
        verdict = validate_completion(completion, official)
        verify_originals(evidence)
        result = {"status": "judged", "score": int(verdict.verdict), "judgement": verdict.model_dump()}
    except Exception as error:
        result = {"status": "judge_error", "error": redact(str(error), api_key)}
    result.update(judge_model=model_name, reasoning_effort="low", evidence_version=VERSION,
                  source_folder=str(folder), judge_http_requests=calls,
                  official_judge_sha256=digest(VENDOR / "official_judge.py"),
                  reference_judge_model_changed=True)
    write(grade_file, result)
    return result


async def judge_task(folder, task, destination, settings, credentials, *, grade=judge_model):
    destination = Path(destination)
    canonical = destination / "judge.json"
    if canonical.exists() and read(canonical).get("status") == "judged":
        existing = read(canonical)
        if existing.get("source_folder") != str(folder) or existing.get("task_id") != task["id"]:
            raise ValueError("Existing grade belongs to another task")
        raw = Path(existing["raw_gpt_grade"] if existing.get("raw_gpt_grade") else existing["raw_deepseek_grade"])
        verify_originals(read(raw.parent / "evidence-manifest.json"))
        return existing
    destination.mkdir(parents=True, exist_ok=True)
    raw_ds = destination / "deepseek" / task["id"]
    original = await grade(folder, task, raw_ds, settings, credentials, model_name="deepseek-v4.1-flash")
    merged = copy.deepcopy(original)
    refused = original.get("status") == "judge_error" and is_content_refusal(original.get("error", ""))
    replacement = None
    if refused:
        raw_gpt = destination / "gpt-fallback" / task["id"]
        replacement = await grade(folder, task, raw_gpt, settings, credentials, model_name="gpt-6.1-sol")
        if replacement.get("status") == "judged":
            merged = copy.deepcopy(replacement)
    merged.update(
        source_folder=str(folder), task_id=task["id"], benchmark="BU-filter",
        raw_deepseek_grade=str(raw_ds / "judge-bu_v1.json"),
        raw_deepseek_grade_sha256=digest(raw_ds / "judge-bu_v1.json"),
        refused_rubric_ids=["whole_task"] if refused else [], normal_failures_not_rejudged=True,
    )
    if replacement is not None:
        merged.update(raw_gpt_grade=str(raw_gpt / "judge-bu_v1.json"),
                      raw_gpt_grade_sha256=digest(raw_gpt / "judge-bu_v1.json"),
                      judge_http_requests=original.get("judge_http_requests", 0) + replacement.get("judge_http_requests", 0))
    write(canonical, merged)
    return merged


async def run(folder, output, task_id, settings):
    validate_settings(settings)
    folder, output = Path(folder).resolve(), Path(output).resolve()
    task = selected_task(task_id)
    actor_task = read(folder / "task.json")
    expected = {k: task[k] for k in ("id", "instruction", "start_url")}
    if actor_task != expected:
        raise ValueError("Actor instruction differs from the pinned BU-filter task")
    credentials = read(settings["credentials_file"])
    return await judge_task(folder, task, output, settings, credentials)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--settings", required=True, type=Path)
    args = parser.parse_args()
    if not all(p.is_absolute() for p in (args.folder, args.output, args.settings)):
        parser.error("folder, output and settings must be absolute paths")
    result = asyncio.run(run(args.folder, args.output, args.task_id, read(args.settings)))
    print(json.dumps({k: result.get(k) for k in ("task_id", "status", "score", "judge_model")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
