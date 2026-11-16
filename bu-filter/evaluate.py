#!/usr/bin/env python3
"""BU-filter controller: frozen 87-task allowlist, independent dynamic pools."""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import getpass
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dataset import actor_task, load_tasks, validate_dataset


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def executable(path):
    # Keep the venv/bin/python symlink: resolving it selects the base interpreter and loses the venv.
    return Path(os.path.abspath(Path(path).expanduser()))


def event(run, name, **fields):
    with (Path(run) / 'events.jsonl').open('a') as stream:
        stream.write(json.dumps({'at': datetime.now(timezone.utc).isoformat(),
                                 'event': name, **fields}, ensure_ascii=False) + '\n')


def config(path=HERE / 'config.json'):
    value = read(path)
    if value['benchmark'] != 'BU-filter' or value['expected_tasks'] != 87:
        raise ValueError('Only the fixed BU-filter 87-task dataset is supported')
    if value['agent']['max_steps'] != 300 or value['agent']['timeout_seconds'] != 3600:
        raise ValueError('BU-filter uses exactly 300 model turns and 3600 seconds')
    if value['agent']['model'] != 'deepseek-v4.1-flash' or value['agent']['reasoning_effort'] != 'high':
        raise ValueError('The frozen Actor model/effort must remain DeepSeek high')
    if value['agent']['mode'] != 'ultrafast':
        raise ValueError('The frozen browser interaction mode is ultrafast')
    if value['judge']['model'] != 'deepseek-v4.1-flash' or value['judge']['reasoning_effort'] != 'low':
        raise ValueError('The primary Judge must remain DeepSeek low')
    if value['judge']['refusal_fallback_model'] != 'gpt-6.1-sol':
        raise ValueError('Only the archived refusal-only fallback is supported')
    expected_judge = {'max_tokens': 16384, 'timeout_seconds': 600, 'sdk_retries': 2,
                      'logical_attempts': 2, 'process_timeout_seconds': 14400}
    if any(value['judge'].get(key) != expected for key, expected in expected_judge.items()):
        raise ValueError('The archived Judge transport/recovery limits must remain unchanged')
    if value['viewport'] != {'width': 1440, 'height': 900}:
        raise ValueError('The frozen viewport is 1440 x 900')
    for key in ('actor_concurrency', 'judge_concurrency'):
        if type(value[key]) is not int or value[key] < 1:
            raise ValueError(f'{key} must be a positive integer')
    return value


def select_tasks(selectors=None):
    tasks = load_tasks()
    if not selectors:
        return tasks
    selected = []
    for selector in selectors:
        matches = [task for task in tasks if selector == task['id'] or selector.lstrip('#0') == str(task['ordinal'])]
        if len(matches) != 1:
            raise ValueError(f'Task {selector!r} is not in BU-filter; excluded/unknown IDs cannot run')
        if matches[0] in selected:
            raise ValueError(f'Duplicate task selection: {selector}')
        selected.append(matches[0])
    wanted = {task['id'] for task in selected}
    return [task for task in tasks if task['id'] in wanted]


