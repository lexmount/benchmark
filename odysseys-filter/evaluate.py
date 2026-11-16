#!/usr/bin/env python3
"""Prepare and run only odysseys-filter: 168 tasks, 300 model turns, 3600 seconds."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time

from dataset import load_rows, tasks, sha
from runtime import load_runtime, source_audit

PACKAGE = Path(__file__).resolve().parent
SUITE = 'odysseys'


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + '.tmp')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    pending.replace(path)


def verify(quiet=False):
    for relative, expected in read(PACKAGE / 'frozen-files.json').items():
        if sha(PACKAGE / relative) != expected:
            raise ValueError('Package content changed: ' + relative)
    provenance = read(PACKAGE / 'provenance.json')
    for relative, expected in (provenance['original_files_sha256'] | provenance['actor_max_files_sha256']).items():
        if sha(PACKAGE / relative) != expected:
            raise ValueError('Original implementation changed: ' + relative)
    config = read(PACKAGE / 'config.json')
    if (config['count'], config['max_steps'], config['timeout_seconds']) != (168, 300, 3600):
        raise ValueError('The task count and budgets are fixed at 168/300/3600')
    rows = load_rows()
    audit = source_audit()
    if [x for x, v in audit['functions'].items() if not v['unchanged']] != ['run']:
        raise ValueError('Unexpected execution-function changes')
    info = {'benchmark': 'odysseys-filter', 'tasks': len(rows), 'excluded': 32,
            'max_steps': 300, 'timeout_seconds': 3600,
            'actor_effort': 'max', 'runtime_source_audit': audit}
    if not quiet:
        print(json.dumps(info, ensure_ascii=False))
    return info


def preflight_run(run_dir):
    run_dir = Path(run_dir).resolve()
    plan = read(run_dir / 'plan.json')
    expected = {t['id']: t for t in tasks()}
    if plan['counts'] != {SUITE: 168} or len(plan['jobs']) != 168:
        raise ValueError('Only a complete 168-task plan is supported')
    if {j['task_id'] for j in plan['jobs']} != set(expected):
        raise ValueError('Plan contains excluded, missing or unexpected task IDs')
    if read(run_dir / 'task-data.json') != {SUITE: list(expected.values())}:
        raise ValueError('Prepared task or judge content differs from original retained tasks')
    for path, digest in plan['file_sha256'].items():
        if sha(path) != digest:
            raise ValueError('Frozen run file changed: ' + path)
    for job in plan['jobs']:
        if job['suite'] != SUITE:
            raise ValueError('Other benchmark suites are not accepted')
        folder = Path(job['source_folder'])
        if folder.resolve() != run_dir / 'runs' / SUITE / job['task_id']:
            raise ValueError('Task path does not belong to this run')
        if Path(job['judge_folder']).resolve() != run_dir / 'judges' / SUITE / job['task_id']:
            raise ValueError('Judge path does not belong to this run')
        task = expected[job['task_id']]
        public = {name: task.get(name) for name in ('id', 'instruction', 'start_url')}
        if read(folder / 'task.json') != public or sha(folder / 'task.json') != job['task_input_sha256']:
            raise ValueError('Actor input changed: ' + job['task_id'])
        config = read(folder / 'actor-config.json')
        if sha(folder / 'actor-config.json') != job['actor_config_sha256']:
            raise ValueError('Actor configuration changed: ' + job['task_id'])
        if (config['max_steps'], config['timeout_seconds'], config['fixed_viewport']) != (300, 3600, False):
            raise ValueError('Actor budget or viewport differs from the approved configuration')
        if config['feature_config'] != {}:
            raise ValueError('Original Odysseys feature configuration changed')
    return plan


def prepare(run_dir, product_source, credentials, judge_python):
    verify(quiet=True)
    run_dir, product_source = Path(run_dir).resolve(), Path(product_source).resolve()
    judge_python = Path(os.path.abspath(os.path.expanduser(judge_python)))
    if run_dir.exists():
        raise ValueError('Use a fresh output directory; existing evidence must be preserved')
    if not shutil.which('bwrap') or not Path('/opt/google/chrome/chrome').is_file():
        raise ValueError('The existing 5090 bwrap and local Chrome installation are required')
    commit = subprocess.check_output(['git', '-C', str(product_source), 'rev-parse', 'HEAD'], text=True).strip()
    if subprocess.check_output(['git', '-C', str(product_source), 'status', '--porcelain', '--', 'src', 'pyproject.toml', 'uv.lock'], text=True):
        raise ValueError('Product source and lockfile must be clean')
    cfg = read(credentials)
    if cfg.get('model') != 'deepseek-v4.1-flash' or cfg.get('mode', 'ultrafast') != 'ultrafast':
        raise ValueError('Use the DeepSeek / ultrafast model configuration')
    if not cfg.get('api_key') or not cfg.get('base_url') or not judge_python.is_file():
        raise ValueError('External credentials and an installed judge environment are required')
    run_dir.mkdir(parents=True)
    product = run_dir / 'product'
    product.mkdir()
    shutil.copytree(product_source / 'src', product / 'src', ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.egg-info'))
    for name in ('pyproject.toml', 'uv.lock'):
        shutil.copyfile(product_source / name, product / name)
    subprocess.run(['uv', 'sync', '--frozen', '--no-dev', '--python', '3.12'], cwd=product, check=True)
    engine = subprocess.check_output([str(product / '.venv/bin/python'), '-c', 'from importlib.metadata import version; print(version("browser-use"))'], text=True).strip()
    assert engine == '1.0.4', 'Expected the locked official Browser Use 1.0.4 product'
    frozen_product = sorted(q for q in (product / 'src').rglob('*') if q.is_file() and '__pycache__' not in q.parts and not q.name.endswith('.pyc'))
    frozen_product += [product / 'pyproject.toml', product / 'uv.lock']
    build = {'commit': commit, 'engine_version': engine,
             'source_sha256': {str(q.relative_to(product)): sha(q) for q in frozen_product}}
    write(run_dir / 'build.json', build)
    support = run_dir / 'support'
    shutil.copytree(PACKAGE / 'legacy/code', support / 'code')
    (support / '.private').mkdir(mode=0o700)
    write(support / '.private/model.json', dict(cfg, reasoning_effort='max'))
    (support / '.private/model.json').chmod(0o600)
    env = support / 'envs/baseline'
    env.parent.mkdir(parents=True)
    env.symlink_to(judge_python.parent.parent, target_is_directory=True)
    write(run_dir / 'settings.json', {'agent_python': str(product / '.venv/bin/python'), 'judge_python': str(judge_python)})
    driver = run_dir / 'driver'
    driver.mkdir()
    shutil.copyfile(PACKAGE / 'legacy/actor.py', driver / 'actor.py')
    (driver / 'run.py').write_text('import sys\nsys.path.insert(0, ' + repr(str(PACKAGE)) + ')\nimport evaluate\nevaluate.main([*sys.argv[1:], "--run-dir", ' + repr(str(run_dir)) + '])\n')
    rows = tasks()
    write(run_dir / 'task-data.json', {SUITE: rows})
    ordinals = {x['task_id']: x['original_ordinal'] for x in read(PACKAGE / 'data/manifest.json')['tasks']}
    config = read(PACKAGE / 'config.json')
    pending = []
    for task in rows:
        tid = task['id']
        if '/' in tid or '..' in tid:
            raise ValueError('Invalid task ID')
        folder = run_dir / 'runs' / SUITE / tid
        write(folder / 'task.json', {name: task.get(name) for name in ('id', 'instruction', 'start_url')})
        write(folder / 'actor-config.json', {'source_folder': str(folder), 'max_steps': 300, 'timeout_seconds': 3600,
              'feature_config': config['feature_config'], 'fixed_viewport': False, 'product': build})
        pending.append({'arm': 'candidate', 'suite': SUITE, 'task_id': tid, 'ordinal': ordinals[tid],
                        'source_folder': str(folder), 'judge_folder': str(run_dir / 'judges' / SUITE / tid),
                        'task_input_sha256': sha(folder / 'task.json'), 'actor_config_sha256': sha(folder / 'actor-config.json')})
    random.Random(config['seed']).shuffle(pending)
    jobs = list(reversed(pending))  # Preserve the original single-suite shuffle/pop order.
    # Install only path/source-check bindings; this does not execute Actor or Judge.
    from legacy.environment_bindings import install
    install(run_dir, support, support / 'code', judge_python)
    frozen = [run_dir / 'build.json', run_dir / 'task-data.json', run_dir / 'settings.json',
              *driver.glob('*.py'), *sorted((support / 'code').glob('*.py')), support / 'sources.json']
    frozen += [PACKAGE / name for name in read(PACKAGE / 'frozen-files.json')]
    frozen += [PACKAGE / 'frozen-files.json', *frozen_product]
    write(run_dir / 'plan.json', {'product_commit': commit, 'created_at': time.time(),
          'context_anchor': datetime.now(timezone.utc).isoformat(),
          'actor_concurrency': 32, 'judge_concurrency': 4, 'counts': {SUITE: 168},
          'new_actor_runs': 168, 'reused_actor_runs': 0, 'old_actor_runs': 0,
          'agent_model': 'deepseek-v4.1-flash', 'agent_reasoning': 'max', 'mode': 'ultrafast',
          'judge_reasoning': 'low', 'judge_protocol': config['judge_protocol'], 'seed': config['seed'],
          'jobs': jobs, 'file_sha256': {str(q): sha(q) for q in frozen}})
    write(run_dir / 'probes/candidate/actor-config.json', {'product': build})
    preflight_run(run_dir)
    print(json.dumps({'prepared': str(run_dir), 'jobs': 168, 'commit': commit, 'engine': engine,
                      'max_steps': 300, 'timeout_seconds': 3600, 'model_requests': 0}))


def summarize(run_dir):
    plan = preflight_run(run_dir)
    totals, rows = Counter(), []
    credit = rubric_count = 0
    scores = []
    expected = {t['id']: {r['id'] for r in t['rubrics']} for t in tasks()}
    for job in sorted(plan['jobs'], key=lambda j: j['ordinal']):
        packet = Path(job['judge_folder']) / 'judge-odysseys.json'
        grade = read(packet) if packet.exists() else {}
        rubric_scores = grade.get('rubric_scores', {})
        valid = (grade.get('status') == 'judged' and isinstance(rubric_scores, dict)
                 and set(rubric_scores) == expected[job['task_id']]
                 and all(type(v) in (int, float) and v in (0, 1) for v in rubric_scores.values()))
        score = sum(rubric_scores.values()) / len(rubric_scores) if valid else None
        state = 'unknown' if score is None else 'pass' if score >= 0.5 else 'fail'
        totals[state] += 1
        if valid:
            credit += sum(rubric_scores.values())
            rubric_count += len(rubric_scores)
            scores.append(score)
            totals['perfect'] += all(v == 1 for v in rubric_scores.values())
        rows.append({'original_ordinal': job['ordinal'], 'task_id': job['task_id'],
                     'judge_status': grade.get('status', 'missing'), 'state': state,
                     'score': score, 'perfect': bool(valid and all(v == 1 for v in rubric_scores.values()))})
    result = {'benchmark': 'odysseys-filter', 'tasks': 168, 'excluded': 32,
              'scored': len(scores), 'passed_at_0_5': totals['pass'], 'failed_below_0_5': totals['fail'],
              'unknown': totals['unknown'], 'complete': totals['unknown'] == 0,
              'task_success_rate_over_168': totals['pass'] / 168,
              'rubric_micro_average_on_scored': credit / rubric_count if rubric_count else None,
              'task_macro_average_on_scored': sum(scores) / len(scores) if scores else None,
              'perfect_tasks': totals['perfect'], 'perfect_rate_over_168': totals['perfect'] / 168,
              'note': 'Original per-rubric judgements are unchanged. Rates are incomplete while unknown > 0; no historical results are merged.',
              'rows': rows}
    write(Path(run_dir) / 'report.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, ensure_ascii=False))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['verify', 'prepare', 'probe', 'run', 'resume', 'report', 'judge'])
    parser.add_argument('job', nargs='*')
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--product', type=Path)
    parser.add_argument('--credentials', type=Path)
    parser.add_argument('--judge-python', type=Path, default=PACKAGE.parent / '.venvs/odysseys-filter-judge/bin/python')
    args = parser.parse_args(argv)
    if args.command == 'verify':
        verify()
        return
    if not args.run_dir:
        parser.error('--run-dir is required')
    if args.command == 'prepare':
        if not args.product or not args.credentials:
            parser.error('--product and --credentials are required')
        prepare(args.run_dir, args.product, args.credentials, args.judge_python)
        return
    verify(quiet=True)
    preflight_run(args.run_dir)
    if args.command == 'report':
        summarize(args.run_dir)
        return
    rt = load_runtime(args.run_dir)
    if args.command == 'probe':
        subprocess.run(rt['actor_command'](args.run_dir.resolve() / 'probes/candidate', probe=True), check=True, timeout=100)
    elif args.command in ('run', 'resume'):
        with (args.run_dir / 'controller.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            asyncio.run(rt['run']())
    else:
        if len(args.job) != 2 or args.job[0] != SUITE:
            parser.error('judge accepts only odysseys <retained-task-id>')
        job = next(j for j in read(args.run_dir / 'plan.json')['jobs'] if (j['suite'], j['task_id']) == tuple(args.job))
        asyncio.run(rt['grade'](job))


if __name__ == '__main__':
    main()
