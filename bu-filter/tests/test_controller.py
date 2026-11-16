"""Offline controller acceptance tests: no model, browser, or external process."""
from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bu_filter_evaluate", ROOT / "evaluate.py")
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)
PUBLIC_TASKS = controller.load_tasks()
EXCLUDED = json.loads((ROOT / "data" / "exclusions.json").read_text())


def fixture(parent, tasks):
    run = Path(parent) / "run"
    run.mkdir()
    harness = run / "frozen" / "harness"
    (harness / "data").mkdir(parents=True)
    shutil.copy2(ROOT / "data" / "manifest.json", harness / "data" / "manifest.json")
    (harness / "vendor").mkdir()
    (harness / "vendor" / "official_judge.py").write_text("# frozen offline judge fixture\n")
    settings = {
        "agent_python": sys.executable,
        "judge_python": sys.executable,
        "actor_concurrency": 2,
        "judge_concurrency": 1,
        "agent": {"timeout_seconds": 3600},
        "judge": {"process_timeout_seconds": 14400},
        "watchdog_grace_seconds": 300,
    }
    controller.write(run / "settings.json", settings)
    plan = {
        "benchmark": "BU-filter", "dataset_count": 87,
        "selected_count": len(tasks),
        "scope": "full87" if len(tasks) == 87 else "subset",
        "selected_ids": [task["id"] for task in tasks],
        "ordinals": {task["id"]: task["ordinal"] for task in tasks},
        "settings_sha256": controller.sha(run / "settings.json"),
        "dataset_manifest_sha256": controller.sha(harness / "data" / "manifest.json"),
        "frozen_files": {"harness": controller.files_digest(harness), "product": {}},
    }
    controller.write(run / "run.json", plan)
    for task in tasks:
        controller.write(run / "runs" / task["id"] / "task.json", controller.actor_task(task))
    return run, plan, settings


def write_execution(run, task_id):
    folder = run / "runs" / task_id
    controller.write(folder / "execution.json", {
        "status": "completed", "wall_seconds": 0.01, "usage": {}, "cost_usd": None,
    })
    controller.write(folder / "agent" / "messages.json", [])
    screenshot = folder / "screenshots" / "0001.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    # Valid 1x1 PNG fixture; never obtained from a live browser.
    import base64
    screenshot.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jZioAAAAASUVORK5CYII="))
    controller.write(folder / "frames.json", [{
        "step_num": 1, "screenshot_file": "screenshots/0001.png",
        "sha256": controller.sha(screenshot), "url": "https://offline.invalid/fixture",
    }])


def write_grade(run, task_id, score):
    folder = (run / "runs" / task_id).resolve()
    output = (run / "judges" / task_id).resolve()
    evidence_dir = output / "raw-deepseek"
    raw_path = evidence_dir / "judge-bu_v1.json"
    version = "1113-native-visible-observations-v3"
    sources = {str(folder / name): controller.sha(folder / name)
               for name in ("execution.json", "frames.json", "agent/messages.json", "task.json")}
    image = folder / "screenshots" / "0001.png"
    controller.write(evidence_dir / "evidence-manifest.json", {
        "source_folder": str(folder), "suite": "bu_v1", "version": version,
        "source_files": sources,
        "screenshots": [{"path": str(image), "sha256": controller.sha(image)}],
    })
    controller.write(raw_path, {
        "status": "judged", "score": score, "source_folder": str(folder),
        "evidence_version": version,
        "official_judge_sha256": controller.sha(run / "frozen/harness/vendor/official_judge.py"),
    })
    controller.write(output / "judge.json", {
        "status": "judged", "score": score, "judge_model": "deepseek-v4.1-flash",
        "benchmark": "BU-filter", "task_id": task_id, "source_folder": str(folder),
        "evidence_version": version, "raw_deepseek_grade": str(raw_path),
        "raw_deepseek_grade_sha256": controller.sha(raw_path),
    })


