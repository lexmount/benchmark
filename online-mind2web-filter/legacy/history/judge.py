"""Native BU/AgentTrek scoring; maximum two durable physical POST reservations per task."""
from pathlib import Path
import argparse,base64,copy,fcntl,hashlib,json,os,signal,sys,time
N=Path(__file__).resolve().parents[1];J=N/'judge-common'
sys.path[:0]=[str(J),str(J/'tools'),str(N/'runner'),str(N/'control')]
from wire_audit import WireAudit
from judge_profiles import explicit_moderation
from upstream_remote_sdk_request import stream_completion
from native_evidence import build_payload,parse_response,rd,sha
VERSION='native-BU-AgentTrek-max2-v1';MAX_POSTS=2;BODY_LIMIT=64*1024*1024;ATTEMPT_SECONDS=150

def durable_write(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.tmp')
 with temp.open('w')as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(temp,path);fd=os.open(path.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
def native_cfg(task,profile=None):
 old=task['baseline']['judge'];old_model=(old.get('native')or{}).get('judge_model')if task['suite']=='bu_bench_v1'else old.get('model')
 assert old_model in ['deepseek-v4.1-flash','gpt-6.1-sol']
 initial='moderation_fallback'if old_model=='gpt-6.1-sol'else'primary';name=profile or initial
 cfg=copy.deepcopy(rd(N/'.private/judge-profiles.json')[name]);assert cfg['base_url'].rstrip('/')=='https://litellm.local.lexmount.net/v1'
 assert cfg['model']==('deepseek-v4.1-flash'if name=='primary'else'gpt-6.1-sol')
 cfg['wire_effort']='high'if name==initial=='moderation_fallback'else cfg.get('reasoning_effort','low')
 if name=='primary':assert cfg['wire_effort']=='low'
 cfg['wire_output_cap']=8096 if task['suite']=='bu_bench_v1'else 4096
 return name,cfg

def wire_payload(base,cfg):
 return {**copy.deepcopy(base),'model':cfg['model'],'reasoning_effort':cfg['wire_effort'],'max_tokens':cfg['wire_output_cap'],'extra_body':{'allowed_openai_params':['reasoning_effort'],'cache':{'no-cache':True,'no-store':True}}}
def preflight(base,cfg):
 """Serialize using the same installed SDK and stream path through MockTransport, never a socket."""
 import httpx,openai
 payload=wire_payload(base,cfg);captures=[]
 def respond(req):
  captures.append(req.content);o=json.loads(req.content)
  chunk={'id':'offline-preflight','object':'chat.completion.chunk','created':0,'model':o['model'],'choices':[{'index':0,'delta':{'role':'assistant','content':'{}'},'finish_reason':None}]}
  stop={**chunk,'choices':[{'index':0,'delta':{},'finish_reason':'stop'}],'usage':{'prompt_tokens':0,'completion_tokens':0,'total_tokens':0}}
  return httpx.Response(200,headers={'content-type':'text/event-stream'},text='data: '+json.dumps(chunk)+'\n\ndata: '+json.dumps(stop)+'\n\ndata: [DONE]\n\n')
 with httpx.Client(transport=httpx.MockTransport(respond))as transport:
  with openai.OpenAI(api_key='offline-no-secret',base_url=cfg['base_url'],max_retries=0,http_client=transport)as client:stream_completion(client,payload,{})
 assert len(captures)==1
 raw=captures[0];body=json.loads(raw);images=[x['image_url']['url']for m in body['messages']if isinstance(m.get('content'),list)for x in m['content']if x.get('type')=='image_url']
 valid=len(raw)<=BODY_LIMIT and(cfg['model']!='gpt-6.1-sol'or len(images)<=50)
 return {'passed':valid,'body_bytes':len(raw),'body_limit':BODY_LIMIT,'body_sha256':hashlib.sha256(raw).hexdigest(),'image_count':len(images),'image_sha256_order':[hashlib.sha256(base64.b64decode(x.split(',',1)[1])).hexdigest()for x in images],'model':body['model'],'reasoning_effort':body['reasoning_effort'],'max_tokens':body['max_tokens'],'allowed_openai_params':body.get('allowed_openai_params'),'cache':body.get('cache'),'stream':body.get('stream'),'stream_options':body.get('stream_options'),'real_POSTs':0,'mock_POSTs':1}
def error_receipt(exc,cfg):
 chain=[];e=exc
 while e is not None and len(chain)<8:
  chain.append({'type':type(e).__name__,'message':str(e).replace(cfg['api_key'],'<redacted>')[:1800]});e=e.__cause__
 return {'ok':False,'error_type':type(exc).__name__,'http_status':getattr(exc,'status_code',None),'chain':chain}
def request_once(base,cfg,folder,proof):
 import httpx,openai
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);payload=wire_payload(base,cfg)
 def exact(req):assert hashlib.sha256(req.content).hexdigest()==proof['body_sha256'],'Actual SDK body changed after preflight'
 wire=WireAudit(folder,cfg).install();meta={'SDK_max_retries':0,'attempt_seconds':ATTEMPT_SECONDS,'collector_function':'stream_completion (no complete_with_retries)'}
 def expired(*a):raise TimeoutError('Native Judge single attempt exceeded 150 seconds')
 previous=signal.signal(signal.SIGALRM,expired);signal.alarm(ATTEMPT_SECONDS)
 try:
  with httpx.Client(timeout=httpx.Timeout(ATTEMPT_SECONDS,connect=20),follow_redirects=False,trust_env=False,event_hooks={'request':[exact]})as transport:
   with openai.OpenAI(api_key=cfg['api_key'],base_url=cfg['base_url'],max_retries=0,http_client=transport)as client:response=stream_completion(client,payload,meta)
  durable_write(folder/'completion.json',response.model_dump(mode='json'));return response
 finally:
  signal.alarm(0);signal.signal(signal.SIGALRM,previous);wire.restore();durable_write(folder/'usage.json',wire.summary());durable_write(folder/'transport.json',meta)
def evaluate(task,base,out,*,request_fn=request_once,preflight_fn=preflight):
 from openai.types.chat import ChatCompletion
 assert not(N/'invalid-judge-attempts'/task['task_id']).exists(),'Archived Judge history cannot reset the lifetime budget'
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 binding={'suite':task['suite'],'task_id':task['task_id'],'base_payload_sha256':hashlib.sha256(json.dumps(base,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
 with(out/'budget.lock').open('a')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  p=out/'attempt-budget.json';state=rd(p,{'version':VERSION,'max_POSTs':MAX_POSTS,'attempts':[],**binding})
  assert all(state[k]==v for k,v in binding.items())and state['max_POSTs']==2,'Budget is bound to this task+payload'
  effective=rd(out/'effective.json',{})
  if effective.get('status')=='judged':return effective
  initial,cfg=native_cfg(task);profile=initial;valid=None;score=None
  # Recover any already accepted complete response without another physical request.
  for attempt in state['attempts']:
   completed=out/attempt['folder']/'completion.json'
   if completed.exists():
    try:
     score,valid=parse_response(ChatCompletion.model_validate(rd(completed)),task,attempt['model']);profile=attempt['profile'];break
    except Exception:
     profile=None;break
   if attempt.get('status')=='failed' and 'next_profile'in attempt:
    profile=attempt['next_profile']
    if profile is None:break
    continue
   error=attempt.get('error',{})
   if explicit_moderation(error):
    if attempt['profile']=='moderation_fallback':profile=None;break
    profile='moderation_fallback'
   else:profile=attempt['profile']
  while valid is None and profile is not None and len(state['attempts'])<MAX_POSTS:
   name,cfg=native_cfg(task,profile);proof=preflight_fn(base,cfg);durable_write(out/('preflight-'+str(len(state['attempts'])+1)+'-'+profile+'.json'),proof)
   if not proof['passed']:
    state['skip_reason']='preflight_limit';durable_write(p,state);break
   idx=len(state['attempts'])+1;relative='attempt-'+str(idx)+'-'+profile
   attempt={'attempt':idx,'profile':profile,'model':cfg['model'],'effort':cfg['wire_effort'],'cap':cfg['wire_output_cap'],'folder':relative,'reserved_at':time.time(),'status':'reserved','preflight_body_sha256':proof['body_sha256']}
   state['attempts'].append(attempt);durable_write(p,state)
   try:
    response=request_fn(base,cfg,out/relative,proof);score,valid=parse_response(response,task,cfg['model']);attempt.update(status='accepted',response_id=response.id,finished_at=time.time())
   except Exception as exc:
    error=error_receipt(exc,cfg);attempt.update(status='failed',error=error,finished_at=time.time());durable_write(out/relative/'error.json',error)
    if explicit_moderation(error):profile='moderation_fallback'if profile=='primary'else None
    else:
     import openai,httpx
     status=getattr(exc,'status_code',None)
     transient=isinstance(exc,(openai.APIConnectionError,openai.APITimeoutError,httpx.TransportError,TimeoutError))or status in {408,429}or isinstance(status,int)and 500<=status<600 and status not in {501,505}
     if not transient:profile=None
    attempt['next_profile']=profile
   durable_write(p,state)
  result={**binding,'ordinal':task['ordinal'],'status':'judged'if valid is not None else'unknown','score':score if valid is not None else None,'perfect':score==1 if valid is not None else None,'selected_profile':(profile if valid is not None else state['attempts'][-1]['profile']if state['attempts']else profile),'native_verdict':valid,'attempt_count':len(state['attempts']),'max_physical_POSTs':2,'protocol':VERSION,'skip_reason':state.get('skip_reason'),'segmented_analysis':False}
  durable_write(out/'effective.json',result);return result

def main():
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['judge','preflight','check']);p.add_argument('--arm',choices=['mcp'],default='mcp');p.add_argument('--suite',choices=['bu_bench_v1','online_mind2web']);p.add_argument('--task-id');a=p.parse_args()
 from selection_guard import validate_selection
 tasks=validate_selection(require_frozen=True)
 if a.mode=='check':print(json.dumps({'tasks':len(tasks),'protocol':VERSION,'real_POSTs':0,'max_POSTs':2}));return
 task=next(t for t in tasks if t['suite']==a.suite and t['task_id']==a.task_id);source=N/'runs/mcp'/task['suite']/task['task_id'];out=N/'scoring-new/mcp'/task['suite']/task['task_id'];started=time.time()
 assert(source/'worker-completion.json').exists()and rd(source/'agent/session.json',{}).get('closed')is True,'Solver must finish and close owned browser before Judge'
 base,receipt=build_payload(task,source);durable_write(out/'native-evidence.json',receipt)
 if a.mode=='preflight':
  if base is None:print(json.dumps({'task_id':task['task_id'],'native_no_request':receipt['native_zero_or_skip'],'real_POSTs':0}));return
  _,cfg=native_cfg(task);proof=preflight(base,cfg);durable_write(out/'preflight-only.json',proof);print(json.dumps(proof));return
 from judge_gate import check_judge_approved
 check_judge_approved()
 if base is None:
  score=receipt['score'];result={'task_id':task['task_id'],'suite':task['suite'],'status':'judged'if score is not None else'unknown','score':score,'perfect':score==1 if score is not None else None,'selected_profile':None,'attempt_count':0,'max_physical_POSTs':2,'protocol':VERSION,'native_zero_or_skip':receipt['native_zero_or_skip']};durable_write(out/'effective.json',result)
 else:result=evaluate(task,base,out)
 durable_write(source/'judge-effective.json',result);durable_write(source/'judge-completion.json',{'finished_at':time.time(),'seconds':time.time()-started,'arm':'mcp','suite':task['suite'],'status':result['status'],'score':result['score'],'selected_profile':result.get('selected_profile')})
 print(json.dumps({k:result.get(k)for k in ['task_id','suite','status','score','attempt_count','selected_profile']}))
if __name__=='__main__':main()
