"""Narrow alias and preserved-folder contracts; no network, VM, or model."""
import ast
from copy import deepcopy
import itertools
import os
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bookmark_reference_repair as repair
import repair_bookmark_reference as cli


def fixture():
    rows = [('Linxi Fan', 'https://jimfan.me/'), ('De-An Huang', 'https://ai.stanford.edu/~dahuang/'),
            ('Yuke Zhu', repair.ALIAS), ('Anima Anandkumar', 'http://tensorlab.cms.caltech.edu/users/anima/')]
    disk = {'id': '5', 'name': 'Liked Authors', 'type': 'folder', 'children': [
        {'id': str(i + 6), 'type': 'url', 'name': title, 'url': url} for i, (title, url) in enumerate(rows)]}
    api = {'id': '1', 'title': 'Bookmarks bar', 'children': [
        {'id': '5', 'parentId': '1', 'title': 'Liked Authors', 'children': [
            {'id': str(i + 6), 'parentId': '5', 'index': i, 'title': title, 'url': url}
            for i, (title, url) in enumerate(rows)]}]}
    verification = {'folder': 'Liked Authors', 'folder_parent': 'Bookmarks bar', 'folder_id': '5',
        'folder_position_in_bar': 0, 'bookmarks': [{'title': t, 'url': u} for t, u in rows]}
    return disk, api, verification


