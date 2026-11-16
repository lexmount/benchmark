import ast
import asyncio
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import dataset
import evaluate
import runtime

PACKAGE = Path(__file__).resolve().parents[1]


def test_exact_168_and_original_content():
    rows = dataset.load_rows()
    manifest = evaluate.read(PACKAGE / 'data/manifest.json')
    exclusions = evaluate.read(PACKAGE / 'data/exclusions.json')['rows']
    assert len(rows) == 168 and len(exclusions) == 32
    assert len({r['task_id'] for r in rows} | {r['task_id'] for r in exclusions}) == 200
    assert manifest['retained_rows_equal_original'] and manifest['retained_instructions_equal_report']
    # Mixed-cause tasks were not silently excluded along with the approved 32.
    assert {97, 100, 118, 136, 199} <= {r['original_ordinal'] for r in manifest['tasks']}
    assert {k for r in rows for k in r} == {'task_id', 'confirmed_task', 'website', 'reference_length', 'level', 'rubrics', 'categories', 'num_categories'}


def test_original_execution_functions_except_one_count_assertion():
    tree, audit = runtime._extracted_module()
    assert {k for k, v in audit['functions'].items() if not v['unchanged']} == {'run'}
    change, = audit['approved_ast_changes']
    assert (change['before'], change['after']) == (600, 168)
    original = ast.parse((PACKAGE / 'legacy/driver.py.txt').read_text())
    old = next(n for n in original.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'run')
    new = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'run')
    restored = deepcopy(new)
    comparison, = [n for n in ast.walk(restored) if isinstance(n, ast.Compare) and ast.unparse(n.left) == "len(plan['jobs'])"]
    comparison.comparators[0].value = 600
    assert ast.dump(old, include_attributes=False) == ast.dump(restored, include_attributes=False)


def test_original_sources_and_policy():
    provenance = evaluate.read(PACKAGE / 'provenance.json')
    for name, expected in provenance['original_files_sha256'].items():
        assert dataset.sha(PACKAGE / name) == expected
    tree = ast.parse((PACKAGE / 'legacy/actor.py').read_text())
    policy = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'policy' for t in n.targets))
    assert hashlib.sha256(policy.encode()).hexdigest() == provenance['actor_policy_sha256']
    assert 'rubrics' not in ast.unparse(next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'main'))
    assert evaluate.read(PACKAGE / 'config.json')['fixed_viewport'] is False
    assert evaluate.verify(quiet=True)['tasks'] == 168


@pytest.fixture
def bound(tmp_path):
    from legacy.environment_bindings import install
    support = tmp_path / 'support'; support.mkdir()
    full = install(tmp_path, support, PACKAGE / 'legacy/code', '/usr/bin/python3')
    evaluate.write(support / '.private/model.json', {'model': 'deepseek-v4.1-flash', 'api_key': 'offline-test', 'base_url': 'https://offline.invalid/v1'})
    return full, support


def test_path_binding_preserves_function_bodies(bound):
    full, support = bound
    assert Path(full.worker_impl.__code__.co_filename) == PACKAGE / 'legacy/code/full_benchmarks.py'
    assert Path(full.judge_model.__code__.co_filename) == PACKAGE / 'legacy/code/full_benchmarks.py'
    assert Path(full.judge.__code__.co_filename) == PACKAGE / 'legacy/code/full_benchmarks.py'
    assert full.OD == PACKAGE / 'legacy/upstream'
    full.verify()


