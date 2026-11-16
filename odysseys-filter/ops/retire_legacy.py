#!/usr/bin/env python3
"""Retire only legacy Odysseys V1 entries; use atomic, reversible archival moves."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import time

ROOT = Path('/data/wf/sxh/workspace/lexmount/exclusive-agent-eval')
ACTIVE = ROOT / 'odysseys-filter'
ARCHIVE = ROOT / '.archives/odysseys-before-filter-20261116'
MARKER = '# ODYSSEYS-V1-200 RETIRED 2026-11-16'
SKIP = {'node_modules', '.venv', 'venv', 'envs', '.venvs', '.git', 'product', 'src',
        'screenshots', 'screens', 'agent', 'model_calls', 'downloads', '__pycache__', '.private'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + '.tmp')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    pending.replace(path)


def processes():
    result = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            raw = (proc / 'cmdline').read_bytes()
            args = [a.decode(errors='replace') for a in raw.split(b'\0') if a]
            cwd = os.readlink(proc / 'cwd')
            if not (cwd.startswith(str(ROOT)) or any(str(ROOT) in a for a in args)):
                continue
            if str(ACTIVE) in cwd or '/results/odysseys-filter' in cwd or any('/results/odysseys-filter' in a or str(ACTIVE) in a for a in args):
                continue
            owned = bool(re.search(r'/runs/(?:[^/]+/)?odysseys/', cwd))
            owned = owned or any(re.search(r'/runs/(?:[^/]+/)?odysseys/', a) for a in args)
            owned = owned or ('judge' in args and 'odysseys' in args)
            ticks = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
            result.append({'pid': int(proc.name), 'start_ticks': ticks, 'cwd': cwd,
                           'cmd_sha256': hashlib.sha256(raw).hexdigest(), 'old_odysseys_owned': owned})
        except (OSError, PermissionError):
            pass
    return result


def same_process(item):
    try:
        proc = Path('/proc') / str(item['pid'])
        return (proc.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19] == item['start_ticks']
                and hashlib.sha256(proc.joinpath('cmdline').read_bytes()).hexdigest() == item['cmd_sha256'])
    except OSError:
        return False


def inventory():
    candidates = set()
    entries = set()
    plans = []
    for top in (ROOT / 'tmp', ROOT / 'docs/exp_records', ROOT / 'runs', ROOT / 'benchmark/odysseys_eval'):
        for current, dirs, files in os.walk(top):
            p = Path(current)
            depth = len(p.relative_to(top).parts)
            dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith('.') and depth < 12]
            if p.name == 'odysseys':
                candidates.add(p)
                dirs[:] = []
                continue
            if 'plan.json' in files:
                try:
                    doc = json.loads((p / 'plan.json').read_bytes())
                    suites = {j.get('suite') for j in doc.get('jobs', [])}
                    if 'odysseys' in suites:
                        plans.append(p)
                        if suites == {'odysseys'}:
                            candidates.add(p)
                            dirs[:] = []
                except (OSError, ValueError):
                    pass
            if p.name == 'driver':
                for name in ('actor.py', 'run.py', 'campaign.py'):
                    if name in files:
                        entries.add(p / name)
    selected = []
    for p in sorted(candidates, key=lambda q: (len(q.parts), str(q))):
        if not any(p.is_relative_to(parent) for parent in selected):
            selected.append(p)
    entries = {p for p in entries if any(p.is_relative_to(parent) for parent in plans)
               and not any(p.is_relative_to(parent) for parent in selected)}
    return selected, sorted(entries), plans


def backup(path):
    target = ARCHIVE / 'original-entrypoints' / path.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copy2(path, target)
    return target


def guard(path):
    source = path.read_text()
    if MARKER in source:
        return None
    condition = ("len(_od_sys.argv) > 1 and '/odysseys/' in _od_os.path.abspath(_od_sys.argv[1])"
                 if path.name == 'actor.py' else
                 "'odysseys' in _od_sys.argv[1:] or any('/odysseys/' in _od_arg for _od_arg in _od_sys.argv[1:])")
    # Add after any future imports, preserving their required position.
    tree = ast.parse(source)
    after = 0
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == '__future__':
            after = node.end_lineno
    lines = source.splitlines(keepends=True)
    prefix = (MARKER + '\nimport sys as _od_sys, os as _od_os\nif ' + condition + ':\n'
              "    raise SystemExit('Old Odysseys V1 entry retired; use odysseys-filter/evaluate.py')\n")
    original = backup(path)
    path.write_text(''.join(lines[:after]) + prefix + ''.join(lines[after:]))
    return {'path': str(path.relative_to(ROOT)), 'original_sha256': sha(original), 'retired_sha256': sha(path)}


def guard_functions(path, names):
    if not path.is_file():
        return None
    source = path.read_text()
    if MARKER in source:
        return None
    tree = ast.parse(source)
    insertions = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            if 'suite' not in [a.arg for a in node.args.args]:
                continue
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                line = first.end_lineno
            else:
                line = first.lineno - 1
            insertions.append((line, "    if suite == 'odysseys':\n        raise RuntimeError('Old Odysseys V1 retired; use odysseys-filter/evaluate.py')\n"))
    if not insertions:
        return None
    original = backup(path)
    lines = source.splitlines(keepends=True)
    for line, text in sorted(insertions, reverse=True):
        lines.insert(line, text)
    path.write_text(''.join(lines) + '\n' + MARKER + '\n')
    return {'path': str(path.relative_to(ROOT)), 'original_sha256': sha(original), 'retired_sha256': sha(path)}


def apply():
    import sys
    sys.path.insert(0, str(ACTIVE))
    import evaluate
    evaluate.verify(quiet=True)
    receipt_path = ARCHIVE / 'migration-receipt.json'
    if receipt_path.exists() and json.loads(receipt_path.read_bytes()).get('complete'):
        print('Already retired:', receipt_path)
        return
    paths, entries, plans = inventory()
    before = processes()
    owned = [p for p in before if p['old_odysseys_owned']]
    receipt = {'created_at': time.time(), 'active_entry': str(ACTIVE / 'evaluate.py'),
               'moved': [], 'guarded': [], 'stopped': [], 'preserved_processes': [p for p in before if not p['old_odysseys_owned']],
               'preserved': ['BU-filter', 'online-mind2web-filter', 'Other non-Odysseys processes and mixed historical metadata'],
               'archive_method': 'Same-filesystem rename; preserves directory inode and all contents; no history deletion', 'complete': False}
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    write(receipt_path, receipt)
    for path in entries:
        item = guard(path)
        if item:
            receipt['guarded'].append(item)
    for path, names in [(ROOT / 'benchmark/odysseys_eval/run.py', {'tasks'}),
                        (ROOT / 'tmp/bu103-helpers-20261114/code/continue_evaluate.py', {'tasks', 'judge'}),
                        (ROOT / 'tmp/bu103-helpers-20261114/code/full_benchmarks.py', {'tasks', 'judge', 'judge_model'})]:
        item = guard_functions(path, names)
        if item:
            receipt['guarded'].append(item)
    write(receipt_path, receipt)
    for item in owned:
        if same_process(item):
            try:
                os.kill(item['pid'], signal.SIGTERM)
            except ProcessLookupError:
                pass
    if owned:
        time.sleep(2)
    for item in owned:
        if same_process(item):
            try:
                os.kill(item['pid'], signal.SIGKILL)
            except ProcessLookupError:
                pass
        receipt['stopped'].append(item)
    for source in paths:
        if not source.exists():
            continue
        for item in processes():
            if not item['old_odysseys_owned'] and Path(item['cwd']).is_relative_to(source):
                raise RuntimeError('Refusing to archive a directory used by another process: ' + str(source))
        target = ARCHIVE / 'retired' / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise RuntimeError('Archive destination already exists: ' + str(target))
        original = source.stat()
        source.rename(target)
        archived = target.stat()
        if (original.st_dev, original.st_ino) != (archived.st_dev, archived.st_ino):
            raise RuntimeError('Archive inode verification failed')
        receipt['moved'].append({'source': str(source.relative_to(ROOT)), 'archive': str(target.relative_to(ROOT)),
                                 'device': original.st_dev, 'inode': original.st_ino, 'same_inode_verified': True})
        write(receipt_path, receipt)
    for name in ('README.md', 'AGENTS.md'):
        path = ROOT / name
        original = path.read_text() if path.exists() else ''
        if path.exists():
            backup(path)
        begin, end = '<!-- odysseys-filter:start -->', '<!-- odysseys-filter:end -->'
        if begin in original:
            before_block, rest = original.split(begin, 1)
            _, after_block = rest.split(end, 1)
            original = before_block + after_block
        block = (begin + '\n# 当前Odysseys V1评测入口（2026-11-16起）\n\n'
                 '只评测odysseys-filter：168题、300模型回合、3600秒。唯一日常入口：' + str(ACTIVE / 'evaluate.py') + '。先读README并运行verify。\n'
                 'Notion确认的32个排除ID见data/exclusions.json。不得启动旧200题、从隐藏维护归档恢复旧入口或拼接旧成绩。\n'
                 '本段仅替代旧指令中保留Odysseys V1入口的部分。保留BU-filter、online-mind2web-filter及其他评测。混合历史元数据仅供追溯，不是旧评测入口。\n' + end + '\n\n')
        path.write_text(block + original)
    old_readme = ROOT / 'benchmark/odysseys_eval/README.md'
    if old_readme.exists():
        backup(old_readme)
        old_readme.write_text('旧Odysseys V1 200题入口已退役，原任务源和旧运行移入隐藏维护归档。\n当前唯一日常入口：' + str(ACTIVE / 'evaluate.py') + '\n教程：' + str(ACTIVE / 'README.md') + '\nOdysseys V2历史资料保留，本次未修改其任务数据。\n')
    receipt['remaining_old_odysseys_processes'] = [p for p in processes() if p['old_odysseys_owned']]
    receipt['completed_at'] = time.time()
    receipt['complete'] = not receipt['remaining_old_odysseys_processes']
    write(receipt_path, receipt)
    write(ACTIVE / 'migration-receipt.json', receipt)
    print(json.dumps({'complete': receipt['complete'], 'moved': len(receipt['moved']),
                      'guarded': len(receipt['guarded']), 'stopped': len(receipt['stopped']), 'receipt': str(receipt_path)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.apply:
        apply()
    else:
        paths, entries, plans = inventory()
        print(json.dumps({'archive': str(ARCHIVE), 'move_count': len(paths), 'moves': [str(p.relative_to(ROOT)) for p in paths],
                          'guard_count': len(entries), 'old_odysseys_processes': [p for p in processes() if p['old_odysseys_owned']]}, ensure_ascii=False))
