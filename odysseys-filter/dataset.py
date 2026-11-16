"""The fixed 168 original Odysseys rows, with original rubrics and order."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def load_rows():
    manifest = json.loads((PACKAGE / 'data/manifest.json').read_bytes())
    data, excluded_path = PACKAGE / 'data/tasks.json', PACKAGE / 'data/exclusions.json'
    if sha(data) != manifest['dataset_sha256'] or sha(excluded_path) != manifest['exclusions_sha256']:
        raise ValueError('Pinned task dataset or approved exclusions changed')
    rows = json.loads(data.read_bytes())
    exclusions = json.loads(excluded_path.read_bytes())['rows']
    ids, excluded = [r['task_id'] for r in rows], {r['task_id'] for r in exclusions}
    if len(rows) != 168 or len(set(ids)) != 168 or len(excluded) != 32 or set(ids) & excluded:
        raise ValueError('Only the approved 200 - 32 = 168 task set is allowed')
    originals = manifest['tasks']
    if len(originals) != 168 or [r['task_id'] for r in originals] != ids:
        raise ValueError('Task IDs or original ordering changed')
    ordinals = [r['original_ordinal'] for r in originals]
    if ordinals != sorted(set(ordinals)) or set(ordinals) | {r['original_ordinal'] for r in exclusions} != set(range(1, 201)):
        raise ValueError('Original ordinal coverage changed')
    for row, original in zip(rows, originals):
        if hashlib.sha256(canonical(row)).hexdigest() != original['original_row_sha256']:
            raise ValueError('Original task content changed: ' + row['task_id'])
        if hashlib.sha256(canonical(row['rubrics'])).hexdigest() != original['rubrics_sha256']:
            raise ValueError('Original rubric changed: ' + row['task_id'])
        public = {k: v for k, v in zip(('id', 'instruction', 'start_url'),
                                      (row['task_id'], row['confirmed_task'], row['website']))}
        if hashlib.sha256((json.dumps(public, ensure_ascii=False, indent=2) + '\n').encode()).hexdigest() != original['task_input_sha256']:
            raise ValueError('Original Actor input changed: ' + row['task_id'])
    return rows


def tasks():
    # Same conversion as the original continue_evaluate.tasks('odysseys').
    return [{'id': str(t['task_id']), 'instruction': t['confirmed_task'], 'start_url': t['website'],
             'level': t['level'], 'rubrics': [{'id': k, **v} for k, v in t['rubrics'].items()]}
            for t in load_rows()]
