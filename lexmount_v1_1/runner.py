"""Per-task process isolation, shared run anchor, immutable evidence and separate judge queue."""

import argparse
import asyncio
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from frameworks import ExecutionResult
from lexmount_v1_1.data import ROOT, context, digest, select, tasks
from lexmount_v1_1.executors import execute
from lexmount_v1_1.judging import adjudicate, make_input
from lexmount_v1_1.storage import read, redact, write_new

ENTRY = ROOT / "run_bu_bench_v1_1.py"


def rates(text):
    if not text:
        return None
    values = [float(x) for x in text.split(",")]
    if len(values) != 3 or any(not math.isfinite(v) or v < 0 for v in values):
        raise argparse.ArgumentTypeError(
            "Rates are input,cached_input,output USD per million tokens"
        )
    return dict(zip(("input", "cached_input", "output"), values))


def judge_config(config):
    return {
        "model": config["judge_model"],
        "base_url": config["judge_base_url"],
        "api_key": os.environ[config["judge_key_env"]],
        "timeout": config["judge_timeout"],
        "max_tokens": config["judge_max_tokens"],
        "reasoning_effort": config["judge_reasoning"],
        "rates": config.get("judge_rates"),
        "price_source": config.get("judge_price_source"),
    }


def task_folder(run, task):
    return Path(run) / "tasks" / f"{task['ordinal']:03d}-{task['task_id']}"


def load_run_task(run, ordinal):
    manifest = read(Path(run) / "run.json")
    if ordinal not in manifest["selected_ordinals"]:
        raise ValueError("Task was not selected for this run")
    row = tasks(manifest["context"]["run_started_at_utc"])[ordinal - 1]
    if digest(row) != manifest["task_sha256"][str(ordinal)]:
        raise ValueError("Task differs from the frozen run manifest")
    return manifest, row, task_folder(run, row)


async def worker(run, ordinal):
    manifest, task, folder = load_run_task(run, ordinal)
    if task["eligibility"] != "eligible":
        raise ValueError("Quarantined tasks cannot execute")
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "trace.json").exists() or (folder / "execution-error.json").exists():
        raise ValueError(
            "Agent execution already exists; create a separate run for a new attempt"
        )
    write_new(folder / "task.json", task)
    start = time.monotonic()
    try:
        result = await execute(task["confirmed_task"], manifest["config"], folder)
        elapsed = time.monotonic() - start
        if not isinstance(result, ExecutionResult):
            raise TypeError(
                "Adapter must return frameworks.ExecutionResult or MeasuredExecutionResult"
            )
        if (
            not isinstance(result.final_result, str)
            or not isinstance(result.steps, list)
            or any(not isinstance(s, str) for s in result.steps)
        ):
            raise TypeError(
                "Adapter result must contain string final_result and list[str] steps"
            )
        if not isinstance(result.screenshots_b64, list) or any(
            not isinstance(s, str) for s in result.screenshots_b64
        ):
            raise TypeError("screenshots_b64 must be a list of base64 PNG strings")
        trace = {
            "final_result": result.final_result,
            "steps": result.steps,
            "screenshots_b64": result.screenshots_b64,
        }
        evidence_seconds = getattr(result, "evidence_seconds", None)
        metrics = getattr(result, "metrics", {})
        write_new(folder / "trace.json", trace)
        write_new(
            folder / "agent.json",
            {
                "task_id": task["task_id"],
                "ordinal": ordinal,
                "adapter_wall_seconds": elapsed,
                "agent_seconds": metrics.get("agent_wall_seconds"),
                "evidence_seconds": evidence_seconds,
                "adapter_reported_duration_seconds": result.duration_seconds,
                "policy_steps": result.num_steps,
                "metrics": metrics,
                "adapter_reported_cost_usd": result.cost if result.cost else None,
                "cost_note": "Legacy ExecutionResult cost=0 is ambiguous; use explicit metrics for a known zero",
                "trace_sha256": digest(trace),
            },
        )
    except BaseException as exc:
        write_new(
            folder / "execution-error.json",
            {
                "error": redact(f"{type(exc).__name__}: {exc}"),
                "elapsed_seconds": time.monotonic() - start,
                "needs_review": True,
            },
        )
        raise


