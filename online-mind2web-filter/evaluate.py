#!/usr/bin/env python3
"""247-task data/path wrapper around the frozen 5090 Online evaluator."""
from __future__ import annotations
import argparse
import ast
import asyncio
from collections import Counter
from datetime import datetime, timezone
UTC = timezone.utc
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import signal
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

PACKAGE = Path(__file__).resolve().parent
SUITE = 'online_mind2web'
RUNTIME_FUNCTIONS = {'read', 'write', 'sha', 'actor_command', 'invoke', 'grade', 'run'}

def read(path):
    return json.loads(Path(path).read_bytes())

def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + '.tmp')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    pending.replace(path)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def tasks():
    manifest = read(PACKAGE / 'data/manifest.json')
    lines = (PACKAGE / 'data/tasks.jsonl').read_bytes().splitlines(keepends=True)
    assert sha(PACKAGE / 'data/tasks.jsonl') == manifest['dataset_sha256']
    rows = [json.loads(line) for line in lines]
    excluded = {r['task_id'] for r in read(PACKAGE / 'data/exclusions.json')['rows']}
    assert len(rows) == len({r['task_id'] for r in rows}) == 247
    assert len(excluded) == 53 and not excluded.intersection(r['task_id'] for r in rows)
    assert len(manifest['tasks']) == 247
    for line, row, original in zip(lines, rows, manifest['tasks']):
        assert row['task_id'] == original['task_id']
        assert hashlib.sha256(line).hexdigest() == original['original_line_sha256']
    assert [r['original_ordinal'] for r in manifest['tasks']] == sorted(r['original_ordinal'] for r in manifest['tasks'])
    return [{'id': r['task_id'], 'instruction': r['task_name'], 'start_url': r['website'],
             'level': r['difficulty'], 'reference_length': r['metadata']['reference_length']}
            for r in rows]

def adapter(support=None):
    sys.path.insert(0, str(PACKAGE / 'legacy/code'))
    a = load_module('omw_adapter', PACKAGE / 'legacy/online-mind2web/omw_adapter.py')
    a.EVAL = PACKAGE
    a.HISTORY = PACKAGE / 'legacy/history'
    a.DATASET = PACKAGE / 'data/tasks.jsonl'
    a.DATASET_SHA256 = read(PACKAGE / 'data/manifest.json')['dataset_sha256']
    a.ROOT = Path(support) if support else PACKAGE
    return a

def verify():
    for name, digest in read(PACKAGE / 'frozen-files.json').items():
        assert sha(PACKAGE / name) == digest, 'Package changed: ' + name
    provenance = read(PACKAGE / 'provenance.json')
    for name, digest in (provenance['original_file_sha256'] | provenance['actor_max_files_sha256']
                         | provenance['actor_default_files_sha256']).items():
        assert sha(PACKAGE / name) == digest, 'Original implementation changed: ' + name
    c = read(PACKAGE / 'config.json')
    assert (c['count'], c['max_steps'], c['timeout_seconds']) == (247, 100, 3600)
    assert (c['actor_concurrency'], c['judge_concurrency']) == (32, 4)
    assert c['fixed_viewport'] is False
    assert c['feature_config'] == {}
    assert (c['agent_model'], c['agent_reasoning'], c['mode']) == ('deepseek-v4.1-flash', 'max', 'default')
    rows = tasks()
    a = adapter()
    a.verify()
    print(json.dumps({'dataset': c['dataset'], 'tasks': len(rows), 'excluded': 53,
                      'max_steps': 100, 'timeout_seconds': 3600,
                      'dataset_sha256': a.DATASET_SHA256, 'actor_effort': 'max', 'actor_mode': c['mode']}))

