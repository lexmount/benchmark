"""Task-scoped, read-only extraction of a non-address document heading.

The fixed upstream identity checks and fuzzy arithmetic are reused unchanged.
Only the first nonempty paragraph can be excluded, and only when its content,
formatting and absence of address identity establish a document heading.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata

TASK_ID = "7ff48d5b-2df2-49da-b500-a5150ffc7f18"
UPSTREAM_COMMIT = "5123bfdbbc34b947bcffcff564abc62d0ab7072d"
FUNCTION_NAMES = {"fuzzy_place_math", "_normalize_place_entry", "_place_contains",
                  "_place_identity_matches", "_fuzzy_distinct_place_score"}


@dataclass(frozen=True)
class ParagraphView:
    paragraphs: tuple


def load_official_functions(root):
    """Reuse the official tests' AST loader, avoiding unrelated VM providers."""
    from docx import Document
    from rapidfuzz import fuzz

    path = Path(root) / "desktop_env/evaluators/metrics/general.py"
    nodes = [n for n in ast.parse(path.read_text()).body
             if isinstance(n, ast.FunctionDef) and n.name in FUNCTION_NAMES]
    if {n.name for n in nodes} != FUNCTION_NAMES:
        raise ValueError("The expected original address metric functions are missing")
    namespace = dict(Document=Document, fuzz=fuzz, re=re, unicodedata=unicodedata)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def _run_format(paragraph):
    runs = [r for r in paragraph.runs if r.text.strip()]
    sizes, bold = [], []
    for run in runs:
        size = run.font.size or paragraph.style.font.size
        sizes.append(float(size.pt) if size is not None else None)
        value = run.bold
        if value is None:
            value = paragraph.style.font.bold
        bold.append(value is True)
    return {"all_text_runs_bold": bool(runs) and all(bold),
            "text_run_font_sizes_pt": sizes,
            "all_font_sizes_known": bool(sizes) and all(s is not None for s in sizes)}


def _address_or_list_shape(text):
    value = unicodedata.normalize("NFKC", text).strip()
    # Never hide a numbered entry, a street, house number, building or venue.
    return bool(re.search(r"^(?:\d+\s*[.)、:]|\(\d+\)|[•●▪*\-])", value)
                or re.search(r"路|街|巷|弄|大道|公路|大厦|公寓|警务室|服务厅|服务区|楼|栋|座|单元", value)
                or re.search(r"\d+\s*(?:[-/]\s*\d+)?\s*号", value))


def prepare_address_scoring_view(document, rules, official):
    """Return a paragraph view and an explicit extraction audit; write nothing."""
    if (type(rules.get("expected_entry_count")) is not int
            or rules["expected_entry_count"] != 5 or rules.get("require_distinct") is not True):
        raise ValueError("This extraction repair only supports the five-distinct-place rule")
    paragraphs = tuple(document.paragraphs)
    nonempty = [(i, p) for i, p in enumerate(paragraphs) if p.text.strip()]
    audit = {"kind": "task-scoped heading extraction repair", "ignored_paragraphs": [],
             "original_nonempty_paragraphs": len(nonempty),
             "remaining_nonempty_paragraphs": len(nonempty)}
    if not nonempty:
        return ParagraphView(paragraphs), audit
    index, first = nonempty[0]
    text = unicodedata.normalize("NFKC", first.text).strip()
    normalized = official["_normalize_place_entry"](text)
    groups = [[official["_normalize_place_entry"](a) for a in
               ([g] if isinstance(g, str) else g)] for g in rules["expected"]]
    identities = [[official["_normalize_place_entry"](a) for a in
                   ([g] if isinstance(g, str) else g)]
                  for g in rules.get("identity_aliases", [[] for _ in groups])]
    if len(identities) != len(groups):
        raise ValueError("Original address identity metadata is malformed")
    matched = official["_place_identity_matches"](normalized, groups, identities)
    # Content is task-scoped; a general unmatched paragraph is never discarded.
    title_tokens = bool(re.fullmatch(
        r"(?:深圳市)?福田区(?:(?:24|二十四)小时)?自助签注(?:机|设备)?"
        r"(?:地址|地点|网点)(?:\(5(?:个|处)?\))?[:：]?", normalized))
    style = first.style.name or ""
    semantic_style = bool(re.fullmatch(r"(?:Title|Heading(?:\s*\d+)?)", style, re.I))
    formatting = _run_format(first)
    body_format = _run_format(nonempty[1][1]) if len(nonempty) > 1 else None
    larger_bold = bool(formatting["all_text_runs_bold"]
        and formatting["all_font_sizes_known"] and body_format
        and body_format["all_font_sizes_known"]
        and min(formatting["text_run_font_sizes_pt"]) > max(body_format["text_run_font_sizes_pt"]))
    if (not title_tokens or matched or _address_or_list_shape(text)
            or not (semantic_style or larger_bold)):
        return ParagraphView(paragraphs), audit
    audit["ignored_paragraphs"].append({"paragraph_index": index, "text": first.text,
        "style": style, "formatting": formatting, "following_body_formatting": body_format,
        "title_style": semantic_style, "larger_bold_title": larger_bold,
        "required_title_tokens_present": True, "original_reference_identities": [],
        "address_or_numbered_entry_shape": False})
    view = ParagraphView(tuple(p for i, p in enumerate(paragraphs) if i != index))
    audit["remaining_nonempty_paragraphs"] -= 1
    return view, audit


def score_document(path, rules, official):
    """Preserve the outer checks, then delegate to the unchanged upstream helper."""
    if path is None:
        return 0.0, {"ignored_paragraphs": []}
    expected = rules["expected"]
    count = rules.get("expected_entry_count", 3)
    if type(count) is not int or count <= 0:
        return 0.0, {"ignored_paragraphs": []}
    if count != 5 or rules.get("require_distinct") is not True:
        raise ValueError("Only the audited five-distinct-place task is supported")
    # Same Document loading/error behavior as upstream fuzzy_place_math.
    document = official["Document"](path)
    view, audit = prepare_address_scoring_view(document, rules, official)
    value = official["_fuzzy_distinct_place_score"](
        view, expected, count, rules.get("identity_aliases"))
    return value, audit


def source_provenance():
    base = f"https://github.com/xlang-ai/OSWorld/blob/{UPSTREAM_COMMIT}/"
    return {"latest_main_head_checked": UPSTREAM_COMMIT,
        "metric_source": base + "desktop_env/evaluators/metrics/general.py#L166",
        "tests_read": base + "tests/test_fuzzy_place_math.py",
        "PRs_read": ["https://github.com/xlang-ai/OSWorld/pull/625",
                     "https://github.com/xlang-ai/OSWorld/pull/627"],
        "research_result": "The merged five-place/identity fixes preserve exact address count but do not exclude non-address document headings. Current main and inspected tests have no heading-plus-five-address case.",
        "reuse": "Official test AST loader and all five original metric functions; custom code is limited to a guarded read-only first-heading view.",
        "unchanged": "Original document bytes, remaining paragraph text, expected address/identity groups, count, distinctness checks and maximum-ratio fuzzy arithmetic."}