def files_digest(root):
    root = Path(root)
    return {str(path.relative_to(root)): sha(path) for path in sorted(root.rglob('*'))
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc'}


def verify_run(run):
    run = Path(run)
    plan = read(run / 'run.json')
    if plan['benchmark'] != 'BU-filter' or plan['dataset_count'] != 87:
        raise ValueError('This is not a BU-filter run')
    canonical = {task['id']: task for task in load_tasks()}
    selected = plan['selected_ids']
    if (not selected or len(selected) != len(set(selected)) or not set(selected) <= canonical.keys()
            or plan['selected_count'] != len(selected)
            or plan['scope'] != ('full87' if len(selected) == 87 else 'subset')
            or plan['ordinals'] != {task_id: canonical[task_id]['ordinal'] for task_id in selected}):
        raise ValueError('Run selection is not a valid subset of the fixed BU-filter allowlist')
    for task_id in selected:
        if read(run / 'runs' / task_id / 'task.json') != actor_task(canonical[task_id]):
            raise ValueError(f'Actor task payload changed: {task_id}')
    if sha(run / 'settings.json') != plan['settings_sha256']:
        raise ValueError('Run settings changed after freezing')
    for tree, hashes in plan['frozen_files'].items():
        for name, expected in hashes.items():
            if sha(run / 'frozen' / tree / name) != expected:
                raise ValueError(f'Frozen input changed: {tree}/{name}')
    frozen = run / 'frozen' / 'harness'
    # Validate the original manifest hash without importing a different process's dataset module.
    if sha(frozen / 'data' / 'manifest.json') != plan['dataset_manifest_sha256']:
        raise ValueError('Frozen dataset manifest changed')
    return plan, read(run / 'settings.json')


def public_credentials(path):
    value = read(path)
    if value.get('model', 'deepseek-v4.1-flash') != 'deepseek-v4.1-flash':
        raise ValueError('Credential file model differs from frozen model')
    if not value.get('api_key') or not value.get('base_url'):
        raise ValueError('Credential file needs api_key and base_url')
    if urlsplit(value['base_url']).scheme not in ('http', 'https'):
        raise ValueError('Invalid model endpoint')
    return {'endpoint_host': urlsplit(value['base_url']).hostname}


def verified_grade(run, task_id):
    """Accept only a receipt bound to this run's executed task and unchanged evidence."""
    run = Path(run).resolve()
    folder = run / 'runs' / task_id
    output = run / 'judges' / task_id
    try:
        value = read(output / 'judge.json')
        if (value.get('status') != 'judged' or type(value.get('score')) is not int
                or value['score'] not in (0, 1) or value.get('task_id') != task_id
                or value.get('benchmark') != 'BU-filter' or value.get('source_folder') != str(folder)
                or value.get('evidence_version') != '1113-native-visible-observations-v3'):
            return None
        for name in ('execution.json', 'frames.json', 'agent/messages.json'):
            if not (folder / name).is_file():
                return None
        raw_name = 'raw_gpt_grade' if value.get('raw_gpt_grade') and value.get('judge_model') == 'gpt-6.1-sol' else 'raw_deepseek_grade'
        raw_path = Path(value[raw_name]).resolve()
        if not raw_path.is_relative_to(output) or sha(raw_path) != value[raw_name + '_sha256']:
            return None
        raw = read(raw_path)
        if (raw.get('status') != 'judged' or type(raw.get('score')) is not int or raw['score'] != value['score']
                or raw.get('source_folder') != str(folder)
                or raw.get('evidence_version') != value['evidence_version']
                or raw.get('official_judge_sha256') != sha(run / 'frozen/harness/vendor/official_judge.py')):
            return None
        evidence = read(raw_path.parent / 'evidence-manifest.json')
        if (evidence.get('source_folder') != str(folder) or evidence.get('suite') != 'bu_v1'
                or evidence.get('version') != value['evidence_version']):
            return None
        sources = evidence['source_files']
        if not {str(folder / name) for name in ('execution.json', 'frames.json', 'agent/messages.json')} <= sources.keys():
            return None
        for name, expected in sources.items():
            path = Path(name).resolve()
            if not path.is_relative_to(folder) or sha(path) != expected:
                return None
        for image in evidence.get('screenshots', []):
            path = Path(image['path']).resolve()
            if not path.is_relative_to(folder / 'screenshots') or sha(path) != image['sha256']:
                return None
        return value
    except (OSError, ValueError, KeyError, TypeError):
        return None


def product_probe(source, python):
    code = '''import sys,json,hashlib,inspect
from pathlib import Path
from importlib.metadata import version
sys.path.insert(0,str(Path(sys.argv[1])/'src'))
engine=Path(sys.argv[1])/'src/lexmount_browser_agent/engine'
if (engine/'browser_use/__init__.py').is_file():sys.path.insert(0,str(engine))
import lexmount_browser_agent, browser_use
from lexmount_browser_agent import AgentConfig
cfg=AgentConfig(api_key='offline-check-key',base_url='http://127.0.0.1/v1',model='deepseek-v4.1-flash',reasoning_effort='high',mode='ultrafast',max_steps=300,timeout_seconds=3600)
installed=Path(browser_use.__file__).resolve().parent
hashes={str(p.relative_to(installed)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(installed.rglob('*.py')) if '__pycache__' not in p.parts}
packages={n:version(n) for n in ('browser-use','browser-harness','pydantic-ai-slim','pydantic','openai','httpx','cdp-use')}
print(json.dumps({'product_import':lexmount_browser_agent.__file__,'browser_use_import':browser_use.__file__,'browser_use_version':version('browser-use'),'engine_files_sha256':hashes,'package_versions':packages,'max_steps':cfg.max_steps,'timeout_seconds':cfg.timeout_seconds,'mode':cfg.mode,'reasoning_effort':cfg.reasoning_effort}))
'''
    result = subprocess.run([str(python), '-c', code, str(source)], capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError('Product import/preflight failed; check the selected product environment: ' + result.stderr[-1200:])
    proof = json.loads(result.stdout.strip().splitlines()[-1])
    if not Path(proof['product_import']).resolve().is_relative_to(Path(source).resolve()):
        raise ValueError('The selected Python imported a different product checkout')
    return proof


def preflight(args):
    cfg = config(args.config)
    dataset = validate_dataset()
    source = Path(args.agent_source).expanduser().resolve()
    if not (source / 'src' / 'lexmount_browser_agent').is_dir():
        raise ValueError('--agent-source must point to the product checkout containing src/')
    credentials = Path(args.credentials_file).expanduser().resolve()
    public = public_credentials(credentials)
    browser = Path(args.browser or cfg['browser_executable']).resolve()
    version = subprocess.run([str(browser), '--version'], check=True, capture_output=True, text=True, timeout=20).stdout.strip()
    probe = product_probe(source, executable(args.agent_python))
    # The scoring process uses the archived 0.x message types, never the Actor interpreter.
    check = subprocess.run([str(executable(args.judge_python)), '-c',
                            'import openai,httpx,cryptography;from browser_use.llm.messages import UserMessage;print("judge-import-ok")'],
                           check=True, capture_output=True, text=True, timeout=60)
    return {'dataset': dataset, 'product': probe, 'browser': {'path': str(browser), 'version': version, 'sha256': sha(browser)},
            'judge_import': check.stdout.strip().splitlines()[-1], 'model': public}


def prepare(args):
    proof = preflight(args)
    cfg = config(args.config)
    tasks = select_tasks(args.ids)
    run = Path(args.output).expanduser().resolve()
    run.mkdir(parents=True, exist_ok=False, mode=0o700)
    frozen = run / 'frozen'
    frozen.mkdir()
    shutil.copytree(HERE, frozen / 'harness', ignore=shutil.ignore_patterns('.venv*', '__pycache__', '*.pyc', 'results', '.private', '.git'))
    source = Path(args.agent_source).resolve()
    product = frozen / 'product'
    product.mkdir()
    shutil.copytree(source / 'src', product / 'src', ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.egg-info'))
    for name in ('pyproject.toml', 'uv.lock'):
        if (source / name).is_file():
            shutil.copy2(source / name, product / name)
    settings = {**cfg, 'product_source': str(product), 'agent_python': str(executable(args.agent_python)),
                'judge_python': str(executable(args.judge_python)),
                'credentials_file': str(Path(args.credentials_file).resolve()),
                'browser_executable': proof['browser']['path'],
                'expected_engine': {'version': proof['product']['browser_use_version'],
                                    'files_sha256': proof['product']['engine_files_sha256'],
                                    'package_versions': proof['product']['package_versions']}}
    write(run / 'settings.json', settings)
    plan = {'schema_version': 1, 'benchmark': 'BU-filter', 'dataset_count': 87,
            'selected_count': len(tasks), 'scope': 'full87' if len(tasks) == 87 else 'subset',
            'selected_ids': [task['id'] for task in tasks],
            'ordinals': {task['id']: task['ordinal'] for task in tasks},
            'created_at': datetime.now(timezone.utc).isoformat(),
            'preflight': proof, 'settings_sha256': sha(run / 'settings.json'),
            'dataset_manifest_sha256': sha(frozen / 'harness' / 'data' / 'manifest.json'),
            'frozen_files': {'harness': files_digest(frozen / 'harness'), 'product': files_digest(product)},
            'notes': ['Model rounds are not GUI actions or physical HTTP requests.',
                      'No prior passes are merged into this run.', 'Only the fixed 87 task IDs are runnable.']}
    write(run / 'run.json', plan)
    for task in tasks:
        folder = run / 'runs' / task['id']
        write(folder / 'task.json', actor_task(task))
    return run


async def launch(command, log, timeout):
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('ab') as stream:
        process = await asyncio.create_subprocess_exec(*map(str, command), stdout=stream, stderr=stream,
                                                      start_new_session=True)
        try:
            await asyncio.wait_for(process.wait(), timeout)
            return {'returncode': process.returncode, 'pid': process.pid}
        except (asyncio.TimeoutError, asyncio.CancelledError) as error:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                await asyncio.wait_for(process.wait(), 15)
            except (ProcessLookupError, asyncio.TimeoutError):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.wait()
            if isinstance(error, asyncio.CancelledError):
                raise
            return {'returncode': process.returncode, 'pid': process.pid, 'timeout': True}


def summarize(run):
    run = Path(run)
    plan, settings = verify_run(run)
    rows = []
    for task_id in plan['selected_ids']:
        execution_path = run / 'runs' / task_id / 'execution.json'
        grade_path = run / 'judges' / task_id / 'judge.json'
        execution = read(execution_path) if execution_path.exists() else None
        grade = read(grade_path) if grade_path.exists() else None
        valid = verified_grade(run, task_id)
        state = 'pass' if valid and grade['score'] == 1 else 'fail' if valid else 'unknown' if execution or grade_path.exists() or (run / 'runs' / task_id / 'started.json').exists() else 'pending'
        rows.append({'ordinal': plan['ordinals'][task_id], 'task_id': task_id, 'state': state,
                     'execution_status': execution.get('status') if execution else None,
                     'judge_status': grade.get('status') if grade else None,
                     'receipt_valid': bool(valid),
                     'judge_model': grade.get('judge_model') if grade else None,
                     'wall_seconds': execution.get('wall_seconds') if execution else None,
                     'usage': execution.get('usage') if execution else None,
                     'cost_usd': execution.get('cost_usd') if execution else None})
    counts = {state: sum(row['state'] == state for row in rows) for state in ('pass', 'fail', 'unknown', 'pending')}
    total = len(rows)
    complete = counts['unknown'] == 0 and counts['pending'] == 0
    known_costs = [row['cost_usd'] for row in rows if row['cost_usd'] is not None]
    result = {'benchmark': 'BU-filter', 'dataset_count': 87, 'scope': plan['scope'], 'selected_count': total,
              'updated_at': datetime.now(timezone.utc).isoformat(), 'complete': complete, **counts,
              'success_rate': counts['pass'] / total if complete and total else None,
              'full87_success_rate': counts['pass'] / 87 if complete and total == 87 else None,
              'confirmed_lower_bound': counts['pass'] / total if total else None,
              'upper_bound': (counts['pass'] + counts['unknown'] + counts['pending']) / total if total else None,
              'agent_cost_usd': sum(known_costs) if len(known_costs) == total else None,
              'known_agent_cost_subtotal_usd': sum(known_costs) if known_costs else None,
              'cost_unknown_tasks': total - len(known_costs), 'tasks': rows,
              'scoring_note': 'Fixed denominator; no automatic infra exclusions and no merging historical passes.'}
    write(run / 'summary.json', result)
    return result


async def campaign(run):
    run = Path(run)
    plan, settings = verify_run(run)
    lock = (run / 'controller.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError('A controller is already operating this run')
    actor_slots = asyncio.Semaphore(settings['actor_concurrency'])
    judge_slots = asyncio.Semaphore(settings['judge_concurrency'])
    active = {'actor': 0, 'judge': 0}
    harness = run / 'frozen' / 'harness'
    event(run, 'controller_started', pid=os.getpid(), selected=len(plan['selected_ids']))

    async def one(task_id):
        folder = run / 'runs' / task_id
        judge_folder = run / 'judges' / task_id
        grade_file = judge_folder / 'judge.json'
        if grade_file.exists():
            if verified_grade(run, task_id) is not None:
                event(run, 'valid_grade_reused', task_id=task_id)
                return
            old = read(grade_file)
            if old.get('status') == 'judged':
                event(run, 'invalid_grade_preserved', task_id=task_id)
                return  # Preserve disputed evidence; never silently rerun a copied/mismatched receipt.
        if not (folder / 'execution.json').exists():
            # An admitted but interrupted Actor is unknown. Resume never reruns it silently.
            if (folder / 'started.json').exists():
                event(run, 'interrupted_actor_preserved', task_id=task_id)
                return
            async with actor_slots:
                verify_run(run)
                write(folder / 'started.json', {'started_at': datetime.now(timezone.utc).isoformat()})
                active['actor'] += 1
                event(run, 'actor_started', task_id=task_id, active=dict(active))
                try:
                    receipt = await launch([settings['agent_python'], harness / 'actor.py', '--folder', folder,
                                            '--settings', run / 'settings.json'], folder / 'actor.log',
                                           settings['agent']['timeout_seconds'] + settings['watchdog_grace_seconds'])
                    write(folder / 'process.json', receipt)
                finally:
                    active['actor'] -= 1
                    event(run, 'actor_released', task_id=task_id, active=dict(active))
                    summarize(run)
        # Actor slot has already been released: a slow Judge never holds it.
        if not (folder / 'execution.json').exists():
            event(run, 'actor_missing_execution', task_id=task_id)
            return
        async with judge_slots:
            verify_run(run)
            active['judge'] += 1
            event(run, 'judge_started', task_id=task_id, active=dict(active))
            try:
                receipt = await launch([settings['judge_python'], harness / 'judge.py', '--folder', folder,
                                        '--output', judge_folder, '--task-id', task_id, '--settings', run / 'settings.json'],
                                       judge_folder / 'judge.log', settings['judge']['process_timeout_seconds'])
                write(judge_folder / 'process.json', receipt)
            finally:
                active['judge'] -= 1
                event(run, 'judge_released', task_id=task_id, active=dict(active))
                summarize(run)

    async def guarded(task_id):
        try:
            await one(task_id)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            event(run, 'task_controller_error', task_id=task_id, error_type=type(error).__name__, message=str(error))

    jobs = [asyncio.create_task(guarded(task_id)) for task_id in plan['selected_ids']]
    try:
        await asyncio.gather(*jobs)
    finally:
        for job in jobs:
            if not job.done():
                job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        event(run, 'controller_finished', active=dict(active))
        summarize(run)
        lock.close()


def add_runtime_arguments(parser):
    parser.add_argument('--config', default=str(HERE / 'config.json'))
    parser.add_argument('--agent-source', required=True)
    parser.add_argument('--agent-python', required=True)
    parser.add_argument('--judge-python', required=True)
    parser.add_argument('--credentials-file', default=str(HERE.parent / '.private' / 'bu-filter-model.json'))
    parser.add_argument('--browser')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('verify', help='Offline dataset/config verification; no model requests')
    credentials = commands.add_parser('configure', help='Store credentials outside this package; never commit them')
    credentials.add_argument('--credentials-file', default=str(HERE.parent / '.private' / 'bu-filter-model.json'))
    credentials.add_argument('--base-url', default='https://llmapi.hk.lexmount.net/v1')
    check = commands.add_parser('preflight', help='Imports/Chrome/version check; no model requests')
    add_runtime_arguments(check)
    run = commands.add_parser('run', help='Start a new evaluation; model requests are billable')
    add_runtime_arguments(run)
    run.add_argument('--output', required=True)
    run.add_argument('--ids', nargs='+', help='Optional BU-filter original ordinals or full UUIDs')
    resume = commands.add_parser('resume', help='Resume pending work without rerunning finished or interrupted Actors')
    resume.add_argument('--output', required=True)
    summary = commands.add_parser('summarize', help='Read saved receipts without model requests')
    summary.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.command == 'verify':
        print(json.dumps({'dataset': validate_dataset(), 'config': config()}, ensure_ascii=False, indent=2))
    elif args.command == 'configure':
        path = Path(args.credentials_file).expanduser().resolve()
        if path.is_relative_to(HERE):
            raise ValueError('Store credentials outside the versioned bu-filter/ package')
        if path.exists():
            raise FileExistsError('Credential file already exists; edit it in place for key rotation')
        key = os.environ.get('OPENAI_API_KEY') or getpass.getpass('Model API key (hidden): ')
        if not key or any(char.isspace() for char in key):
            raise ValueError('API key must not be blank or contain whitespace')
        write(path, {'api_key': key, 'base_url': args.base_url, 'model': 'deepseek-v4.1-flash'})
        print(f'Credentials saved with mode 0600: {path}')
    elif args.command == 'preflight':
        print(json.dumps(preflight(args), ensure_ascii=False, indent=2))
    elif args.command == 'run':
        select_tasks(args.ids)  # Reject excluded IDs before any credential/model work.
        target = prepare(args)
        asyncio.run(campaign(target))
        print(json.dumps(summarize(target), ensure_ascii=False, indent=2))
    elif args.command == 'resume':
        asyncio.run(campaign(Path(args.output).resolve()))
        print(json.dumps(summarize(args.output), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(summarize(args.output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
