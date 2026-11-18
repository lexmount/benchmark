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
    plan = {"benchmark": "BU-filter", "counts": {"bu_v1": 88}, "jobs": jobs, "file_sha256": {}}
    evaluate.write(run / "plan.json", plan)
    return run, plan


def test_actor_mode_is_fixed_when_credentials_are_read(tmp_path):
    path = tmp_path / "model.json"
    for raw in ({}, {"mode": "default"}):
        evaluate.write(path, raw)
        assert evaluate.actor_credentials(path)["mode"] == "default"
    for invalid in ("ultrafast", "", None):
        evaluate.write(path, {"mode": invalid})
        with pytest.raises(ValueError, match="default"):
            evaluate.actor_credentials(path)


def test_execution_rejects_incompatible_frozen_mode(tmp_path):
    run, plan = prepared_run(tmp_path)
    with pytest.raises(ValueError, match="default"):
        evaluate.verify_run(run, for_execution=True)
    plan["agent_mode"] = "default"
    evaluate.write(run / "plan.json", plan)
    evaluate.write(run / "support/.private/model.json", {"mode": "ultrafast"})
    with pytest.raises(ValueError, match="default"):
        evaluate.verify_run(run, for_execution=True)
    evaluate.write(run / "support/.private/model.json", {"mode": "default"})
    with pytest.raises(ValueError, match="every task"):
        evaluate.verify_run(run, for_execution=True)


def test_valid_88_task_packaging_passes_offline_validation(tmp_path):
    run, plan = prepared_run(tmp_path)
    assert evaluate.verify_run(run) == plan


@pytest.mark.parametrize("field", ["judge_folder", "suite", "ordinal"])
def test_misbound_job_is_rejected_before_reporting_old_results(tmp_path, field):
    run, plan = prepared_run(tmp_path)
    assert len(evaluate.verify_run(run)["jobs"]) == 88
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


def test_bu_archive_preserves_other_benchmarks():
    from ops.migrate_legacy import bu_defaults
    original = {
        "schema_version": 1,
        "default_bu_benchmark": "bu-lexmount",
        "default_odysseys_benchmark": "odysseys-filter",
        "operator_note": "Keep existing work",
        "benchmarks": {
            "bu-lexmount": {"task_count": 100},
            "odysseys-filter": {"task_count": 168, "max_steps": 300},
            "online-mind2web-filter": {"task_count": 247, "max_steps": 100},
        },
    }
    merged = bu_defaults(original, "bu-filter/evaluate.py")
    assert original["default_bu_benchmark"] == "bu-lexmount"
    assert merged["default_bu_benchmark"] == "bu-filter"
    assert "bu-lexmount" not in merged["benchmarks"]
    for name in ["odysseys-filter", "online-mind2web-filter"]:
        assert merged["benchmarks"][name] == original["benchmarks"][name]
    assert merged["default_odysseys_benchmark"] == original["default_odysseys_benchmark"]
    assert merged["operator_note"] == original["operator_note"]
    assert merged["benchmarks"]["bu-filter"] == {
        "task_count": 88, "max_steps": 300, "timeout_seconds": 3600,
        "entry": "bu-filter/evaluate.py",
    }

def test_published_actor_is_selected_by_commit_before_creating_a_run(tmp_path, monkeypatch):
    import hashlib
    monkeypatch.syspath_prepend(str(ROOT.parent))
    from shared_actor_runtime import bind_actor, select_release

    commit = 'a' * 40
    store = tmp_path / 'registry'
    root = store / commit
    monkeypatch.setenv('LEXMOUNT_ACTOR_RUNTIME_STORE', str(store))
    with pytest.raises(FileNotFoundError, match='Publish Agent'):
        select_release(tmp_path, commit)
    for name in ('uv.lock', '.venv/bin/python', 'src/lexmount_browser_agent/__init__.py', 'chrome/chrome', 'cpython/bin/python3'):
        f = root / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(name)
    manifest = root / 'actor-runtime.json'
    manifest.write_text(json.dumps({'product_commit': commit, 'uv_lock_sha256': hashlib.sha256(b'uv.lock').hexdigest()}))
    auto = select_release(tmp_path, commit)
    assert auto == select_release(root, commit) == select_release(tmp_path, commit, manifest)
    scope = {'COMMIT': commit}
    def actor_command():
        return ['bwrap', '--ro-bind', '/opt/google/chrome', '/opt/google/chrome', '--ro-bind',
                '/home/wf/.local/share/uv/python', '/home/wf/.local/share/uv/python', '--', str(scope['ENV']/'bin/python')]
    scope['actor_command'] = actor_command
    bind_actor(scope, auto)
    args = scope['actor_command']()
    assert str(root/'chrome') in args and str(root/'cpython') in args and args[-1] == str(root/'.venv/bin/python')
    assert scope['SOURCE'] == root/'src'
    manifest.write_text(manifest.read_text()+' ')
    with pytest.raises(ValueError, match='changed'):
        bind_actor(scope, auto)
