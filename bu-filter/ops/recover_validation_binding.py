"""Finish an ungraded v3 packet when an argument-validation retry repeated the executed code."""
import argparse
import asyncio
from hashlib import sha256
import inspect
import json
from pathlib import Path
import sys
from unittest.mock import patch


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def arguments(part):
    value = part.get("args")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("ordinal", type=int)
    parser.add_argument("--grade", action="store_true")
    args = parser.parse_args()
    run = args.run.resolve()
    job = next(j for j in read(run / "plan.json")["jobs"] if j["ordinal"] == args.ordinal)
    folder, destination = Path(job["source_folder"]), Path(job["judge_folder"])
    grade = destination / "judge-bu_v1.json"
    original_error = "Unsupported native Python tool-return content part"
    if grade.exists() or list(destination.rglob("*.request.json")):
        raise ValueError("Recovery requires an absent grade and zero prior Judge requests")
    assert original_error in (destination / "judge.log").read_text()
    paths = [folder / name for name in ("frames.json", "execution.json", "agent/messages.json", "final_response.txt")]
    paths.append(destination / "judge.log")
    before = {str(p): digest(p) for p in paths}
    sys.path.insert(0, str(run / "frozen/harness"))
    from strict_runtime import load_runtime
    runtime = load_runtime(run)
    import evidence_adapter as adapter

    adapter_hash = digest(Path(adapter.__file__))
    assert adapter_hash == "e7ca6b50950e176e96b76337d7b428de9338f5b8deb8ea1ba64f14f6408b6abf"
    try:
        adapter.bind_observations(folder)
    except adapter.EvidenceBindingError as exc:
        assert str(exc) == original_error
    else:
        raise ValueError("Frozen adapter already supports this trajectory")
    parts = [p for m in read(folder / "agent/messages.json") for p in m.get("parts", [])]
    returns = {p["tool_call_id"]: p for p in parts if p.get("part_kind") == "tool-return"}
    calls = [p for p in parts if p.get("part_kind") == "tool-call" and p.get("tool_name") == "python"]
    rejected = {key for key, p in returns.items() if p.get("tool_name") == "python"
                and p.get("outcome") == "retried" and (p.get("retry") or {}).get("cause") == "validation_error"}
    frames = read(folder / "frames.json")
    pairs = []
    for index, call in enumerate(calls):
        if call["tool_call_id"] not in rejected:
            continue
        code = arguments(call).get("code")
        if not isinstance(code, str):
            continue
        following = [c["tool_call_id"] for c in calls[index + 1:] if arguments(c).get("code") == code
                     and returns.get(c["tool_call_id"], {}).get("outcome") == "success"]
        steps = [i for i, f in enumerate(frames) if f.get("action") == "python " + code]
        if not following or not steps:
            continue
        if len(following) != 1 or len(steps) != 1:
            raise ValueError("Ambiguous repeated code; a unique successful call and frame are required")
        pairs.append({"refused_id": call["tool_call_id"], "executed_id": following[0], "frame_index": steps[0]})
    assert pairs

    # Both observations must also match what was actually sent back to the Actor.
    wire = {}
    needed = {p[k] for p in pairs for k in ("refused_id", "executed_id")}
    for f in sorted((folder / "agent/model_calls").glob("*.request.json")):
        for msg in read(f).get("messages", []):
            key = msg.get("tool_call_id")
            if key in needed and key not in wire and msg.get("role") == "tool":
                value = json.loads(msg["content"])
                expected = returns[key]["content"]
                assert value == ({"error": expected} if key in rejected else expected)
                wire[key] = {"request": f.name, "sha256": digest(f)}
        if wire.keys() == needed:
            break
    assert wire.keys() == needed

    # Reuse the frozen binder, changing only eligibility in its ordered exact-code match.
    # The full transcript, including every rejected call, still reaches _ordered_interactions().
    source = inspect.getsource(adapter.bind_observations)
    predicate = 'if calls[i]["code"] == code'
    assert source.count(predicate) == 1
    fixed = source.replace(predicate, predicate + ' and calls[i]["tool_call_id"] not in rejected_ids')
    namespace = dict(vars(adapter), rejected_ids={p["refused_id"] for p in pairs})
    exec(compile(fixed, "<v3-validation-binding>", "exec"), namespace)
    with patch.object(adapter, "bind_observations", namespace["bind_observations"]):
        _, bindings, unmatched = adapter.bind_observations(folder, frames)
        assert len(bindings) == len(frames)
        for pair in pairs:
            assert bindings[pair["frame_index"]]["tool_call_id"] == pair["executed_id"]
            assert pair["refused_id"] in {u["tool_call_id"] for u in unmatched}
        proof = {"original_judge_requests": 0, "original_judge_error": original_error,
                 "frozen_adapter_sha256": adapter_hash, "recovery_script_sha256": digest(Path(__file__)),
                 "modified_function_sha256": sha256(fixed.encode()).hexdigest(), "source_sha256": before,
                 "ordinal": args.ordinal, "task_id": job["task_id"], "frames_bound": len(bindings),
                 "confirmed_pairs": pairs, "wire_observations": wire}
        audit = run / "technical-recoveries/validation-binding" / job["task_id"]
        audit.mkdir(parents=True, exist_ok=True)
        (audit / "precheck.json").write_text(json.dumps(proof, indent=2) + "\n")
        if args.grade:
            asyncio.run(runtime["grade"](job))
            assert read(grade)["status"] == "judged" and all(digest(p) == before[str(p)] for p in paths)
            proof.update(grade_sha256=digest(grade), score=read(grade)["score"],
                         new_judge_requests=len(list(destination.rglob("*.request.json"))))
            (audit / "completed.json").write_text(json.dumps(proof, indent=2) + "\n")
    print(json.dumps({"ordinal": args.ordinal, "frames": len(frames), "verified_retry_pairs": len(pairs),
                      "grade": read(grade)["score"] if args.grade else None}))


if __name__ == "__main__":
    main()