def runtime(run_dir):
    run_dir = Path(run_dir).resolve()
    support = run_dir / 'support'
    os.environ['LEXMOUNT_EVAL_ROOT'] = str(support)
    sys.path.insert(0, str(support / 'code'))
    adapter(support)
    source = PACKAGE / 'legacy/driver.py'
    tree = ast.parse(source.read_text())
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in RUNTIME_FUNCTIONS]
    assert {n.name for n in nodes} == RUNTIME_FUNCTIONS
    # Bind the archived scheduler to the filtered task count and the supported Actor profile.
    run = next(n for n in nodes if n.name == 'run')
    counts = [n for n in ast.walk(run) if isinstance(n, ast.Constant) and n.value == 600]
    assert len(counts) == 1
    counts[0].value = 247
    profile_checks = {
        "public_config.get('reasoning_effort', 'high') == 'high'": "public_config['reasoning_effort'] == 'max'",
        "public_config.get('mode', 'ultrafast') == 'ultrafast'": "public_config['mode'] == 'default'",
    }
    for original, required in profile_checks.items():
        guard, = (node for node in run.body if isinstance(node, ast.Assert) and ast.unparse(node.test) == original)
        guard.test = ast.copy_location(ast.parse(required, mode="eval").body, guard.test)
    scope = dict(globals(), RUN=run_dir, ROOT=support, PRODUCT=run_dir / 'product',
                 ENV=run_dir / 'product/.venv', SOURCE=run_dir / 'product/src',
                 CODE=support / 'code', DEPENDENCIES=support / 'code', LEGACY=None,
                 COMMIT=read(run_dir / 'plan.json')['product_commit'],
                 __file__=str(run_dir / 'driver/run.py'))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), scope)
    build = read(run_dir / 'build.json')
    if 'actor_runtime' in build:
        sys.path.insert(0, str(PACKAGE.parent))
        from shared_actor_runtime import bind_actor
        bind_actor(scope, build['actor_runtime'])
    return SimpleNamespace(**scope)

def matches_frozen_file(path, digest, *, historical_report):
    path = Path(path)
    if path.is_file() and sha(path) == digest:
        return True
    if historical_report:
        # The first 5090 release recorded absolute paths in the original flat package.
        for parent in path.parents:
            if parent.name == 'online-mind2web-filter' and parent.is_symlink():
                archive = parent.parent / '.archives' / 'online-mind2web-filter-flat'
                original = archive / path.relative_to(parent)
                return original.is_file() and sha(original) == digest
    return False

def preflight_run(run_dir, *, for_execution=False, historical_report=False):
    run_dir = Path(run_dir).resolve()
    plan = read(run_dir / 'plan.json')
    if for_execution and (plan.get('mode') != 'default'
                          or read(run_dir/'support/.private/model.json').get('mode') != 'default'):
        raise ValueError("Online requires a run prepared with Actor mode 'default'")
    assert plan['counts'] == {SUITE: 247} and len(plan['jobs']) == 247
    allowed = {t['id'] for t in tasks()}
    assert {j['task_id'] for j in plan['jobs']} == allowed
    for path, digest in plan['file_sha256'].items():
        assert matches_frozen_file(path, digest, historical_report=historical_report), path
    for job in plan['jobs']:
        assert job['suite'] == SUITE
        folder = Path(job['source_folder'])
        actor_path = folder / 'actor-config.json'
        c = read(actor_path)
        if for_execution and c.get('mode') != 'default':
            raise ValueError("Online requires every task to use Actor mode 'default'")
        assert (c['max_steps'], c['timeout_seconds'], c['fixed_viewport']) == (100, 3600, False)
        if historical_report:
            assert sha(actor_path) == job['actor_config_sha256'], actor_path
            assert sha(folder / 'task.json') == job['task_input_sha256'], folder
        else:
            assert c['feature_config'] == {}
    return plan

def actor_credentials(path):
    cfg = read(path)
    if cfg.get('mode', 'default') != 'default':
        raise ValueError("Online requires Actor mode 'default'")
    return dict(cfg, mode='default', reasoning_effort='max')

