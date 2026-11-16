"""Zero-provider tests for the unchanged historical AgentTrek protocol."""
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from PIL import Image
import evaluate
a = evaluate.adapter()

CONFIG = {"api_key": "offline-not-a-real-key", "base_url": "https://judge.invalid/v1",
          "model": "deepseek-v4.1-flash"}
FAILURE = 'Thoughts: Goal not reached.\nStatus: "failure"'
SUCCESS = 'Thoughts: Correct actions were performed.\nStatus: "success"'


def source_fixture(folder, *, images=2):
    (folder / "agent").mkdir(parents=True)
    (folder / "screenshots").mkdir()
    calls, frames, messages = [], [], []
    for i in range(1, images + 1):
        reason = ("why" + str(i)) * 300
        code = "print(" + repr("x" * 700) + ")"
        calls.append({"reasoning": reason, "content": "",
                      "tool_calls": [{"name": "python", "args": {"code": code}}]})
        messages.extend([
            {"kind": "response", "parts": [
                {"part_kind": "thinking", "content": reason},
                {"part_kind": "tool-call", "tool_name": "python", "tool_call_id": "c" + str(i),
                 "args": {"code": code}}]},
            {"kind": "request", "parts": [{"part_kind": "tool-return", "tool_name": "python",
                "tool_call_id": "c" + str(i), "content": ["DO_NOT_APPEND_FULL_STDOUT"]}]},
        ])
        p = folder / "screenshots" / f"{i:04d}.png"
        Image.new("RGB", (8, 8), "red" if i == 1 else "blue").save(p)
        frames.append({"step_num": i, "action": "python " + code, "screenshot_file": str(p.relative_to(folder)),
                       "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    (folder / "task.json").write_text(json.dumps({"id": "fixture"}))
    (folder / "agent/messages.json").write_text(json.dumps(messages))
    (folder / "frames.json").write_text(json.dumps(frames))
    (folder / "final_response.txt").write_text("DO_NOT_APPEND_FINAL_RESPONSE")
    return calls, frames


def streamed(request, text=FAILURE):
    body = json.loads(request.content)
    chunk = {"id": "offline", "object": "chat.completion.chunk", "created": 1,
             "model": body["model"], "choices": [{"index": 0,
             "delta": {"role": "assistant", "content": text}, "finish_reason": None}]}
    stop = {**chunk, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
    wire = "data: " + json.dumps(chunk) + "\n\ndata: " + json.dumps(stop) + "\n\ndata: [DONE]\n\n"
    return httpx.Response(200, headers={"content-type": "text/event-stream",
        "x-litellm-response-cost": "0.0123", "authorization": "must-not-be-recorded"}, stream=httpx.ByteStream(wire.encode()))


class HistoricalSources(unittest.TestCase):
    def test_filtered_247_preserve_original_rows_and_exclusions(self):
        rows = evaluate.tasks()
        source = [json.loads(x) for x in a.DATASET.read_text().splitlines() if x]
        self.assertEqual(len(rows), 247)
        self.assertEqual(len({r['id'] for r in rows}), 247)
        self.assertEqual([r['id'] for r in rows], [r['task_id'] for r in source])
        self.assertEqual([r['instruction'] for r in rows], [r['task_name'] for r in source])
        self.assertEqual(a.EXECUTION_RULES, '')
        self.assertEqual(a.digest(a.DATASET), a.DATASET_SHA256)

    def test_prompt_and_native_limits_are_exact_historical(self):
        n = a.native()
        self.assertEqual(hashlib.sha256(n.PROMPT.SYSTEM_PROMPT.encode()).hexdigest(),
                         "6906e021cb15a3398225fe82232ea5ee61b1cb7489c0bbbd9be4ad82f2000ca9")
        self.assertEqual(n.parse_verdict(FAILURE), 0)
        self.assertEqual(n.parse_verdict(SUCCESS), 1)
        self.assertIsNone(n.parse_verdict("No Status line"))
        self.assertEqual(n.parse_verdict("Status: something else"), 0)

    def test_projection_matches_historical_builder_and_does_not_add_answer_or_returns(self):
        with tempfile.TemporaryDirectory() as td:
            folder, destination = Path(td) / "source", Path(td) / "grade"
            calls, frames = source_fixture(folder)
            trajectory, shot, evidence = a.prepare(folder, destination)
            expected, _, _ = a.native().build_trajectory({"prompt_calls": calls}, destination)
            self.assertEqual(trajectory, expected)
            self.assertNotIn("DO_NOT_APPEND", trajectory)
            self.assertEqual(evidence["thought_limit"], 600)
            self.assertEqual(evidence["action_limit"], 300)
            self.assertFalse(evidence["final_answer_appended"])
            self.assertEqual(len(trajectory.split("Thought 1: ")[1].split("\nAction 1:")[0]), 600)
            self.assertEqual(len(trajectory.split("\nAction 1: ")[1].split("\n\n")[0]), 300)
            final_image = base64.b64decode(shot["image_url"]["url"].split(",", 1)[1])
            self.assertEqual(hashlib.sha256(final_image).hexdigest(), frames[-1]["sha256"])
            self.assertEqual(evidence["n_steps"], 2)
            a.verify_originals(evidence)

    def test_modified_original_screenshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / "source"
            source_fixture(folder)
            (folder / "screenshots/0002.png").write_bytes(b"tampered")
            with self.assertRaisesRegex(AssertionError, "Original PNG changed"):
                a.prepare(folder, Path(td) / "judge")


class HistoricalJudge(unittest.IsolatedAsyncioTestCase):
    async def run_judge(self, folder, destination, handler):
        original_read, request_type = a.read, a.HistoricalRequest
        def safe_read(path):
            return CONFIG if Path(path) == a.ROOT / ".private/model.json" else original_read(path)
        def request(config, destination):
            return request_type(config, destination, transport=httpx.MockTransport(handler))
        with patch.object(a, "read", side_effect=safe_read), patch.object(a, "HistoricalRequest", side_effect=request):
            return await a.judge(folder, {"id": "fixture", "instruction": "Historical task"}, destination)

    async def test_one_call_legacy_wire_messages_last_image_and_legal_failure_cache(self):
        with tempfile.TemporaryDirectory() as td:
            folder, destination = Path(td) / "source", Path(td) / "grade"
            source_fixture(folder)
            seen = []
            def handler(request):
                body = json.loads(request.content)
                seen.append(body)
                return streamed(request)
            result = await self.run_judge(folder, destination, handler)
            again = await self.run_judge(folder, destination, handler)
            self.assertEqual(result["status"], "judged", result)
            self.assertEqual(result["score"], 0)
            self.assertEqual(len(seen), 1)
            body = seen[0]
            self.assertEqual(body["max_tokens"], 4096)
            self.assertEqual(body["reasoning_effort"], "low")
            self.assertEqual(body["seed"], 42)
            self.assertTrue(body["stream"])
            self.assertEqual(body["stream_options"], {"include_usage": True})
            self.assertEqual(body["cache"], {"no-cache": True, "no-store": True})
            self.assertEqual(body["messages"][0]["content"], a.native().PROMPT.SYSTEM_PROMPT)
            self.assertEqual(len([x for x in body["messages"][1]["content"] if x["type"] == "image_url"]), 1)
            self.assertNotIn("DO_NOT_APPEND", json.dumps(body))
            self.assertEqual(again, result)
            billing = a.read(destination / "model_calls/0001.billing.json")
            self.assertNotIn("authorization", json.dumps(billing))
            self.assertTrue((destination / "model_calls/0001.response.json").exists())
            self.assertNotIn(CONFIG["api_key"], (destination / "model_calls/0001.request.json").read_text())

    async def test_content_refusal_only_uses_authorized_fallback_and_keeps_both_receipts(self):
        with tempfile.TemporaryDirectory() as td:
            folder, destination = Path(td) / "source", Path(td) / "grade"
            source_fixture(folder)
            seen = []
            def handler(request):
                model = json.loads(request.content)["model"]
                seen.append(model)
                if model == CONFIG["model"]:
                    return httpx.Response(400, json={"error": {
                        "message": "content inspection", "code": "data_inspection_failed"}})
                return streamed(request, SUCCESS)
            result = await self.run_judge(folder, destination, handler)
            self.assertEqual(result["status"], "judged", result)
            self.assertEqual(result["score"], 1)
            self.assertEqual(seen, [CONFIG["model"], "gpt-6.1-sol"])
            self.assertEqual(result["attempt_count"], 2)
            self.assertEqual(a.read(destination / "model_calls/0001.response.json")["error"]["code"],
                             "data_inspection_failed")
            self.assertTrue((destination / "model_calls/0002.response.json").exists())

    async def test_transient_failures_never_exceed_historical_two_posts(self):
        with tempfile.TemporaryDirectory() as td:
            folder, destination = Path(td) / "source", Path(td) / "grade"
            source_fixture(folder)
            seen = []
            def handler(request):
                seen.append(json.loads(request.content)["model"])
                return httpx.Response(502, json={"error": {"message": "temporary gateway"}})
            result = await self.run_judge(folder, destination, handler)
            again = await self.run_judge(folder, destination, handler)
            self.assertEqual(result["status"], "judge_error")
            self.assertEqual(again["status"], "judge_error")
            self.assertEqual(seen, [CONFIG["model"], CONFIG["model"]])
            self.assertEqual(len(a.read(destination / "attempt-budget.json")["attempts"]), 2)

    async def test_unrelated_400_does_not_trigger_fallback_or_retry(self):
        with tempfile.TemporaryDirectory() as td:
            folder, destination = Path(td) / "source", Path(td) / "grade"
            source_fixture(folder)
            seen = []
            def handler(request):
                seen.append(request)
                return httpx.Response(400, json={"error": {"message": "bad argument", "code": "invalid_request"}})
            result = await self.run_judge(folder, destination, handler)
            self.assertEqual(result["status"], "judge_error")
            self.assertEqual(len(seen), 1)

    async def test_unparseable_output_is_unknown_not_rejudged_into_success(self):
        with tempfile.TemporaryDirectory() as td:
            folder, destination = Path(td) / "source", Path(td) / "grade"
            source_fixture(folder)
            seen = []
            def handler(request):
                seen.append(request)
                return streamed(request, "No valid verdict returned")
            result = await self.run_judge(folder, destination, handler)
            self.assertEqual(result["status"], "judge_error")
            self.assertEqual(len(seen), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
