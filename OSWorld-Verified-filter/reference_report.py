#!/usr/bin/env python3
"""Compose validated, separately recorded reference corrections over raw scores."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import json
import importlib
import math
from pathlib import Path

import repair_pdf_reference as pdf
import repair_search_reference as search
import repair_file_evaluation as files

ADDITIONAL = {
    '7ff48d5b-2df2-49da-b500-a5150ffc7f18': ('repair_address_reference', 'verify_correction'),
    'a82b78bb-7fde-4cb3-94a4-035baf10bcf0': ('repair_bookmark_reference', 'verify_correction'),
    '0ed39f63-6049-43d4-ba4d-5fa2fe04a951': ('technical_retry_record', 'verify_record'),
    '5990457f-2adb-467b-a4af-5c857c92d762': ('repair_scholar_reference', 'verify_correction'),
    'd1acdb87-bb67-4f30-84aa-990e56a09c92': ('repair_restaurant_reference', 'verify_correction'),
}


def report(run_dir, correction_paths=()):
    run_dir = Path(run_dir).resolve()
    records, paths = {}, {}
    for path in map(lambda p: Path(p).resolve(), correction_paths):
        value = json.loads(path.read_text())
        task_id = value.get('task_id')
        if task_id in records:
            raise ValueError('Multiple corrections for the same task are not selectable outcomes')
        if task_id == pdf.TASK_ID:
            value = pdf.verify_correction(run_dir, path)
        elif task_id == search.TASK_ID:
            value = search.verify_correction(run_dir, path)
        elif task_id in files.TASKS:
            value = files.verify_correction(run_dir, path)
        elif task_id in ADDITIONAL:
            module_name, function_name = ADDITIONAL[task_id]
            value = getattr(importlib.import_module(module_name), function_name)(run_dir, path)
        else:
            raise ValueError('Unsupported reference correction task')
        records[task_id], paths[task_id] = value, path
    base = pdf.report(run_dir, paths.get(pdf.TASK_ID))
    rows = copy.deepcopy(base['tasks'])
    for row in rows:
        task_id = row['task_id']
        if task_id in records:
            value, path = records[task_id], paths[task_id]
            rerun = value.get('actor_rerun') is True
            row.update(status='technical_retry' if rerun else 'corrected', score=value['score'], original_score=value['original_score'],
                       correction=str(path), correction_sha256=pdf.sha(path),
                       correction_kind=value.get('kind', 'pdf-reference-v1-original-output'),
                       actor_rerun=rerun,
                       correction_input_kind=value.get('input_kind', 'new_actor_attempt_after_provider_error' if rerun else 'original_actual_pdf_and_repaired_reference'))
    scores = [row['score'] for row in rows if row['status'] in {'scored', 'corrected', 'technical_retry'}]
    total = math.fsum(scores)
    full = len(scores) == 76
    return {'benchmark': 'OSWorld-Verified-filter', 'run_dir': str(run_dir),
            'scoring_version': 'official-5123 + separately validated reference corrections',
            'fixed_denominator': 76, 'task_count': 76, 'valid_scored': len(scores),
            'unscored_tasks': 76 - len(scores), 'complete': full,
            'corrected_tasks': sum(value.get('actor_rerun') is not True for value in records.values()),
            'technical_actor_retries': sum(value.get('actor_rerun') is True for value in records.values()),
            'status_counts': dict(Counter(r['status'] for r in rows)),
            'score_sum': total, 'full_76_mean': total / 76 if full else None,
            'fully_successful_tasks': sum(score == 1 for score in scores),
            'full_76_exact_one_rate': sum(score == 1 for score in scores) / 76 if full else None,
            'raw_official': base['raw_official'],
            'correction_records': [{'task_id': key, 'path': str(paths[key]),
                'sha256': pdf.sha(paths[key]), 'kind': value.get('kind', 'pdf-reference-v1-original-output'),
                'input_kind': value.get('input_kind', 'new_actor_attempt_after_provider_error' if value.get('actor_rerun') is True else 'original_actual_pdf_and_repaired_reference'),
                'actor_rerun': value.get('actor_rerun') is True}
                for key, value in records.items()], 'tasks': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--correction', type=Path, action='append', default=[])
    args = parser.parse_args()
    print(json.dumps(report(args.run_dir, args.correction), ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
