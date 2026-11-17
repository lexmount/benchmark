"""Opt-in expected-rule repair for the Calc-to-Chrome search task.

The original task asks for a search in Chrome, without selecting a search
engine. This adds Bing to the expected rule; the original Google/Sorry branch,
task JSON, active-tab getter and is_expected_search_query metric remain unchanged.

Inspected sources:
* Original 2024 instruction, unchanged in the 2025 review and pinned task:
  https://github.com/xlang-ai/OSWorld/blob/f194fb8d75186c9bfaf07d7d096bb6f356f1253b/evaluation_examples/examples/multi_apps/f8cfa149-d1c1-4215-8dac-4a0932bad3c2.json
  https://github.com/xlang-ai/OSWorld/blob/97ed6f99b0039c76eb82d1210b299c7fef87d85b/evaluation_examples/examples/multi_apps/f8cfa149-d1c1-4215-8dac-4a0932bad3c2.json
* PR469, merged as 9f5083c2f54808705208296853f830f91c8bc701, only
  adds Google Sorry redirects. Its diff contains no test or Google-only task
  requirement: https://github.com/xlang-ai/OSWorld/pull/469
* Original task source discusses Chrome/Calc clipboard transfer, not Google:
  https://superuser.com/questions/1803088/libreoffice-calc-clears-clipboard
* Pinned metric only searches rules['expect']['pattern'] in the supplied URL:
  https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/chrome.py#L198

This module is not loaded into the running frozen v3 workers.  Any historical
correction must retain the original score and bind the preserved URL evidence.
The logged active URL precedes get_active_tab_info's page reload; it must not
be misrepresented as a retained post-navigation metric input.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib
from pathlib import Path

TASK_ID = "f8cfa149-d1c1-4215-8dac-4a0932bad3c2"
UPSTREAM_COMMIT = "5123bfdbbc34b947bcffcff564abc62d0ab7072d"
REPAIR_VERSION = "search-reference-bing-v1"
ORIGINAL_PATTERN = r"(?i)https?://(?:www\.)?google\.com/(?:search\?q=nereida(?:&|$|#)|sorry/index\?.*?continue=https?://(?:www\.)?google\.com/search%3Fq%3Dnereida).*"

# Non-query parameters cannot be a second q (including a bare q). Restricting
# their names to unescaped ASCII also prevents %71 from smuggling a duplicate
# query key. Values may retain ordinary URL escapes. The literal query retains
# the original case-insensitive Nereida contract and does not accept substrings.
_OTHER_PARAMETER = r"(?!q(?:=|&|#|$))[a-z0-9_.~-]+(?:=[^&#\s]*)?"
_BING_PATTERN = (
    r"\Ahttps?://(?:(?:www|cn)\.)?bing\.com/search\?"
    + rf"(?:{_OTHER_PARAMETER}&)*q=nereida(?:&{_OTHER_PARAMETER})*"
    + r"(?:#[^\s]*)?\Z"
)
REPAIRED_PATTERN = ORIGINAL_PATTERN + "|" + _BING_PATTERN


def repair_rules(rules: dict) -> dict:
    """Copy precisely the pinned rule and add the independently scoped branch."""
    if not isinstance(rules, dict) or not isinstance(rules.get("expect"), dict):
        raise ValueError("Expected the original f8cfa149 search rule")
    if rules["expect"].get("pattern") != ORIGINAL_PATTERN:
        raise ValueError("Original f8cfa149 search pattern changed; refusing reference drift")
    result = deepcopy(rules)
    result["expect"]["pattern"] = REPAIRED_PATTERN
    return result


def source_provenance() -> dict:
    return {
        "repair_version": REPAIR_VERSION,
        "repair_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "task_id": TASK_ID,
        "upstream_commit": UPSTREAM_COMMIT,
        "original_pattern": ORIGINAL_PATTERN,
        "repaired_pattern": REPAIRED_PATTERN,
        "metric_unchanged": "desktop_env.evaluators.metrics.chrome.is_expected_search_query",
        "scope": "Original Google/Sorry rule plus one Bing search for the same query",
        "historical_evidence_boundary": "Preserved pre-reload active URL, not a retained post-navigation getter result",
    }


def install_getter_patch() -> dict:
    """Wrap the two get_rule exports before reset binds the expected getter.

    Other task IDs retain the original implementation and result object. The
    target task must still present its exact original pattern. No task file,
    metric implementation, relative-time rule or existing Env is rewritten.
    """
    misc = importlib.import_module("desktop_env.evaluators.getters.misc")
    getters = importlib.import_module("desktop_env.evaluators.getters")
    original = misc.get_rule
    if not getattr(original, "_lexmount_search_reference_repair", False):
        if getters.get_rule is not original:
            raise RuntimeError("get_rule exports differ; refusing an unknown existing patch")

        def get_rule(env, config):
            rules = original(env, config)
            if getattr(env, "task_id", None) == TASK_ID:
                return repair_rules(rules)
            return rules

        get_rule._lexmount_search_reference_repair = True
        misc.get_rule = get_rule
        getters.get_rule = get_rule
    elif getters.get_rule is not original:
        raise RuntimeError("Installed search reference exports differ")
    return {
        **source_provenance(),
        "patched_exports": [
            "desktop_env.evaluators.getters.misc.get_rule",
            "desktop_env.evaluators.getters.get_rule",
        ],
        "install_before_reset": True,
    }
