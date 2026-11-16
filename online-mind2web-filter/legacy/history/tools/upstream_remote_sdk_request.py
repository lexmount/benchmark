"""Use the installed SDK stream collector with an explicit terminal-choice guard."""
from pathlib import Path
import hashlib,json,sys,time,signal
import openai,httpx
from openai import OpenAI
class IncompleteGradingStream(RuntimeError):pass
def stream_completion(client,payload,meta):
 options=dict(payload);options['stream_options']={'include_usage':True}
 wire={**options,'stream':True};meta['wire_request_sha256']=hashlib.sha256(json.dumps(wire,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 meta['stream']=True;meta['stream_options']=options['stream_options'];meta['chunks']=0
 with client.chat.completions.stream(**options) as stream:
  for event in stream:
   if event.type=='chunk':meta['chunks']+=1
  response=stream.get_final_completion()
 if len(response.choices)!=1 or response.choices[0].finish_reason!='stop':
  raise IncompleteGradingStream('A grading stream must contain exactly one completed stop choice; partial or truncated results are not accepted')
 if response.model!=payload['model']:raise IncompleteGradingStream('The response model differs from the fixed requested model')
 return response
def retryable(exc):
 status=getattr(exc,'status_code',None)
 return (isinstance(exc,(openai.APIConnectionError,openai.APITimeoutError,httpx.TransportError))
         or status in {408,429} or isinstance(status,int) and 500<=status<600 and status not in {501,505})

def complete_with_retries(payload,cfg,meta,*,clock=time.monotonic,sleep=time.sleep,client_factory=OpenAI):
 started=clock();deadline=started+600;meta['attempts']=[]
 for attempt in range(1,4):
  remaining=deadline-clock()
  if remaining<=0:raise TimeoutError('The grading request exhausted its shared 600-second deadline')
  record={'attempt':attempt,'started_seconds':clock()-started};meta['attempts'].append(record)
  try:
   with client_factory(api_key=cfg['api_key'],base_url=cfg['base_url'],timeout=httpx.Timeout(remaining,connect=min(30,remaining),write=remaining,read=remaining),max_retries=0) as client:
    response=stream_completion(client,payload,meta)
   record.update(status='succeeded',finished_seconds=clock()-started)
   return response
  except Exception as exc:
   record.update(status='failed',error_type=type(exc).__name__,http_status=getattr(exc,'status_code',None),finished_seconds=clock()-started)
   delay=(8,16)[attempt-1] if attempt<3 else None
   if delay is None or not retryable(exc) or deadline-clock()<=delay:raise
   record['backoff_seconds']=delay;sleep(delay)

def main():
 from judge_profiles import settings,current
 cfg=settings();raw=sys.stdin.buffer.read();digest=hashlib.sha256(raw).hexdigest();started=time.time()
 meta={'request_sha256':digest,'host':'server-5090-local-browser','judge_profile':current(),'openai_version':openai.__version__,'httpx_version':httpx.__version__,'remote_helper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'sdk_max_retries':0,'total_deadline_seconds':600,'max_attempts':3,'transport_revision':'1106_shared_deadline_retry','upstream_base_url':cfg['base_url']}
 def deadline(*_):raise TimeoutError('The grading request exceeded its 600-second total deadline')
 signal.signal(signal.SIGALRM,deadline);signal.alarm(600)
 try:
  payload=json.loads(raw);assert payload['model']==cfg['model'];assert payload['reasoning_effort']==cfg['reasoning_effort'];assert not payload.get('stream') and not payload.get('stream_options')
  response=complete_with_retries(payload,cfg,meta)
  result={**meta,'ok':True,'response':response.model_dump(mode='json')}
 except BaseException as e:
  chain=[];v=e
  while v is not None and len(chain)<8:
   chain.append({'type':type(v).__name__,'message':str(v).replace(cfg['api_key'],'<redacted>')[:1000]});v=v.__cause__
  result={**meta,'ok':False,'error_type':type(e).__name__,'http_status':getattr(e,'status_code',None),'chain':chain}
 finally:signal.alarm(0)
 result['seconds']=time.time()-started;print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
