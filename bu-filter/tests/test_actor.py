import asyncio
import base64
import copy
import sys
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import actor


def settings():
    return {"agent": {"model": "deepseek-v4.1-flash", "reasoning_effort": "high", "mode": "ultrafast",
                      "max_steps": 300, "timeout_seconds": 3600, "max_context_chars": None}}


def test_actor_rejects_reference_answer_in_public_input(tmp_path):
    path = tmp_path / "task.json"
    actor.write(path, {"id": "fixture", "instruction": "Read the page", "start_url": None, "answer": "hidden"})
    with pytest.raises(ValueError, match="exactly"):
        actor.public_task(path)


def test_direct_actor_rejects_excluded_task_before_credentials_or_browser(tmp_path, monkeypatch):
    excluded = "1bab296c-8836-453f-9008-5e5cae260cea"
    actor.write(tmp_path / "task.json", {"id": excluded, "instruction": "Excluded task", "start_url": None})
    dataset = ModuleType("dataset")

    def allowlisted(task):
        if task["id"] == excluded:
            raise ValueError("Excluded task id")
        return task

    dataset.actor_task = allowlisted
    monkeypatch.setitem(sys.modules, "dataset", dataset)
    # No product path or credentials are supplied. Reaching either dependency
    # would fail differently, so this covers the real direct Actor entry path.
    with pytest.raises(ValueError, match="Excluded task id"):
        asyncio.run(actor.run(tmp_path, {}))


@pytest.mark.parametrize("changed", ["version", "files_sha256", "package_versions", "missing"])
def test_environment_drift_is_rejected_before_credentials_or_browser(tmp_path, monkeypatch, changed):
    actor.write(tmp_path / "task.json", {"id": "allowed-fixture", "instruction": "Fixture", "start_url": None})
    dataset = ModuleType("dataset")
    dataset.actor_task = lambda task: task
    monkeypatch.setitem(sys.modules, "dataset", dataset)
    monkeypatch.setattr(actor, "configure_source", lambda settings: tmp_path)
    expected = {"version": "1.0.3", "files_sha256": {"agent/loop.py": "frozen"},
                "package_versions": {"browser-use": "1.0.3", "openai": "3.50.0"}}
    actual = {"engine_version": expected["version"], "engine_files_sha256": copy.deepcopy(expected["files_sha256"]),
              "package_versions": copy.deepcopy(expected["package_versions"])}
    if changed == "version":
        actual["engine_version"] = "1.0.3+changed"
    elif changed == "files_sha256":
        actual["engine_files_sha256"]["agent/loop.py"] = "changed-source"
    elif changed == "package_versions":
        actual["package_versions"]["openai"] = "changed-dependency"
    monkeypatch.setattr(actor, "runtime_provenance", lambda project: actual)
    settings = {} if changed == "missing" else {"expected_engine": expected}
    # No credential location or browser settings exist. The frozen-runtime
    # check must reject before execution reaches either of those operations.
    with pytest.raises((RuntimeError, ValueError), match="preflight"):
        asyncio.run(actor.run(tmp_path, settings))
    assert not (tmp_path / "agent").exists()


def test_evaluation_does_not_force_product_features():
    result = actor.model_config(settings(), {"api_key": "fixture", "base_url": "https://example.invalid/v1"})
    assert result["max_steps"] == 300 and result["timeout_seconds"] == 3600
    assert "review_answer" not in result and "public_source_lookup" not in result
    assert "track_task_progress" not in result


def test_document_change_during_capture_is_preserved_as_missing_screenshot(tmp_path):
    count = 0

    def daemon(name, payload, timeout):
        nonlocal count
        if payload["method"] == "Page.getFrameTree":
            count += 1
            return {"result": {"frameTree": {"frame": {"id": "page", "url": "https://example.invalid/", "loaderId": str(count)}}}}
        return {"result": {"data": base64.b64encode(b"not-used").decode()}}

    observer = actor.Observer(SimpleNamespace(name="fixture"), tmp_path, daemon)
    result = observer.capture(1)
    assert result["screenshot_file"] is None
    assert "Document changed" in result["capture_error"]
    assert not (tmp_path / "screenshots").exists()


def test_observer_records_exact_executed_code_and_full_archived_stdout(tmp_path):
    observer = actor.Observer(SimpleNamespace(name="fixture"), tmp_path, None)
    observer.capture = lambda n: {"step_num": n, "screenshot_file": None, "capture_seconds": 0, "capture_error": "fixture"}
    full = tmp_path / "output.txt"
    full.write_text("complete source output")
    asyncio.run(observer.after_tool("python", {"code": "print(value)"}, {"output_file": str(full), "output": "clipped", "error": None}))
    asyncio.run(observer.after_tool("finish", {}, {}))
    frames = actor.read(tmp_path / "frames.json")
    assert len(frames) == 1 and frames[0]["action"] == "python print(value)"
    assert frames[0]["response"] == "complete source output\nObserved tabs: []"