def immutable_decision(folder, result):
    path = Path(folder) / "result.json"
    if path.exists():
        if read(path) != result:
            raise ValueError("Original decision is immutable; use the review command")
    else:
        write_new(path, result)


async def judge_task(run, ordinal):
    manifest, task, folder = load_run_task(run, ordinal)
    if (folder / "result.json").exists():
        return read(folder / "result.json")
    if task["eligibility"] != "eligible":
        result = {
            "task_id": task["task_id"],
            "ordinal": ordinal,
            "category": "benchmark_invalid",
            "reward": None,
            "reason": "Quarantined by the versioned dataset audit; task was not dispatched",
            "evidence_refs": ["dataset_audit"],
            "evidence_sha256": digest(task),
            "verdict_source": "dataset_audit",
            "attempt_count": 0,
            "needs_review": False,
        }
    elif not (folder / "trace.json").exists():
        error = (
            read(folder / "execution-error.json")
            if (folder / "execution-error.json").exists()
            else {"error": "Worker did not retain a trace"}
        )
        result = {
            "task_id": task["task_id"],
            "ordinal": ordinal,
            "category": "judge_error",
            "reward": None,
            "reason": error["error"],
            "evidence_refs": ["execution-error.json"],
            "evidence_sha256": digest(error),
            "verdict_source": "harness_error",
            "attempt_count": 0,
            "needs_review": True,
            "review_reason": "execution_or_evidence_failure",
        }
    else:
        trace = read(folder / "trace.json")
        if digest(trace) != read(folder / "agent.json")["trace_sha256"]:
            raise ValueError("Frozen execution evidence changed")
        frozen = make_input(task, trace, manifest["context"])
        result = await adjudicate(
            folder / "judge", frozen, judge_config(manifest["config"])
        )
    immutable_decision(folder, result)
    return result


def validate_decision(result):
    expected = {
        "pass": 1,
        "fail": 0,
        "infra": None,
        "judge_error": None,
        "benchmark_invalid": None,
    }
    category = result.get("category")
    if category not in expected or result.get("reward") != expected[category]:
        raise ValueError("Invalid outcome category/reward")
    if result.get("reward") is not None and type(result["reward"]) not in (int, float):
        raise ValueError("Reward must be numeric or null, not boolean/string")
    for key in ("task_id", "ordinal", "reason", "evidence_sha256", "verdict_source"):
        if not result.get(key):
            raise ValueError("Missing outcome provenance: " + key)
    if result["verdict_source"] not in {
        "original_judge",
        "recovered_original",
        "bounded_rejudge",
        "evidence_review",
        "dataset_audit",
        "harness_error",
    }:
        raise ValueError("Unknown verdict source")
    if result["verdict_source"] == "dataset_audit" and category != "benchmark_invalid":
        raise ValueError("Dataset audit cannot assign Agent pass/fail")
    if result["verdict_source"] == "harness_error" and category != "judge_error":
        raise ValueError("Harness errors cannot assign Agent pass/fail")
    return result


def verify_recovery_identity(manifest, task, folder, original, frozen):
    expected = digest(
        {
            "task": task,
            "trace": read(folder / "trace.json"),
            "context": manifest["context"],
        }
    )
    if original["task_id"] != task["task_id"] or frozen["task_id"] != task["task_id"]:
        raise ValueError("Recovery task identity differs from original run")
    if original["ordinal"] != task["ordinal"] or frozen["ordinal"] != task["ordinal"]:
        raise ValueError("Recovery ordinal differs from original run")
    if original["evidence_sha256"] != expected or frozen["evidence_sha256"] != expected:
        raise ValueError("Recovery evidence differs from original run")


