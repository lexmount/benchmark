#!/usr/bin/env python3
"""Apply an explicit concurrency override without changing a frozen Actor/grader.

The old dispatcher receives SIGINT and drains its existing workers. This
coordinator counts those workers against the new cap and schedules only the
remaining task IDs. All VM/task execution uses the original frozen runtime.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import signal
import socket
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text())


def optional_read(path):
    try:
        value = read(path)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write(path, value, *, exclusive=False):
    path = Path(path)
    if exclusive:
        with path.open('x') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
    else:
        temporary = path.with_name(path.name + '.tmp-' + uuid4().hex)
        write(temporary, value, exclusive=True)
        temporary.replace(path)


def now():
    return datetime.now(timezone.utc).isoformat()


def identity(pid):
    """PID plus Linux start time avoids attributing a reused PID to this run."""
    try:
        value = Path(f'/proc/{int(pid)}/stat').read_text()
        fields = value[value.rfind(')') + 2:].split()
        if fields[0] == 'Z':
            return None
        return {'pid': int(pid), 'start_ticks': fields[19]}
    except FileNotFoundError:
        return None


def live_legacy_workers(snapshot):
    return [worker for worker in snapshot
            if identity(worker['pid']) == {k: worker[k] for k in ('pid', 'start_ticks')}]


def pending_legacy_workers(snapshot, run_dir):
    live = live_legacy_workers(snapshot)
    pending = []
    for worker in snapshot:
        folder = run_dir / 'tasks' / worker['task_id']
        receipt = optional_read(folder / 'receipt.json')
        cleanup = optional_read(folder / 'worker-cleanup.json')
        if worker in live or not (receipt.get('owned_vm_closed') is True or cleanup.get('verified_absent') is True):
            pending.append(worker)
    return pending


def remaining_tasks(tasks, run_dir, legacy_ids):
    return [item['task_id'] for item in tasks if item['task_id'] not in legacy_ids
            and not (run_dir / 'tasks' / item['task_id'] / 'receipt.json').exists()]


def frozen_runtime(run_dir):
    metadata = read(run_dir / 'run.json')
    sys.path.insert(0, metadata['harness_root'])
    import runtime
    if Path(runtime.__file__).resolve() != (Path(metadata['harness_root']) / 'runtime.py').resolve():
        raise RuntimeError('The execution runtime is not the original frozen source')
    return runtime, metadata


def task_worker(run_dir, task_id, model_config):
    runtime, _ = frozen_runtime(Path(run_dir))
    runtime._worker_entry(run_dir, task_id, model_config)


@contextmanager
def lock(run_dir):
    path = run_dir / 'concurrency-override.lock'
    owner = {'pid': os.getpid(), 'hostname': socket.gethostname(), 'started_at': now()}
    write(path, owner, exclusive=True)
    try:
        yield path, owner
    finally:
        if path.exists() and read(path).get('pid') == os.getpid():
            path.unlink()


def stop_old_dispatcher(run_dir, event):
    path = run_dir / 'runtime.lock'
    if not path.exists():
        return []
    old = read(path)
    if old.get('hostname') != socket.gethostname():
        raise RuntimeError('Old dispatcher belongs to another host')
    pid = old['pid']
    original_identity = identity(pid)
    if original_identity is None:
        raise RuntimeError('Stale original run lock; inspect ownership before takeover')
    command = Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0', b' ').decode()
    if str(run_dir) not in command or 'run' not in command:
        raise RuntimeError('Old dispatcher identity does not match this run')
    events_path = run_dir / 'events.jsonl'
    old_length = events_path.read_bytes().rfind(b'\n') + 1 if events_path.exists() else 0
    os.kill(pid, signal.SIGINT)
    event('old_dispatch_pause_requested', old_dispatcher=original_identity)
    deadline = time.monotonic() + 40
    while True:
        appended = events_path.read_bytes()[old_length:].decode() if events_path.exists() else ''
        acknowledged = any(json.loads(line).get('event') == 'dispatch_paused'
                           for line in appended.splitlines(keepends=True) if line.endswith('\n') and line.strip())
        if acknowledged or identity(pid) != original_identity:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError('Old dispatcher did not acknowledge stopping new dispatch')
        time.sleep(.25)
    workers = optional_read(path).get('worker_pids', [])
    mapping = {}
    for line in events_path.read_text().splitlines(keepends=True):
        if not line.endswith('\n'):
            continue
        row = json.loads(line)
        if row.get('event') == 'worker_started':
            mapping[row['pid']] = row['task_id']
    result = []
    for worker_pid in workers:
        value = identity(worker_pid)
        if worker_pid not in mapping:
            raise RuntimeError('Cannot identify an inherited task; refusing overlapping dispatch')
        # A dead worker can still own a VM while its original parent is cleaning
        # it. Reserve that task/slot too; never mark its partial directory interrupted.
        result.append({**(value or {'pid': worker_pid, 'start_ticks': None}),
                       'task_id': mapping[worker_pid], 'owner_identity': original_identity})
    event('old_dispatch_paused', old_dispatcher=original_identity, inherited_workers=result)
    return result


def run(args):
    run_dir = args.run_dir.resolve()
    if type(args.concurrency) is not int or not 1 <= args.concurrency <= 12:
        raise ValueError('The supported override is between 1 and 12 VM workers')
    # Use the existing full source/manifest checks before signaling or dispatching.
    spec = importlib.util.spec_from_file_location('override_control', ROOT / 'evaluate.py')
    control = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(control)
    metadata = control.verify_run(run_dir)
    runtime, _ = frozen_runtime(run_dir)
    runtime._actor_settings(metadata, args.model_config.resolve())
    tasks = runtime._tasks(metadata)
    checked_probe = read(run_dir / 'probe.json')
    if (checked_probe.get('status') != 'passed'
            or checked_probe.get('run_metadata_sha256') != runtime._digest(run_dir / 'run.json')):
        raise RuntimeError('A passed original model-free probe is required')
    audit = run_dir / 'control-overrides' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-') + uuid4().hex[:8])
    audit.mkdir(parents=True)
    source = Path(__file__).read_bytes()
    (audit / 'concurrency_override.py').write_bytes(source)

    def event(name, **values):
        with (audit / 'events.jsonl').open('a') as stream:
            stream.write(json.dumps({'at': now(), 'event': name, **values}, allow_nan=False) + '\n')

    active, paused, stop_reason = {}, False, None
    counts = {'scored': 0, 'invalid': 0, 'skipped_existing': 0}
    context = multiprocessing.get_context('spawn')

    def pause(_signum, _frame):
        nonlocal paused
        paused = True

    previous = signal.signal(signal.SIGINT, pause)
    with lock(run_dir) as (lock_path, owner):
        legacy = stop_old_dispatcher(run_dir, event)
        ordered = remaining_tasks(tasks, run_dir, {w['task_id'] for w in legacy})
        record = {'schema_version': 1, 'created_at': now(), 'run_dir': str(run_dir),
                  'old_concurrency': metadata['config']['runtime']['concurrency'],
                  'concurrency_override': args.concurrency, 'inherited_workers': legacy,
                  'remaining_task_ids': ordered, 'actor_and_grader': 'original frozen runtime',
                  'source_sha256': hashlib.sha256(source).hexdigest(),
                  'run_metadata_sha256': runtime._digest(run_dir / 'run.json'),
                  'resource_policy': metadata['config']['runtime'], 'model_or_task_changes': False}
        write(audit / 'override.json', record, exclusive=True)
        index = 0
        try:
            while active or pending_legacy_workers(legacy, run_dir) or (index < len(ordered) and stop_reason is None):
                inherited = pending_legacy_workers(legacy, run_dir)
                if paused and stop_reason is None:
                    stop_reason = 'interrupted'
                    event('dispatch_paused', in_flight=len(active) + len(inherited))
                for task_id in [key for key, process in active.items() if not process.is_alive()]:
                    result, failed = runtime._finished_process(run_dir, metadata, task_id, active.pop(task_id))
                    runtime._count_outcome(counts, result)
                    if failed:
                        stop_reason = stop_reason or 'worker_or_cleanup_failure'
                    event('task_collected', task_id=task_id, status=result.get('status'), score=result.get('score'))
                # Inherited failures also stop new dispatch; their old owner performs cleanup.
                for worker in legacy:
                    path = run_dir / 'tasks' / worker['task_id'] / 'receipt.json'
                    if optional_read(path).get('owned_vm_closed') is False:
                        stop_reason = stop_reason or 'inherited_cleanup_failure'
                    owner_token = worker.get('owner_identity')
                    if (worker in inherited and worker not in live_legacy_workers(legacy)
                            and owner_token and identity(owner_token['pid']) != owner_token):
                        folder = path.parent
                        cleanup = runtime._cleanup_dead_worker(metadata, folder, worker['task_id'])
                        if not path.exists():
                            item = next(t for t in tasks if t['task_id'] == worker['task_id'])
                            write(path, {'schema_version': 1, 'task_id': worker['task_id'],
                                'task_sha256': item['sha256'], 'status': 'interrupted', 'score': None,
                                'finished_at': now(), 'error_type': 'InheritedWorkerFailure',
                                'owned_vm_closed': cleanup['verified_absent'],
                                'owned_container_removal_verified': cleanup['verified_absent']}, exclusive=True)
                        stop_reason = stop_reason or 'inherited_worker_failure'
                        event('inherited_worker_failure', task_id=worker['task_id'], cleanup=cleanup)
                        if not cleanup['verified_absent']:
                            raise RuntimeError('Inherited VM cleanup remains unconfirmed; stop and inspect')
                while stop_reason is None and index < len(ordered) and len(active) + len(inherited) < args.concurrency:
                    if paused or any(not process.is_alive() for process in active.values()):
                        break
                    total = len(active) + len(inherited)
                    admission = runtime._resource_admission(total, metadata['config']['runtime'])
                    if not admission['admitted']:
                        event('resource_wait', **admission)
                        break
                    task_id = ordered[index]
                    index += 1
                    previous_outcome = runtime._prior_outcome(run_dir, task_id)
                    if previous_outcome is not None:
                        runtime._count_outcome(counts, previous_outcome)
                        continue
                    process = context.Process(target=task_worker,
                        args=(str(run_dir), task_id, str(args.model_config.resolve())), name='OSWorld12-' + task_id[:8])
                    active[task_id] = process
                    try:
                        process.start()
                    except Exception as error:
                        if process.pid is None:
                            active.pop(task_id)
                            index -= 1
                        stop_reason = 'worker_start_failed'
                        event('worker_start_failed', task_id=task_id, error_type=type(error).__name__)
                        break
                    event('worker_started', task_id=task_id, pid=process.pid,
                          in_flight=len(active) + len(inherited), admission=admission)
                write(lock_path, {**owner, 'concurrency': args.concurrency, 'audit_dir': str(audit),
                      'worker_pids': [p.pid for p in active.values()],
                      'inherited_worker_pids': [w['pid'] for w in inherited]})
                if active or inherited or (index < len(ordered) and stop_reason is None):
                    time.sleep(2)
        finally:
            # Preserve all running tasks even when the coordinator itself errors.
            for task_id, process in active.items():
                process.join()
                runtime._finished_process(run_dir, metadata, task_id, process)
            while live_legacy_workers(legacy):
                time.sleep(2)
            signal.signal(signal.SIGINT, previous)
        summary = {'status': 'failed' if stop_reason else 'completed', 'stop_reason': stop_reason,
                   'collected_new_workers': counts, 'not_started': len(ordered) - index,
                   'finished_at': now(), 'audit_dir': str(audit)}
        write(audit / 'summary.json', summary, exclusive=True)
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--model-config', type=Path, required=True)
    parser.add_argument('--concurrency', type=int, required=True)
    value = run(parser.parse_args())
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 1 if value['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
