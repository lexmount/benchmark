"""Keep original, evidence regrade and new Actor retry outcomes distinct."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import reference_report as report_module


class ReferenceReportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        items = json.loads((ROOT / 'data/manifest.json').read_text())['tasks']
        self.rows = [{**{k: item[k] for k in ('task_id', 'category', 'ordinal')},
                      'status': 'scored', 'score': 1.0} for item in items]
        self.pdf = report_module.pdf.TASK_ID
        self.search = report_module.search.TASK_ID
        self.retry = '0ed39f63-6049-43d4-ba4d-5fa2fe04a951'
        for row in self.rows:
            if row['task_id'] == self.pdf:
                row.update(status='reference_unavailable', score=None)
            elif row['task_id'] == self.search:
                row['score'] = 0.0
            elif row['task_id'] == self.retry:
                row.update(status='actor_error', score=None)
        next(row for row in self.rows if row['task_id'] not in {self.pdf, self.search, self.retry})['score'] = .5
        self.base = {'tasks': self.rows, 'raw_official': {'marker': 'preserved original report'}}

    def packet(self, name, task_id, score, *, rerun=False):
        path = self.root / name
        value = {'task_id': task_id, 'score': score, 'original_score': None if rerun else 0.0,
                 'actor_rerun': rerun, 'kind': 'technical-actor-retry-v1' if rerun else 'fixture-reference-repair'}
        path.write_text(json.dumps(value))
        return path, value

    def test_fractional_regrade_and_valid_zero_retry_are_not_rounded_or_cherry_picked(self):
        pdf_path, pdf_value = self.packet('pdf.json', self.pdf, .75)
        search_path, search_value = self.packet('search.json', self.search, 1.0)
        retry_path, retry_value = self.packet('retry.json', self.retry, 0.0, rerun=True)
        before = copy.deepcopy(self.base)
        import technical_retry_record
        with patch.object(report_module.pdf, 'report', return_value=self.base), \
             patch.object(report_module.pdf, 'verify_correction', return_value=pdf_value), \
             patch.object(report_module.search, 'verify_correction', return_value=search_value), \
             patch.object(technical_retry_record, 'verify_record', return_value=retry_value):
            value = report_module.report(self.root, [pdf_path, search_path, retry_path])
        self.assertEqual(value['valid_scored'], 76)
        self.assertEqual(value['corrected_tasks'], 2)
        self.assertEqual(value['technical_actor_retries'], 1)
        self.assertEqual(value['score_sum'], 74.25)
        self.assertEqual(value['full_76_mean'], 74.25 / 76)
        self.assertEqual(value['fully_successful_tasks'], 73)
        retry_row = next(row for row in value['tasks'] if row['task_id'] == self.retry)
        self.assertEqual(retry_row['score'], 0)
        self.assertEqual(retry_row['status'], 'technical_retry')
        self.assertEqual(retry_row['correction_input_kind'], 'new_actor_attempt_after_provider_error')
        self.assertEqual(self.base, before)
        self.assertEqual(value['raw_official'], before['raw_official'])

    def test_missing_outcomes_never_become_zero_or_a_complete_mean(self):
        with patch.object(report_module.pdf, 'report', return_value=self.base):
            value = report_module.report(self.root)
        self.assertEqual(value['valid_scored'], 74)
        self.assertEqual(value['unscored_tasks'], 2)
        self.assertIsNone(value['full_76_mean'])
        self.assertFalse(value['complete'])

    def test_duplicate_corrections_are_rejected_instead_of_selecting_best_score(self):
        first, a = self.packet('first.json', self.search, 0)
        second, _ = self.packet('second.json', self.search, 1)
        with patch.object(report_module.search, 'verify_correction', return_value=a):
            with self.assertRaisesRegex(ValueError, 'Multiple corrections'):
                report_module.report(self.root, [first, second])

    def test_arbitrary_task_rejudges_are_not_accepted(self):
        task_id = next(row['task_id'] for row in self.rows if row['task_id'] not in
                       {self.pdf, self.search, self.retry} and row['task_id'] not in report_module.ADDITIONAL
                       and row['task_id'] not in report_module.files.TASKS)
        path, _ = self.packet('unsupported.json', task_id, 1)
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            report_module.report(self.root, [path])


if __name__ == '__main__':
    unittest.main()