def report(run):
    run = Path(run)
    manifest = read(run / "run.json")
    rows = []
    for ordinal in manifest["selected_ordinals"]:
        _, task, folder = load_run_task(run, ordinal)
        original = (
            read(folder / "result.json") if (folder / "result.json").exists() else None
        )
        reviews = sorted(folder.glob("review-*.json"))
        recoveries = sorted(folder.glob("recovery-*.json"))
        supplements = reviews or recoveries
        result = read(supplements[-1]) if supplements else original
        if result:
            validate_decision(result)
            if result["task_id"] != task["task_id"] or result["ordinal"] != ordinal:
                raise ValueError("Outcome identity differs from run manifest")
            if (folder / "trace.json").exists():
                expected_hash = digest(
                    {
                        "task": task,
                        "trace": read(folder / "trace.json"),
                        "context": manifest["context"],
                    }
                )
            elif task["eligibility"] != "eligible":
                expected_hash = digest(task)
            else:
                error = (
                    read(folder / "execution-error.json")
                    if (folder / "execution-error.json").exists()
                    else {"error": "Worker did not retain a trace"}
                )
                expected_hash = digest(error)
            if result["evidence_sha256"] != expected_hash:
                raise ValueError("Outcome evidence hash differs from frozen evidence")
        agent = (
            read(folder / "agent.json") if (folder / "agent.json").exists() else None
        )
        attempts = [read(p) for p in sorted((folder / "judge").glob("attempt-*.json"))]
        rows.append(
            {
                "ordinal": ordinal,
                "task_id": task["task_id"],
                "eligible": task["eligibility"] == "eligible",
                "result": result,
                "original_result": original if supplements else None,
                "agent": agent,
                "judge_seconds": sum(a["elapsed_seconds"] for a in attempts),
                "judge_usage": [a.get("usage") for a in attempts],
                "judge_estimated_cost_usd": (
                    sum(a["estimated_cost_usd"] for a in attempts)
                    if attempts
                    and all(a.get("estimated_cost_usd") is not None for a in attempts)
                    else None
                ),
            }
        )
    counts = Counter((r["result"] or {}).get("category", "pending") for r in rows)
    valid = counts["pass"] + counts["fail"]
    eligible_rows = [r for r in rows if r["eligible"]]
    costs = [
        (r["agent"] or {}).get("metrics", {}).get("estimated_cost_usd")
        for r in eligible_rows
    ]
    seconds = [(r["agent"] or {}).get("agent_seconds") for r in eligible_rows]
    summary = {
        "benchmark": "Lexmount BU Bench 1.1",
        "version": "1.1.0",
        "original_universe": 100,
        "selected": len(rows),
        "counts": dict(counts),
        "passed_over_original_100": counts["pass"] / 100,
        "valid_agent_success_rate": counts["pass"] / valid if valid else None,
        "valid_coverage_over_original_100": valid / 100,
        "subset_run": len(rows) != 100,
        "complete": counts["pending"] == 0,
        "review_required": [
            r["ordinal"] for r in rows if (r["result"] or {}).get("needs_review")
        ],
        "agent_total_known_seconds": sum(
            r["agent"]["agent_seconds"]
            for r in rows
            if r["agent"] and r["agent"].get("agent_seconds") is not None
        ),
        "agent_total_seconds": sum(seconds)
        if seconds and all(v is not None for v in seconds)
        else None,
        "agent_seconds_missing": sum(v is None for v in seconds),
        "agent_estimated_cost_usd": sum(costs)
        if costs and all(c is not None for c in costs)
        else None,
        "agent_known_cost_subtotal_usd": sum(c for c in costs if c is not None)
        if any(c is not None for c in costs)
        else None,
        "agent_cost_missing": sum(c is None for c in costs),
        "judge_total_seconds": sum(r["judge_seconds"] for r in rows),
        "task_results": rows,
    }
    # Reports are derived snapshots; immutable raw decisions/attempts are never overwritten.
    reports = run / "reports"
    reports.mkdir(exist_ok=True)
    serial = len(list(reports.glob("summary-*.json"))) + 1
    path = reports / f"summary-{serial:04}.json"
    write_new(path, summary)
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k != "task_results"},
            ensure_ascii=False,
        )
    )
    print(f"Report: {path}")
    return summary


async def subprocess_task(mode, run, ordinal, timeout):
    _, _, folder = load_run_task(run, ordinal)
    folder.mkdir(parents=True, exist_ok=True)
    log = folder / f"{mode}.log"
    with log.open("ab") as stream:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(ENTRY),
            mode,
            "--output",
            str(run),
            "--case",
            str(ordinal),
            cwd=str(ROOT),
            stdout=stream,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout)
        except BaseException:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                await asyncio.wait_for(proc.wait(), 30)
            except (TimeoutError, ProcessLookupError):
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await proc.wait()
            raise
    return proc.returncode


