import hashlib
import json
from pathlib import Path

import pytest
import evidence_adapter as evidence



def fixture(folder, codes, outputs):
    (folder / "agent").mkdir(parents=True)
    messages, frames = [], []
    for i, (code, text) in enumerate(zip(codes, outputs), 1):
        call = "call-" + str(i)
        messages.append({"parts": [{"part_kind": "tool-call", "tool_name": "python",
                                  "tool_call_id": call, "args": {"code": code}}]})
        messages.append({"parts": [{"part_kind": "tool-return", "tool_name": "python",
                                  "tool_call_id": call, "content": [text]}]})
        frames.append({"step_num": i, "action": "python " + code,
                       "response": ("UNBOUNDED FULL STDOUT " * 2000) + "\nObserved tabs: []"})
    (folder / "agent/messages.json").write_text(json.dumps(messages))
    (folder / "frames.json").write_text(json.dumps(frames))
    (folder / "final_response.txt").write_text("Final answer unchanged")
    return messages, frames


def test_repeated_code_is_bound_by_order_and_call_id(tmp_path):
    folder = tmp_path / "source"
    fixture(folder, ["print(x)", "print(x)", "print(y)"], ["first", "second", "third"])
    observations, bindings, unexecuted = evidence.bind_observations(folder)
    assert observations == ["first", "second", "third"]
    assert [b["tool_call_id"] for b in bindings] == ["call-1", "call-2", "call-3"]
    assert not unexecuted
    assert all(b["original_full_stdout"]["stdout_characters"] > b["actual_observation_characters"] for b in bindings)


def test_code_mismatch_is_rejected_instead_of_guessed(tmp_path):
    folder = tmp_path / "source"
    _, frames = fixture(folder, ["print(x)"], ["actual observation"])
    frames[0]["action"] = "python print(unrelated)"
    (folder / "frames.json").write_text(json.dumps(frames))
    with pytest.raises(evidence.EvidenceBindingError, match="No ordered exact"):
        evidence.bind_observations(folder)


def test_missing_native_transcript_is_explicit(tmp_path):
    folder = tmp_path / "source"; folder.mkdir()
    (folder / "frames.json").write_text("[]")
    with pytest.raises(evidence.EvidenceBindingError, match="Missing native transcript"):
        evidence.bind_observations(folder)


def test_actual_native_text_is_never_clipped_again(tmp_path):
    folder = tmp_path / "source"
    actual = "Preserve every character.\n" * 2000
    fixture(folder, ["print(large)"], [actual])
    _, manifest = evidence.prepare(folder, "odysseys", tmp_path / "judge")
    rows = [json.loads(line) for line in (tmp_path / "judge/steps.jsonl").open()]
    assert rows[0]["response"] == actual
    assert rows[1]["response"] == "Final answer unchanged"
    assert manifest["max_chars"] is None and manifest["omitted"] == []
    assert manifest["actual_observation_characters"] == len(actual)
    evidence.verify_originals(manifest)




def test_unexecuted_validation_error_remains_structured(tmp_path):
    folder = tmp_path / "source"
    messages, frames = fixture(folder, ["print(x)"], ["actual"])
    rejected = [{"type": "missing", "loc": ["code"], "msg": "Field required", "input": {}}]
    messages.extend([
        {"parts": [{"part_kind": "tool-call", "tool_name": "python", "tool_call_id": "rejected", "args": {}}]},
        {"parts": [{"part_kind": "tool-return", "tool_name": "python", "tool_call_id": "rejected", "content": rejected}]},
    ])
    (folder / "agent/messages.json").write_text(json.dumps(messages))
    observations, bindings, unexecuted = evidence.bind_observations(folder)
    assert observations == ["actual"] and len(bindings) == 1
    assert unexecuted[0]["native_return_content"] == rejected
    evidence.prepare(folder, "odysseys", tmp_path / "judge")
    rows = [json.loads(line) for line in (tmp_path / "judge/steps.jsonl").open()]
    assert rows[1]["record_type"] == "unexecuted_tool_call"
    assert json.loads(rows[1]["response"]) == rejected
    assert rows[1]["screenshot_file"] is None
    assert rows[2]["final"] is True




def test_output_tool_retries_are_full_native_history(tmp_path):
    folder = tmp_path / "source"
    messages, _ = fixture(folder, ["print(x)"], ["observed"])
    messages.extend([
        {"parts": [{"part_kind": "tool-call", "tool_name": "finish_from_repl", "tool_call_id": "bad-finish", "args": {"expression": "missing"}}]},
        {"parts": [{"part_kind": "retry-feedback", "tool_name": "finish_from_repl", "tool_call_id": "bad-finish", "content": {"error": "NameError: missing"}}]},
        {"parts": [{"part_kind": "tool-call", "tool_name": "finish", "tool_call_id": "good-finish", "args": {"result": "final"}}]},
        {"parts": [{"part_kind": "tool-return", "tool_name": "finish", "tool_call_id": "good-finish", "content": "Final result processed"}]},
    ])
    (folder / "agent/messages.json").write_text(json.dumps(messages))
    _, manifest = evidence.prepare(folder, "odysseys", tmp_path / "judge")
    rows = [json.loads(line) for line in (tmp_path / "judge/steps.jsonl").open()]
    assert [r.get("tool_call_id") for r in rows[:-1]] == ["call-1", "bad-finish", "good-finish"]
    assert json.loads(rows[1]["response"]) == {"error": "NameError: missing"}
    assert rows[1]["record_type"] == "native_output_tool_call"
    assert rows[-1]["response"] == "Final answer unchanged"
    assert manifest["executed_frame_count"] == 1 and manifest["record_count"] == 3
