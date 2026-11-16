"""Free equivalence checks for the frozen df93 evaluation implementation."""
import ast
import asyncio
import hashlib
import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from legacy import environment_bindings as bindings

LEGACY = ROOT / "legacy"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def policy(text):
    tree = ast.parse(text)
    return ast.literal_eval(next(n.value for n in tree.body if isinstance(n, ast.Assign)
                                and any(isinstance(t, ast.Name) and t.id == "policy" for t in n.targets)))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def frozen(tmp_path):
    support = tmp_path / "support"
    module = bindings.install(tmp_path, support, LEGACY / "code", sys.executable)
    return module, support


def test_all_original_source_bytes_match_pinned_origin_hashes():
    manifest = bindings.verify_frozen()
    for name, entry in manifest["files"].items():
        assert sha((LEGACY / name).read_bytes()) == entry["sha256"]
        if entry.get("copied_verbatim"):
            assert entry["sha256"] == entry["source_sha256"]


def test_actor300_is_only_one_budget_assertion_change_from_df93():
    original = (LEGACY / "reference/df93-actor.py.txt").read_text()
    used = (LEGACY / "actor.py").read_text()
    before = "assert check_config.max_steps == 100 and check_config.timeout_seconds == 3600"
    after = "assert check_config.max_steps == 300 and check_config.timeout_seconds == 3600"
    assert original.count(before) == 1
    assert original.replace(before, after) == used
    assert policy(original) == policy(used)
    assert sha(policy(used).encode()) == "853bb13f8dd4cdfd8aac55acd1c351c1eb3830d47f789be925320d212e1b7d5a"


def test_binding_changes_paths_without_rewriting_worker_or_judge(frozen):
    module, support = frozen
    assert module.ROOT == support
    assert module.BU == LEGACY / "upstream"
    assert module.LEGACY_PYTHON == Path(sys.executable).absolute()
    manifest = bindings.verify_frozen()
    symbols = manifest["frozen_symbols_sha256"]["code/full_benchmarks.py"]
    text = (LEGACY / "code/full_benchmarks.py").read_text()
    tree = ast.parse(text)
    for name, expected in symbols.items():
        node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
        assert sha(ast.get_source_segment(text, node).encode()) == expected
        assert Path(inspect.getsourcefile(getattr(module, name))).resolve() == LEGACY / "code/full_benchmarks.py"
    module.verify()
    assert json.loads((support / "sources.json").read_text()) == module._bu_filter_bindings["source_record"]


@pytest.mark.parametrize("model,limit_key", [("deepseek-v4.1-flash", "max_tokens"), ("gpt-6.1-sol", "max_completion_tokens")])
def test_original_model_payload_offline(frozen, tmp_path, monkeypatch, model, limit_key):
    import httpx
    import openai
    from openai.types.chat import ChatCompletion

    module, support = frozen
    write(support / ".private/model.json", {"api_key": "offline-fixture", "base_url": "https://example.invalid/v1", "model": "deepseek-v4.1-flash"})
    evidence = sys.modules["evidence_adapter"]
    trace = {"agent_steps": ["Synthetic observed result"], "final_result": "Synthetic answer", "screenshots_b64": []}
    monkeypatch.setattr(evidence, "prepare", lambda *args: (trace, {}))
    monkeypatch.setattr(evidence, "verify_originals", lambda *args: None)
    captured = []
    settings = []

    class HTTP:
        def __init__(self, **kwargs):
            settings.append({"http_timeout": kwargs["timeout"]})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class API:
        async def create(self, **kwargs):
            captured.append(kwargs)
            return ChatCompletion.model_validate({"id": "fixture", "object": "chat.completion", "created": 0,
                "model": model, "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": '{"verdict":false}'}}]})

    class Client:
        def __init__(self, **kwargs):
            settings.append({"sdk_retries": kwargs["max_retries"], "sdk_timeout": kwargs["timeout"]})
            self.chat = SimpleNamespace(completions=API())

    monkeypatch.setattr(httpx, "AsyncClient", HTTP)
    monkeypatch.setattr(openai, "AsyncOpenAI", Client)
    result = asyncio.run(module.judge_model(tmp_path / "source", "bu_v1", {"id": "fixture", "instruction": "Synthetic task"}, tmp_path / "judge", model_name=model))
    assert result["status"] == "judged" and result["score"] == 0
    assert len(captured) == 1
    request = captured[0]
    assert request["model"] == model and request["reasoning_effort"] == "low"
    assert request[limit_key] == 16384
    assert request["extra_body"] == {"allowed_openai_params": ["reasoning_effort"]}
    assert request["response_format"] == {"type": "json_object"}
    official = module.module_at("offline_reference_judge", LEGACY / "upstream/judge.py")
    expected = official.construct_judge_messages(task="Synthetic task", ground_truth=None, **trace)
    assert request["messages"] == [m.model_dump(exclude_none=True) for m in expected]
    assert settings == [{"http_timeout": 600}, {"sdk_retries": 2, "sdk_timeout": 600}]


@pytest.mark.parametrize("original,replacement,expected_models,expected_score", [
    ({"status": "judged", "score": 0}, None, ["deepseek-v4.1-flash"], 0),
    ({"status": "judge_error", "error": "APIConnectionError"}, None, ["deepseek-v4.1-flash"], None),
    ({"status": "judge_error", "error": "HTTP400 data_inspection_failed"}, {"status": "judged", "score": 1}, ["deepseek-v4.1-flash", "gpt-6.1-sol"], 1),
])
def test_original_refusal_routing_does_not_rejudge_valid_failures(frozen, tmp_path, monkeypatch, original, replacement, expected_models, expected_score):
    module, _ = frozen
    models = []

    async def grade(folder, suite, task, destination, *, model_name="deepseek-v4.1-flash"):
        models.append(model_name)
        result = dict(original if len(models) == 1 else replacement, judge_http_requests=1)
        write(destination / "judge-bu_v1.json", result)
        return result

    monkeypatch.setattr(module, "judge_model", grade)
    result = asyncio.run(module.judge(tmp_path / "source", "bu_v1", {"id": "fixture"}, tmp_path / "judgements"))
    assert models == expected_models
    assert result.get("score") == expected_score
    assert result["normal_failures_not_rejudged"]
