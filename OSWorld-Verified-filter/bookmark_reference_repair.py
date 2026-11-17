"""Task-scoped addition of the MineDojo author's university webpage alias.

The paper's own author link https://minedojo.org/ points to the exact UT Austin
URL below. Its observed 165-byte HTML performs a meta refresh to the already
accepted https://yukezhu.me. This adds that one alias to Yuke Zhu's group; it
does not normalize arbitrary URLs or change the task, folder, four authors,
active bookmark getter, or official is_expected_bookmarks comparison.

Inspected pinned source and task history:
https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/chrome.py#L155
https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/a82b78bb-7fde-4cb3-94a4-035baf10bcf0.json
https://github.com/xlang-ai/OSWorld/pull/243
PR243 clarified the Bookmarks bar location, without requiring a canonical URL.
The later 97ed6f99 review added LinkedIn alternatives but not this paper link.
No existing alias repair was found in the inspected official task history.

Historical correction must explicitly use retained pre-cleanup observations:
the complete original post-cleanup getter input was not archived.
"""
from __future__ import annotations
from copy import deepcopy
from functools import wraps
import hashlib
import importlib
from pathlib import Path

TASK_ID = "a82b78bb-7fde-4cb3-94a4-035baf10bcf0"
UPSTREAM_COMMIT = "5123bfdbbc34b947bcffcff564abc62d0ab7072d"
REPAIR_VERSION = "bookmark-reference-yuke-alias-v1"
ALIAS = "https://www.cs.utexas.edu/~yukez/"
ORIGINAL_RULES = {'type': 'liked_authors_websites_urls', 'names': ['Liked Authors'], 'urls': [['https://jimfan.me/', 'https://research.nvidia.com/person/linxi-jim-fan', 'https://www.linkedin.com/in/drjimfan/'], ['https://research.nvidia.com/person/de-an-huang', 'https://ai.stanford.edu/~dahuang/', 'https://www.linkedin.com/in/de-an-huang-38242a69'], ['https://yukezhu.me/', 'https://www.cs.utexas.edu/people/faculty-researchers/yuke-zhu', 'https://experts.utexas.edu/yuke_zhu', 'https://research.nvidia.com/person/yuke-zhu', 'https://www.linkedin.com/in/yukez/'], ['https://tensorlab.cms.caltech.edu/users/anima/', 'http://tensorlab.cms.caltech.edu/users/anima/', 'https://www.eas.caltech.edu/people/anima', 'https://en.wikipedia.org/wiki/Anima_Anandkumar', 'https://www.linkedin.com/in/anima-anandkumar/']]}


def repair_rules(rules: dict) -> dict:
    """Deep-copy only the precisely pinned four-author rule, then add one URL."""
    if rules != ORIGINAL_RULES:
        raise ValueError("Original a82b78bb bookmark rule changed; refusing reference drift")
    result = deepcopy(rules)
    result["urls"][2].append(ALIAS)
    return result


def source_provenance() -> dict:
    return {
        "repair_version": REPAIR_VERSION,
        "repair_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "task_id": TASK_ID, "upstream_commit": UPSTREAM_COMMIT,
        "alias": ALIAS, "author_group_index": 2,
        "metric_unchanged": "desktop_env.evaluators.metrics.chrome.is_expected_bookmarks",
        "independent_sources": [
            {"url": "https://minedojo.org/", "observed_at": "2026-11-17T13:01:11+00:00",
             "status": 200, "bytes": 32652,
             "sha256": "0b62e8ce5a4c5d93e0c1d570ef04bd0d017a0ece879727ceaa4b90cc0da3460e",
             "finding": "Yuke Zhu author anchor links to the exact alias"},
            {"url": ALIAS, "status": 200, "bytes": 165,
             "sha256": "41549ecb02fc1c2a5a98e31d1af5e44baeaad8f5867070089e733a56331c632d",
             "finding": "HTML meta refresh to https://yukezhu.me (not an HTTP redirect)"}],
        "historical_evidence_boundary": "Complete retained pre-cleanup folder observations, not the unretained post-cleanup full getter input",
    }


def install_getter_patch() -> dict:
    """Install before reset; preserve any earlier search-wrapper marker."""
    misc = importlib.import_module("desktop_env.evaluators.getters.misc")
    getters = importlib.import_module("desktop_env.evaluators.getters")
    original = misc.get_rule
    if getters.get_rule is not original:
        raise RuntimeError("get_rule exports differ; refusing an unknown existing patch")
    if not getattr(original, "_lexmount_bookmark_reference_repair", False):
        @wraps(original)
        def get_rule(env, config):
            rules = original(env, config)
            return repair_rules(rules) if getattr(env, "task_id", None) == TASK_ID else rules
        get_rule._lexmount_bookmark_reference_repair = True
        misc.get_rule = get_rule
        getters.get_rule = get_rule
    return {**source_provenance(), "patched_exports": [
        "desktop_env.evaluators.getters.misc.get_rule", "desktop_env.evaluators.getters.get_rule"],
        "install_before_reset": True}
