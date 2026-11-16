"""Run all 600 tasks with one frozen product and independent dynamic actor/judge pools."""

import asyncio
from collections import Counter
from datetime import UTC, datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import time

RUN = Path(__file__).resolve().parents[1]
ROOT = RUN.parent
PRODUCT = RUN / "product"
ENV = PRODUCT / ".venv"
CODE = ROOT / "code"
SOURCE = PRODUCT / "src"
LEGACY = ROOT.parents[1] / "tmp/bu-0x-5090-local-bu100-20261112/.venv/bin/python"
DEPENDENCIES = ROOT / "research-recovery-1114/judge-dependencies"
EXPECTED = {"bu_v1": 100, "online_mind2web": 300, "odysseys": 200}
COMMIT = "23ee669ce507787fd4e7e55d996c0a8fa0ff2753"
sys.path.insert(0, str(CODE))


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    pending.replace(path)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare():
    import full_benchmarks as evaluator
    from continue_evaluate import module_at

    assert not (RUN / "plan.json").exists(), "Preserve the existing frozen plan"
    build = read(RUN / "build.json")
    assert build["commit"] == COMMIT
    commit = subprocess.check_output(["git", "-C", PRODUCT, "rev-parse", "HEAD"], text=True).strip()
    assert commit == COMMIT
    assert not subprocess.check_output(["git", "-C", PRODUCT, "status", "--porcelain"], text=True)
    for name, digest in build["source_sha256"].items():
        assert sha(PRODUCT / name) == digest, name
    assert sha(RUN / "product-23ee669.tar.gz") == build["archive_sha256"]

    anchor = datetime.now(UTC).isoformat()
    sys.path.insert(0, str(DEPENDENCIES))
    previous = read(ROOT / "bu-lexmount-standard-eval-20261114/plan.json")
    task_source = Path(previous["task_data_source"])
    data = module_at("full_lexmount_data", task_source / "lexmount_v1_1/data.py")
    bu = data.tasks(anchor)
    tasks = {
        "bu_v1": [{"id": t["task_id"], "instruction": t["confirmed_task"],
                   "start_url": None, "answer": t.get("answer")} for t in bu],
        "online_mind2web": evaluator.tasks("online_mind2web"),
        "odysseys": evaluator.tasks("odysseys"),
    }
    assert {suite: len(rows) for suite, rows in tasks.items()} == EXPECTED
    assert [t["ordinal"] for t in bu] == list(range(1, 101))
    write(RUN / "task-data.json", tasks)
    rng = random.Random(2026111523)
    pending = {}
    for suite, rows in tasks.items():
        assert len({t["id"] for t in rows}) == len(rows)
        pending[suite] = []
        for ordinal, task in enumerate(rows, 1):
            tid = task["id"]
            assert isinstance(task["instruction"], str) and task["instruction"].strip()
            assert "/" not in tid and ".." not in tid
            folder = RUN / "runs" / suite / tid
            task_input = {name: task.get(name) for name in ("id", "instruction", "start_url")}
            write(folder / "task.json", task_input)
            steps = 200 if suite == "odysseys" else 100
            config = {
                "source_folder": str(folder), "max_steps": steps, "timeout_seconds": 3600,
                "feature_config": {"preparation_fraction": 0.0, "track_task_progress": False},
                "fixed_viewport": suite == "bu_v1", "product": build,
            }
            write(folder / "actor-config.json", config)
            pending[suite].append({
                "arm": "candidate", "suite": suite, "task_id": tid, "ordinal": ordinal,
                "source_folder": str(folder), "judge_folder": str(RUN / "judges" / suite / tid),
                "task_input_sha256": sha(folder / "task.json"),
                "actor_config_sha256": sha(folder / "actor-config.json"),
            })
        rng.shuffle(pending[suite])
    jobs = []
    while any(pending.values()):
        for suite in EXPECTED:
            if pending[suite]:
                jobs.append(pending[suite].pop())
    assert len(jobs) == 600
    frozen = [RUN / "build.json", RUN / "task-data.json", *sorted((RUN / "driver").glob("*.py"))]
    frozen += sorted(CODE.glob("*.py"))
    frozen += [ROOT / "sources.json", ROOT / "online-mind2web/omw_adapter.py",
               ROOT / "online-mind2web/historical-sources.json", task_source / "lexmount_v1_1/data.py",
               task_source / "lexmount_v1_1/manifest.json", task_source / "BU_Bench_V1_1.enc"]
    frozen += [PRODUCT / name for name in build["source_sha256"]]
    write(RUN / "plan.json", {
        "product_commit": COMMIT, "created_at": time.time(), "context_anchor": anchor,
        "actor_concurrency": 32, "judge_concurrency": 4, "counts": EXPECTED,
        "new_actor_runs": 600, "reused_actor_runs": 0, "old_actor_runs": 0,
        "agent_model": "deepseek-v4.1-flash", "agent_reasoning": "high",
        "mode": "ultrafast", "judge_reasoning": "low",
        "judge_protocol": "Existing 5090 official adapters and refusal-only fallback",
        "bu_dataset": "Lexmount BU Bench 1.1", "bu_dataset_flagged_ordinals": [19],
        "task_source": str(task_source), "seed": 2026111523, "jobs": jobs,
        "file_sha256": {str(path): sha(path) for path in frozen},
    })
    probe = RUN / "probes" / "candidate"
    write(probe / "actor-config.json", {"product": build})
    print(json.dumps({"commit": commit, "counts": EXPECTED, "jobs": len(jobs), "context_anchor": anchor}), flush=True)


