"""User-authorized judge-only fallback. Original actor, evidence and grades remain immutable.

Reuses the existing judge adapter function; the sole internal change selects gpt-6.1-sol.
The caller passes only refused rubric IDs to the unchanged official evaluator.
"""
from __future__ import annotations
import asyncio, copy, hashlib, json, time
from pathlib import Path
from continue_evaluate import ROOT, BU, OD, read, write, digest, verify, module_at, tasks


def deduplicate_exact_images(kwargs):
    """Preserve every distinct original image, first-occurrence order and a complete ordinal mapping."""
    manifests=[]
    for message in kwargs.get('messages',[]):
        content=message.get('content')
        if not isinstance(content,list):
            continue
        original=[part for part in content if part.get('type')=='image_url']
        if not original:
            continue
        assert len({json.dumps({k:v for k,v in part['image_url'].items() if k!='url'},sort_keys=True)
                    for part in original})==1, 'Mixed image detail settings cannot be silently deduplicated'
        unique=[]; seen={}; mapping=[]
        for part in original:
            identity=part['image_url']['url']
            if identity not in seen:
                seen[identity]=len(unique)+1
                unique.append(part)
            mapping.append(seen[identity])
        assert [unique[i-1] for i in mapping]==original, 'Image mapping must reconstruct the original blocks exactly'
        assert len(unique)<=50, 'The gateway still cannot carry every distinct image; no sampling is allowed'
        texts=[part for part in content if part.get('type')!='image_url']
        assert texts and texts[0].get('type')=='text'
        assert content==texts+original, 'Unexpected interleaved official judge input'
        old_count=f'Screenshots attached below: {len(original)} '
        new_count=f'Screenshots attached below: {len(unique)} distinct original images '
        assert old_count in texts[0]['text']
        original_text=texts[0]['text']
        note=('\n\nImage transport note: this gateway accepts at most 50 images. Byte-identical images '
              'are attached once in first-occurrence order. No screenshot was resized, cropped or sampled out. '
              'For each ORIGINAL chronological screenshot ordinal, the following list gives its ATTACHED '
              'distinct-image ordinal (1-based): '+json.dumps(mapping)+'.')
        texts[0]['text']=original_text.replace(old_count,new_count,1)+note
        message['content']=texts+unique
        manifests.append({'original_image_blocks':len(original),'actual_distinct_image_blocks':len(unique),
            'original_to_attached_ordinal':mapping,
            'distinct_data_url_sha256':[hashlib.sha256(part['image_url']['url'].encode()).hexdigest() for part in unique],
            'original_judge_text_sha256':hashlib.sha256(original_text.encode()).hexdigest(),
            'transport_judge_text_sha256':hashlib.sha256(texts[0]['text'].encode()).hexdigest(),
            'complete_reconstruction_verified':True,'image_bytes_changed':False,
            'image_detail_settings_changed':False,'action_history_changed':False})
    return manifests

