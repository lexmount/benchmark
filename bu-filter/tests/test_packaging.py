"""Offline checks for the new file-path packaging around the unchanged runtime."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("bu_filter_packaging_evaluate", ROOT / "evaluate.py")
evaluate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate)


def prepared_run(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    jobs = []
    for task in evaluate.load_tasks():
        folder = run / "runs" / "bu_v1" / task["id"]
        evaluate.write(folder / "task.json", evaluate.actor_task(task))
        evaluate.write(folder / "actor-config.json", {"max_steps": 300, "timeout_seconds": 3600})
        jobs.append({"suite": "bu_v1", "ordinal": task["ordinal"], "task_id": task["id"],
                     "source_folder": str(folder),
                     "judge_folder": str(run / "judges" / "bu_v1" / task["id"])})
    plan = {"benchmark": "BU-filter", "counts": {"bu_v1": 87}, "jobs": jobs, "file_sha256": {}}
    evaluate.write(run / "plan.json", plan)
    return run, plan


def test_valid_87_task_packaging_passes_offline_validation(tmp_path):
    run, plan = prepared_run(tmp_path)
    assert evaluate.verify_run(run) == plan


@pytest.mark.parametrize("field", ["judge_folder", "suite", "ordinal"])
def test_misbound_job_is_rejected_before_reporting_old_results(tmp_path, field):
    run, plan = prepared_run(tmp_path)
    assert len(evaluate.verify_run(run)["jobs"]) == 87
    job = plan["jobs"][0]
    if field == "judge_folder":
        old = tmp_path / "old-bu100-run" / job["task_id"]
        evaluate.write(old / "judge-bu_v1.json", {"status": "judged", "score": 1})
        job[field] = str(old)
    elif field == "suite":
        job[field] = "odysseys"
    else:
        job[field] += 1
    evaluate.write(run / "plan.json", plan)
    with pytest.raises(ValueError, match="Task or Judge output path"):
        evaluate.verify_run(run)
    with pytest.raises(ValueError, match="Task or Judge output path"):
        evaluate.summarize(run)


def test_changed_canonical_configuration_cannot_validate_against_itself(tmp_path, monkeypatch):
    # Reproduce editing the package's own config: comparing it with itself would
    # accept the change. The hard-pinned checksum must reject it instead.
    package = tmp_path / "package"
    package.mkdir()
    path = package / "config.json"
    path.write_bytes((ROOT / "config.json").read_bytes())
    monkeypatch.setattr(evaluate, "HERE", package)
    original = evaluate.config(path)
    changed = dict(original)
    changed["judge"] = dict(original["judge"], model="changed-offline-model")
    path.write_text(json.dumps(changed, ensure_ascii=False, indent=2) + "\n")
    with pytest.raises(ValueError, match="configuration checksum changed"):
        evaluate.config(path)