async def run_all(args):
    cfg = vars(args).copy()
    for key in ("command", "output", "cases", "tasks", "run_start"):
        cfg.pop(key, None)
    cfg["output"] = str(args.output.resolve())
    for key in ("agent_base_url", "judge_base_url"):
        from urllib.parse import urlsplit

        url = urlsplit(cfg[key])
        if url.username or url.password or url.query or url.fragment:
            raise ValueError(
                f"{key} cannot contain embedded credentials, query or fragment"
            )
    if not args.adapter and not os.environ.get(args.agent_key_env):
        raise ValueError(
            f"Missing agent credential environment variable: {args.agent_key_env}"
        )
    if not os.environ.get(args.judge_key_env):
        raise ValueError(
            f"Missing judge credential environment variable: {args.judge_key_env}"
        )
    rows = select(tasks(args.run_start), args.cases, args.tasks)
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        source = (
            await asyncio.to_thread(
                subprocess.check_output,
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT,
                text=True,
            )
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        source = None
    source_files = [
        ENTRY,
        ROOT / "frameworks/__init__.py",
        ROOT / "judge.py",
        *sorted((ROOT / "lexmount_v1_1").glob("*.py")),
    ]
    source_hashes = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in source_files
    }
    try:
        dirty = bool(
            (
                await asyncio.to_thread(
                    subprocess.check_output,
                    ["git", "status", "--porcelain"],
                    cwd=ROOT,
                    text=True,
                )
            ).strip()
        )
    except (OSError, subprocess.CalledProcessError):
        dirty = None
    manifest = {
        "source_sha256": source_hashes,
        "source_dirty": dirty,
        "context": context(args.run_start),
        "config": cfg,
        "selected_ordinals": [t["ordinal"] for t in rows],
        "task_sha256": {str(t["ordinal"]): digest(t) for t in rows},
        "dataset": read(ROOT / "lexmount_v1_1/manifest.json"),
        "source_commit": source,
        "python": sys.version,
        "created_at_utc": datetime.now(UTC).isoformat(),
    }
    write_new(args.output / "run.json", manifest)
    agents = asyncio.Semaphore(args.parallel)
    judges = asyncio.Semaphore(args.judge_parallel)
    started = time.monotonic()

    async def one(task):
        ordinal = task["ordinal"]
        if task["eligibility"] == "eligible":
            async with agents:
                try:
                    await subprocess_task(
                        "worker", args.output, ordinal, args.task_timeout + 180
                    )
                except TimeoutError:
                    folder = task_folder(args.output, task)
                    if not (folder / "execution-error.json").exists():
                        write_new(
                            folder / "execution-error.json",
                            {
                                "error": "Worker watchdog expired; inspect worker.log",
                                "needs_review": True,
                            },
                        )
        async with judges:
            try:
                code = await subprocess_task(
                    "judge", args.output, ordinal, args.judge_timeout * 3 + 90
                )
                if code:
                    print(
                        f"Case {ordinal}: judge process exited {code}; inspect judge.log",
                        flush=True,
                    )
            except TimeoutError:
                print(
                    f"Case {ordinal}: judge watchdog expired; frozen evidence retained",
                    flush=True,
                )
        print(f"Finished case {ordinal}", flush=True)

    await asyncio.gather(*(one(t) for t in rows))
    write_new(
        args.output / "completion.json",
        {
            "batch_wall_seconds": time.monotonic() - started,
            "completed_at_utc": datetime.now(UTC).isoformat(),
        },
    )
    summary = report(args.output)
    return 2 if not summary["complete"] or summary["review_required"] else 0


