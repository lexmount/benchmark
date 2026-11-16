import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace, ModuleType
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel
from openai.types.chat import ChatCompletion

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import judge


class Verdict(BaseModel):
    verdict: bool


OFFICIAL = SimpleNamespace(JudgementResult=Verdict)


def completion(verdict=False, finish="stop"):
    return ChatCompletion.model_validate({
        "id": "fixture", "object": "chat.completion", "created": 0, "model": "fixture",
        "choices": [{"index": 0, "finish_reason": finish,
                     "message": {"role": "assistant", "content": json.dumps({"verdict": verdict})}}],
    })


def client(*results):
    create = AsyncMock(side_effect=list(results))
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), create


def test_valid_zero_is_not_retried_and_is_reused(tmp_path):
    transport, create = client(completion(False))
    kwargs = {"model": "fixture", "messages": []}
    first = asyncio.run(judge.request_with_recovery(transport, kwargs, tmp_path, OFFICIAL))
    second = asyncio.run(judge.request_with_recovery(transport, kwargs, tmp_path, OFFICIAL))
    assert not judge.validate_completion(first, OFFICIAL).verdict
    assert not judge.validate_completion(second, OFFICIAL).verdict
    assert create.await_count == 1


def test_incomplete_response_has_one_technical_recovery(tmp_path):
    transport, create = client(completion(True, "length"), completion(False))
    sleep = AsyncMock()
    result = asyncio.run(judge.request_with_recovery(transport, {}, tmp_path, OFFICIAL, sleep=sleep))
    assert not judge.validate_completion(result, OFFICIAL).verdict
    assert create.await_count == 2
    sleep.assert_awaited_once_with(1)


def test_attempt_budget_survives_process_resume(tmp_path):
    transport, create = client(completion(True, "length"), completion(True, "length"))
    with pytest.raises(ValueError, match="incomplete"):
        asyncio.run(judge.request_with_recovery(transport, {}, tmp_path, OFFICIAL, sleep=AsyncMock()))
    with pytest.raises(RuntimeError, match="exhausted"):
        asyncio.run(judge.request_with_recovery(transport, {}, tmp_path, OFFICIAL, sleep=AsyncMock()))
    assert create.await_count == 2


@pytest.mark.parametrize("original,replacement,models,expected", [
    ({"status": "judged", "score": 0}, None, ["deepseek-v4.1-flash"], ("judged", 0)),
    ({"status": "judge_error", "error": "APIConnectionError"}, None, ["deepseek-v4.1-flash"], ("judge_error", None)),
    ({"status": "judge_error", "error": "HTTP400 data_inspection_failed"}, {"status": "judged", "score": 1},
     ["deepseek-v4.1-flash", "gpt-6.1-sol"], ("judged", 1)),
    ({"status": "judge_error", "error": "HTTP400 content_filter"}, {"status": "judge_error", "error": "timeout"},
     ["deepseek-v4.1-flash", "gpt-6.1-sol"], ("judge_error", None)),
])
def test_only_content_refusal_uses_another_model(tmp_path, original, replacement, models, expected):
    calls = []

    async def grade(folder, task, destination, settings, credentials, *, model_name):
        calls.append(model_name)
        result = dict(original if len(calls) == 1 else replacement, judge_http_requests=1)
        judge.write(destination / "judge-bu_v1.json", result)
        return result

    result = asyncio.run(judge.judge_task(tmp_path / "source", {"id": "fixture"}, tmp_path / "judge", {}, {}, grade=grade))
    assert calls == models
    assert (result["status"], result.get("score")) == expected
    assert judge.read(tmp_path / "judge/deepseek/fixture/judge-bu_v1.json")["status"] == original["status"]
    assert result["normal_failures_not_rejudged"]


def test_task_outside_filter_is_rejected(monkeypatch):
    dataset = ModuleType("dataset")
    dataset.load_judge_tasks = lambda: [{"id": "allowed", "instruction": "fixture", "start_url": None}]
    monkeypatch.setitem(sys.modules, "dataset", dataset)
    assert judge.selected_task("allowed")["id"] == "allowed"
    with pytest.raises(ValueError, match="not uniquely present"):
        judge.selected_task("excluded")