class InterpreterTests(unittest.TestCase):
    def test_executable_keeps_the_virtualenv_path_and_runtime_prefix(self):
        import subprocess
        with tempfile.TemporaryDirectory() as temp:
            venv = Path(temp) / "venv"
            (venv / "bin").mkdir(parents=True)
            binary = Path(sys.executable).resolve()
            link = venv / "bin" / "python"
            link.symlink_to(binary)
            (venv / "pyvenv.cfg").write_text(f"home = {binary.parent}\ninclude-system-site-packages = false\n")
            selected = controller.executable(link)
            self.assertEqual(selected, link.absolute())
            self.assertNotEqual(selected, selected.resolve())
            result = subprocess.run([str(selected), "-c", "import sys; print(sys.prefix)"],
                                    check=True, capture_output=True, text=True)
            self.assertEqual(Path(result.stdout.strip()), venv)

    def test_preflight_and_prepare_preserve_both_interpreter_symlinks(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            actor_python = base / "actor-venv" / "bin" / "python"
            judge_python = base / "judge-venv" / "bin" / "python"
            for link in [actor_python, judge_python]:
                link.parent.mkdir(parents=True)
                link.symlink_to(Path(sys.executable).resolve())
            product = base / "product"
            (product / "src" / "lexmount_browser_agent").mkdir(parents=True)
            (product / "src" / "lexmount_browser_agent" / "__init__.py").write_text("# offline product fixture\n")
            credentials = base / "credentials.json"
            args = SimpleNamespace(config=ROOT / "config.json", agent_source=str(product),
                                   agent_python=str(actor_python), judge_python=str(judge_python),
                                   credentials_file=str(credentials), browser=str(Path(sys.executable).resolve()),
                                   output=str(base / "new-run"), ids=[PUBLIC_TASKS[0]["id"]])
            cfg = {"browser_executable": args.browser}
            product_proof = {"browser_use_version": "1.0.3", "engine_files_sha256": {}, "package_versions": {}}
            with patch.object(controller, "config", return_value=cfg), \
                 patch.object(controller, "public_credentials", return_value={"endpoint_host": "offline.invalid"}), \
                 patch.object(controller, "product_probe", return_value=product_proof) as probe, \
                 patch.object(controller.subprocess, "run", side_effect=[
                     SimpleNamespace(stdout="Chrome offline\n"), SimpleNamespace(stdout="judge-import-ok\n")]) as process:
                proof = controller.preflight(args)
            probe.assert_called_once_with(product.resolve(), actor_python.absolute())
            judge_command = process.call_args_list[1].args[0]
            self.assertEqual(Path(judge_command[0]), judge_python.absolute())
            with patch.object(controller, "preflight", return_value=proof), \
                 patch.object(controller, "config", return_value=cfg):
                run = controller.prepare(args)
            settings = controller.read(run / "settings.json")
            self.assertEqual(settings["agent_python"], str(actor_python.absolute()))
            self.assertEqual(settings["judge_python"], str(judge_python.absolute()))


class SelectionTests(unittest.TestCase):
    def test_excluded_uuid_and_original_number_selectors_are_rejected(self):
        for row in EXCLUDED:
            for selector in [row["task_id"], str(row["original_ordinal"]),
                             f"{row['original_ordinal']:03}", f"#{row['original_ordinal']:03}"]:
                with self.subTest(selector=selector), self.assertRaises(ValueError):
                    controller.select_tasks([selector])

    def test_selection_uses_only_fixed_allowlist_and_rejects_duplicates(self):
        self.assertEqual(len(controller.select_tasks()), 87)
        task = PUBLIC_TASKS[0]
        self.assertEqual(controller.select_tasks([task["id"]]), [task])
        with self.assertRaises(ValueError):
            controller.select_tasks([task["id"], str(task["ordinal"])])
        with self.assertRaises(ValueError):
            controller.select_tasks(["BU_Bench_V1"])


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_dynamic_actor_replacement_and_slow_judge_have_separate_pools(self):
        tasks = PUBLIC_TASKS[:4]
        slow_id = tasks[0]["id"]
        actor_release = asyncio.Event()
        judge_release = asyncio.Event()
        non_slow_done = asyncio.Event()
        all_actor_done = asyncio.Event()
        counts = {"actor": 0, "judge": 0}
        peak = {"actor": 0, "judge": 0}
        actor_finished = []
        judge_finished = []
        timeline = []
        with tempfile.TemporaryDirectory() as temp:
            run, _, _ = fixture(temp, tasks)

            async def fake_launch(command, log, timeout):
                phase = "actor" if Path(command[1]).name == "actor.py" else "judge"
                folder = Path(command[command.index("--folder") + 1])
                task_id = folder.name
                counts[phase] += 1
                peak[phase] = max(peak[phase], counts[phase])
                timeline.append((phase + "_started", task_id))
                try:
                    if phase == "actor":
                        if task_id == slow_id:
                            await actor_release.wait()
                        else:
                            await asyncio.sleep(0)
                        write_execution(run, task_id)
                        actor_finished.append(task_id)
                        if sum(item != slow_id for item in actor_finished) == 3:
                            non_slow_done.set()
                        if len(actor_finished) == 4:
                            all_actor_done.set()
                    else:
                        await judge_release.wait()
                        await asyncio.sleep(0)
                        write_grade(run, task_id, 1)
                        judge_finished.append(task_id)
                finally:
                    counts[phase] -= 1
                    timeline.append((phase + "_finished", task_id))
                return {"returncode": 0, "pid": 123}

            with patch.object(controller, "launch", fake_launch):
                campaign = asyncio.create_task(controller.campaign(run))
                try:
                    # Three short actors finish through one slot while the first actor
                    # and the first judge remain blocked. A fixed batch would stall here.
                    await asyncio.wait_for(non_slow_done.wait(), 3)
                    self.assertNotIn(slow_id, actor_finished)
                    self.assertEqual(judge_finished, [])
                    actor_release.set()
                    await asyncio.wait_for(all_actor_done.wait(), 3)
                    self.assertEqual(judge_finished, [])
                    self.assertEqual(peak, {"actor": 2, "judge": 1})
                finally:
                    actor_release.set()
                    judge_release.set()
                    await asyncio.wait_for(campaign, 5)
            self.assertLess(timeline.index(("actor_finished", tasks[3]["id"])),
                            timeline.index(("actor_finished", slow_id)))
            summary = controller.summarize(run)
            self.assertEqual((summary["pass"], summary["fail"]), (4, 0))
            self.assertTrue(summary["complete"])
            self.assertIsNone(summary["full87_success_rate"])

    async def test_resume_keeps_legal_zero_without_actor_or_judge_rerun(self):
        task = PUBLIC_TASKS[0]
        with tempfile.TemporaryDirectory() as temp:
            run, _, _ = fixture(temp, [task])
            write_execution(run, task["id"])
            write_grade(run, task["id"], 0)
            grade = run / "judges" / task["id"] / "judge.json"
            original = grade.read_bytes()
            launch = AsyncMock(side_effect=AssertionError("A valid zero must not be rerun"))
            with patch.object(controller, "launch", launch):
                await controller.campaign(run)
                await controller.campaign(run)
            launch.assert_not_awaited()
            self.assertEqual(grade.read_bytes(), original)
            summary = controller.summarize(run)
            self.assertEqual((summary["pass"], summary["fail"], summary["unknown"]), (0, 1, 0))
            self.assertEqual(summary["success_rate"], 0)

    async def test_boolean_score_is_unknown_and_not_silently_rerun(self):
        task = PUBLIC_TASKS[0]
        with tempfile.TemporaryDirectory() as temp:
            run, _, _ = fixture(temp, [task])
            write_execution(run, task["id"])
            write_grade(run, task["id"], False)
            await self.assert_invalid_receipt_preserved(run, task["id"])

    async def test_resume_preserves_admitted_actor_without_execution_as_unknown(self):
        task = PUBLIC_TASKS[0]
        with tempfile.TemporaryDirectory() as temp:
            run, _, _ = fixture(temp, [task])
            started = run / "runs" / task["id"] / "started.json"
            controller.write(started, {"started_at": "original-admission"})
            original = started.read_bytes()
            launch = AsyncMock(side_effect=AssertionError("Interrupted actor must not rerun automatically"))
            with patch.object(controller, "launch", launch):
                await controller.campaign(run)
            launch.assert_not_awaited()
            self.assertEqual(started.read_bytes(), original)
            summary = controller.summarize(run)
            self.assertEqual((summary["unknown"], summary["pending"], summary["fail"]), (1, 0, 0))
            self.assertIsNone(summary["success_rate"])

    async def test_resume_refuses_an_excluded_id_in_edited_run_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            run, plan, _ = fixture(temp, [PUBLIC_TASKS[0]])
            excluded = EXCLUDED[0]
            task_id = excluded["task_id"]
            plan.update(selected_ids=[task_id], ordinals={task_id: excluded["original_ordinal"]})
            controller.write(run / "run.json", plan)
            launch = AsyncMock(side_effect=AssertionError("Excluded task must fail before launch"))
            with patch.object(controller, "launch", launch), self.assertRaises(ValueError):
                await controller.campaign(run)
            launch.assert_not_awaited()

    async def test_resume_refuses_modified_actor_task_payload(self):
        task = PUBLIC_TASKS[0]
        with tempfile.TemporaryDirectory() as temp:
            run, _, _ = fixture(temp, [task])
            path = run / "runs" / task["id"] / "task.json"
            changed = controller.read(path)
            changed["instruction"] += " changed"
            controller.write(path, changed)
            launch = AsyncMock(side_effect=AssertionError("Modified task must fail before launch"))
            with patch.object(controller, "launch", launch), self.assertRaises(ValueError):
                await controller.campaign(run)
            launch.assert_not_awaited()

    async def assert_invalid_receipt_preserved(self, run, task_id):
        receipt = run / "judges" / task_id / "judge.json"
        original = receipt.read_bytes()
        self.assertIsNone(controller.verified_grade(run, task_id))
        summary = controller.summarize(run)
        self.assertEqual((summary["pass"], summary["fail"], summary["unknown"], summary["pending"]), (0, 0, 1, 0))
        self.assertFalse(summary["tasks"][0]["receipt_valid"])
        launch = AsyncMock(side_effect=AssertionError("Mismatched receipt must not trigger a silent rerun"))
        with patch.object(controller, "launch", launch):
            await controller.campaign(run)
        launch.assert_not_awaited()
        self.assertEqual(receipt.read_bytes(), original)
        self.assertEqual(controller.summarize(run)["unknown"], 1)
        events = [json.loads(line)["event"] for line in (run / "events.jsonl").read_text().splitlines()]
        self.assertIn("invalid_grade_preserved", events)
        self.assertNotIn("valid_grade_reused", events)

    async def test_copied_old100_receipt_without_current_execution_stays_unknown(self):
        task = PUBLIC_TASKS[0]
        with tempfile.TemporaryDirectory() as temp:
            run, _, _ = fixture(temp, [task])
            old = Path(temp) / "old-bu100-run" / "judge.json"
            controller.write(old, {
                "status": "judged", "score": 1, "benchmark": "BU_Bench_V1",
                "task_id": task["id"], "source_folder": str(Path(temp) / "old-bu100-run" / task["id"]),
            })
            destination = run / "judges" / task["id"] / "judge.json"
            destination.parent.mkdir(parents=True)
            shutil.copy2(old, destination)
            self.assertFalse((run / "runs" / task["id"] / "execution.json").exists())
            await self.assert_invalid_receipt_preserved(run, task["id"])

    async def test_other_task_id_receipt_is_not_counted_or_reused(self):
        task = PUBLIC_TASKS[0]
        with tempfile.TemporaryDirectory() as temp:
            run, _, _ = fixture(temp, [task])
            write_execution(run, task["id"])
            write_grade(run, task["id"], 1)
            self.assertIsNotNone(controller.verified_grade(run, task["id"]))
            receipt = run / "judges" / task["id"] / "judge.json"
            changed = controller.read(receipt)
            changed["task_id"] = PUBLIC_TASKS[1]["id"]
            controller.write(receipt, changed)
            await self.assert_invalid_receipt_preserved(run, task["id"])

    async def test_execution_changed_after_judging_invalidates_pass(self):
        task = PUBLIC_TASKS[0]
        with tempfile.TemporaryDirectory() as temp:
            run, _, _ = fixture(temp, [task])
            write_execution(run, task["id"])
            write_grade(run, task["id"], 1)
            self.assertIsNotNone(controller.verified_grade(run, task["id"]))
            execution = run / "runs" / task["id"] / "execution.json"
            changed = controller.read(execution)
            changed["status"] = "altered-after-judging"
            controller.write(execution, changed)
            await self.assert_invalid_receipt_preserved(run, task["id"])

    async def test_screenshot_changed_after_judging_invalidates_pass(self):
        task = PUBLIC_TASKS[0]
        with tempfile.TemporaryDirectory() as temp:
            run, _, _ = fixture(temp, [task])
            write_execution(run, task["id"])
            write_grade(run, task["id"], 1)
            self.assertIsNotNone(controller.verified_grade(run, task["id"]))
            (run / "runs" / task["id"] / "screenshots" / "0001.png").write_bytes(b"changed-image")
            await self.assert_invalid_receipt_preserved(run, task["id"])

    async def test_summary_keeps_fixed_87_denominator_and_ignores_historical_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            run, _, _ = fixture(temp, PUBLIC_TASKS)
            # Historical receipts outside the new run must not fill pending cells.
            archive = Path(temp) / "old-bu100-run"
            for task in PUBLIC_TASKS:
                controller.write(archive / "judges" / task["id"] / "judge.json", {"status": "judged", "score": 1, "benchmark": "BU_Bench_V1"})
            first, second, third, fourth = PUBLIC_TASKS[:4]
            write_execution(run, first["id"])
            write_grade(run, first["id"], 1)
            write_execution(run, second["id"])
            write_grade(run, second["id"], 0)
            write_execution(run, third["id"])
            controller.write(run / "judges" / third["id"] / "judge.json", {"status": "judge_error", "score": None})
            controller.write(run / "runs" / fourth["id"] / "started.json", {"started_at": "interrupted"})
            summary = controller.summarize(run)
            self.assertEqual((summary["dataset_count"], summary["selected_count"]), (87, 87))
            self.assertEqual((summary["pass"], summary["fail"], summary["unknown"], summary["pending"]), (1, 1, 2, 83))
            self.assertFalse(summary["complete"])
            self.assertIsNone(summary["success_rate"])
            self.assertIsNone(summary["full87_success_rate"])
            self.assertAlmostEqual(summary["confirmed_lower_bound"], 1 / 87)
            self.assertAlmostEqual(summary["upper_bound"], 86 / 87)
            self.assertIsNone(summary["agent_cost_usd"])


if __name__ == "__main__":
    unittest.main()