def prepare(run_dir, product_source, credentials, judge_python, actor_runtime=None):
    verify()
    run_dir, product_source = Path(run_dir).resolve(), Path(product_source).resolve()
    assert not run_dir.exists(), 'Use a new run directory; existing evidence is preserved'
    assert shutil.which('bwrap')
    published = product_source/'actor-runtime.json'
    if published.is_file():
        commit = read(published)['product_commit']
    else:
        commit = subprocess.check_output(['git', '-C', str(product_source), 'rev-parse', 'HEAD'], text=True).strip()
        assert not subprocess.check_output(['git', '-C', str(product_source), 'status', '--porcelain', '--', 'src', 'pyproject.toml', 'uv.lock'], text=True), 'Product source must be clean'
    sys.path.insert(0, str(PACKAGE.parent))
    from shared_actor_runtime import select_release
    frozen_actor = select_release(product_source, commit, actor_runtime)
    actor_root = Path(frozen_actor['manifest']).parent
    cfg = actor_credentials(credentials)
    assert cfg['model'] == 'deepseek-v4.1-flash'
    assert cfg.get('api_key') and cfg.get('base_url')
    assert Path(judge_python).is_file()
    run_dir.mkdir(parents=True)
    product = run_dir / 'product'
    product.mkdir()
    shutil.copytree(actor_root / 'src', product / 'src', ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.egg-info'))
    for name in ('pyproject.toml', 'uv.lock'):
        shutil.copyfile(actor_root / name, product / name)
    engine = subprocess.check_output([str(actor_root / '.venv/bin/python'), '-c', 'from importlib.metadata import version; print(version("browser-use"))'], text=True).strip()
    assert engine == '1.0.4', 'Expected the locked official Browser Use 1.0.4 product'
    frozen_product = sorted(q for q in (product / 'src').rglob('*') if q.is_file() and '__pycache__' not in q.parts and not q.name.endswith('.pyc'))
    frozen_product += [product / 'pyproject.toml', product / 'uv.lock']
    build = {'commit': commit, 'engine_version': engine,
             'source_sha256': {str(q.relative_to(product)): sha(q) for q in frozen_product}}
    build['actor_runtime'] = frozen_actor
    write(run_dir / 'build.json', build)
    support = run_dir / 'support'
    shutil.copytree(PACKAGE / 'legacy/code', support / 'code')
    (support / '.private').mkdir(mode=0o700)
    write(support / '.private/model.json', cfg)
    (support / '.private/model.json').chmod(0o600)
    target_env = Path(judge_python).absolute().parent.parent
    # Preserve the original judge interpreter lookup, without depending on the old campaign tree.
    env = support / 'envs/baseline'
    env.parent.mkdir(parents=True)
    env.symlink_to(target_env, target_is_directory=True)
    driver = run_dir / 'driver'
    driver.mkdir()
    shutil.copyfile(PACKAGE / 'legacy/actor.py', driver / 'actor.py')
    (driver / 'run.py').write_text('import sys\nsys.path.insert(0, ' + repr(str(PACKAGE)) + ')\nimport evaluate\nevaluate.main([*sys.argv[1:], "--run-dir", ' + repr(str(run_dir)) + '])\n')
    rows = tasks()
    write(run_dir / 'task-data.json', {SUITE: rows})
    ordinals = {x['task_id']: x['original_ordinal'] for x in read(PACKAGE / 'data/manifest.json')['tasks']}
    pending = []
    config = read(PACKAGE / 'config.json')
    for task in rows:
        tid = task['id']
        assert '/' not in tid and '..' not in tid
        folder = run_dir / 'runs' / SUITE / tid
        write(folder / 'task.json', {name: task.get(name) for name in ('id', 'instruction', 'start_url')})
        write(folder / 'actor-config.json', {'source_folder': str(folder), 'mode': 'default', 'max_steps': 100, 'timeout_seconds': 3600,
              'feature_config': config['feature_config'], 'fixed_viewport': False, 'product': build})
        pending.append({'arm': 'candidate', 'suite': SUITE, 'task_id': tid, 'ordinal': ordinals[tid],
                        'source_folder': str(folder), 'judge_folder': str(run_dir / 'judges' / SUITE / tid),
                        'task_input_sha256': sha(folder / 'task.json'), 'actor_config_sha256': sha(folder / 'actor-config.json')})
    random.Random(config['seed']).shuffle(pending)
    jobs = list(reversed(pending))  # Same shuffle/pop order as the original one-suite scheduler.
    frozen = [run_dir / 'build.json', run_dir / 'task-data.json', *driver.glob('*.py'), *sorted((support / 'code').glob('*.py'))]
    frozen += [PACKAGE / name for name in read(PACKAGE / 'frozen-files.json')]
    frozen += [PACKAGE / 'frozen-files.json', *frozen_product]
    write(run_dir / 'plan.json', {'product_commit': commit, 'created_at': time.time(), 'context_anchor': datetime.now(UTC).isoformat(),
          'actor_concurrency': 32, 'judge_concurrency': 4, 'counts': {SUITE: 247},
          'new_actor_runs': 247, 'reused_actor_runs': 0, 'old_actor_runs': 0,
          'agent_model': 'deepseek-v4.1-flash', 'agent_reasoning': 'max', 'mode': 'default',
          'judge_reasoning': 'low', 'judge_protocol': config['judge_protocol'], 'seed': config['seed'],
          'jobs': jobs, 'file_sha256': {str(q): sha(q) for q in frozen}})
    write(run_dir / 'probes/candidate/actor-config.json', {'product': build, 'mode': 'default'})
    preflight_run(run_dir)
    print(json.dumps({'prepared': str(run_dir), 'jobs': 247, 'commit': commit, 'engine': engine}))

def report(run_dir):
    run_dir = Path(run_dir).resolve()
    plan = preflight_run(run_dir, historical_report=True)
    totals = Counter()
    rows = []
    for job in sorted(plan['jobs'], key=lambda j: j['ordinal']):
        packet = Path(job['judge_folder']) / ('judge-' + SUITE + '.json')
        grade = read(packet) if packet.exists() else {}
        score = grade.get('score') if grade.get('status') == 'judged' else None
        state = 'pass' if score == 1 else 'fail' if score == 0 else 'unknown'
        totals[state] += 1
        rows.append({'original_ordinal': job['ordinal'], 'task_id': job['task_id'], 'status': grade.get('status', 'missing'), 'score': score})
    result = {'tasks': 247, 'passed': totals['pass'], 'failed': totals['fail'], 'unknown': totals['unknown'],
              'score_over_247': totals['pass'] / 247, 'rows': rows}
    write(run_dir / 'report.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['verify', 'prepare', 'probe', 'run', 'report', 'judge'])
    parser.add_argument('job', nargs='*')
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--product', type=Path)
    parser.add_argument('--actor-runtime', type=Path)
    parser.add_argument('--credentials', type=Path)
    parser.add_argument('--judge-python', type=Path, default=PACKAGE / '.venv-judge/bin/python')
    args = parser.parse_args(argv)
    if args.command == 'verify':
        verify()
        return
    assert args.run_dir, '--run-dir is required'
    if args.command == 'prepare':
        assert args.product and args.credentials, '--product and --credentials are required'
        prepare(args.run_dir, args.product, args.credentials, args.judge_python, args.actor_runtime)
        return
    verify()
    if args.command == 'report':
        report(args.run_dir)
        return
    preflight_run(args.run_dir, for_execution=args.command in ('probe', 'run'))
    rt = runtime(args.run_dir)
    if args.command == 'probe':
        subprocess.run(rt.actor_command(args.run_dir.resolve() / 'probes/candidate', probe=True), check=True, timeout=100)
    elif args.command == 'run':
        with (args.run_dir / 'controller.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            asyncio.run(rt.run())
    else:
        assert len(args.job) == 2 and args.job[0] == SUITE
        job = next(j for j in read(args.run_dir / 'plan.json')['jobs'] if (j['suite'], j['task_id']) == tuple(args.job))
        asyncio.run(rt.grade(job))

if __name__ == '__main__':
    main()
