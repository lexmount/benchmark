"""Check the opt-in rule repair against the pinned metric's re.search contract.

OSWorld 5123bf's is_expected_search_query reads rules['expect']['pattern']
and applies re.search to the supplied URL. These cases exercise that public
rule output without a browser, VM, network request, model or score correction.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("search_reference_contract", ROOT / "search_reference_repair.py")
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)
TASK = ROOT / "data/tasks/multi_apps" / (repair.TASK_ID + ".json")


def matches(pattern, url):
    return re.search(pattern, url) is not None


class SearchRuleTests(unittest.TestCase):
    def setUp(self):
        self.original_bytes = TASK.read_bytes()
        self.task = json.loads(self.original_bytes)
        self.rules = self.task["evaluator"]["expected"]["rules"]

    def test_repair_starts_with_the_exact_frozen_rule_and_does_not_mutate_nested_inputs_or_task(self):
        self.assertEqual(self.rules["expect"]["pattern"], repair.ORIGINAL_PATTERN)
        self.assertTrue(repair.REPAIRED_PATTERN.startswith(repair.ORIGINAL_PATTERN + "|"))
        self.rules["metadata"] = {"nested": ["leave intact"]}
        before = deepcopy(self.rules)
        actual = repair.repair_rules(self.rules)
        self.assertEqual(self.rules, before)
        self.assertEqual(actual["expect"]["pattern"], repair.REPAIRED_PATTERN)
        actual["metadata"]["nested"].append("independent mutation")
        actual["expect"]["new"] = True
        self.assertEqual(self.rules, before)
        self.assertEqual(TASK.read_bytes(), self.original_bytes)

    def test_accepted_original_google_and_sorry_urls_keep_their_original_behavior(self):
        urls = [
            "https://www.google.com/search?q=nereida",
            "http://google.com/search?q=NEREIDA&sourceid=chrome&ie=UTF-8",
            "HTTPS://WWW.GOOGLE.COM/search?q=Nereida#results",
            "https://www.google.com/sorry/index?continue=https://www.google.com/search%3Fq%3Dnereida&other=1",
            "https://google.com/sorry/index?x=y&continue=http://google.com/search%3Fq%3DNEREIDA",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertTrue(matches(repair.ORIGINAL_PATTERN, url))
                self.assertTrue(matches(repair.REPAIRED_PATTERN, url))
        # These historical weaknesses are intentionally not broadened or fixed
        # by this independent Bing branch. New strictness belongs to Bing only.
        historical = "https://google.com/search?q=nereida&q=other"
        self.assertTrue(matches(repair.ORIGINAL_PATTERN, historical))
        self.assertTrue(matches(repair.REPAIRED_PATTERN, historical))

    def test_bing_search_accepts_only_the_exact_query_with_case_and_parameter_order_variations(self):
        urls = [
            "https://cn.bing.com/search?q=Nereida",
            "https://www.bing.com/search?q=nereida&form=QBLH",
            "https://www.bing.com/search?form=QBLH&qs=n&q=NEREIDA&sp=-1",
            "HTTP://CN.BING.COM/search?FORM=QBLH&Q=NeReIdA#results",
            "https://bing.com/search?q=Nereida",
            "https://cn.bing.com/search?FORM=x&empty=&bare&q=Nereida&safe=a%20b",
        ]
        pattern = repair.repair_rules(self.rules)["expect"]["pattern"]
        for url in urls:
            with self.subTest(url=url):
                self.assertFalse(matches(repair.ORIGINAL_PATTERN, url))
                self.assertTrue(matches(pattern, url))

    def test_new_branch_rejects_wrong_partial_missing_or_duplicate_queries(self):
        urls = [
            "https://www.bing.com/search?q=other",
            "https://cn.bing.com/search?q=NereidaOther",
            "https://cn.bing.com/search?q=Nereida+other",
            "https://cn.bing.com/search?q=Nereida%20",
            "https://cn.bing.com/search?q=%4Eereida",
            "https://cn.bing.com/search?qq=Nereida",
            "https://cn.bing.com/search?form=Nereida",
            "https://cn.bing.com/search?q=Nereida&q=other",
            "https://cn.bing.com/search?q=other&q=Nereida",
            "https://cn.bing.com/search?form=x&q=Nereida&Q=Nereida",
            "https://cn.bing.com/search?q=Nereida&q",
            "https://cn.bing.com/search?q&q=Nereida",
            "https://cn.bing.com/search?q=Nereida&%71=other",
            "https://cn.bing.com/search?%71=Nereida&q=Nereida",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertFalse(matches(repair.REPAIRED_PATTERN, url))

    def test_new_branch_cannot_match_fake_domains_embedded_urls_or_arbitrary_navigation(self):
        urls = [
            "https://bing.com.evil.example/search?q=Nereida",
            "https://evil.bing.com/search?q=Nereida",
            "https://www.bing.com.evil.example/search?q=Nereida",
            "https://www.bing.com@evil.example/search?q=Nereida",
            "https://evil.example/?next=https://www.bing.com/search?q=Nereida",
            "prefix https://cn.bing.com/search?q=Nereida",
            "https://cn.bing.com/search?q=Nereida trailing text",
            "https://cn.bing.com/search?q=Nereida\n",
            "https://cn.bing.com/notsearch?q=Nereida",
            "https://cn.bing.com/search/?q=Nereida",
            "https://www.baidu.com/s?wd=Nereida",
            "https://duckduckgo.com/?q=Nereida",
            "https://example.com/search?q=Nereida",
            "file:///tmp/Nereida.html",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertFalse(matches(repair.REPAIRED_PATTERN, url))

    def test_unknown_or_already_changed_rules_are_rejected_instead_of_silently_widened(self):
        invalid = [None, [], {}, {"expect": []}, {"expect": {}},
                   {"expect": {"pattern": repair.ORIGINAL_PATTERN + "changed"}},
                   {"expect": {"pattern": repair.REPAIRED_PATTERN}}]
        for rules in invalid:
            with self.subTest(rules=rules):
                before = deepcopy(rules)
                with self.assertRaises(ValueError):
                    repair.repair_rules(rules)
                self.assertEqual(rules, before)

    def test_provenance_binds_the_custom_source_and_discloses_its_historical_input_boundary(self):
        value = repair.source_provenance()
        self.assertEqual(value["repair_source_sha256"], hashlib.sha256((ROOT / "search_reference_repair.py").read_bytes()).hexdigest())
        self.assertEqual(value["task_id"], repair.TASK_ID)
        self.assertEqual(value["original_pattern"], repair.ORIGINAL_PATTERN)
        self.assertEqual(value["repaired_pattern"], repair.REPAIRED_PATTERN)
        self.assertIn("pre-reload", value["historical_evidence_boundary"])
        self.assertIn("is_expected_search_query", value["metric_unchanged"])
        json.dumps(value, allow_nan=False)


class FutureRuleHookTests(unittest.TestCase):
    def exports(self):
        calls = []
        def original(env, config):
            calls.append((env, config))
            return config["rules"]
        misc = types.ModuleType("desktop_env.evaluators.getters.misc")
        misc.get_rule = original
        getters = types.ModuleType("desktop_env.evaluators.getters")
        getters.get_rule = original
        return misc, getters, original, calls

    def test_only_target_task_gets_a_copied_rule_and_repeated_install_does_not_double_wrap(self):
        misc, getters, original, calls = self.exports()
        config = {"rules": {"expect": {"pattern": repair.ORIGINAL_PATTERN}, "other": [1, 2]}}
        before = deepcopy(config)
        with mock.patch.dict(sys.modules, {"desktop_env.evaluators.getters.misc": misc,
                                          "desktop_env.evaluators.getters": getters}):
            first = repair.install_getter_patch()
            wrapped = misc.get_rule
            second = repair.install_getter_patch()
            self.assertIs(misc.get_rule, wrapped)
            self.assertIs(getters.get_rule, wrapped)
            self.assertIsNot(wrapped, original)
            changed = getters.get_rule(types.SimpleNamespace(task_id=repair.TASK_ID), config)
            self.assertEqual(changed["expect"]["pattern"], repair.REPAIRED_PATTERN)
            self.assertEqual(config, before)
            self.assertEqual(len(calls), 1)
            for env in (types.SimpleNamespace(task_id="other-task"), types.SimpleNamespace()):
                result = misc.get_rule(env, config)
                self.assertIs(result, config["rules"])
            self.assertEqual(len(calls), 3)
            self.assertEqual(first, second)
            self.assertTrue(first["install_before_reset"])
            json.dumps(first, allow_nan=False)

    def test_target_with_drifted_pattern_fails_but_other_tasks_are_passed_through(self):
        misc, getters, original, calls = self.exports()
        config = {"rules": {"expect": {"pattern": "another-task-rule"}}}
        with mock.patch.dict(sys.modules, {"desktop_env.evaluators.getters.misc": misc,
                                          "desktop_env.evaluators.getters": getters}):
            repair.install_getter_patch()
            self.assertIs(misc.get_rule(types.SimpleNamespace(task_id="other-task"), config), config["rules"])
            with self.assertRaisesRegex(ValueError, "pattern changed"):
                misc.get_rule(types.SimpleNamespace(task_id=repair.TASK_ID), config)
        self.assertEqual(config["rules"]["expect"]["pattern"], "another-task-rule")
        self.assertEqual(len(calls), 2)

    def test_disagreeing_exports_are_rejected_before_any_patch_is_applied(self):
        misc, getters, original, calls = self.exports()
        other = lambda env, config: config["rules"]
        getters.get_rule = other
        with mock.patch.dict(sys.modules, {"desktop_env.evaluators.getters.misc": misc,
                                          "desktop_env.evaluators.getters": getters}):
            with self.assertRaisesRegex(RuntimeError, "exports differ"):
                repair.install_getter_patch()
        self.assertIs(misc.get_rule, original)
        self.assertIs(getters.get_rule, other)


if __name__ == "__main__":
    unittest.main()
