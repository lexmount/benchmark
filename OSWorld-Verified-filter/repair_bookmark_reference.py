#!/usr/bin/env python3
"""Apply the one-author URL alias repair to retained pre-cleanup bookmark evidence.

The original full post-cleanup getter input was not retained. This separately
labelled correction uses its complete recorded Liked Authors folder, checked
against the same run's actual chrome.bookmarks.getTree and saved verification
file. It does not replay the Actor, VM, or original getter.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import shutil
import sys
import tarfile

from bookmark_reference_repair import TASK_ID, ALIAS, repair_rules, source_provenance

ROOT = Path(__file__).resolve().parent
KIND = 'bookmark-reference-yuke-alias-v1-retained-folder'
SOURCE_FILES = ('bookmark_reference_repair.py', 'repair_bookmark_reference.py')
VERIFICATION_MEMBER = 'actor-output/workspace/bookmarks_verification.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def _prefix_json(text):
    # raw_decode rejects truncation, while allowing the tool's subsequent log
    # lines. We never reconstruct missing nodes from a screenshot or answer.
    return json.JSONDecoder().raw_decode(text.lstrip())[0]


def bookmark_projection(disk_observation, api_observation, verification):
    """Validate the two complete observations and project the original folder."""
    folders = _prefix_json(disk_observation)
    bar = _prefix_json(api_observation)
    if (not isinstance(folders, list) or len(folders) != 1 or not isinstance(bar, dict)
            or bar.get('title') != 'Bookmarks bar' or bar.get('id') != '1'):
        raise ValueError('A complete disk folder and native Bookmarks bar are required')
    disk = folders[0]
    api_folders = [node for node in bar.get('children', []) if node.get('title') == 'Liked Authors']
    if (disk.get('type') != 'folder' or disk.get('name') != 'Liked Authors'
            or len(api_folders) != 1):
        raise ValueError('Liked Authors must remain a folder directly under Bookmarks bar')
    api = api_folders[0]
    disk_children, api_children = disk.get('children'), api.get('children')
    if (not isinstance(disk_children, list) or not isinstance(api_children, list)
            or len(disk_children) != 4 or len(api_children) != 4
            or disk.get('id') != api.get('id') or api.get('parentId') != '1'):
        raise ValueError('The complete four-author folder or its parent identity changed')
    disk_rows, api_rows = [], []
    for index, (left, right) in enumerate(zip(disk_children, api_children)):
        if (left.get('type') != 'url' or not isinstance(left.get('url'), str)
                or left.get('id') != right.get('id')
                or right.get('parentId') != api['id'] or right.get('index') != index):
            raise ValueError('Folder entries must be four matching native URL nodes')
        disk_rows.append({'title': left.get('name'), 'url': left['url']})
        api_rows.append({'title': right.get('title'), 'url': right.get('url')})
    expected_summary = {'folder': 'Liked Authors', 'folder_parent': 'Bookmarks bar',
        'folder_id': disk['id'], 'bookmarks': disk_rows,
        'folder_position_in_bar': bar['children'].index(api)}
    if disk_rows != api_rows or verification != expected_summary:
        raise ValueError('Disk, native API and archived verification do not agree')
    if (len({row['url'] for row in disk_rows}) != 4
            or disk_rows[2] != {'title': 'Yuke Zhu', 'url': ALIAS}):
        raise ValueError('This is not the confirmed four-author Yuke alias observation')
    return {'bookmark_bar': {'children': deepcopy(folders)}}


def _recorded_calls(messages):
    """Read original tool calls/returns only; do not use model reasoning as evidence."""
    calls, by_id = [], {}
    for message in messages:
        for part in message.get('parts', []):
            if part.get('part_kind') == 'tool-call':
                args = part.get('args')
                if isinstance(args, str):
                    args = json.loads(args)
                call = {'step': len(calls) + 1, 'tool': part.get('tool_name'),
                        'args': args, 'observations': []}
                calls.append(call)
                by_id[part.get('tool_call_id')] = call
            elif part.get('part_kind') in ('tool-return', 'retry-prompt'):
                call = by_id.get(part.get('tool_call_id'))
                if call is None:
                    continue
                content = part.get('content', [])
                if isinstance(content, (str, dict)):
                    content = [content]
                for item in content:
                    if isinstance(item, str):
                        call['observations'].append(item)
                    elif isinstance(item, dict) and 'data' not in item:
                        for key in ('text', 'content'):
                            if isinstance(item.get(key), str):
                                call['observations'].append(item[key])
    return calls


def inputs(run_dir, evidence_path):
    run_dir = Path(run_dir).resolve()
    spec = importlib.util.spec_from_file_location('bookmark_repair_control', ROOT / 'evaluate.py')
    control = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(control)
    metadata = control.verify_run(run_dir)
    item = next(t for t in read(Path(metadata['harness_root']) / 'data/manifest.json')['tasks']
                if t['task_id'] == TASK_ID)
    task_path = Path(metadata['harness_root']) / item['task_path']
    task = read(task_path)
    if (task['evaluator']['func'] != 'is_expected_bookmarks'
            or task['evaluator']['result'] != {'type': 'bookmarks'}
            or task['evaluator']['expected']['type'] != 'rule'
            or sha(task_path) != item['sha256']):
        raise ValueError('Original task/getter/metric identity changed')
    original_rule = task['evaluator']['expected']['rules']
    repaired = repair_rules(original_rule)
    receipt_path = run_dir / 'tasks' / TASK_ID / 'receipt.json'
    receipt = read(receipt_path)
    if (receipt.get('task_id') != TASK_ID or receipt.get('task_sha256') != item['sha256']
            or receipt.get('status') != 'scored' or type(receipt.get('score')) not in (int, float)
            or receipt['score'] != 0 or receipt.get('official_terminal_action') != 'DONE'
            or receipt.get('actor_status') != 'completed' or receipt.get('agent_success') is not True):
        raise ValueError('Expected the original completed/DONE scored-zero task')
    evidence = read(evidence_path)
    if (evidence.get('task_id') != TASK_ID or Path(evidence['run']).resolve() != run_dir
            or evidence['task_json_sha256'] != item['sha256']
            or evidence['receipt_sha256'] != sha(receipt_path)
            or evidence.get('post_cleanup_full_getter_input_retained') is not False):
        raise ValueError('Retained evidence is not bound to this task, receipt and boundary')
    folder = receipt_path.parent
    archive_path = folder / 'actor-output.tar.gz'
    bindings = {}
    for filename in ('actor-output.tar.gz', 'final.png', 'actor-result.json'):
        path = folder / filename
        if sha(path) != evidence['artifact_sha256'][filename]:
            raise ValueError('Original artifact changed: ' + filename)
        bindings[filename] = sha(path)
    messages_member = evidence['messages_member']
    if messages_member != 'actor-output/messages.json':
        raise ValueError('Expected the original product tool-message archive member')
    with tarfile.open(archive_path, 'r:gz') as archive:
        messages_file = archive.extractfile(messages_member)
        verification_file = archive.extractfile(VERIFICATION_MEMBER)
        if messages_file is None or verification_file is None:
            raise ValueError('Required retained evidence is absent from the original archive')
        messages_bytes, verification_bytes = messages_file.read(), verification_file.read()
    if hashlib.sha256(verification_bytes).hexdigest() != evidence['verification_member_sha256']:
        raise ValueError('Archived bookmark verification changed')
    original_calls = _recorded_calls(json.loads(messages_bytes))
    calls = evidence['observations']
    if set(calls) != {'disk', 'native_api'}:
        raise ValueError('Both original disk and native API observations are required')
    for name, call in calls.items():
        step = call.get('step')
        if type(step) is not int or not 1 <= step <= len(original_calls):
            raise ValueError('Original tool step is missing: ' + name)
        original_call = original_calls[step - 1]
        if (original_call['tool'] != 'python' or not isinstance(original_call['args'], dict)
                or original_call['args'].get('code') != call.get('code')
                or not isinstance(call.get('observation'), str)
                or call['observation'] not in original_call['observations']):
            raise ValueError('Evidence does not match its original tool call and return: ' + name)
    if ("/home/user/.config/google-chrome/Default/Bookmarks" not in calls['disk']['code']
            or "d['roots']['bookmark_bar']['children']" not in calls['disk']['code']
            or 'chrome.bookmarks.getTree()' not in calls['native_api']['code']):
        raise ValueError('The recorded observations do not come from the required original sources')
    projection = bookmark_projection(calls['disk']['observation'], calls['native_api']['observation'],
                                     json.loads(verification_bytes))
    bindings.update(messages_member=messages_member,
        messages_member_sha256=hashlib.sha256(messages_bytes).hexdigest(),
        verification_member=VERIFICATION_MEMBER,
        verification_member_sha256=hashlib.sha256(verification_bytes).hexdigest())
    return metadata, receipt_path, evidence, projection, original_rule, repaired, bindings


def repair(run_dir, evidence_path, output):
    run_dir, evidence_path, output = [Path(p).resolve() for p in (run_dir, evidence_path, output)]
    metadata, original, evidence, projection, old_rule, repaired, bindings = inputs(run_dir, evidence_path)
    sys.path.insert(0, metadata['osworld_root'])
    from desktop_env.evaluators.metrics.chrome import is_expected_bookmarks
    metric_path = Path(metadata['osworld_root']) / 'desktop_env/evaluators/metrics/chrome.py'
    if Path(inspect.getsourcefile(is_expected_bookmarks)).resolve() != metric_path.resolve():
        raise ValueError('Comparison must come from the original frozen checkout')
    old = is_expected_bookmarks(deepcopy(projection), deepcopy(old_rule))
    value = is_expected_bookmarks(deepcopy(projection), deepcopy(repaired))
    if old != 0 or value != 1:
        raise ValueError('The unchanged comparison did not isolate the one-alias false negative')
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(evidence_path, output / 'terminal-evidence.json')
    for name in SOURCE_FILES:
        shutil.copyfile(ROOT / name, output / name)
    write_new(output / 'retained-folder-projection.json', projection)
    write_new(output / 'reference-rule.json', repaired)
    record = {'schema_version': 1, 'kind': KIND, 'task_id': TASK_ID, 'run_dir': str(run_dir),
        'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'corrected',
        'original_score': 0.0, 'score': float(value), 'old_rule_on_retained_folder_score': float(old),
        'model_calls': 0, 'vm_starts': 0, 'actor_rerun': False, 'getter_replayed': False,
        'input_kind': 'retained_pre_cleanup_complete_folder_projection',
        'original_post_cleanup_full_getter_input_retained': False,
        'metric': 'is_expected_bookmarks', 'metric_source_sha256': sha(metric_path),
        'source_provenance': source_provenance(), 'artifact_bindings': bindings,
        'run_metadata_sha256': sha(run_dir / 'run.json'),
        'original_receipt': str(original), 'original_receipt_sha256': sha(original),
        'task_sha256': evidence['task_json_sha256'],
        'evidence': str(output / 'terminal-evidence.json'),
        'evidence_sha256': sha(output / 'terminal-evidence.json'),
        'reference_rule': str(output / 'reference-rule.json'),
        'reference_rule_sha256': sha(output / 'reference-rule.json'),
        'folder_projection': str(output / 'retained-folder-projection.json'),
        'folder_projection_sha256': sha(output / 'retained-folder-projection.json'),
        'repair_sources_sha256': {name: sha(output / name) for name in SOURCE_FILES},
        'evidence_errors': [],
        'boundary': 'Uses complete retained pre-cleanup disk-folder and native browser API observations; the original full post-cleanup getter input was not retained. Only the Yuke URL alias is added; original metric and original zero remain unchanged.'}
    write_new(output / 'correction.json', record)
    return record


def verify_correction(run_dir, path):
    run_dir, path = Path(run_dir).resolve(), Path(path).resolve()
    record = read(path)
    if (record.get('schema_version') != 1 or record.get('kind') != KIND
            or record.get('task_id') != TASK_ID or record.get('status') != 'corrected'
            or Path(record['run_dir']).resolve() != run_dir
            or record.get('actor_rerun') is not False or record.get('getter_replayed') is not False
            or record.get('model_calls') != 0 or record.get('vm_starts') != 0
            or type(record.get('original_score')) not in (float, int) or record['original_score'] != 0
            or type(record.get('score')) not in (float, int) or record['score'] != 1
            or record.get('old_rule_on_retained_folder_score') != 0
            or record.get('input_kind') != 'retained_pre_cleanup_complete_folder_projection'
            or record.get('original_post_cleanup_full_getter_input_retained') is not False
            or record.get('evidence_errors') or sha(run_dir / 'run.json') != record['run_metadata_sha256']):
        raise ValueError('Correction identity, score or retained-evidence boundary changed')
    metadata, original, _, projection, _, repaired, bindings = inputs(run_dir, record['evidence'])
    if (str(original) != record['original_receipt'] or sha(original) != record['original_receipt_sha256']
            or sha(record['evidence']) != record['evidence_sha256']
            or sha(record['reference_rule']) != record['reference_rule_sha256']
            or read(record['reference_rule']) != repaired
            or sha(record['folder_projection']) != record['folder_projection_sha256']
            or read(record['folder_projection']) != projection or record['artifact_bindings'] != bindings):
        raise ValueError('Correction artifacts, original observations or rules changed')
    if set(record['repair_sources_sha256']) != set(SOURCE_FILES):
        raise ValueError('Correction source inventory changed')
    for name, checksum in record['repair_sources_sha256'].items():
        if sha(path.parent / name) != checksum:
            raise ValueError('Archived correction source changed')
    if (record['source_provenance']['repair_source_sha256'] != record['repair_sources_sha256']['bookmark_reference_repair.py']
            or sha(Path(metadata['osworld_root']) / 'desktop_env/evaluators/metrics/chrome.py') != record['metric_source_sha256']):
        raise ValueError('Original comparison or repair source changed')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(repair(args.run_dir, args.evidence, args.output), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
