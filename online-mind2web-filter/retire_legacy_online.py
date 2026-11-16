#!/usr/bin/env python3
"""5090-only retirement of old Online entry points; never touches BU/OD jobs."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import signal
import time

ROOT = Path('/data/wf/sxh/workspace/lexmount/exclusive-agent-eval')
HELPERS = ROOT / 'tmp/bu103-helpers-20261114'
ARCHIVE = ROOT / '.archives/online-mind2web-before-filter-20261116'
ACTIVE = ROOT / 'online-mind2web-filter'
MARKER = '# ONLINE-MIND2WEB-300 RETIRED 2026-11-16'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + '.tmp')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    pending.replace(path)

def online_processes():
    result = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            raw = (proc / 'cmdline').read_bytes()
            args = [x.decode(errors='replace') for x in raw.split(b'\0') if x]
            cwd = os.readlink(proc / 'cwd')
            task_owned = cwd.startswith(str(HELPERS) + '/') and '/runs/online_mind2web/' in cwd
            argument_owned = any(x.startswith(str(HELPERS) + '/') and '/runs/online_mind2web/' in x for x in args)
            judge_owned = any(x.endswith('/driver/run.py') or x == 'driver/run.py' for x in args) and 'judge' in args and 'online_mind2web' in args
            if not (task_owned or argument_owned or judge_owned):
                continue
            # The complete cmdline is deliberately not persisted: legacy commands may contain secrets.
            ticks = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
            result.append({'pid': int(proc.name), 'start_ticks': ticks, 'cwd': cwd,
                           'cmd_sha256': hashlib.sha256(raw).hexdigest()})
        except (OSError, PermissionError):
            pass
    return result

def same_process(item):
    try:
        proc = Path('/proc') / str(item['pid'])
        return proc.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19] == item['start_ticks'] and hashlib.sha256(proc.joinpath('cmdline').read_bytes()).hexdigest() == item['cmd_sha256']
    except OSError:
        return False

def guard(path, kind, receipt):
    if not path.is_file() or MARKER in path.read_text():
        return
    relative = path.relative_to(ROOT)
    backup = ARCHIVE / 'original-entrypoints' / relative
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup)
    original = path.read_text()
    if kind == 'actor':
        condition = "len(_omw_sys.argv) > 1 and '/runs/online_mind2web/' in _omw_os.path.abspath(_omw_sys.argv[1])"
    else:
        condition = "len(_omw_sys.argv) > 3 and _omw_sys.argv[1:3] == ['judge', 'online_mind2web']"
    prefix = (MARKER + '\nimport sys as _omw_sys, os as _omw_os\nif ' + condition + ':\n'
              "    print('Old Online-Mind2Web 300-task entry retired; use online-mind2web-filter/evaluate.py', file=_omw_sys.stderr)\n"
              '    raise SystemExit(78)\n')
    # Both historical driver and Actor were inspected: neither has a future import.
    assert 'from __future__ import' not in original
    pending = path.with_suffix('.retire.tmp')
    pending.write_text(prefix + original)
    pending.chmod(path.stat().st_mode)
    pending.replace(path)
    receipt['guarded'].append({'path': str(relative), 'original_sha256': sha(backup), 'retired_sha256': sha(path), 'kind': kind})

def apply():
    assert ACTIVE.joinpath('data/tasks.jsonl').is_file()
    receipt_path = ARCHIVE / 'migration-receipt.json'
    if receipt_path.exists():
        print('Already retired:', receipt_path)
        return
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    receipt = {'created_at': time.time(), 'active': str(ACTIVE), 'guarded': [], 'archived': [], 'stopped': [],
               'preserved': ['BU-filter', 'Odysseys processes and data', 'mixed historical trees and frozen task-data required by their live Odysseys judges'],
               'boundary': 'Entry retirement and hidden backup; not an OS permission boundary against the same account.'}
    # Prevent future queued Online children without killing the mixed controller or any OD children.
    for plan in sorted(HELPERS.glob('*/plan.json')):
        try:
            data = json.loads(plan.read_text())
        except (ValueError, OSError):
            continue
        if any(j.get('suite') == 'online_mind2web' for j in data.get('jobs', [])):
            guard(plan.parent / 'driver/actor.py', 'actor', receipt)
            guard(plan.parent / 'driver/run.py', 'judge', receipt)
    owned = online_processes()
    save_json(ARCHIVE / 'stopped-processes.json', owned)
    for item in owned:
        if same_process(item):
            try: os.kill(item['pid'], signal.SIGTERM)
            except ProcessLookupError: pass
    time.sleep(2)
    for item in owned:
        if same_process(item):
            try: os.kill(item['pid'], signal.SIGKILL)
            except ProcessLookupError: pass
        receipt['stopped'].append({'pid': item['pid'], 'start_ticks': item['start_ticks']})
    for source in [ROOT / 'benchmark/OnlineMind2Web', HELPERS / 'online-mind2web']:
        if source.exists():
            relative = source.relative_to(ROOT)
            destination = ARCHIVE / 'retired' / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            assert not destination.exists()
            # A rename on the same filesystem preserves all files, including private files, in the hidden archive.
            source.rename(destination)
            receipt['archived'].append({'source': str(relative), 'archive': str(destination.relative_to(ROOT))})
    # Historical shared import name must reject Online calls while other suite imports still work.
    retired_adapter = HELPERS / 'online-mind2web'
    retired_adapter.mkdir(exist_ok=True)
    retired_adapter.joinpath('omw_adapter.py').write_text("raise RuntimeError('Online-Mind2Web 300-task entry is retired. Use online-mind2web-filter/evaluate.py')\n")
    retired_adapter.joinpath('README.md').write_text('旧Online-Mind2Web入口已归档。唯一日常入口：' + str(ACTIVE / 'evaluate.py') + '\n')
    agents = ROOT / 'AGENTS.md'
    old = agents.read_text()
    begin, end = '<!-- online-mind2web-filter:start -->', '<!-- online-mind2web-filter:end -->'
    if begin in old:
        before, rest = old.split(begin, 1)
        _, after = rest.split(end, 1)
        old = before + after
    section = (begin + '\n# 当前Online评测入口（2026-11-16起）\n\n'
               'Online-Mind2Web只评测online-mind2web-filter：247题、100模型回合、3600秒。唯一日常入口：' + str(ACTIVE / 'evaluate.py') + '。先读README并运行verify。\n'
               'Notion确认的53个排除ID见data/exclusions.json。不得启动旧300题、从归档恢复旧入口或拼接旧成绩。\n'
               '保留BU-filter和Odysseys进程与数据；上文/下文关于为BU归档而保留Online的旧指令，现仅对Online被本段替代。混合历史树为只读追溯/其他评测兼容资源，不是Online入口。\n'
               + end + '\n\n')
    pending = agents.with_suffix('.online-filter.tmp')
    pending.write_text(section + old)
    pending.replace(agents)
    receipt['remaining_online_processes'] = online_processes()
    save_json(receipt_path, receipt)
    # Publish a credential-free operational receipt beside the deployment.
    save_json(ACTIVE / 'migration-receipt.json', receipt)
    print(json.dumps({'guarded': len(receipt['guarded']), 'archived': len(receipt['archived']), 'stopped': len(receipt['stopped']), 'remaining_online_processes': len(receipt['remaining_online_processes']), 'receipt': str(receipt_path)}))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.apply:
        apply()
    else:
        print(json.dumps({'mode': 'read-only inventory', 'online_processes': len(online_processes()), 'archive': str(ARCHIVE)}))
