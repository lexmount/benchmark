"""Reuse the actual historical 5090 AgentTrek protocol; evaluation glue only."""
from __future__ import annotations

import ast
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EVAL = ROOT.parents[1]
HISTORY = EVAL / "docs/exp_records/1112/skyvern-mcp-bu-mindweb-local-r1/judge-common"
DATASET = EVAL / "benchmark/OnlineMind2Web/online_mind2web.jsonl"
DATASET_SHA256 = "8343c23be98d6d63856e9b53ff3884222be099cc0f55ad5edb475176f54317ed"
PROTOCOL = "AgentTrek_eval-native-5090-max2"
EXECUTION_RULES = ""
_NATIVE = None


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


def verify():
    lock = read(HERE / "historical-sources.json")
    assert digest(DATASET) == DATASET_SHA256 == lock["dataset"]["sha256"]
    for name, expected in lock["files"].items():
        assert digest(EVAL / name) == expected, "Historical evaluator source changed: " + name
    return lock


def tasks():
    """All original 300 rows, without applying historical selection exclusions."""
    verify()
    rows = [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]
    assert len(rows) == len({r["task_id"] for r in rows}) == 300
    return [{"id": row["task_id"], "instruction": row["task_name"], "start_url": row["website"],
             "level": row["difficulty"], "reference_length": row["metadata"]["reference_length"]}
            for row in rows]


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def native():
    """Same AST extraction used in the historical native_evidence.py; function bodies are unchanged."""
    global _NATIVE
    if _NATIVE is None:
        verify()
        path = HISTORY / "upstream/om/onlinemind2web_judge.py"
        names = {"format_action", "_clip", "_call_step", "_ace_steps", "_dom_steps",
                 "build_trajectory", "last_shot_message", "parse_verdict"}
        tree = ast.parse(path.read_text())
        nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
        assert {n.name for n in nodes} == names
        scope = dict(Path=Path, json=json, base64=base64, MAX_THOUGHT_CHARS=600,
                     MAX_ACTION_CHARS=300, JEV_DECIDERS=set())
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), scope)
        prompt = module_at("_omw_historical_prompt", HISTORY / "upstream/om/evaluation_prompt.py")
        collector = module_at("_omw_historical_stream", HISTORY / "tools/upstream_remote_sdk_request.py")
        _NATIVE = SimpleNamespace(**scope, PROMPT=prompt, collector=collector)
    return _NATIVE


def prepare(folder, destination):
    """Project native model responses into the existing prompt_calls schema; do not add final answer."""
    folder, destination = Path(folder).resolve(), Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    messages_path = folder / "agent/messages.json"
    frames_path = folder / "frames.json"
    messages, frames = read(messages_path), read(frames_path)
    calls, pointers = [], []
    for index, message in enumerate(messages):
        parts = message.get("parts", [])
        if message.get("kind") != "response" and not any(
            p.get("part_kind") in {"thinking", "text", "tool-call"} for p in parts
        ):
            continue
        calls.append({
            "reasoning": "\n".join(str(p.get("content") or "") for p in parts if p.get("part_kind") == "thinking"),
            "content": "\n".join(str(p.get("content") or "") for p in parts if p.get("part_kind") == "text"),
            "tool_calls": [{"name": p["tool_name"], "args": p.get("args")}
                           for p in parts if p.get("part_kind") == "tool-call"],
        })
        pointers.append({"file": str(messages_path), "json_pointer": "/" + str(index)})
    shots = destination / "shots"
    shots.mkdir(exist_ok=True)
    image_proof = []
    for index, frame in enumerate(frames, 1):
        relative = frame.get("screenshot_file")
        if not relative:
            continue
        image = (folder / relative).resolve()
        assert image.is_relative_to((folder / "screenshots").resolve()), "Screenshot outside task capture directory"
        assert image.is_file() and digest(image) == frame["sha256"], "Original PNG changed"
        assert image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), "Original capture is not PNG"
        target = shots / f"step_{index:04d}.png"
        if target.exists():
            assert digest(target) == frame["sha256"], "Previously projected screenshot changed"
        else:
            os.link(image, target)
        image_proof.append({"step_num": index, "path": str(image), "sha256": frame["sha256"]})
    record = {"task_id": read(folder / "task.json").get("id"), "prompt_calls": calls,
              "bucket": "agent_run" if calls else "infra"}
    write(destination / "record.json", record)
    n = native()
    trajectory, source, steps = n.build_trajectory(record, destination)
    shot = n.last_shot_message(destination)
    evidence = {
        "protocol": PROTOCOL, "source_folder": str(folder),
        "source_files": {str(p): digest(p) for p in (messages_path, frames_path)},
        "native_response_sources": pointers, "original_frame_images": image_proof,
        "n_steps": steps, "trajectory_source": source, "record_bucket": record["bucket"],
        "thought_limit": 600, "action_limit": 300, "final_answer_appended": False,
        "system_prompt_sha256": hashlib.sha256(n.PROMPT.SYSTEM_PROMPT.encode()).hexdigest(),
        "trajectory_sha256": hashlib.sha256(trajectory.encode()).hexdigest(),
        "image_policy": "historical last_shot_message: last available captured frame only",
        "selected_screenshot": str(image_proof[-1]["path"]) if image_proof else None,
        "capture_errors": [f.get("capture_error") for f in frames if f.get("capture_error")],
        "native_projection": "ModelResponse thinking/text/tool-call parts to historical prompt_calls; tool returns/final_response.txt not appended",
    }
    write(destination / "evidence-manifest.json", evidence)
    return trajectory, shot, evidence