async def recover(args):
    manifest, task, folder = load_run_task(args.output, args.case)
    original = read(folder / "result.json")
    if (
        not original.get("needs_review")
        or list(folder.glob("review-*.json"))
        or list(folder.glob("recovery-*.json"))
    ):
        raise ValueError("No unresolved original verdict available for recovery")
    frozen = read(folder / "judge/input.json")
    verify_recovery_identity(manifest, task, folder, original, frozen)
    cfg = {**read(folder / "judge/config.json"), "api_key": "unused-offline-recovery"}
    result = await adjudicate(folder / "judge", frozen, cfg, allow_requests=False)
    if result.get("needs_review"):
        raise ValueError(
            "Saved responses remain insufficient; inspect frozen evidence and use review"
        )
    result.update(
        original_decision_sha256=digest(original),
        recovered_at_utc=datetime.now(UTC).isoformat(),
        recovery_note="Recovered from already saved complete response; no model request or Agent rerun",
        recovery_source_sha256={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__), ROOT / "lexmount_v1_1/judging.py"]
        },
        requests_recorded=len(list((folder / "judge").glob("attempt-*.json"))),
        additional_model_requests=0,
    )
    write_new(folder / "recovery-01.json", result)
    report(args.output)


def review(args):
    manifest, task, folder = load_run_task(args.output, args.case)
    original = read(folder / "result.json")
    if not original.get("needs_review") or list(folder.glob("recovery-*.json")):
        raise ValueError(
            "This command only closes flagged review cases, not score-based retries"
        )
    if args.category in ("pass", "fail") and not (folder / "judge/input.json").exists():
        raise ValueError(
            "Missing task evidence cannot be reviewed as an Agent pass/fail; obtain a new run"
        )
    reason = args.reason_file.read_text().strip()
    if len(reason) < 20:
        raise ValueError("Review needs a substantive evidence-based reason")
    allowed_refs = (
        read(folder / "judge/input.json")["evidence_refs"]
        if (folder / "judge/input.json").exists()
        else original["evidence_refs"]
    )
    if not args.evidence_ref or any(r not in allowed_refs for r in args.evidence_ref):
        raise ValueError("Review references must resolve to original frozen evidence")
    if (folder / "judge/input.json").exists():
        frozen = read(folder / "judge/input.json")
        verify_recovery_identity(manifest, task, folder, original, frozen)
        if frozen["evidence_sha256"] != original["evidence_sha256"]:
            raise ValueError("Review evidence hash differs from original")
    reviews = list(folder.glob("review-*.json"))
    if reviews:
        raise ValueError(
            "Review already exists; do not repeatedly review for a preferred score"
        )
    result = {
        **original,
        "category": args.category,
        "reward": {"pass": 1, "fail": 0}.get(args.category),
        "reason": reason,
        "evidence_refs": args.evidence_ref,
        "verdict_source": "evidence_review",
        "reviewer": args.reviewer,
        "reviewer_type": args.reviewer_type,
        "needs_review": False,
        "reviewed_at_utc": datetime.now(UTC).isoformat(),
        "original_decision_sha256": digest(original),
    }
    write_new(folder / "review-01.json", result)
    report(args.output)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser(
        "run", help="Run selected tasks, preserve evidence and judge independently"
    )
    run.add_argument(
        "--run-start",
        required=True,
        help="Shared ISO-8601 anchor with timezone for all comparison arms",
    )
    run.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New private run directory (must not exist)",
    )
    run.add_argument(
        "--cases",
        type=lambda s: [int(v) for v in s.split(",")],
        help="Original 1-based ordinals, e.g. 1,4",
    )
    run.add_argument(
        "--tasks",
        type=int,
        help="Limit selected tasks; omitted means all 100, with 19 quarantined",
    )
    run.add_argument("--parallel", type=int, default=1)
    run.add_argument("--judge-parallel", type=int, default=4)
    run.add_argument(
        "--adapter",
        help="Custom asynchronous module:function accepting only instruction",
    )
    run.add_argument("--model", default="gpt-4.1-mini")
    run.add_argument(
        "--agent-base-url",
        default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )
    run.add_argument("--agent-key-env", default="OPENAI_API_KEY")
    run.add_argument("--agent-reasoning", default=None)
    run.add_argument("--agent-max-tokens", type=int, default=16384)
    run.add_argument(
        "--agent-price-source",
        help="Provider pricing URL/date or account price source, stored with supplied rates",
    )
    run.add_argument(
        "--agent-rates",
        type=rates,
        help="input,cached_input,output USD / million tokens; omitted means unknown cost",
    )
    run.add_argument(
        "--browser",
        choices=["local_headless", "local_headful"],
        default="local_headless",
    )
    run.add_argument("--chrome-bin", default=None)
    run.add_argument(
        "--use-vision", action=argparse.BooleanOptionalAction, default=True
    )
    run.add_argument("--max-steps", type=int, default=100)
    run.add_argument("--task-timeout", type=float, default=1800)
    run.add_argument("--model-timeout", type=float, default=120)
    run.add_argument("--judge-model", default="gpt-4.1-mini")
    run.add_argument(
        "--judge-base-url",
        default=os.environ.get(
            "JUDGE_BASE_URL",
            os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        ),
    )
    run.add_argument("--judge-key-env", default="OPENAI_API_KEY")
    run.add_argument("--judge-timeout", type=float, default=180)
    run.add_argument("--judge-max-tokens", type=int, default=8192)
    run.add_argument("--judge-reasoning", default=None)
    run.add_argument("--judge-price-source", help="Pricing source for judge rates")
    run.add_argument("--judge-rates", type=rates)
    for mode in ("worker", "judge", "recover"):
        cmd = sub.add_parser(
            mode,
            help="Internal worker"
            if mode == "worker"
            else "Resume bounded judging from saved evidence, without rerunning agent",
        )
        cmd.add_argument("--output", type=Path, required=True)
        cmd.add_argument("--case", type=int, required=True)
    summary = sub.add_parser(
        "report", help="Write a derived summary; do not alter raw records"
    )
    summary.add_argument("--output", type=Path, required=True)
    check = sub.add_parser(
        "check",
        help="Offline dataset and order verification; no model or browser requests",
    )
    check.add_argument("--run-start", required=True)
    rev = sub.add_parser(
        "review",
        help="Close a flagged judgement using original evidence; preserve original decision",
    )
    rev.add_argument("--output", type=Path, required=True)
    rev.add_argument("--case", type=int, required=True)
    rev.add_argument(
        "--category",
        choices=["pass", "fail", "infra", "judge_error", "benchmark_invalid"],
        required=True,
    )
    rev.add_argument("--reviewer", required=True)
    rev.add_argument("--reviewer-type", choices=["human", "agent"], required=True)
    rev.add_argument("--reason-file", type=Path, required=True)
    rev.add_argument("--evidence-ref", action="append", required=True)
    return p


