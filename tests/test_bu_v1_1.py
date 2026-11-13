"""1.1 contracts: no network/model calls except an explicitly synthetic local gateway."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from lexmount_v1_1.data import ROOT, context, select, tasks
from lexmount_v1_1.executors import union_seconds, usage_summary
from lexmount_v1_1.judging import (
    adjudicate,
    estimate_cost,
    http_judge,
    make_input,
    parse_verdict,
)
from lexmount_v1_1.storage import read


def verdict(category="pass"):
    return {
        "category": category,
        "verdict": {"pass": True, "fail": False}.get(category),
        "reason": "Synthetic test evidence supports this classification",
        "evidence_refs": ["final_result"],
    }


def response(value, finish="stop"):
    return {
        "choices": [
            {"finish_reason": finish, "message": {"content": json.dumps(value)}}
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


class DatasetTests(unittest.TestCase):
    def test_identity_order_quarantine_and_common_anchor(self):
        from frameworks import interleave, load_tasks

        rows = tasks("2026-11-13T00:30:00Z")
        old = interleave(load_tasks("BU_Bench_V1"))
        self.assertEqual([r["task_id"] for r in rows], [r["task_id"] for r in old])
        self.assertEqual([r["ordinal"] for r in rows], list(range(1, 101)))
        self.assertEqual(
            [r["ordinal"] for r in rows if r["eligibility"] != "eligible"], [19]
        )
        self.assertEqual(select(rows, [20])[0]["ordinal"], 20)
        for a, b in zip(rows, old):
            self.assertEqual(a["category"], b["category"])
        changed = [
            i + 1
            for i, (a, b) in enumerate(zip(rows, old))
            if a.get("answer") != b.get("answer")
        ]
        self.assertEqual(changed, [84])
        self.assertEqual(
            context("2026-11-13T00:30:00Z")["window_start_date"], "2026-11-10"
        )
        self.assertTrue(all("{{" not in r["confirmed_task"] for r in rows))
        with self.assertRaises(ValueError):
            context("2026-11-13T00:30:00")
        with self.assertRaises(ValueError):
            select(rows, [1, 1])

    def test_evidence_packing_and_conflicting_legacy_prompt_removed(self):
        row = tasks("2026-11-13T00:30:00Z")[3]
        trace = {
            "final_result": "test",
            "steps": ["A" * 50000, "not sent"],
            "screenshots_b64": [],
        }
        frozen = make_input(row, trace, context("2026-11-13T00:30:00Z"))
        system = frozen["messages"][0]["content"]
        self.assertNotIn("ABSOLUTE precedence", system)
        self.assertEqual(frozen["evidence_refs"], ["final_result", "trajectory"])
        self.assertNotIn("not sent", json.dumps(frozen["messages"]))


class JudgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "judge"
        self.frozen = {
            "task_id": "synthetic",
            "ordinal": 1,
            "messages": [],
            "evidence_refs": ["final_result"],
            "evidence_sha256": "frozen",
        }
        self.config = {
            "model": "synthetic",
            "base_url": "http://127.0.0.1",
            "api_key": "test-only",
            "timeout": 1,
            "max_tokens": 100,
            "rates": None,
        }

    async def test_valid_fail_never_retried(self):
        calls = []

        async def transport(payload, config):
            calls.append(payload)
            return response(verdict("fail"))

        result = await adjudicate(self.folder, self.frozen, self.config, transport)
        self.assertEqual(result["reward"], 0)
        self.assertEqual(len(calls), 1)
        await adjudicate(self.folder, self.frozen, self.config, transport)
        self.assertEqual(len(calls), 1)

    async def test_truncation_retry_same_evidence_and_append_only(self):
        calls = []

        async def transport(payload, config):
            calls.append(payload)
            return response(verdict(), "length" if len(calls) == 1 else "stop")

        result = await adjudicate(self.folder, self.frozen, self.config, transport)
        self.assertEqual(result["verdict_source"], "bounded_rejudge")
        self.assertEqual(calls[0], calls[1])
        records = [read(p) for p in sorted(self.folder.glob("attempt-*.json"))]
        self.assertEqual(len({r["input_sha256"] for r in records}), 1)
        with self.assertRaises(ValueError):
            await adjudicate(
                self.folder,
                {**self.frozen, "evidence_sha256": "changed"},
                self.config,
                transport,
            )

    async def test_bad_schema_exhausts_bounded_recovery(self):
        async def transport(payload, config):
            return response({**verdict(), "verdict": "true"})

        result = await adjudicate(self.folder, self.frozen, self.config, transport)
        self.assertEqual(result["category"], "judge_error")
        self.assertIsNone(result["reward"])
        self.assertEqual(result["attempt_count"], 3)
        self.assertEqual(len(list(self.folder.glob("attempt-*.json"))), 3)

    async def test_reference_conflict_goes_to_review(self):
        async def transport(payload, config):
            return response(verdict("reference_conflict"))

        result = await adjudicate(self.folder, self.frozen, self.config, transport)
        self.assertEqual(result["category"], "judge_error")
        self.assertTrue(result["needs_review"])
        self.assertEqual(result["attempt_count"], 1)

    def test_strict_boolean_duplicate_conflict_and_wrapper(self):
        for bad in [
            {**verdict(), "verdict": 1},
            {**verdict(), "verdict": "false"},
            {**verdict("fail"), "verdict": True},
        ]:
            with self.assertRaises(ValueError):
                parse_verdict(json.dumps(bad), ["final_result"])
        with self.assertRaises(ValueError):
            parse_verdict('{"category":"pass","category":"fail"}', ["final_result"])
        with self.assertRaises(ValueError):
            parse_verdict(
                json.dumps({**verdict(), "evidence_refs": ["step:999"]}),
                ["final_result"],
            )
        _, recovered = parse_verdict(
            json.dumps({"properties": verdict("fail")}), ["final_result"]
        )
        self.assertTrue(recovered)


class MeasurementTests(unittest.TestCase):
    def test_unknown_usage_is_not_zero_or_complete(self):
        for calls in [[], [{"usage": {}}], [{"usage": {"prompt_tokens": 1}}]]:
            value = usage_summary(calls)
            self.assertIsNone(value["reported"])
            self.assertFalse(value["complete"])
        value = usage_summary(
            [
                {
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "prompt_tokens_details": {"cached_tokens": 7},
                    }
                },
                {},
            ]
        )
        self.assertFalse(value["complete"])
        self.assertEqual(value["reported"]["total_tokens"], 15)
        self.assertEqual(value["reported"]["cached_input_tokens"], 7)
        self.assertEqual(
            estimate_cost(None, {"input": 1, "cached_input": 1, "output": 2}), None
        )
        self.assertEqual(
            union_seconds(
                [{"started": 1, "finished": 4}, {"started": 3, "finished": 6}]
            ),
            5,
        )


class SyntheticPipelineTests(unittest.TestCase):
    def test_isolated_workers_and_judge_report_loop(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.server.requests.append(data)
                body = json.dumps(response(verdict())).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.requests = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "run"
            env = {**os.environ, "BU11_TEST_KEY": "synthetic"}
            command = [
                sys.executable,
                str(ROOT / "run_bu_bench_v1_1.py"),
                "run",
                "--output",
                str(out),
                "--run-start",
                "2026-11-13T00:30:00Z",
                "--cases",
                "1,2,19",
                "--parallel",
                "2",
                "--judge-parallel",
                "2",
                "--adapter",
                "tests.bu11_fixture:execute",
                "--judge-key-env",
                "BU11_TEST_KEY",
                "--judge-base-url",
                f"http://127.0.0.1:{server.server_port}/v1",
                "--judge-model",
                "synthetic",
            ]
            run = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=60,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            summary = read(max((out / "reports").glob("summary-*.json")))
            self.assertEqual(summary["counts"], {"pass": 2, "benchmark_invalid": 1})
            self.assertEqual(summary["passed_over_original_100"], 0.02)
            self.assertEqual(summary["valid_agent_success_rate"], 1)
            pids = [
                r["agent"]["metrics"]["fixture_pid"]
                for r in summary["task_results"]
                if r["agent"]
            ]
            self.assertEqual(len(set(pids)), 2)
            self.assertEqual(len(server.requests), 2)
            again = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
            self.assertNotEqual(again.returncode, 0)


class FailureEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_initialization_and_cleanup_errors_keep_metrics(self):
        from unittest.mock import AsyncMock, patch

        from lexmount_v1_1.executors import browser_use_execute

        fake = type("FakeBrowser", (), {})()
        fake.start = AsyncMock(side_effect=RuntimeError("synthetic init failure"))
        fake.kill = AsyncMock(side_effect=RuntimeError("synthetic cleanup failure"))
        config = {
            "model": "synthetic",
            "agent_key_env": "BU11_TEST_KEY",
            "agent_base_url": "http://127.0.0.1",
            "agent_max_tokens": 100,
            "model_timeout": 1,
            "browser": "local_headless",
            "task_timeout": 1,
            "use_vision": False,
            "max_steps": 1,
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"BU11_TEST_KEY": "synthetic"}),
            patch("browser_use.Browser", return_value=fake),
        ):
            result = await browser_use_execute(
                "synthetic task", config, Path(directory)
            )
            self.assertEqual(result.metrics["execution_status"], "execution_error")
            self.assertIn("init failure", result.metrics["execution_error"])
            self.assertIn("cleanup failure", result.metrics["cleanup_error"])
            self.assertGreaterEqual(result.duration_seconds, 0)
            self.assertIsNone(result.cost)
            self.assertIsNone(result.metrics["usage"]["reported"])

    async def test_http_failure_retains_raw_status_and_body(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b"synthetic upstream unavailable")

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        response = await http_judge(
            {},
            {
                "base_url": f"http://127.0.0.1:{server.server_port}",
                "api_key": "synthetic",
                "timeout": 2,
            },
        )
        self.assertEqual(response["_transport"]["http_status"], 503)
        self.assertEqual(
            response["_transport"]["raw_body"], "synthetic upstream unavailable"
        )
        self.assertIn("transport_error", response)


class ReportIntegrityTests(unittest.TestCase):
    def test_invalid_category_reward_rejected(self):
        from lexmount_v1_1.runner import validate_decision

        base = {
            "task_id": "test",
            "ordinal": 1,
            "reason": "recorded",
            "evidence_sha256": "hash",
            "verdict_source": "original_judge",
        }
        for change in [
            {"category": "infra", "reward": 0},
            {"category": "pass", "reward": True},
            {"category": "unknown", "reward": None},
        ]:
            with self.assertRaises(ValueError):
                validate_decision({**base, **change})


class FormattingRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def test_only_complete_single_json_fence_recovers(self):
        from lexmount_v1_1.judging import parse_verdict

        body = json.dumps(verdict())
        parsed, recovered = parse_verdict(
            "```json\n" + body + "\n```", ["final_result"]
        )
        self.assertTrue(recovered)
        self.assertTrue(parsed["verdict"])
        for raw in [
            "explanation\n```json\n" + body + "\n```",
            "```json\n" + body,
            "```json\n" + body + "\n```\n" + body,
        ]:
            with self.assertRaises(ValueError):
                parse_verdict(raw, ["final_result"])

    async def test_saved_response_recovery_never_calls_model(self):
        from lexmount_v1_1.storage import write_new

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            frozen = {
                "task_id": "synthetic",
                "ordinal": 1,
                "messages": [],
                "evidence_refs": ["final_result"],
                "evidence_sha256": "frozen",
            }
            config = {
                "model": "synthetic",
                "base_url": "http://127.0.0.1",
                "api_key": "synthetic",
                "timeout": 1,
                "max_tokens": 100,
                "rates": None,
            }
            from lexmount_v1_1.data import digest

            data = response(verdict())
            data["choices"][0]["message"]["content"] = (
                "```json\n" + json.dumps(verdict()) + "\n```"
            )
            write_new(
                folder / "attempt-01.json",
                {"input_sha256": digest(frozen), "response": data},
            )

            async def forbidden(*args):
                raise AssertionError("Offline recovery called a model")

            result = await adjudicate(
                folder, frozen, config, forbidden, allow_requests=False
            )
            self.assertEqual(result["verdict_source"], "recovered_original")
            self.assertEqual(result["reward"], 1)
            self.assertEqual(len(list(folder.glob("attempt-*.json"))), 1)


class RecoveryIdentityTests(unittest.TestCase):
    def test_tampered_evidence_rejected_before_supplement(self):
        from lexmount_v1_1.data import digest
        from lexmount_v1_1.runner import verify_recovery_identity
        from lexmount_v1_1.storage import write_new

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            task = {"task_id": "t", "ordinal": 1}
            trace = {"steps": ["original"]}
            ctx = {"start": "fixed"}
            write_new(folder / "trace.json", trace)
            sha = digest({"task": task, "trace": trace, "context": ctx})
            original = {"task_id": "t", "ordinal": 1, "evidence_sha256": sha}
            verify_recovery_identity({"context": ctx}, task, folder, original, original)
            with self.assertRaises(ValueError):
                verify_recovery_identity(
                    {"context": ctx}, task, folder, original, {**original, "ordinal": 2}
                )
            (folder / "trace.json").write_text(json.dumps({"steps": ["changed"]}))
            with self.assertRaises(ValueError):
                verify_recovery_identity(
                    {"context": ctx}, task, folder, original, original
                )