def verify_originals(evidence):
    for path, expected in evidence["source_files"].items():
        assert digest(path) == expected, "Original native transcript changed"
    for item in evidence["original_frame_images"]:
        assert digest(item["path"]) == item["sha256"], "Original screenshot changed"


def content_refusal(exc):
    body = getattr(exc, "body", None)
    text = json.dumps(body, ensure_ascii=False) if body is not None else str(exc)
    return getattr(exc, "status_code", None) in (400, 403) and any(
        s in text.lower() for s in
        ("data_inspection_failed", "content_filter", "content_policy_violation", "content_policy", "safety_policy")
    )


class HistoricalRequest:
    """Only add request/stream/billing receipts around the unchanged SDK stream collector."""
    def __init__(self, config, destination, *, transport=None):
        import httpx
        from openai import OpenAI

        self.config, self.destination = config, Path(destination)
        numbers = [int(p.name.split(".")[0]) for p in (self.destination / "model_calls").glob("*.request.json")]
        self.calls = max(numbers, default=0)
        self.http = httpx.Client(
            timeout=httpx.Timeout(150, connect=20), transport=transport, trust_env=False,
            follow_redirects=False, event_hooks={"request": [self.request], "response": [self.response]},
        )
        self.client = OpenAI(api_key=config["api_key"], base_url=config["base_url"],
                             max_retries=0, http_client=self.http)

    def request(self, request):
        self.calls += 1
        request.extensions["receipt"] = self.calls
        request.extensions["started"] = time.monotonic()
        write(self.destination / "model_calls" / f"{self.calls:04d}.request.json", json.loads(request.content))

    def response(self, response):
        import httpx
        code_path = str(ROOT / "code")
        if code_path not in sys.path:
            sys.path.insert(0, code_path)
        from eval_billing import record_billing

        number = response.request.extensions["receipt"]
        record_billing(self.destination / "model_calls", number, response)
        original = response.stream
        destination = self.destination
        started = response.request.extensions["started"]
        status = response.status_code

        def archive(body):
            try:
                value = json.loads(body)
            except ValueError:
                value = {"raw_stream": body.decode(errors="replace")}
            write(destination / "model_calls" / f"{number:04d}.response.json", value)
            write(destination / "model_calls" / f"{number:04d}.transport.json",
                  {"status": status, "seconds": time.monotonic() - started, "response_bytes": len(body)})

        if response.is_stream_consumed:
            archive(response.content)
            return

        class RecordedStream(httpx.SyncByteStream):
            def __iter__(self):
                chunks = []
                try:
                    for chunk in original:
                        chunks.append(chunk)
                        yield chunk
                finally:
                    archive(b"".join(chunks))

            def close(self):
                original.close()

        response.stream = RecordedStream()

    def once(self, payload, attempt):
        def expired(*_):
            raise TimeoutError("Native Judge single attempt exceeded 150 seconds")

        previous = signal.signal(signal.SIGALRM, expired)
        signal.alarm(150)
        metadata = {}
        try:
            response = native().collector.stream_completion(self.client, payload, metadata)
            write(self.destination / f"attempt-{attempt}.completion.json", response.model_dump(mode="json"))
            return response
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
            write(self.destination / f"attempt-{attempt}.transport.json", metadata)

    def close(self):
        self.client.close()