def main(argv=None):
    os.umask(0o077)
    load_dotenv()
    args = parser().parse_args(argv)
    if hasattr(args, "output"):
        args.output = args.output.resolve()
    try:
        if args.command == "check":
            rows = tasks(args.run_start)
            print(
                json.dumps(
                    {
                        "version": "1.1.0",
                        "total": len(rows),
                        "eligible": sum(t["eligibility"] == "eligible" for t in rows),
                        "ordinals_preserved": True,
                        "context": context(args.run_start),
                    },
                    ensure_ascii=False,
                )
            )
            return
        if args.command == "run":
            if any(
                not math.isfinite(getattr(args, k)) or getattr(args, k) <= 0
                for k in (
                    "parallel",
                    "judge_parallel",
                    "max_steps",
                    "task_timeout",
                    "model_timeout",
                    "judge_timeout",
                    "agent_max_tokens",
                    "judge_max_tokens",
                )
            ):
                raise ValueError("Concurrency, budgets and timeouts must be positive")
            if (args.agent_rates and not args.agent_price_source) or (
                args.judge_rates and not args.judge_price_source
            ):
                raise ValueError(
                    "Supplied rates require the corresponding --agent-price-source or --judge-price-source"
                )
            raise SystemExit(asyncio.run(run_all(args)))
        if args.command == "worker":
            asyncio.run(worker(args.output.resolve(), args.case))
        elif args.command == "judge":
            asyncio.run(judge_task(args.output.resolve(), args.case))
        elif args.command == "recover":
            asyncio.run(recover(args))
        elif args.command == "review":
            review(args)
        else:
            report(args.output)
    except (ValueError, KeyError, FileNotFoundError, FileExistsError) as exc:
        raise SystemExit(redact(f"{type(exc).__name__}: {exc}")) from None
