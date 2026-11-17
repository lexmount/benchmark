#!/usr/bin/env python3
"""Recover the one unscored Scholar reference from three independent official sources.

This is a cross-official-source reconstruction, not a successful retry of the
original UI getter. Five fields come from the original Google Scholar profile;
the top paper's identity is checked against Nature, then its PDF link is taken
from a unique HAL DOI record. A HAL-registered link does not prove that its PDF
binary was downloadable. The Actor and original receipt remain unchanged.

Inspected pinned get_info_from_website/get_content_from_vm_file/literal_match:
https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/getters/chrome.py#L46
https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/getters/file.py#L17
https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/general.py#L87
Official HAL search API documents q, fl, wt and DOI lookup:
https://api.hal.science/docs/search
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import importlib
import inspect
import math
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import parse_qs, urlsplit

from repair_pdf_reference import load, read, sha, write_new

ROOT = Path(__file__).resolve().parent
TASK_ID = '5990457f-2adb-467b-a4af-5c857c92d762'
KIND = 'scholar-reference-cross-official-source-v1'
UPSTREAM_COMMIT = '5123bfdbbc34b947bcffcff564abc62d0ab7072d'
PROFILE_URL = 'https://scholar.google.com/citations?user=WLN3QrAAAAAJ&hl=en'
PUBLISHER_URL = 'https://www.nature.com/articles/nature14539'
DOI = '10.1038/nature14539'
SOURCES = ('repair_scholar_reference.py', 'repair_pdf_reference.py')
OPTIONS = {'type': 'list', 'ignore_case': True}
AUTHOR_KEYS = {('lecun', 'yann'), ('bengio', 'yoshua'), ('geoffrey', 'hinton')}


def _author_key(name):
    return tuple(sorted(re.findall(r'[a-z]+', name.lower())))


def _single(nodes, label):
    if len(nodes) != 1:
        raise ValueError('Expected one original source element: ' + label)
    return nodes[0]


def _source(records, key, base):
    record = records[key]
    if (type(record.get('http_status')) is not int or record['http_status'] != 200
            or record.get('verified_tls') is not True):
        raise ValueError('Source needs independently recorded HTTP200/verified TLS: ' + key)
    observed = datetime.fromisoformat(record['observed_at'].replace('Z', '+00:00'))
    if observed.tzinfo is None:
        raise ValueError('Source observation must include a timezone: ' + key)
    path = Path(record['path'])
    if not path.is_absolute():
        path = base / path
    if sha(path) != record['sha256']:
        raise ValueError('Primary source snapshot changed: ' + key)
    final = urlsplit(record.get('final_url', record['url']))
    if final.scheme != 'https':
        raise ValueError('A primary source redirected away from verified HTTPS')
    return record, path.resolve(), final


def expected_from_sources(sources_path):
    """Derive six values exclusively from the retained primary-source snapshots."""
    from lxml import html
    sources_path = Path(sources_path).resolve()
    records = read(sources_path)
    if (records.get('schema_version') != 1 or records.get('task_id') != TASK_ID
            or set(records.get('sources', {})) != {'profile', 'publisher', 'hal_api'}):
        raise ValueError('Expected exactly the three original official-source records')
    records = records['sources']
    profile_record, profile_path, profile_final = _source(records, 'profile', sources_path.parent)
    publisher_record, publisher_path, publisher_final = _source(records, 'publisher', sources_path.parent)
    api_record, api_path, api_final = _source(records, 'hal_api', sources_path.parent)
    if (profile_record['url'] != PROFILE_URL or profile_final.hostname != 'scholar.google.com'
            or profile_final.path != '/citations'
            or parse_qs(profile_final.query).get('user') != ['WLN3QrAAAAAJ']
            or publisher_record['url'] != PUBLISHER_URL
            or publisher_final.hostname != 'www.nature.com' or publisher_final.path != '/articles/nature14539'):
        raise ValueError('Profile ID or publisher source URL changed')
    profile = html.fromstring(profile_path.read_bytes())
    xpaths = ["//*[@id='gsc_prf_in']", "//*[@id='gsc_rsb_st']/tbody/tr[1]/td[2]",
              "//*[@id='gsc_rsb_st']/tbody/tr[2]/td[2]", "//*[@id='gsc_rsb_st']/tbody/tr[3]/td[2]",
              "//*[@id='gsc_a_b']/tr[1]/td[contains(concat(' ',normalize-space(@class),' '),' gsc_a_t ')]/a"]
    expected = [_single(profile.xpath(path), path).text_content().strip() for path in xpaths]
    if expected[0] != 'Yann LeCun' or expected[4] != 'Deep learning' or any(not re.fullmatch(r'\d+', n) for n in expected[1:4]):
        raise ValueError('Original profile identity, counters or first paper are unavailable')
    row = _single(profile.xpath("//*[@id='gsc_a_b']/tr[1]"), 'first paper')
    author_text = _single(row.xpath("./td[contains(@class,'gsc_a_t')]/div[1]"), 'first paper authors').text_content()
    journal = _single(row.xpath("./td[contains(@class,'gsc_a_t')]/div[2]"), 'first paper journal').text_content()
    year = _single(row.xpath("./td[contains(@class,'gsc_a_y')]/span"), 'first paper year').text_content().strip()
    if (re.sub('[^a-z]', '', author_text.lower()) != 'ylecunybengioghinton'
            or re.sub('[^a-z0-9]', '', journal.lower()) != 'nature52175534364442015' or year != '2015'):
        raise ValueError('Scholar first paper is not the independently identified Nature article')
    first_href = _single(row.xpath("./td[contains(@class,'gsc_a_t')]/a"), 'first citation href').get('href')
    if parse_qs(urlsplit(first_href).query).get('user') != ['WLN3QrAAAAAJ']:
        raise ValueError('Scholar first citation belongs to a different profile')
    publisher = html.fromstring(publisher_path.read_bytes())
    def meta(name):
        return publisher.xpath('//meta[@name=$name]/@content', name=name)
    facts = {'citation_title': 'Deep learning', 'citation_journal_title': 'Nature',
        'citation_volume': '521', 'citation_issue': '7553', 'citation_firstpage': '436',
        'citation_lastpage': '444', 'citation_doi': DOI, 'citation_publication_date': '2015/05'}
    if (any(meta(key) != [value] for key, value in facts.items())
            or len(meta('citation_author')) != 3 or {_author_key(n) for n in meta('citation_author')} != AUTHOR_KEYS):
        raise ValueError('Publisher identity/DOI/authors do not agree with the Scholar first paper')
    api_url = urlsplit(api_record['url'])
    query = parse_qs(api_url.query)
    if (api_url.scheme != 'https' or api_url.hostname not in {'api.hal.science', 'api.archives-ouvertes.fr'}
            or api_url.path != '/search/' or api_final.hostname not in {'api.hal.science', 'api.archives-ouvertes.fr'}
            or query.get('q') != ['doiId_s:"' + DOI + '"'] or query.get('wt') != ['json']):
        raise ValueError('HAL lookup must independently query the publisher DOI, not an Actor URL or HAL ID')
    response = read(api_path).get('response', {})
    docs = response.get('docs', [])
    if type(response.get('numFound')) is not int or response['numFound'] != 1 or len(docs) != 1:
        raise ValueError('HAL DOI lookup is absent or ambiguous')
    doc = docs[0]
    if (doc.get('title_s') != ['Deep learning'] or doc.get('doiId_s') != DOI
            or doc.get('producedDateY_i') != 2015 or len(doc.get('authFullName_s', [])) != 3
            or {_author_key(n) for n in doc['authFullName_s']} != AUTHOR_KEYS
            or not re.fullmatch(r'hal-\d+', doc.get('halId_s', ''))):
        raise ValueError('HAL title, DOI, authors or year do not identify the same paper')
    pdf_url = doc.get('fileMain_s')
    uri = doc.get('uri_s')
    if (not isinstance(pdf_url, str) or pdf_url != 'https://hal.science/' + doc['halId_s'] + '/document'
            or not isinstance(uri, str) or uri.rstrip('/').split('/')[-1] not in {doc['halId_s'], doc['halId_s'] + 'v1'}
            or urlsplit(uri).hostname != 'hal.science'):
        raise ValueError('HAL does not register the expected official document link')
    expected.append(pdf_url)
    identity = {'scholar_profile_id': 'WLN3QrAAAAAJ', 'title': expected[4], 'scholar_authors': author_text,
        'scholar_journal': journal, 'year': 2015, 'publisher_doi': DOI,
        'publisher_authors': meta('citation_author'), 'hal_id': doc['halId_s'],
        'hal_authors': doc['authFullName_s'], 'hal_registered_pdf_url': pdf_url,
        'hal_record_uri': uri, 'pdf_binary_verified': False,
        'pdf_validation_status': 'official_api_registered_link_only_binary_not_verified'}
    return expected, identity, {key: {**deepcopy(record), 'path': str(path)}
        for key, record, path in [('profile', profile_record, profile_path),
            ('publisher', publisher_record, publisher_path), ('hal_api', api_record, api_path)]}


def inputs(run_dir):
    run_dir = Path(run_dir).resolve()
    metadata = load(ROOT / 'evaluate.py', 'scholar_recovery_control').verify_run(run_dir)
    if metadata['upstream_commit'] != UPSTREAM_COMMIT:
        raise ValueError('Unsupported upstream revision')
    item = next(t for t in read(Path(metadata['harness_root']) / 'data/manifest.json')['tasks'] if t['task_id'] == TASK_ID)
    task_path = Path(metadata['harness_root']) / item['task_path']
    task = read(task_path)
    evaluator = task['evaluator']
    if (sha(task_path) != item['sha256'] or evaluator['func'] != 'literal_match'
            or evaluator['result'] != {'type': 'content_from_vm_file', 'path': '/home/user/Desktop/researchers.xlsx', 'file_type': 'xlsx', 'file_content': 'last_row'}
            or evaluator['expected']['type'] != 'info_from_website' or evaluator['expected']['url'] != PROFILE_URL
            or evaluator.get('options') != OPTIONS or evaluator.get('postconfig')):
        raise ValueError('Original task/getter/metric/options identity changed')
    original = run_dir / 'tasks' / TASK_ID / 'receipt.json'
    receipt = read(original)
    if (receipt.get('task_id') != TASK_ID or receipt.get('task_sha256') != item['sha256']
            or receipt.get('status') != 'evaluation_error' or receipt.get('score') is not None
            or receipt.get('actor_status') != 'completed' or receipt.get('agent_success') is not True
            or receipt.get('official_terminal_action') != 'DONE' or receipt.get('owned_vm_closed') is not True
            or 'Reference unavailable' not in receipt.get('error', '') or PROFILE_URL not in receipt.get('error', '')):
        raise ValueError('Expected the preserved original cleaned-up unscored Scholar-reference failure')
    actual = original.parent / 'official-cache' / TASK_ID / 'researchers.xlsx'
    binding = {'kind': 'retained_original_result_getter_cache_reparsed_with_original_pandas_semantics',
        'original_actual': str(actual), 'actual_sha256': sha(actual), 'actual_bytes': actual.stat().st_size}
    return metadata, task, original, actual, binding


def actual_last_row(path):
    # These are the pinned get_content_from_vm_file lines 28-30, using its
    # already-retained original XLSX. No VM/file download is repeated.
    import pandas as pd
    df = pd.read_excel(path)
    return df.iloc[-1].astype(str).tolist()


def _metric(metadata):
    sys.path.insert(0, metadata['osworld_root'])
    metric = importlib.import_module('desktop_env.evaluators.metrics.general').literal_match
    path = Path(metadata['osworld_root']) / 'desktop_env/evaluators/metrics/general.py'
    if Path(inspect.getsourcefile(metric)).resolve() != path.resolve():
        raise ValueError('Comparison must come from the original frozen checkout')
    return metric, path


def repair(run_dir, sources_path, output):
    run_dir, sources_path, output = [Path(p).resolve() for p in (run_dir, sources_path, output)]
    metadata, task, original, actual, binding = inputs(run_dir)
    original_sha = sha(original)
    expected, identity, source_records = expected_from_sources(sources_path)
    last_row = actual_last_row(actual)
    metric, metric_path = _metric(metadata)
    metric_sha = sha(metric_path)
    score = metric(last_row, expected, **deepcopy(task['evaluator']['options']))
    if type(score) not in (float, int) or not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError('Original literal_match returned an invalid score')
    _, _, checked_original, _, checked_binding = inputs(run_dir)
    if checked_binding != binding or sha(checked_original) != original_sha or sha(metric_path) != metric_sha:
        raise ValueError('Original evidence or comparison changed during recovery')
    output.mkdir(parents=True, exist_ok=False)
    copied = {}
    for key, record in source_records.items():
        name = {'profile': 'scholar-profile.html', 'publisher': 'nature-article.html', 'hal_api': 'hal-doi-query.json'}[key]
        shutil.copyfile(record['path'], output / name)
        copied[key] = {**deepcopy(record), 'path': name, 'original_snapshot_path': record['path']}
    write_new(output / 'primary-sources.json', {'schema_version': 1, 'task_id': TASK_ID, 'sources': copied})
    write_new(output / 'expected.json', expected)
    write_new(output / 'actual-last-row.json', last_row)
    for name in SOURCES:
        shutil.copyfile(ROOT / name, output / name)
    record = {'schema_version': 1, 'kind': KIND, 'task_id': TASK_ID, 'run_dir': str(run_dir),
        'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'corrected',
        'original_status': 'evaluation_error', 'original_score': None, 'score': float(score),
        'model_calls': 0, 'vm_starts': 0, 'online_requests': 0, 'actor_rerun': False,
        'getter_replayed': False, 'original_ui_reference_getter_succeeded': False,
        'input_kind': binding['kind'], 'reference_kind': 'cross_official_source_reconstruction',
        'pdf_binary_verified': False, 'pdf_validation_status': identity['pdf_validation_status'],
        'identity': identity, 'actual_source': binding, 'options': deepcopy(task['evaluator']['options']),
        'metric': 'literal_match', 'metric_source_sha256': metric_sha,
        'file_getter_source_sha256': sha(Path(metadata['osworld_root']) / 'desktop_env/evaluators/getters/file.py'),
        'run_metadata_sha256': sha(run_dir / 'run.json'), 'task_sha256': read(original)['task_sha256'],
        'original_receipt': str(original), 'original_receipt_sha256': original_sha,
        'primary_sources': str(output / 'primary-sources.json'), 'primary_sources_sha256': sha(output / 'primary-sources.json'),
        'expected': str(output / 'expected.json'), 'expected_sha256': sha(output / 'expected.json'),
        'actual_last_row': str(output / 'actual-last-row.json'), 'actual_last_row_sha256': sha(output / 'actual-last-row.json'),
        'repair_sources_sha256': {name: sha(output / name) for name in SOURCES}, 'evidence_errors': [],
        'boundary': 'Reconstructs five fields from a later original Google Scholar profile snapshot and the PDF field from an independently DOI-queried HAL record matched to the Nature publisher. Original UI getter failure and original null score remain. The registered PDF link binary was not verified. No Actor output or static backup supplied reference values.'}
    write_new(output / 'correction.json', record)
    return record


def verify_correction(run_dir, path):
    run_dir, path = Path(run_dir).resolve(), Path(path).resolve()
    record = read(path)
    if (record.get('schema_version') != 1 or record.get('kind') != KIND or record.get('task_id') != TASK_ID
            or record.get('status') != 'corrected' or Path(record['run_dir']).resolve() != run_dir
            or record.get('original_score') is not None or record.get('original_status') != 'evaluation_error'
            or any(type(record.get(k)) is not int or record[k] != 0 for k in ('model_calls', 'vm_starts', 'online_requests'))
            or record.get('actor_rerun') is not False or record.get('getter_replayed') is not False
            or record.get('original_ui_reference_getter_succeeded') is not False
            or record.get('reference_kind') != 'cross_official_source_reconstruction'
            or record.get('pdf_binary_verified') is not False or record.get('evidence_errors')
            or sha(run_dir / 'run.json') != record.get('run_metadata_sha256')):
        raise ValueError('Invalid Scholar recovery identity or source boundary')
    metadata, task, original, actual, binding = inputs(run_dir)
    expected, identity, _ = expected_from_sources(record['primary_sources'])
    if (record.get('original_receipt') != str(original) or record.get('original_receipt_sha256') != sha(original)
            or record.get('task_sha256') != read(original)['task_sha256'] or record.get('actual_source') != binding
            or record.get('input_kind') != binding['kind'] or record.get('identity') != identity
            or record.get('options') != task['evaluator']['options'] or record.get('metric') != 'literal_match'
            or record.get('pdf_validation_status') != identity['pdf_validation_status']):
        raise ValueError('Original task, result cache or reference identity changed')
    for key, filename in [('primary_sources', 'primary-sources.json'), ('expected', 'expected.json'), ('actual_last_row', 'actual-last-row.json')]:
        if Path(record[key]).resolve() != path.parent / filename or sha(record[key]) != record[key + '_sha256']:
            raise ValueError('Archived source/reference projection changed: ' + key)
    last_row = actual_last_row(actual)
    if read(record['expected']) != expected or read(record['actual_last_row']) != last_row:
        raise ValueError('Expected or actual values do not derive from their archived sources')
    if set(record.get('repair_sources_sha256', {})) != set(SOURCES):
        raise ValueError('Recovery source inventory changed')
    for name, checksum in record['repair_sources_sha256'].items():
        if sha(path.parent / name) != checksum:
            raise ValueError('Archived recovery source changed')
    metric, metric_path = _metric(metadata)
    if (sha(metric_path) != record['metric_source_sha256']
            or sha(Path(metadata['osworld_root']) / 'desktop_env/evaluators/getters/file.py') != record['file_getter_source_sha256']):
        raise ValueError('Original comparison or result-file parser source changed')
    value = metric(last_row, expected, **deepcopy(record['options']))
    if type(record.get('score')) not in (int, float) or not math.isfinite(record['score']) or record['score'] != value or not 0 <= value <= 1:
        raise ValueError('Recovery score does not match the unchanged original comparison')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(__import__('json').dumps(repair(args.run_dir, args.sources, args.output), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
