"""Pure evidence primitives reused from the existing 5090 evaluation. No legacy Agent imports."""

import json

import hashlib

VERSION = "1113-native-visible-observations-v3"

CHUNK_CHARS = 1800

def _chunks(text):
    """Line-aligned ranges with a little preceding context; no rewritten text."""
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK_CHARS)
        if end < len(text):
            newline = text.rfind("\n", start + CHUNK_CHARS // 2, end)
            if newline >= 0:
                end = newline + 1
        if text[start:end].strip():
            yield start, end
        if end == len(text):
            break
        # Keep a heading/preceding row without splitting a short line.
        overlap = text.rfind("\n", max(start + 1, end - 180), end - 1)
        start = overlap + 1 if overlap >= 0 else max(start + 1, end - 180)

def _uncovered(start, end, covered):
    """Subtract already rendered intervals without merging different sources."""
    parts = [(start, end)]
    for lo, hi in covered:
        remaining = []
        for first, last in parts:
            if hi <= first or lo >= last:
                remaining.append((first, last))
            else:
                if first < lo:
                    remaining.append((first, lo))
                if hi < last:
                    remaining.append((hi, last))
        parts = remaining
    return parts

def whole_text(text, limit, kind):
    if len(text) <= limit:
        return text
    return json.dumps({'evidence_omitted': kind, 'source_characters': len(text),
        'source_sha256': hashlib.sha256(text.encode()).hexdigest(), 'omitted_range': [0, len(text)],
        'reason': 'Whole record exceeds submission limit; original preserved locally, not proof of absence.'})

def _encoded(value):
    return json.dumps(value, ensure_ascii=False)

def _observed_projection(text, budget):
    # Reuse the frozen product's exact source-range primitives. ACE outlines are
    # not Markdown, and the native verifier has a hard serialization ceiling.

    if len(_encoded(text)) <= budget:
        return text
    result = {
        'source_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'source_characters': len(text),
        'projection': 'Exact raw observed_text; character offsets are zero-based, end-exclusive.',
        'ranges': [], 'omitted_ranges': [[0, len(text)]],
    }
    covered = []
    for first, last in _chunks(text):
        for a, b in _uncovered(first, last, covered):
            fragment = {'start': a, 'end': b, 'text': text[a:b]}
            result['ranges'].append(fragment)
            candidate = covered + [(a, b)]
            result['omitted_ranges'] = _uncovered(0, len(text), candidate)
            if len(_encoded(result)) > budget:
                result['ranges'].pop()
                result['omitted_ranges'] = _uncovered(0, len(text), covered)
                return result
            covered = candidate
    return result

def bounded_units(records, limit):
    # Selection remains recent-first and never reads the task, answer, rubric or
    # score. Tool receipts remain atomic. Only observed page text can be projected
    # to exact, bounded source ranges. Keep at least one third of the overall
    # ceiling available beyond any one new page's text.
    if type(limit) is not int or limit < 512:
        raise ValueError('Evidence submission limit must be at least512 characters')
    result, omitted, used, retained_text = [], [], 0, {}
    # Reserve up to one third of the cap for recent complete tool receipts.
    # Page bodies must not crowd out small acknowledgements or read results.
    # The reservation includes every original metadata field; it cannot splice
    # a large receipt into a misleading success fragment.
    reserved, remaining_reserved = {}, 0
    for i in reversed(range(len(records))):
        if records[i].get('native_result') is None:
            continue
        stub = {**records[i], 'evidence_unit_index': i}
        text = stub.get('observed_text')
        if isinstance(text, str):
            stub['observed_text_sha256'] = hashlib.sha256(text.encode()).hexdigest()
            stub['observed_text'] = _observed_projection(text, 0)
        size = len(_encoded(stub)) + 1
        if remaining_reserved + size <= limit // 3:
            reserved[i] = size
            remaining_reserved += size
    for i in reversed(range(len(records))):
        remaining_reserved -= reserved.get(i, 0)
        value = dict(records[i])
        value['evidence_unit_index'] = i
        text = value.get('observed_text')
        source_key = None
        note = None
        if isinstance(text, str):
            digest = hashlib.sha256(text.encode()).hexdigest()
            value['observed_text_sha256'] = digest
            # Equal bytes alone cannot rebind a page to a different URL. Keep
            # each observation's own ID, time and action even when text repeats.
            if value.get('url') and value.get('observation_id') is not None:
                source_key = (value['url'], digest)
            if source_key is not None and source_key in retained_text:
                value['observed_text'] = {
                    'same_text_as_unit': retained_text[source_key],
                    'source_sha256': digest, 'source_characters': len(text),
                }
            else:
                base = {**value, 'observed_text': None}
                budget = min(limit * 2 // 3, limit - 500 - used - remaining_reserved - len(_encoded(base)) - 1)
                value['observed_text'] = _observed_projection(text, max(0, budget))
                if isinstance(value['observed_text'], dict):
                    projection = value['observed_text']
                    note = {'unit': i, 'field': 'observed_text',
                            'reason': 'observation_ranges_exceed_budget',
                            'source_sha256': digest,
                            'source_characters': len(text),
                            'retained_ranges': [[r['start'],r['end']] for r in projection['ranges']],
                            'omitted_ranges': projection['omitted_ranges']}
        encoded = _encoded(value)
        if used + len(encoded) + 1 > limit - 500 - remaining_reserved:
            omitted.append({'unit': i, 'reason': 'whole_record_exceeds_remaining_budget',
                            'source_record_sha256': hashlib.sha256(
                                json.dumps(records[i], ensure_ascii=False, sort_keys=True).encode()).hexdigest()})
            continue
        used += len(encoded) + 1
        result.append((i, encoded))
        if note is not None:
            omitted.append(note)
        if source_key is not None:
            # References always point to a materialized text/range record,
            # never form chains or refer to an omitted unit.
            retained_text.setdefault(source_key, i)
    lines = [text for _, text in sorted(result)]
    notice = _encoded({'evidence_version': VERSION, 'total_records': len(records),
        'retained_records': len(lines), 'omitted_units_or_fields': len(omitted),
        'notice': 'Missing evidence is not proof of absence. Text references mean identical bytes only; each action keeps its own observation identity. Full records and omitted ranges remain in the evidence manifest.'})
    assert len('\n'.join([notice, *lines])) <= limit
    return [notice, *lines], omitted
