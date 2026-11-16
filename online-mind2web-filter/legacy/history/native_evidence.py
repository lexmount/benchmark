"""Reuse pinned native builders; only JSONL physical framing is adapted to LF."""
from pathlib import Path
import ast,base64,hashlib,importlib.util,io,json,os,sys,types
N=Path(__file__).resolve().parents[1];J=N/'judge-common';U=J/'upstream'
def rd(p,default=None):return json.loads(Path(p).read_text())if Path(p).exists()else default
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,value):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def lf_calls(folder,since=''):
 p=Path(folder)/'model_calls.jsonl';latest={}
 if not p.exists():return {'calls':[],'legacy':False}
 with p.open()as f:
  for line in f:
   if not line.strip():continue
   x=json.loads(line);latest[x['id']]=x
 return {'calls':sorted(latest.values(),key=lambda x:x['started_elapsed_ms']),'legacy':False}
def extracted(path,names,*,base=None,lf_import=False):
 tree=ast.parse(Path(path).read_text(encoding='utf-8-sig'));nodes=[x for x in tree.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))and x.name in names]
 assert {x.name for x in nodes}==set(names)
 if lf_import:
  class LF(ast.NodeTransformer):
   def visit_ImportFrom(self,node):
    if node.module=='lexmount_browser_agent.execution.diagnostics'and any(a.name=='read_calls'for a in node.names):return ast.Assign(targets=[ast.Name(id='read_calls',ctx=ast.Store())],value=ast.Name(id='lf_calls',ctx=ast.Load()))
    return node
  nodes=[LF().visit(x)for x in nodes]
 scope=dict(Path=Path,json=json,base64=base64,hashlib=hashlib,io=io,os=os,read=rd,write=write,lf_calls=lf_calls,BASE=base,MAX_THOUGHT_CHARS=600,MAX_ACTION_CHARS=300)
 exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(path),'exec'),scope)
 return types.SimpleNamespace(**scope)
BU=extracted(U/'bu/adapter.py',['tasks','make_trace'],base=U/'bu')
BU_JUDGE=load('native_bu_judge',U/'bu/upstream/judge.py')
# The actual historical harness installed one of these versioned range projections.
# Reuse its exact make_trace/units/bounded_units; no hand-built approximation.
sys.path.insert(0,str(N/'runtime/origin/bundle/frozen/src'))
BU_PROJECTIONS={}
for family in ['prototype','formal']:
 evidence=load('native_bu_evidence_'+family,U/'bu'/('evidence-'+family+'.py'))
 original_validator=evidence.validated_frames
 def compatible_frames(folder,original_validator=original_validator):
  original=rd(Path(folder)/'frames.json',[]);validated=original_validator(folder)
  for before,after in zip(original,validated):
   if before.get('screenshot_source')!='harness_verified_skyvern_selected_target'or not before.get('screenshot'):continue
   image=(Path(folder)/before['screenshot']).resolve()
   okay=image.is_relative_to((Path(folder)/'screenshots').resolve())and image.is_file()and sha(image)==before.get('screenshot_sha256')and bool(before.get('target_id'))
   if okay:
    # Preserve the real source string. This is an explicit extra validated source,
    # not relabeling the image as a legacy observation or mutating frames.json.
    after.clear();after.update(before)
   else:after.update(screenshot=None,capture_missing_reason='MCP_source_path_hash_or_target_invalid')
  return validated
 evidence.validated_frames=compatible_frames
 adapter=types.SimpleNamespace(environment=lambda:None,evidence_module=lambda:None)
 evidence.install(adapter);BU_PROJECTIONS[family]=(evidence,adapter)

OM_RECORD=extracted(U/'om/adapter.py',['make_record'],lf_import=True)
OM=extracted(U/'om/onlinemind2web_judge.py',['format_action','_clip','_call_step','_ace_steps','_dom_steps','build_trajectory','last_shot_message','parse_verdict'])
PROMPT=load('native_om_prompt',U/'om/evaluation_prompt.py')
assert hashlib.sha256(PROMPT.SYSTEM_PROMPT.encode()).hexdigest()=='6906e021cb15a3398225fe82232ea5ee61b1cb7489c0bbbd9be4ad82f2000ca9'
def image_proof(folder):
 frames=rd(Path(folder)/'frames.json',[]);proof=[]
 for x in frames:
  rel=x.get('screenshot')
  if not rel:continue
  p=(Path(folder)/rel).resolve();assert p.is_relative_to(Path(folder).resolve())and p.is_file(),'Missing/outside-run original PNG'
  digest=sha(p)
  if x.get('screenshot_sha256'):assert digest==x['screenshot_sha256'],'Original PNG changed'
  proof.append({'step_num':x['step_num'],'path':str(p),'sha256':digest,'target_id':x.get('target_id'),'capture_partial':x.get('capture_partial')})
 return proof
