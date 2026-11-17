#!/usr/bin/env python3
"""Supplement the search rule using preserved terminal evidence, without an Actor/VM.

This does not replay the original getter's page reload. Its post-navigation URL
was not retained. The independent score uses the original logged active URL,
the repaired expected rule and the unchanged official URL-comparison metric.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
import inspect
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tarfile
from urllib.parse import urlsplit

from search_reference_repair import TASK_ID, repair_rules, source_provenance

ROOT = Path(__file__).resolve().parent
KIND = 'cell-search-reference-v1-terminal-evidence'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def inputs(run_dir, evidence_path):
    run_dir = Path(run_dir).resolve()
    spec = importlib.util.spec_from_file_location('search_repair_control', ROOT / 'evaluate.py')
    control = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(control)
    metadata = control.verify_run(run_dir)
    item = next(t for t in read(Path(metadata['harness_root']) / 'data/manifest.json')['tasks']
                if t['task_id'] == TASK_ID)
    task_path = Path(metadata['harness_root']) / item['task_path']
    task = read(task_path)
    if (task['evaluator']['func'] != 'is_expected_search_query'
            or task['evaluator']['expected']['type'] != 'rule'
            or sha(task_path) != item['sha256']):
        raise ValueError('Original task/metric identity changed')
    repaired = repair_rules(task['evaluator']['expected']['rules'])
    receipt_path = run_dir / 'tasks' / TASK_ID / 'receipt.json'
    receipt = read(receipt_path)
    if (receipt.get('task_id') != TASK_ID or receipt.get('task_sha256') != item['sha256']
            or receipt.get('status') != 'scored' or type(receipt.get('score')) not in (int, float)
            or receipt['score'] != 0 or receipt.get('official_terminal_action') != 'DONE'):
        raise ValueError('Expected the original completed/DONE scored-zero task')
    evidence = read(evidence_path)
    if (evidence['task_id'] != TASK_ID or Path(evidence['run']).resolve() != run_dir
            or evidence['task_json_sha256'] != item['sha256']
            or Path(evidence['receipt_path']).resolve() != receipt_path.resolve()
            or evidence['receipt_sha256'] != sha(receipt_path)
            or evidence['original_expected_rule'] != task['evaluator']['expected']['rules']):
        raise ValueError('Terminal evidence is not bound to this original task/receipt')
    folder = receipt_path.parent
    expected_files = {'actor_archive_path': ('actor-output.tar.gz', 'actor_archive_sha256'),
                      'final_screenshot_path': ('final.png', 'final_screenshot_sha256')}
    for key, (filename, hash_key) in expected_files.items():
        if (Path(evidence[key]).resolve() != (folder / filename).resolve()
                or sha(evidence[key]) != evidence[hash_key]):
            raise ValueError('Original terminal artifact identity changed: ' + key)
    with tarfile.open(evidence['actor_archive_path'], 'r:gz') as stream:
        member = stream.extractfile(evidence['messages_member'])
        if member is None or hashlib.sha256(member.read()).hexdigest() != evidence['messages_member_sha256']:
            raise ValueError('Original tool evidence member changed')
    log = evidence['grader_log']
    expected_log = run_dir.parent.parent / 'osworld76-runtime/formal-v3-concurrency12.log'
    if Path(log['log_path']).resolve() != expected_log.resolve():
        raise ValueError('The terminal observation is not from this run\'s recorded grading log')
    # Log is append-only during this run; bind its exact historical prefix.
    with Path(log['log_path']).open('rb') as stream:
        prefix = stream.read(log['log_byte_size_at_snapshot'])
    if hashlib.sha256(prefix).hexdigest() != log['log_sha256_at_snapshot']:
        raise ValueError('Original grader log prefix changed')
    line = prefix.splitlines(keepends=True)[log['line_number'] - 1]
    if (line != base64.b64decode(log['line_bytes_with_ending_base64'], validate=True)
            or hashlib.sha256(line).hexdigest() != log['line_sha256_with_ending']):
        raise ValueError('Original active-URL observation changed')
    text = line.decode().rstrip('\r\n')
    marker = 'Active tab url now: '
    if not text.startswith(marker):
        raise ValueError('Evidence is not the official active-URL observation')
    url = text[len(marker):]
    original_rule = task['evaluator']['expected']['rules']
    if (urlsplit(url).hostname not in {'bing.com', 'www.bing.com', 'cn.bing.com'}
            or re.search(original_rule['expect']['pattern'], url)
            or not re.search(repaired['expect']['pattern'], url)):
        raise ValueError('This observation is not the confirmed Bing same-query false negative')
    return metadata, receipt_path, evidence, url, original_rule, repaired


def repair(run_dir, evidence_path, output):
    run_dir, evidence_path, output = map(lambda p: Path(p).resolve(), (run_dir, evidence_path, output))
    metadata, original, evidence, url, original_rule, repaired = inputs(run_dir, evidence_path)
    sys.path.insert(0, metadata['osworld_root'])
    from desktop_env.evaluators.metrics.chrome import is_expected_search_query
    metric_path = Path(metadata['osworld_root']) / 'desktop_env/evaluators/metrics/chrome.py'
    if Path(inspect.getsourcefile(is_expected_search_query)).resolve() != metric_path.resolve():
        raise ValueError('Imported comparison does not come from the frozen checkout')
    old_value = is_expected_search_query({'url': url}, original_rule)
    value = is_expected_search_query({'url': url}, repaired)
    if old_value != 0 or value != 1:
        raise ValueError('The unchanged comparison did not verify the controlled rule correction')
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(evidence_path, output / 'terminal-evidence.json')
    for name in ('search_reference_repair.py', 'repair_search_reference.py'):
        shutil.copyfile(ROOT / name, output / name)
    write_new(output / 'reference-rule.json', repaired)
    record = {'schema_version': 1, 'kind': KIND, 'task_id': TASK_ID,
        'run_dir': str(run_dir), 'created_at': datetime.now(timezone.utc).isoformat(),
        'status': 'corrected', 'original_score': 0.0, 'score': float(value),
        'model_calls': 0, 'vm_starts': 0, 'actor_rerun': False, 'getter_replayed': False,
        'input_kind': 'preserved_pre_reload_active_url', 'original_post_reload_url': None,
        'original_post_reload_metric_input_retained': False,
        'observed_terminal_url': url, 'old_rule_on_observed_terminal_score': float(old_value),
        'metric': 'is_expected_search_query', 'metric_source_sha256': sha(metric_path),
        'source_provenance': source_provenance(),
        'run_metadata_sha256': sha(run_dir / 'run.json'),
        'original_receipt': str(original), 'original_receipt_sha256': sha(original),
        'task_sha256': evidence['task_json_sha256'],
        'evidence': str(output / 'terminal-evidence.json'),
        'evidence_sha256': sha(output / 'terminal-evidence.json'),
        'reference_rule': str(output / 'reference-rule.json'),
        'reference_rule_sha256': sha(output / 'reference-rule.json'),
        'repair_sources_sha256': {name: sha(output / name) for name in
            ('search_reference_repair.py', 'repair_search_reference.py')},
        'evidence_errors': [],
        'boundary': 'Uses the preserved original foreground URL and unchanged metric with a repaired engine rule; the old getter reload was not replayed and its post-navigation URL is unknown.'}
    write_new(output / 'correction.json', record)
    return record


def verify_correction(run_dir, path):
    run_dir, path = Path(run_dir).resolve(), Path(path).resolve()
    record = read(path)
    if (record.get('kind') != KIND or record.get('task_id') != TASK_ID
            or record.get('status') != 'corrected' or Path(record['run_dir']).resolve() != run_dir
            or record.get('actor_rerun') is not False or record.get('getter_replayed') is not False
            or record.get('model_calls') != 0 or record.get('vm_starts') != 0
            or type(record.get('original_score')) not in (int, float) or record['original_score'] != 0
            or record.get('input_kind') != 'preserved_pre_reload_active_url'
            or record.get('original_post_reload_metric_input_retained') is not False
            or record.get('original_post_reload_url') is not None or record.get('evidence_errors')
            or sha(run_dir / 'run.json') != record['run_metadata_sha256']):
        raise ValueError('Correction identity or declared evidence boundary changed')
    metadata, original, _, url, _, expected = inputs(run_dir, record['evidence'])
    if (str(original) != record['original_receipt'] or sha(original) != record['original_receipt_sha256']
            or url != record['observed_terminal_url'] or sha(record['evidence']) != record['evidence_sha256']
            or sha(record['reference_rule']) != record['reference_rule_sha256']
            or read(record['reference_rule']) != expected):
        raise ValueError('Correction inputs, terminal observation or reference changed')
    if set(record['repair_sources_sha256']) != {'search_reference_repair.py', 'repair_search_reference.py'}:
        raise ValueError('Correction source inventory is incomplete')
    for name, checksum in record['repair_sources_sha256'].items():
        if sha(path.parent / name) != checksum:
            raise ValueError('Archived correction source changed')
    metric_path = Path(metadata['osworld_root']) / 'desktop_env/evaluators/metrics/chrome.py'
    if sha(metric_path) != record['metric_source_sha256']:
        raise ValueError('Original comparison source changed')
    score = record.get('score')
    if type(score) not in (float, int) or not math.isfinite(score) or score != 1:
        raise ValueError('Invalid same-query search correction score')
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