def test_actual_original_odysseys_judge_payload_offline(bound, tmp_path, monkeypatch):
    import openai
    from openai.types.chat import ChatCompletion
    full, support = bound
    folder = tmp_path / 'runs' / ('f' * 40)
    (folder / 'agent').mkdir(parents=True)
    code, observed = "print('observed')", 'actual observed text\n' * 5000
    messages = [{'parts': [{'part_kind': 'tool-call', 'tool_name': 'python', 'tool_call_id': 'call-1', 'args': {'code': code}}]},
                {'parts': [{'part_kind': 'tool-return', 'tool_name': 'python', 'tool_call_id': 'call-1', 'content': [observed]}]}]
    evaluate.write(folder / 'agent/messages.json', messages)
    evaluate.write(folder / 'frames.json', [{'step_num': 1, 'action': 'python ' + code, 'response': observed, 'screenshot_file': None}])
    (folder / 'final_response.txt').write_text('final answer')
    rubrics = [{'id': 'R1', 'requirement': 'First exact requirement', 'verification': 'First exact verification'},
               {'id': 'R2', 'requirement': 'Second exact requirement', 'verification': 'Second exact verification'}]
    task = {'id': folder.name, 'instruction': 'Original task text.', 'rubrics': rubrics}
    requests = []
    class OfflineClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        async def create(self, **kwargs):
            requests.append(kwargs)
            text = 'Thoughts: Evidence inspected.\nStatus: "' + ('success' if len(requests) == 1 else 'failure') + '"'
            return ChatCompletion.model_validate({'id': 'offline', 'object': 'chat.completion', 'created': 0,
                'model': kwargs['model'], 'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': text}}]})
    monkeypatch.setattr(openai, 'AsyncOpenAI', OfflineClient)
    result = asyncio.run(full.judge_model(folder, 'odysseys', task, tmp_path / 'judge' / folder.name))
    assert result['status'] == 'judged' and result['rubric_scores'] == {'R1': 1, 'R2': 0}
    assert result['average_rubric_score'] == 0.5 and result['perfect'] is False
    assert len(requests) == 2
    for request, rubric in zip(requests, rubrics):
        assert (request['model'], request['reasoning_effort'], request['max_tokens']) == ('deepseek-v4.1-flash', 'low', 16384)
        text = request['messages'][1]['content'][0]['text']
        assert rubric['requirement'] in text and rubric['verification'] in text
        assert observed.strip() in text and 'final answer' in text
        assert 'If the agent was blocked' in request['messages'][0]['content']


@pytest.mark.parametrize('refusal', [False, True])
def test_refusal_fallback_is_not_used_for_valid_zero(bound, tmp_path, monkeypatch, refusal):
    full, _ = bound
    folder = tmp_path / 'source'; folder.mkdir()
    task = {'id': 'd' * 40, 'rubrics': [{'id': 'R1'}]}
    calls = []
    async def fake(folder, suite, task, destination, *, model_name='deepseek-v4.1-flash'):
        calls.append(model_name)
        reason = 'Error judging rubric R1: data_inspection_failed' if refusal and len(calls) == 1 else 'ordinary failure' if not refusal else 'verified success'
        value = 0 if len(calls) == 1 else 1
        result = {'status': 'judge_error' if reason.startswith('Error') else 'judged', 'rubric_scores': {'R1': value},
                  'rubric_results': [{'rubric_id': 'R1', 'score': value, 'final_reasoning': reason}],
                  'average_rubric_score': value, 'perfect': bool(value), 'judge_http_requests': 0}
        evaluate.write(destination / 'judge-odysseys.json', result)
        return result
    monkeypatch.setattr(full, 'judge_model', fake)
    result = asyncio.run(full.judge(folder, 'odysseys', task, tmp_path / 'destination'))
    assert calls == (['deepseek-v4.1-flash', 'gpt-6.1-sol'] if refusal else ['deepseek-v4.1-flash'])
    assert result['rubric_scores']['R1'] == int(refusal)


def test_summary_keeps_unknown_in_168_denominator(tmp_path, monkeypatch):
    rows = dataset.tasks()
    jobs = [{'task_id': t['id'], 'ordinal': i, 'judge_folder': str(tmp_path / 'judges' / t['id'])}
            for i, t in enumerate(rows, 1)]
    monkeypatch.setattr(evaluate, 'preflight_run', lambda run: {'jobs': jobs})
    for i, task in enumerate(rows[:3]):
        values = {r['id']: (1 if i == 0 else 0) for r in task['rubrics']}
        if i == 2:
            values.pop(next(iter(values)))  # A missing rubric is unknown, not a valid zero.
        evaluate.write(Path(jobs[i]['judge_folder']) / 'judge-odysseys.json', {'status': 'judged', 'rubric_scores': values})
    report = evaluate.summarize(tmp_path)
    assert (report['passed_at_0_5'], report['failed_below_0_5'], report['unknown']) == (1, 1, 166)
    assert report['task_success_rate_over_168'] == 1 / 168 and not report['complete']