def actor_command(folder, probe=False):
    command = [
        "bwrap", "--die-with-parent", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/dev/shm", "--tmpfs", "/tmp",
        "--dir", "/home/wf", "--dir", "/run",
    ]
    for path in ["/usr", "/etc", "/opt/google/chrome", "/sys", "/run/systemd/resolve",
                 "/home/wf/.local/share/uv/python", str(ENV), str(SOURCE)]:
        command.extend(["--ro-bind", path, path])
    for name in ["bin", "sbin", "lib", "lib32", "lib64", "libx32"]:
        command.extend(["--symlink", "usr/" + name, "/" + name])
    modules = ["full_benchmarks", "continue_evaluate", "eval_billing", "image_transport",
               "judge_refusals_dedup", "bu_lexmount_viewport"]
    mounts = [(RUN / "driver/actor.py", "/public/actor.py")]
    mounts += [(CODE / (name + ".py"), "/public/" + name + ".py") for name in modules]
    for source, destination in mounts:
        command.extend(["--ro-bind", str(source), destination])
    command.extend(["--bind", str(folder), str(folder), "--chdir", str(folder), "--clearenv"])
    env = {
        "HOME": "/home/wf", "PATH": str(ENV / "bin") + ":/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8", "PYTHONPATH": "/public", "PYTHONUNBUFFERED": "1",
        "BH_TELEMETRY": "0", "ANONYMIZED_TELEMETRY": "false",
        "LEXMOUNT_EVAL_ROOT": str(ROOT), "EXPECTED_ARM": "candidate",
    }
    for name in ["HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy", "TZ"]:
        if name in os.environ:
            env[name] = os.environ[name]
    if probe:
        env["PROBE_ONLY"] = "1"
    for key, value in env.items():
        command.extend(["--setenv", key, value])
    return command + ["--", str(ENV / "bin/python"), "/public/actor.py", str(folder)]


async def invoke(command, log_path, timeout, stdin=None):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        process = await asyncio.create_subprocess_exec(
            *command, stdin=asyncio.subprocess.PIPE if stdin else asyncio.subprocess.DEVNULL,
            stdout=log, stderr=log, start_new_session=True,
        )
        try:
            await asyncio.wait_for(process.communicate(stdin), timeout)
        except asyncio.TimeoutError:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(process.wait(), 5)
            except asyncio.TimeoutError:
                os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
            return 124
        return process.returncode


