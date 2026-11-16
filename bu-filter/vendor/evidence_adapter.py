"""Native observation evidence adapter for unchanged official benchmark judges.

Version 3 corrects the former full-output-file projection: every executed frame is
bound to its original Python tool call and its native tool-return text. No second
truncation is performed. Complete stdout files remain immutable source evidence.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from evidence_ranges import VERSION, bounded_units


class EvidenceBindingError(ValueError):
    """Recorded frames cannot be bound to the native transcript without guessing."""


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text_digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _native_text(content):
    if isinstance(content, str):
        return content, [content], 0
    if not isinstance(content, list):
        raise EvidenceBindingError("Python tool-return content is neither a string nor a list")
    strings, binary_count = [], 0
    for item in content:
        if isinstance(item, str):
            strings.append(item)
        elif isinstance(item, dict) and (
            item.get("kind") == "binary" or ("data" in item and "media_type" in item)
        ):
            binary_count += 1
        else:
            raise EvidenceBindingError("Unsupported native Python tool-return content part")
    # Python returns [text, *images]. If image pruning inserted string markers,
    # preserve those exact strings too; the original list remains in messages.json.
    return "\n".join(strings), strings, binary_count


def _raw_stdout(frame, folder, frame_index):
    full = str(frame.get("response", ""))
    stdout = full
    prefix, marker, tail = full.rpartition("\nObserved tabs: ")
    if marker:
        try:
            tabs = json.loads(tail)
        except (ValueError, TypeError):
            tabs = None
        if isinstance(tabs, list):
            stdout = prefix
    source = {
        "file": str(folder / "frames.json"),
        "json_pointer": "/" + str(frame_index) + "/response",
        "frame_response_characters": len(full),
        "frame_response_sha256": text_digest(full),
        "stdout_characters": len(stdout),
        "stdout_sha256": text_digest(stdout),
    }
    # This conventional path is only recorded when its actual bytes agree with
    # the archived full stdout; a mismatch is not repaired by guessing a path.
    candidate = folder / "agent/workspace/.browser-use/cells" / f"{frame.get('step_num', frame_index + 1):04d}.txt"
    if candidate.is_file():
        candidate_text = candidate.read_text(errors="replace")
        if candidate_text == stdout:
            source["verified_output_file"] = str(candidate)
            source["verified_output_file_sha256"] = digest(candidate)
    return source


def bind_observations(folder, frames=None):
    folder = Path(folder).resolve()
    frames_path, messages_path = folder / "frames.json", folder / "agent/messages.json"
    if not messages_path.is_file():
        raise EvidenceBindingError("Missing native transcript: " + str(messages_path))
    if frames is None:
        if not frames_path.is_file():
            raise EvidenceBindingError("Missing executed frame ledger: " + str(frames_path))
        frames = json.loads(frames_path.read_text())
    messages = json.loads(messages_path.read_text())
    calls, returns = [], {}
    for message_index, message in enumerate(messages):
        for part_index, part in enumerate(message.get("parts", [])):
            kind = part.get("part_kind")
            if kind == "tool-call" and part.get("tool_name") == "python":
                args = part.get("args")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except ValueError:
                        args = None
                code = args.get("code") if isinstance(args, dict) else None
                calls.append({
                    "tool_call_id": part.get("tool_call_id"), "code": code,
                    "message_index": message_index, "part_index": part_index,
                })
            elif kind == "tool-return":
                key = part.get("tool_call_id")
                if key in returns and returns[key][0] != part:
                    raise EvidenceBindingError("Conflicting native tool-return IDs: " + str(key))
                returns[key] = (part, message_index, part_index)
    observations, bindings, offset, matched_call_indices = [], [], 0, set()
    for frame_index, frame in enumerate(frames):
        action = frame.get("action")
        if not isinstance(action, str) or not action.startswith("python "):
            raise EvidenceBindingError("Frame does not contain an exact Python action: " + str(frame_index + 1))
        code = action[len("python "):]
        found = next((i for i in range(offset, len(calls)) if calls[i]["code"] == code), None)
        if found is None:
            raise EvidenceBindingError("No ordered exact native code match for frame " + str(frame_index + 1))
        call = calls[found]
        offset = found + 1
        matched_call_indices.add(found)
        if call["tool_call_id"] not in returns:
            raise EvidenceBindingError("No native tool-return for frame " + str(frame_index + 1))
        part, message_index, part_index = returns[call["tool_call_id"]]
        if part.get("tool_name") != "python":
            raise EvidenceBindingError("Bound tool-return is not Python")
        text, strings, binary_count = _native_text(part.get("content"))
        observations.append(text)
        bindings.append({
            "step": frame.get("step_num", frame_index + 1),
            "frame_index": frame_index,
            "tool_call_id": call["tool_call_id"],
            "native_call_message_index": call["message_index"],
            "native_call_part_index": call["part_index"],
            "native_return_message_index": message_index,
            "native_return_part_index": part_index,
            "native_return_source": {
                "file": str(messages_path),
                "json_pointer": f"/{message_index}/parts/{part_index}/content",
            },
            "python_code_sha256": text_digest(code),
            "actual_observation_characters": len(text),
            "actual_observation_sha256": text_digest(text),
            "native_text_part_count": len(strings),
            "native_binary_part_count": binary_count,
            "second_text_truncation": False,
            "original_full_stdout": _raw_stdout(frame, folder, frame_index),
        })
    unmatched = []
    for i, call in enumerate(calls):
        if i not in matched_call_indices:
            returned = returns.get(call["tool_call_id"])
            content = returned[0].get("content") if returned else None
            # Unexecuted/refused calls have no after_tool frame. Their complete
            # source is retained and explicitly identified, never guessed away.
            unmatched.append({
                "tool_call_id": call["tool_call_id"],
                "native_call_message_index": call["message_index"],
                "native_call_part_index": call["part_index"],
                "code_sha256": text_digest(call["code"]) if isinstance(call["code"], str) else None,
                "native_return_content": content,
                "reason": "no_executed_frame_in_original_after_tool_ledger",
            })
    return observations, bindings, unmatched



def _feedback_text(content):
    """Serialize structured native feedback completely; do not reinterpret it."""
    if isinstance(content, str):
        return content, "native_string"
    if isinstance(content, list) and all(
        isinstance(v, str) or (isinstance(v, dict) and (v.get("kind") == "binary" or ("data" in v and "media_type" in v)))
        for v in content
    ):
        return _native_text(content)[0], "native_text_parts"
    return json.dumps(content, ensure_ascii=False), "native_structured_content_json"


def _ordered_interactions(folder, bindings):
    messages = json.loads((folder / "agent/messages.json").read_text())
    frame_by_call = {b["tool_call_id"]: b["frame_index"] for b in bindings}
    calls, feedback, free_feedback = [], {}, []
    all_call_ids = {
        part.get("tool_call_id")
        for m in messages for part in m.get("parts", [])
        if part.get("part_kind") == "tool-call"
    }
    for mi, message in enumerate(messages):
        for pi, part in enumerate(message.get("parts", [])):
            kind = part.get("part_kind")
            source = {"message_index": mi, "part_index": pi}
            if kind == "tool-call":
                calls.append((part, source))
            elif kind in {"tool-return", "retry-feedback", "retry-prompt"}:
                key = part.get("tool_call_id")
                item = (part, source)
                if key is not None and key in all_call_ids:
                    feedback.setdefault(key, []).append(item)
                else:
                    free_feedback.append(item)
    result = []
    for part, source in calls:
        key = part.get("tool_call_id")
        pieces, formats, origins = [], [], []
        for returned, returned_source in feedback.get(key, []):
            text, fmt = _feedback_text(returned.get("content"))
            pieces.append(text)
            formats.append(fmt)
            origins.append({**returned_source, "part_kind": returned.get("part_kind")})
        result.append({
            **source, "tool_call_id": key, "tool_name": part.get("tool_name"),
            "arguments": part.get("args"), "frame_index": frame_by_call.get(key),
            "response": "\n".join(pieces), "response_formats": formats,
            "feedback_sources": origins, "has_recorded_return": bool(origins),
            "record_type": "executed_python_cell" if key in frame_by_call else (
                "unexecuted_tool_call" if part.get("tool_name") == "python" else "native_output_tool_call"
            ),
        })
    for part, source in free_feedback:
        text, fmt = _feedback_text(part.get("content"))
        result.append({
            **source, "tool_call_id": part.get("tool_call_id"), "tool_name": part.get("tool_name"),
            "arguments": None, "frame_index": None, "response": text,
            "response_formats": [fmt], "feedback_sources": [{**source, "part_kind": part.get("part_kind")}],
            "has_recorded_return": True, "record_type": "native_retry_feedback",
            "native_feedback_part": part,
        })
    return sorted(result, key=lambda x: (x["message_index"], x["part_index"]))


def prepare(folder, suite, destination):
    folder, destination = Path(folder).resolve(), Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    frames_path = folder / "frames.json"
    if not frames_path.is_file():
        raise EvidenceBindingError("Missing executed frame ledger: " + str(frames_path))
    frames = json.loads(frames_path.read_text())
    observations, bindings, unexecuted = bind_observations(folder, frames)
    final_path = folder / "final_response.txt"
    final = final_path.read_text() if final_path.exists() else ""
    records, rows, images, image_refs = [], [], [], []
    interactions = _ordered_interactions(folder, bindings)
    for i, (frame, response, binding) in enumerate(zip(frames, observations, bindings), 1):
        screenshot = None
        if frame.get("screenshot_file"):
            screenshot = (folder / frame["screenshot_file"]).resolve()
            if not screenshot.is_relative_to((folder / "screenshots").resolve()):
                raise ValueError("Screenshot is outside its task capture directory")
            data = screenshot.read_bytes()
            if hashlib.sha256(data).hexdigest() != frame.get("sha256"):
                raise ValueError("Recorded screenshot hash changed")
            if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("Recorded screenshot is not PNG")
            if suite == "bu_v1":
                images.append(base64.b64encode(data).decode())
            image_refs.append({"step": i, "path": str(screenshot), "sha256": hashlib.sha256(data).hexdigest()})
        records.append({
            "native_history_step": frame.get("step_num", i),
            "action": frame.get("action", ""),
            "native_result": {
                "error": frame.get("tool_error"),
                "output_source": "Original native Python tool-return text, bound by ordered code and tool_call_id",
            },
            "url": frame.get("url"),
            "observation_id": "cell-" + str(i),
            "observed_text": response,
            "screenshot": str(screenshot) if screenshot else None,
            "screenshot_sha256": frame.get("sha256"),
            "capture_missing_reason": frame.get("capture_error"),
        })
        rows.append({
            "step_num": i, "action": frame.get("action", ""), "response": response,
            "screenshot_file": str(screenshot) if screenshot else None,
            "tool_call_id": binding["tool_call_id"],
            "tool_error": frame.get("tool_error"), "capture_error": frame.get("capture_error"),
        })
    frame_records, frame_rows = records, rows
    records, rows, interaction_manifest = [], [], []
    for interaction in interactions:
        frame_index = interaction["frame_index"]
        if frame_index is not None:
            record, row = dict(frame_records[frame_index]), dict(frame_rows[frame_index])
            record["record_type"] = "executed_python_cell"
            row["record_type"] = "executed_python_cell"
        else:
            tool_name = str(interaction.get("tool_name") or "")
            if interaction["record_type"] == "native_retry_feedback":
                action = "native_retry_feedback"
            else:
                prefix = "unexecuted_tool_call " if interaction["record_type"] == "unexecuted_tool_call" else "native_tool_call "
                action = prefix + tool_name + " " + json.dumps(interaction["arguments"], ensure_ascii=False)
            record = {
                "native_history_step": None, "record_type": interaction["record_type"],
                "action": action, "native_result": {
                    "recorded_return": interaction["has_recorded_return"],
                    "output_source": "Complete original native tool feedback; not a Python execution frame",
                },
                "observed_text": interaction["response"], "screenshot": None,
                "observation_id": "native-tool-" + str(interaction["tool_call_id"]),
            }
            row = {
                "action": action, "response": interaction["response"], "screenshot_file": None,
                "record_type": interaction["record_type"], "tool_call_id": interaction["tool_call_id"],
            }
        record["tool_call_id"] = interaction["tool_call_id"]
        record["native_message_index"] = interaction["message_index"]
        record["native_part_index"] = interaction["part_index"]
        row["step_num"] = len(rows) + 1
        rows.append(row)
        records.append(record)
        interaction_manifest.append({
            **interaction, "submitted_record_index": len(records) - 1,
            "response_characters": len(interaction["response"]),
            "response_sha256": text_digest(interaction["response"]),
        })
    if final:
        rows.append({"step_num": len(rows) + 1, "action": "final_response", "response": final, "final": True})
    source_files = [
        p for p in (
            frames_path, folder / "agent/messages.json", final_path,
            folder / "execution.json", folder / "steps.jsonl",
        ) if p.exists()
    ]
    manifest = {
        "version": VERSION, "suite": suite, "source_folder": str(folder),
        "source_files": {str(p): digest(p) for p in source_files},
        "record_count": len(records), "executed_frame_count": len(frames), "screenshots": image_refs,
        "native_interactions": interaction_manifest,
        "full_records_sha256": hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "selection_uses_task_answer_rubric_or_score": False,
        "observation_source": "native.messages Python tool-return strings; no extra clipping",
        "cell_bindings": bindings, "unexecuted_python_calls_without_frames": unexecuted,
        "original_stdout_characters": sum(b["original_full_stdout"]["stdout_characters"] for b in bindings),
        "original_frame_response_characters": sum(b["original_full_stdout"]["frame_response_characters"] for b in bindings),
        "actual_observation_characters": sum(len(x) for x in observations),
        "all_executed_frames_bound": len(bindings) == len(frames),
        "official_judge_prompt_parser_and_scoring_changed": False,
    }
    if suite == "bu_v1":
        steps, omitted = bounded_units(records, 39000)
        trace = {"agent_steps": steps, "final_result": final, "screenshots_b64": images}
        manifest.update(
            max_chars=39000, retained_records=len(steps) - 1,
            submitted_characters=len("\n".join(steps)),
            retained_unit_indices=[json.loads(s)["evidence_unit_index"] for s in steps[1:]],
            omitted=omitted,
        )
        write(destination / "trace.json", {**trace, "screenshots_b64": image_refs})
    else:
        trace = None
        manifest.update(
            max_chars=None, retained_records=len(records), omitted=[],
            protocol="official full executed native action history, actual tool returns, unlimited screenshots",
            submitted_history_characters=len("\n".join(f"{i}. Response: {r['response'].strip()}\nAction: {r['action'].strip()}" for i, r in enumerate(rows, 1))),
        )
        (destination / "steps.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    write(destination / "evidence-manifest.json", manifest)
    return trace, manifest


def verify_originals(manifest):
    for name, expected in manifest["source_files"].items():
        if digest(name) != expected:
            raise RuntimeError("Original trajectory changed while grading: " + name)
    for image in manifest.get("screenshots", []):
        if digest(image["path"]) != image["sha256"]:
            raise RuntimeError("Original screenshot changed while grading: " + image["path"])