def official_metric():
    # Execute the exact checked-in official function, without importing its many
    # unrelated optional desktop dependencies. This is not a reimplementation.
    source = Path(os.environ.get('OSWORLD_UPSTREAM_DIR', '/tmp/osworld-corpus-5123')) / 'desktop_env/evaluators/metrics/chrome.py'
    if not source.is_file():
        return None
    function = next(node for node in ast.parse(source.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == 'is_expected_bookmarks')
    function.returns = None
    for arg in function.args.args:
        arg.annotation = None
    class Logger:
        def info(self, *_):
            pass
    namespace = {'logger': Logger(), 'product': itertools.product}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
    return namespace['is_expected_bookmarks']


class AliasTests(unittest.TestCase):
    def test_exact_original_rule_deep_copy_only_one_alias(self):
        task = json.loads((ROOT / 'data/tasks/multi_apps' / (repair.TASK_ID + '.json')).read_text())
        original = task['evaluator']['expected']['rules']
        self.assertEqual(original, repair.ORIGINAL_RULES)
        repaired = repair.repair_rules(original)
        expected = deepcopy(original)
        expected['urls'][2].append(repair.ALIAS)
        self.assertEqual(repaired, expected)
        repaired['urls'][0].clear()
        self.assertEqual(original, repair.ORIGINAL_RULES)

    def test_rule_drift_or_already_repaired_rejected(self):
        for change in ({}, {'type': 'anything'}, repair.repair_rules(repair.ORIGINAL_RULES)):
            with self.subTest(rule=change), self.assertRaises(ValueError):
                repair.repair_rules(change)

    def test_original_metric_isolates_alias_and_preserves_cardinality(self):
        metric = official_metric()
        if metric is None:
            self.skipTest('Pinned upstream checkout is not present locally')
        disk, api, verification = fixture()
        projected = cli.bookmark_projection(json.dumps([disk]), json.dumps(api), verification)
        self.assertEqual(metric(projected, deepcopy(repair.ORIGINAL_RULES)), 0.)
        repaired = repair.repair_rules(repair.ORIGINAL_RULES)
        self.assertEqual(metric(projected, deepcopy(repaired)), 1.)
        for count in (3, 5):
            wrong = deepcopy(projected)
            children = wrong['bookmark_bar']['children'][0]['children']
            if count == 3:
                children.pop()
            else:
                children.append({'type': 'url', 'url': 'https://unrelated.example/'})
            self.assertEqual(metric(wrong, deepcopy(repaired)), 0.)

    def test_source_provenance_json_only(self):
        value = repair.source_provenance()
        self.assertEqual(value['task_id'], repair.TASK_ID)
        self.assertEqual(value['alias'], repair.ALIAS)
        json.dumps(value, allow_nan=False)


class ProjectionTests(unittest.TestCase):
    def test_complete_json_prefix_with_later_logs(self):
        disk, api, verification = fixture()
        result = cli.bookmark_projection(json.dumps([disk]) + '\nchrome://bookmarks/?id=5\n',
            json.dumps(api) + '\n' + json.dumps(verification) + '\nsaved workspace file', verification)
        self.assertEqual(result, {'bookmark_bar': {'children': [disk]}})

    def test_partial_or_disagreeing_observations_fail_closed(self):
        for kind in ('truncated', 'wrong_parent', 'extra_child', 'wrong_url', 'wrong_verification'):
            disk, api, verification = fixture()
            disk_text = json.dumps([disk])
            if kind == 'truncated':
                disk_text = disk_text[:-2]
            elif kind == 'wrong_parent':
                api['children'][0]['parentId'] = '2'
            elif kind == 'extra_child':
                disk['children'].append(deepcopy(disk['children'][0]))
                disk_text = json.dumps([disk])
            elif kind == 'wrong_url':
                api['children'][0]['children'][2]['url'] = 'https://unrelated.example/'
            else:
                verification['bookmarks'][0]['title'] = 'Other'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                cli.bookmark_projection(disk_text, json.dumps(api), verification)


class OriginalToolEvidenceTests(unittest.TestCase):
    def test_calls_and_returns_are_bound_by_id_and_ignore_reasoning(self):
        messages = [{'parts': [
            {'part_kind': 'thinking', 'content': 'This is not tool evidence'},
            {'part_kind': 'tool-call', 'tool_name': 'python', 'tool_call_id': 'a',
             'args': json.dumps({'code': 'first'})},
            {'part_kind': 'tool-call', 'tool_name': 'python', 'tool_call_id': 'b',
             'args': {'code': 'second'}}]}, {'parts': [
            {'part_kind': 'tool-return', 'tool_call_id': 'b', 'content': [{'text': 'second output'}]},
            {'part_kind': 'tool-return', 'tool_call_id': 'a', 'content': ['first output']},
            {'part_kind': 'tool-return', 'tool_call_id': 'missing', 'content': ['ignore']}]}]
        calls = cli._recorded_calls(messages)
        self.assertEqual(calls[0]['args']['code'], 'first')
        self.assertEqual(calls[0]['observations'], ['first output'])
        self.assertEqual(calls[1]['observations'], ['second output'])


class HookTests(unittest.TestCase):
    def modules(self, original):
        misc = types.SimpleNamespace(get_rule=original)
        exports = types.SimpleNamespace(get_rule=original)
        return misc, exports, {'desktop_env.evaluators.getters.misc': misc,
                               'desktop_env.evaluators.getters': exports}

    def test_target_only_and_other_rules_identity(self):
        original = lambda env, config: config['rules']
        misc, exports, modules = self.modules(original)
        with patch.object(repair.importlib, 'import_module', side_effect=modules.__getitem__):
            repair.install_getter_patch()
            other = {'arbitrary': [1]}
            self.assertIs(misc.get_rule(types.SimpleNamespace(task_id='other'), {'rules': other}), other)
            value = misc.get_rule(types.SimpleNamespace(task_id=repair.TASK_ID), {'rules': repair.ORIGINAL_RULES})
            self.assertEqual(value['urls'][2][-1], repair.ALIAS)
            self.assertIs(exports.get_rule, misc.get_rule)
            wrapper = misc.get_rule
            repair.install_getter_patch()
            self.assertIs(misc.get_rule, wrapper)

    def test_wraps_preserves_prior_search_marker(self):
        def earlier_search_wrapper(env, config):
            return config['rules']
        earlier_search_wrapper._lexmount_search_reference_repair = True
        misc, exports, modules = self.modules(earlier_search_wrapper)
        with patch.object(repair.importlib, 'import_module', side_effect=modules.__getitem__):
            repair.install_getter_patch()
        self.assertTrue(misc.get_rule._lexmount_search_reference_repair)
        self.assertIs(misc.get_rule.__wrapped__, earlier_search_wrapper)

    def test_search_then_bookmark_then_reinstall_is_stable(self):
        import search_reference_repair as search
        original = lambda env, config: config['rules']
        misc, exports, modules = self.modules(original)
        with patch.object(repair.importlib, 'import_module', side_effect=modules.__getitem__):
            search.install_getter_patch()
            repair.install_getter_patch()
            combined = misc.get_rule
            search.install_getter_patch()
            repair.install_getter_patch()
            self.assertIs(misc.get_rule, combined)
            value = combined(types.SimpleNamespace(task_id=search.TASK_ID),
                {'rules': {'expect': {'pattern': search.ORIGINAL_PATTERN}}})
            self.assertEqual(value['expect']['pattern'], search.REPAIRED_PATTERN)
            value = combined(types.SimpleNamespace(task_id=repair.TASK_ID),
                {'rules': repair.ORIGINAL_RULES})
            self.assertEqual(value['urls'][2][-1], repair.ALIAS)

    def test_exports_conflict_rejected(self):
        misc, exports, modules = self.modules(lambda env, config: config)
        exports.get_rule = lambda env, config: config
        with patch.object(repair.importlib, 'import_module', side_effect=modules.__getitem__), self.assertRaises(RuntimeError):
            repair.install_getter_patch()


if __name__ == '__main__':
    unittest.main()