async def grade(job):
    sys.path.insert(0, str(DEPENDENCIES))
    import full_benchmarks as evaluator

    task = next(t for t in read(RUN / "task-data.json")[job["suite"]] if t["id"] == job["task_id"])
    folder = Path(job["source_folder"])
    assert task["instruction"] == read(folder / "task.json")["instruction"]
    result = await evaluator.judge(folder, job["suite"], task, Path(job["judge_folder"]))
    print(result.get("status"), flush=True)


async def run():
    plan = read(RUN / "plan.json")
    for path, digest in plan["file_sha256"].items():
        assert sha(path) == digest, path
    assert plan["product_commit"] == COMMIT and len(plan["jobs"]) == 600
    credentials = (ROOT / ".private/model.json").read_bytes()
    public_config = read(ROOT / ".private/model.json")
    assert public_config["model"] == "deepseek-v4.1-flash"
    assert public_config.get("reasoning_effort", "high") == "high"
    assert public_config.get("mode", "ultrafast") == "ultrafast"
    actors, judges = asyncio.Semaphore(32), asyncio.Semaphore(4)
    active = Counter()
    state_file = RUN / "progress.json"
    state = read(state_file) if state_file.exists() else {}

    def event(job, phase, stage, **extra):
        key = "/".join(("candidate", job["suite"], job["task_id"]))
        entry = {"at": time.time(), "status": phase, "stage": stage, **extra}
        state.setdefault(key, {})[stage] = entry
        write(state_file, state)
        with (RUN / "events.jsonl").open("a") as stream:
            stream.write(json.dumps({"key": key, "ordinal": job["ordinal"], "active": dict(active), **entry}) + "\n")
        print(job["suite"], job["ordinal"], stage, phase, "active", dict(active), flush=True)

    async def one(job):
        folder = Path(job["source_folder"])
        assert sha(folder / "task.json") == job["task_input_sha256"]
        assert sha(folder / "actor-config.json") == job["actor_config_sha256"]
        receipt = folder / "execution.json"
        if not receipt.exists():
            async with actors:
                if (folder / "agent").exists():
                    event(job, "interrupted_actor_preserved", "actor")
                    return
                active["actor"] += 1
                event(job, "started", "actor")
                try:
                    code = await invoke(actor_command(folder), folder / "worker.log", 3900, credentials)
                finally:
                    active["actor"] -= 1
                if code or not receipt.exists():
                    event(job, "actor_process_error", "actor", exit_code=code)
                    return
        event(job, "finished", "actor", native=read(receipt).get("status"))
        destination = Path(job["judge_folder"])
        packet = destination / ("judge-" + job["suite"] + ".json")
        if packet.exists():
            event(job, read(packet)["status"], "primary", preserved=True)
            return
        async with judges:
            active["judge"] += 1
            event(job, "started", "primary")
            try:
                python = LEGACY if job["suite"] == "bu_v1" else ROOT / "envs/baseline/bin/python"
                code = await invoke(
                    [str(python), __file__, "judge", job["suite"], job["task_id"]],
                    destination / "judge.log", 14400,
                )
            finally:
                active["judge"] -= 1
            event(job, read(packet)["status"] if packet.exists() else "judge_process_error", "primary", exit_code=code)

    await asyncio.gather(*(one(job) for job in plan["jobs"]))
    write(RUN / "complete-all.json", {"finished_at": time.time(), "records": len(state), "active": dict(active)})


if __name__ == "__main__":
    command = sys.argv[1]
    if command == "prepare":
        prepare()
    elif command == "probe":
        subprocess.run(actor_command(RUN / "probes/candidate", probe=True), check=True, timeout=100)
    elif command == "judge":
        job = next(j for j in read(RUN / "plan.json")["jobs"]
                   if (j["suite"], j["task_id"]) == tuple(sys.argv[2:4]))
        asyncio.run(grade(job))
    elif command == "run":
        with (RUN / "controller.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            asyncio.run(run())