async def judge(folder, task, destination):
    """Dedicated child process inside the root controller's shared four judge slots."""
    folder, destination = Path(folder).resolve(), Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    verify()
    grade_path = destination / "judge-online_mind2web.json"
    if grade_path.exists() and read(grade_path).get("status") == "judged":
        verify_originals(read(destination / "evidence-manifest.json"))
        return read(grade_path)
    cfg = read(ROOT / ".private/model.json")
    assert cfg["model"] == "deepseek-v4.1-flash"
    started = time.monotonic()
    result = {"task_id": task["id"], "status": "judge_error", "protocol": PROTOCOL,
              "source_folder": str(folder), "dataset_sha256": DATASET_SHA256,
              "judge_model": cfg["model"], "reasoning_effort": "low", "max_physical_POSTs": 2}
    request = None
    try:
        trajectory, shot, evidence = prepare(folder, destination)
        if evidence["record_bucket"] == "infra":
            result.update(status="unknown", score=None, judge_bucket="infra")
        elif not evidence["n_steps"] or shot is None:
            result.update(status="judged", score=0,
                          judge_bucket="no_actions" if not evidence["n_steps"] else "no_shots")
        else:
            n = native()
            messages = [
                {"role": "system", "content": n.PROMPT.SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": n.PROMPT.USER_PROMPT.format(
                        task=task["instruction"], thoughts_and_actions=trajectory)}, shot]},
            ]
            write(destination / "judge-input.json", {"messages": messages})
            budget_path = destination / "attempt-budget.json"
            binding = hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            state = read(budget_path) if budget_path.exists() else {
                "payload_sha256": binding, "max_POSTs": 2, "attempts": []}
            assert state["payload_sha256"] == binding and state["max_POSTs"] == 2
            request = HistoricalRequest(cfg, destination)
            model = cfg["model"]
            if state["attempts"]:
                last = state["attempts"][-1]
                model = last.get("next_model", last["model"])
            accepted = None
            for attempt in state["attempts"]:
                completed = destination / f"attempt-{attempt['attempt']}.completion.json"
                if completed.exists():
                    from openai.types.chat import ChatCompletion
                    accepted = ChatCompletion.model_validate(read(completed))
                    break
            while accepted is None and model is not None and len(state["attempts"]) < 2:
                number = len(state["attempts"]) + 1
                attempt = {"attempt": number, "model": model, "status": "reserved", "started_at": time.time()}
                state["attempts"].append(attempt)
                write(budget_path, state)
                payload = {
                    "messages": copy.deepcopy(messages), "seed": 42, "model": model,
                    "reasoning_effort": "low", "max_tokens": 4096,
                    "extra_body": {"allowed_openai_params": ["reasoning_effort"],
                                   "cache": {"no-cache": True, "no-store": True}},
                }
                try:
                    accepted = request.once(payload, number)
                    verdict = n.parse_verdict(accepted.choices[0].message.content or "")
                    if verdict is None:
                        accepted = None
                        raise ValueError("Native OM parser found no status:")
                    attempt.update(status="accepted", finished_at=time.time())
                except Exception as exc:
                    refused = content_refusal(exc)
                    transient = n.collector.retryable(exc) or isinstance(exc, TimeoutError)
                    next_model = "gpt-6.1-sol" if refused and model == cfg["model"] else (
                        model if transient else None)
                    attempt.update(status="failed", error_type=type(exc).__name__,
                                   content_refusal=refused, next_model=next_model, finished_at=time.time())
                    model = next_model
                    if model is None:
                        raise
                finally:
                    write(budget_path, state)
            if accepted is None:
                raise RuntimeError("Native maximum two physical POST reservations exhausted")
            answer = accepted.choices[0].message.content or ""
            verdict = n.parse_verdict(answer)
            if verdict is None:
                raise ValueError("Native OM parser found no status:")
            result.update(status="judged", score=int(verdict), judge_bucket="judged",
                          judge_model=accepted.model, judgement={"reward": int(verdict), "judge_text": answer},
                          judge_usage=accepted.usage.model_dump() if accepted.usage else None,
                          attempt_count=len(state["attempts"]),
                          fallback_used=accepted.model == "gpt-6.1-sol")
        verify_originals(evidence)
        result.update(n_steps=evidence["n_steps"], selected_images=int(shot is not None),
                      final_answer_appended=False, thought_limit=600, action_limit=300)
    except Exception as exc:
        result.update(error_type=type(exc).__name__, error=str(exc).replace(cfg["api_key"], "[REDACTED]"))
    finally:
        if request is not None:
            result["judge_http_requests"] = request.calls
            request.close()
        result["judge_wall_seconds"] = time.monotonic() - started
    write(grade_path, result)
    return result