async def judge(folder, suite, task, destination):
    """Rejudge immutable execution evidence; each protocol owns a new destination."""
    verify()
    from evidence_adapter import prepare, verify_originals
    from evidence_ranges import VERSION
    import httpx
    from openai import AsyncOpenAI, APIConnectionError, APIStatusError
    from openai.types.chat import ChatCompletion
    from types import SimpleNamespace
    import copy, re

    destination.mkdir(parents=True, exist_ok=True)
    grade_file = destination / ("judge-" + suite + ".json")
    if grade_file.exists() and read(grade_file).get("status") == "judged":
        existing = read(grade_file)
        assert existing["reasoning_effort"] == "low" and existing["evidence_version"] == VERSION
        verify_originals(read(destination / "evidence-manifest.json"))
        return existing
    trace, evidence = prepare(folder, suite, destination)
    cfg = read(ROOT / ".private/model.json")
    cfg = dict(cfg, model="gpt-6.1-sol")  # user-authorized fallback for refused rubric judgements only
    calls = len(list((destination / "model_calls").glob("*.request.json")))
    official = module_at("official_" + suite, BU / "judge.py" if suite == "bu_v1" else OD / "scripts/python/run_full_trajectory_per_rubric.py")

    async def request(req):
        nonlocal calls
        calls += 1
        req.extensions["receipt"] = calls
        req.extensions["started"] = time.monotonic()
        write(destination / "model_calls" / f"{calls:04d}.request.json", json.loads(req.content))

    async def response(resp):
        body = await resp.aread()
        try:
            value = json.loads(body)
        except ValueError:
            value = {"unparsed_response": body.decode(errors="replace")}
        number = resp.request.extensions["receipt"]
        write(destination / "model_calls" / f"{number:04d}.response.json", value)
        write(destination / "model_calls" / f"{number:04d}.transport.json",
              {"status": resp.status_code, "seconds": time.monotonic() - resp.request.extensions["started"]})

    def validate(response):
        if not response.choices or response.choices[0].finish_reason != "stop":
            raise ValueError("Judge response is incomplete")
        text = response.choices[0].message.content or ""
        if suite == "bu_v1":
            official.JudgementResult.model_validate_json(text)
        elif not re.search(r"Thoughts:\s*\S", text) or not re.search(r"Status:\s*[\"']?(success|failure)[\"']?", text, re.I):
            raise ValueError("Judge response has no valid Thoughts/Status verdict")

    async with httpx.AsyncClient(timeout=600, event_hooks={"request": [request], "response": [response]}) as http:
        client = AsyncOpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"], http_client=http, max_retries=2, timeout=600)

        async def create(**kwargs):
            kwargs = copy.deepcopy(kwargs)
            transport = deduplicate_exact_images(kwargs)
            transport_path = destination / 'image_transport' / (transport[0]['original_judge_text_sha256'] + '.json')
            if transport_path.exists():
                assert read(transport_path) == transport
            else:
                write(transport_path, transport)
            kwargs["reasoning_effort"] = "low"
            kwargs["extra_body"] = {"allowed_openai_params": ["reasoning_effort"]}
            kwargs.pop("max_tokens", None)
            kwargs["max_completion_tokens"] = 16384
            key = hashlib.sha256(json.dumps(kwargs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            cache = destination / "validated_responses" / (key + ".json")
            attempts_path = destination / "attempts" / (key + ".json")
            if cache.exists():
                result = ChatCompletion.model_validate(read(cache))
                validate(result)
                return result
            attempts = read(attempts_path) if attempts_path.exists() else []
            if len(attempts) >= 2:
                raise RuntimeError("Identical judge request already exhausted its two permitted attempts")
            while len(attempts) < 2:
                row = {"request_sha256": key, "attempt": len(attempts) + 1, "started_at": time.time()}
                attempts.append(row)
                write(attempts_path, attempts)
                try:
                    result = await client.chat.completions.create(**kwargs)
                    validate(result)
                    row.update(status="valid", ended_at=time.time())
                    write(attempts_path, attempts)
                    write(cache, result.model_dump(mode="json"))
                    return result
                except Exception as exc:
                    row.update(status="invalid_or_transport_error", error_type=type(exc).__name__, ended_at=time.time())
                    write(attempts_path, attempts)
                    retryable = isinstance(exc, (ValueError, APIConnectionError)) or (
                        isinstance(exc, APIStatusError) and (exc.status_code == 429 or exc.status_code >= 500)
                    )
                    if not retryable or len(attempts) >= 2:
                        raise
                    await asyncio.sleep(300 if isinstance(exc, (APIConnectionError, APIStatusError)) else 1)
            raise RuntimeError("Judge attempt budget exhausted")

        try:
            if suite == "bu_v1":
                messages = official.construct_judge_messages(
                    task=task["instruction"], ground_truth=task.get("answer"), **trace)
                response = await create(model=cfg["model"], max_tokens=8192,
                    messages=[m.model_dump(exclude_none=True) for m in messages],
                    response_format={"type": "json_object"})
                verdict = official.JudgementResult.model_validate_json(response.choices[0].message.content)
                result = {"status": "judged", "score": int(verdict.verdict), "judgement": verdict.model_dump()}
            else:
                proxy = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
                result = await official.evaluate_run(
                    destination, proxy, "openai", cfg["model"],
                    {task["id"]: {"task": task["instruction"], "rubrics": task["rubrics"]}},
                    max_images=0, max_steps=None)
                bad = (result.get("error") and result["error"] != "Empty trajectory - no steps recorded.") or any(
                    r["final_reasoning"].startswith("Error judging rubric") for r in result.get("rubric_results", []))
                result["status"] = "judge_error" if bad else "judged"
            verify_originals(evidence)
            result.update(
                judge_model=cfg["model"], reasoning_effort="low", evidence_version=VERSION,
                source_folder=str(folder), official_sources=read(ROOT / "sources.json"),
                reference_judge_model_changed=True, judge_http_requests=calls,
            )
        except Exception as exc:
            result = {
                "status": "judge_error", "error": str(exc).replace(cfg["api_key"], "[REDACTED]"),
                "judge_model": cfg["model"], "reasoning_effort": "low", "evidence_version": VERSION,
                "source_folder": str(folder), "judge_http_requests": calls,
            }
        write(grade_file, result)
        return result



async def main():
    root=ROOT/'final-candidate'
    destination=root/'refusal-fallback-gpt-6.1-sol-dedup'
    destination.mkdir(exist_ok=True)
    jobs=read(root/'plan.json')['jobs']
    lookup={t['id']:t for t in tasks('odysseys')}
    selected=[]
    for job in jobs:
        grade_path=Path(job['judge_folder'])/('judge-'+job['suite']+'.json')
        if not grade_path.exists():
            continue
        grade=read(grade_path)
        refused=[r['rubric_id'] for r in grade.get('rubric_results',[])
                 if r.get('final_reasoning','').startswith('Error judging rubric')
                 and ('inappropriate content' in r['final_reasoning'].lower()
                      or 'data_inspection_failed' in r['final_reasoning'].lower())]
        if refused:
            assert job['suite']=='odysseys'
            selected.append({'case_number':job['case_number'],'suite':job['suite'],'id':job['id'],
                'source_folder':job['source_folder'],'original_grade_path':str(grade_path),
                'original_grade_sha256':digest(grade_path),'refused_rubric_ids':refused,
                'fallback_destination':str(destination/job['id'])})
    assert {j['case_number']:j['refused_rubric_ids'] for j in selected}=={
        80:['R1','R2','R3','R4','R5'],88:['R1','R3','R4','R6']},selected
    protocol={'authorized_at':'2026-11-14 user message: content refusals use gpt-6.1-sol',
        'judge_model':'gpt-6.1-sol','reasoning_effort':'low','actor_reruns':0,
        'selection':'Only explicit content-inspection refusal rubric errors; legal existing verdicts preserved',
        'maximum_simultaneous_fallback_judges':2,'normal_failures_not_rejudged':True,
        'original_files_not_overwritten':True,'image_transport':'exact byte-identical dedup; all distinct screenshots preserved with complete original ordinal map','script_sha256':digest(Path(__file__))}
    selection={'protocol':protocol,'jobs':selected}
    selection_path=destination/'selection.json'
    if selection_path.exists():
        assert read(selection_path)==selection
    else:
        write(selection_path,selection)
    async def one(job):
        task=copy.deepcopy(lookup[job['id']])
        task['rubrics']=[r for r in task['rubrics'] if r['id'] in job['refused_rubric_ids']]
        assert len(task['rubrics'])==len(job['refused_rubric_ids'])
        return await judge(Path(job['source_folder']),job['suite'],task,Path(job['fallback_destination']))
    results=await asyncio.gather(*(one(j) for j in selected))
    overlays=[]
    for job,fallback in zip(selected,results):
        assert digest(job['original_grade_path'])==job['original_grade_sha256']
        original=read(job['original_grade_path'])
        merged=copy.deepcopy(original)
        replacements={r['rubric_id']:r for r in fallback.get('rubric_results',[])
                      if not r.get('final_reasoning','').startswith('Error judging rubric')}
        assert set(replacements)<=set(job['refused_rubric_ids'])
        for i,item in enumerate(merged.get('rubric_results',[])):
            rid=item['rubric_id']
            if rid in replacements:
                merged['rubric_results'][i]=dict(replacements[rid],judge_model='gpt-6.1-sol',
                    original_refusal_preserved_at=job['original_grade_path'])
                merged['rubric_scores'][rid]=replacements[rid]['score']
        remaining=[r['rubric_id'] for r in merged.get('rubric_results',[])
                   if r.get('final_reasoning','').startswith('Error judging rubric')]
        merged['status']='judge_error' if remaining else 'judged'
        merged['judge_model']='mixed: deepseek-v4.1-flash + gpt-6.1-sol (refused rubrics only)'
        merged['perfect']=bool(merged['rubric_scores']) and not remaining and all(v==1 for v in merged['rubric_scores'].values())
        for field in ['score','success_rate','mean_score','overall_score']:
            if field in merged:
                merged.pop(field)  # do not retain a stale aggregate; analysis derives task mean from all rubric labels
        merged.update(original_grade_path=job['original_grade_path'],
            original_grade_sha256=job['original_grade_sha256'],
            fallback_grade_path=str(Path(job['fallback_destination'])/'judge-odysseys.json'),
            fallback_model='gpt-6.1-sol',fallback_rubric_ids=sorted(replacements),
            remaining_unknown_rubric_ids=remaining)
        merged_path=destination/job['id']/'merged-grade.json'
        write(merged_path,merged)
        overlays.append({'suite':job['suite'],'id':job['id'],'case_number':job['case_number'],
                         'grade_path':str(merged_path),'sha256':digest(merged_path)})
    write(destination/'grade-overlay.json',{'protocol':protocol,'grades':overlays})
    write(destination/'complete.json',{'finished_at':time.time(),'cases':len(selected),
          'valid_replacement_rubrics':sum(len(r.get('rubric_results',[])) for r in results
              if r.get('status')=='judged'),
          'fallback_statuses':[r.get('status') for r in results]})
    print(json.dumps({'cases':len(selected),'fallback_statuses':[r.get('status') for r in results]}),flush=True)

if __name__=='__main__':
    asyncio.run(main())