def build_payload(task,folder):
 folder=Path(folder);execution=rd(folder/'execution.json',{});raw=rd(folder/'agent/raw_state.json',{})
 error=execution.get('error')or{}
 if execution.get('status')=='failed'and error.get('stage')=='initializing'and raw.get('history')==[]and not any((folder/'agent').glob('wire-*.request.json'))and not any(x.strip()for x in ((folder/'agent/requests.jsonl').read_text().split('\n')if(folder/'agent/requests.jsonl').exists()else[])):
  return None,{'suite':task['suite'],'task_id':task['task_id'],'native_zero_or_skip':'infra','score':None,'initialization_environment_invalid':True,'real_POSTs':0}
 proof=image_proof(folder);suite=task['suite'];receipt={'suite':suite,'task_id':task['task_id'],'original_frame_images':proof,'protocol':'BU-V1-native-binary'if suite=='bu_bench_v1'else'AgentTrek_eval-native','LF_JSONL_only':True,'no_new_solver_calls':True}
 if suite=='bu_bench_v1':
  original=next(x for x in BU.tasks()if str(x['task_id'])==task['task_id']);assert original['confirmed_task']==task['instruction']
  family='formal'if task['baseline']['agent_commit'].startswith('caa7bed')else'prototype'
  evidence,adapter=BU_PROJECTIONS[family];trace=adapter.make_trace(folder)
  if proof and not trace['screenshots_b64']:raise ValueError('Native BU projection dropped all available original PNGs')
  messages=[m.model_dump(exclude_none=True)for m in BU_JUDGE.construct_judge_messages(task=task['instruction'],final_result=trace['final_result'],agent_steps=trace['agent_steps'],screenshots_b64=trace['screenshots_b64'],ground_truth=original.get('answer'))]
  schema=BU_JUDGE.JudgementResult.model_json_schema()
  messages[0]['content']+='\n\nReturn one JSON object conforming to this exact output schema:\n'+json.dumps(schema,ensure_ascii=False,sort_keys=True)
  payload={'messages':messages,'response_format':{'type':'json_object'}}
  receipt.update(native_source='upstream/bu/upstream/judge.py::construct_judge_messages',evidence_builder='upstream/bu/evidence-'+family+'.py::install.make_trace',range_projection_version=evidence.VERSION,range_limit=39000,new_validated_source='harness_verified_skyvern_selected_target (preserved; path/hash/target checked)',text_caps={'task':40000,'final_result':40000,'steps':40000},image_policy='last10 unique base64, chronology restored',original_trace_images=len(trace['screenshots_b64']),schema_sha256=hashlib.sha256(json.dumps(schema,ensure_ascii=False,sort_keys=True).encode()).hexdigest())
 else:
  original={'task_id':task['task_id'],'task_name':task['instruction'],'website':task['start_url']}
  record=OM_RECORD.make_record(folder,original)
  calls=lf_calls(folder/'agent')['calls'];expected=sum(x.get('stage')=='generation'and x.get('status')=='succeeded'and isinstance(x.get('output'),dict)and bool(x['output'].get('choices'))for x in calls)
  assert len(record['prompt_calls'])==expected,'Generation calls silently lost during projection'
  trajectory,source,n=OM.build_trajectory(record,folder);shot=OM.last_shot_message(folder)
  receipt.update(n_steps=n,record_bucket=record['bucket'],trajectory_source=source,thought_limit=600,action_limit=300,final_answer_appended=False,system_prompt_sha256=hashlib.sha256(PROMPT.SYSTEM_PROMPT.encode()).hexdigest(),generation_calls=expected)
  if record['bucket']=='infra':return None,{**receipt,'native_zero_or_skip':'infra','score':None}
  if not n or shot is None:return None,{**receipt,'native_zero_or_skip':'no_actions'if not n else'no_shots','score':0}
  payload={'messages':[{'role':'system','content':PROMPT.SYSTEM_PROMPT},{'role':'user','content':[{'type':'text','text':PROMPT.USER_PROMPT.format(task=task['instruction'],thoughts_and_actions=trajectory)},shot]}],'seed':42}
  receipt['trajectory_sha256']=hashlib.sha256(trajectory.encode()).hexdigest()
 images=[x['image_url']['url']for m in payload['messages']if isinstance(m.get('content'),list)for x in m['content']if x.get('type')=='image_url']
 receipt.update(selected_images=len(images),selected_image_byte_sha256=[hashlib.sha256(base64.b64decode(x.split(',',1)[1])).hexdigest()for x in images],task_instruction_sha256=hashlib.sha256(task['instruction'].encode()).hexdigest())
 return payload,receipt
def parse_response(response,task,expected_model):
 assert response.model==expected_model,"Native Judge response model mismatch"
 assert len(response.choices)==1 and response.choices[0].finish_reason=='stop','Incomplete completion'
 text=response.choices[0].message.content or ''
 if task['suite']=='bu_bench_v1':
  import jsonschema
  value=json.loads(text);jsonschema.validate(value,BU_JUDGE.JudgementResult.model_json_schema());verdict=BU_JUDGE.JudgementResult.model_validate(value)
  assert type(verdict.verdict)is bool
  return int(verdict.verdict),verdict.model_dump()
 value=OM.parse_verdict(text)
 if value is None:raise ValueError('Native OM parser found no status:')
 return value,{'reward':value,'judge_text':text}
