#!/usr/bin/env python3
"""Prepare BU-filter data and invoke the frozen df93 evaluation runtime."""
from __future__ import annotations
import argparse, asyncio, getpass, hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path
from datetime import datetime, timezone
HERE = Path(__file__).resolve().parent
CONFIG_SHA256 = 'c9007c22d094d1b90337c178031933164a93aaa2c51fa843c080013fba95dfef'
sys.path.insert(0, str(HERE))
from dataset import actor_task, load_judge_tasks, load_tasks, validate_dataset


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.chmod(0o600); temporary.replace(path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def executable(path):
    # Do not resolve venv/bin/python to its base interpreter.
    return Path(os.path.abspath(Path(path).expanduser()))


def config(path=HERE/'config.json'):
    if sha(path) != CONFIG_SHA256:
        raise ValueError('The frozen BU-filter configuration checksum changed')
    value=read(path)
    expected=read(HERE/'config.json')
    if value!=expected or value['benchmark']!='BU-filter' or value['expected_tasks']!=87:
        raise ValueError('Only the frozen BU-filter configuration is supported')
    assert value['agent']['max_steps']==300 and value['agent']['timeout_seconds']==3600
    return value


def product_probe(source, python):
    code=r'''import sys,json,hashlib,platform
from pathlib import Path
from importlib.metadata import version,distributions
p=Path(sys.argv[1]);sys.path.insert(0,str(p/'src'))
import browser_use, lexmount_browser_agent
from lexmount_browser_agent import AgentConfig, runner
assert runner.Agent is browser_use.Agent and not (Path(lexmount_browser_agent.__file__).parent/'delivery.py').exists()
from importlib.metadata import distribution
cfg=AgentConfig(api_key='offline-probe-key',base_url='http://127.0.0.1/v1')
package=Path(lexmount_browser_agent.__file__).resolve().parent
engine=Path(browser_use.__file__).resolve().parent
assert package==p/'src/lexmount_browser_agent'
assert engine==distribution('browser-use').locate_file('browser_use').resolve()
assert engine.is_relative_to(Path(sys.prefix)) and version('browser-use')=='1.0.4'
hashes={str(f.relative_to(engine)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(engine.rglob('*.py'))}
fingerprint=hashlib.sha256(b''.join(k.encode()+bytes([0])+bytes.fromhex(v) for k,v in hashes.items())).hexdigest()
# Python sources from the official 1.0.4 wheel locked in the product.
assert fingerprint=='282b10117c542cd24815c98789be68e704f9b671b39103dc28220787dd449673'
assert cfg.reasoning_effort=='max' and cfg.mode=='default' and cfg.model=='deepseek-v4.1-flash'
print(json.dumps({'python_version':platform.python_version(),'all_versions':{d.metadata['Name'].lower().replace('_','-'):d.version for d in distributions()},'product_import':str(package),'engine_source':str(engine),'engine_version':version('browser-use'),'engine_files':hashes,'model':cfg.model,'reasoning_effort':cfg.reasoning_effort,'mode':cfg.mode,'feature_config':{},'versions':{n:version(n) for n in ['browser-use','browser-harness','pydantic-ai-slim','pydantic','openai','httpx','cdp-use']}}))
'''
    result=subprocess.run([str(executable(python)),'-c',code,str(source)],capture_output=True,text=True,timeout=60)
    if result.returncode:
        raise RuntimeError('Official 1.0.4 package or product import verification failed. '+result.stderr[-1000:])
    return json.loads(result.stdout.strip().splitlines()[-1])


def preflight(args):
    cfg=config(args.config); data=validate_dataset()
    source=Path(args.agent_source).expanduser().resolve()
    proof=product_probe(source,args.agent_python)
    environment=read(HERE/'runtime-environment.json')
    assert proof['python_version']==environment['actor']['python_version'], 'Actor Python differs from df93'
    # Product dependencies are frozen by its own uv.lock; record and compare them again after installation.
    controller_version=subprocess.check_output([cfg['controller_python'],'-c','import platform;print(platform.python_version())'],text=True,timeout=20).strip()
    assert controller_version==environment['controller']['python_version'], 'Controller Python differs from df93'
    browser=Path(cfg['browser_executable'])
    if not shutil.which('bwrap'):
        raise RuntimeError('Original df93 bwrap isolation is required')
    browser_version=subprocess.check_output([str(browser),'--version'],text=True,timeout=20).strip()
    judge_code="from browser_use.llm.messages import UserMessage;import httpx,openai,platform,json;from importlib.metadata import distributions;print(json.dumps({'python_version':platform.python_version(),'all_versions':{d.metadata['Name'].lower().replace('_','-'):d.version for d in distributions()}}))"
    judge_proof=json.loads(subprocess.check_output([str(executable(args.judge_python)),'-c',judge_code],text=True,timeout=60))
    assert judge_proof['python_version']==environment['judge']['python_version'], 'Judge Python differs from df93'
    assert judge_proof['all_versions']==environment['judge']['all_versions'], 'Judge dependencies differ from df93'
    credentials=read(args.credentials_file)
    assert credentials['model']=='deepseek-v4.1-flash'
    return {'dataset':data,'product':proof,'controller_python_version':controller_version,'judge':judge_proof,'browser':{'path':str(browser),'version':browser_version,'sha256':sha(browser)},'bwrap':shutil.which('bwrap'),'model_requests':0}


def source_hashes(source):
    source=Path(source)
    return {str(p.relative_to(source)):sha(p) for p in sorted(source.rglob('*')) if p.is_file() and '.venv' not in p.parts and '__pycache__' not in p.parts and '.git' not in p.parts and p.suffix!='.pyc'}


def product_commit(source):
    stamp=Path(source)/'.source-commit'
    if stamp.is_file():return stamp.read_text().strip()
    return subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()


def prepare(args):
    proof=preflight(args);cfg=config(args.config)
    run=Path(args.output).expanduser().resolve();run.mkdir(parents=True,exist_ok=False,mode=0o700)
    harness=run/'frozen/harness'
    shutil.copytree(HERE,harness,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.venv*','results','.git','.private'))
    source=Path(args.agent_source).resolve();product=run/'product';product.mkdir()
    shutil.copytree(source/'src',product/'src',ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.egg-info'))
    for name in ['pyproject.toml','uv.lock','README.md','.source-commit']:
        if (source/name).is_file():shutil.copy2(source/name,product/name)
    # Same dedicated product/.venv and src layout as the original run; no editable path outside bwrap.
    subprocess.run(['uv','sync','--frozen','--python',str(executable(args.agent_python))],cwd=product,check=True)
    installed=product_probe(product,product/'.venv/bin/python')
    assert installed['versions']==proof['product']['versions'] and installed['all_versions']==proof['product']['all_versions'] and installed['python_version']==proof['product']['python_version'],'Product dependency versions changed while installing the frozen build'
    build={'commit':product_commit(source),'engine_version':installed['engine_version'],'engine_files':installed['engine_files'],'source_sha256':source_hashes(product)}
    write(run/'build.json',build)
    support=run/'support';support.mkdir()
    credentials=read(args.credentials_file)
    write(support/'.private/model.json',dict(credentials, mode=cfg['agent']['mode'], reasoning_effort=cfg['agent']['reasoning_effort']))
    capacity=Path(args.capacity_file)
    if not capacity.is_file():raise FileNotFoundError('Capacity metadata is required; do not discard existing evaluators')
    inflight=read(capacity)['in_flight']
    write(support/'previous-capacity/pause-bu-priority.json',{'in_flight':inflight})
    settings={'controller_python':cfg['controller_python'],'product_source':str(product),'agent_python':str(product/'.venv/bin/python'),'judge_python':str(executable(args.judge_python)),'credentials_file':str(support/'.private/model.json'),'agent':cfg['agent'],'judge':cfg['judge'],'browser_executable':cfg['browser_executable'],'viewport':cfg['viewport']}
    write(run/'settings.json',settings)
    tasks=[{k:t[k] for k in ['id','instruction','start_url','answer']} for t in load_judge_tasks()]
    write(run/'task-data.json',{'bu_v1':tasks})
    assert len(tasks)==87
    jobs=[]
    for task in load_tasks():
        folder=run/'runs/bu_v1'/task['id'];folder.mkdir(parents=True)
        write(folder/'task.json',actor_task(task))
        actor_cfg={'source_folder':str(folder),'max_steps':300,'timeout_seconds':3600,'fixed_viewport':True,'feature_config':dict(installed['feature_config']),'product':build}
        write(folder/'actor-config.json',actor_cfg)
        jobs.append({'suite':'bu_v1','id':task['id'],'task_id':task['id'],'ordinal':task['ordinal'],'source_folder':str(folder),'judge_folder':str(run/'judges/bu_v1'/task['id']),'task_input_sha256':sha(folder/'task.json'),'actor_config_sha256':sha(folder/'actor-config.json'),'feature_config':actor_cfg['feature_config']})
    driver=run/'driver';driver.mkdir()
    shutil.copy2(harness/'actor.py',driver/'actor.py')
    bootstrap="import sys\nfrom pathlib import Path\nr=Path(__file__).resolve().parents[1]\nsys.path.insert(0,str(r/'frozen/harness'))\nfrom strict_runtime import main\nmain(r)\n"
    (driver/'run.py').write_text(bootstrap)
    write(run/'probes/candidate/actor-config.json',{'product':build})
    frozen=[run/'build.json',run/'task-data.json',run/'settings.json',*driver.glob('*.py'),*[harness/p for p in source_hashes(harness)],*[product/p for p in build['source_sha256']],*[Path(j['source_folder'])/name for j in jobs for name in ['task.json','actor-config.json']]]
    plan={'schema_version':1,'benchmark':'BU-filter','product_commit':build['commit'],'created_at':time.time(),'counts':{'bu_v1':87},'jobs':jobs,'new_actor_runs':87,'reused_actor_runs':0,'old_actor_runs':0,'actor_concurrency':32,'judge_concurrency':4,'identical_task_inputs':87,'agent_reasoning':'max','agent_mode':'default','feature_config':{},'file_sha256':{str(p):sha(p) for p in frozen},'dataset_manifest_sha256':sha(harness/'data/manifest.json'),'source_df93_commit':'df93e28b9aa1013523f39391dd4cb8a269dae585'}
    write(run/'plan.json',plan)
    return run


def verify_run(run):
    run=Path(run).resolve();plan=read(run/'plan.json')
    allowed={t['id']:t for t in load_tasks()}
    if plan.get('benchmark')!='BU-filter' or plan.get('counts')!={'bu_v1':87} or len(plan['jobs'])!=87:
        raise ValueError('Only the fixed 87-task run is supported')
    if {j['task_id'] for j in plan['jobs']}!=allowed.keys():raise ValueError('Run task set changed')
    for job in plan['jobs']:
        task=allowed[job['task_id']]
        if (job['suite']!='bu_v1' or job['ordinal']!=task['ordinal']
                or Path(job['judge_folder'])!=run/'judges/bu_v1'/job['task_id']):
            raise ValueError('Task or Judge output path differs from this frozen run')
        folder=Path(job['source_folder'])
        if folder!=run/'runs/bu_v1'/job['task_id'] or read(folder/'task.json')!=actor_task(task):raise ValueError('Task input changed')
        actor_cfg=read(folder/'actor-config.json')
        if actor_cfg['max_steps']!=300 or actor_cfg['timeout_seconds']!=3600:raise ValueError('Task budget changed')
    for name,digest in plan['file_sha256'].items():
        if sha(name)!=digest:raise ValueError('Frozen source changed: '+name)
    return plan


def probe(run):
    run=Path(run).resolve();verify_run(run)
    code="import sys,subprocess;from pathlib import Path;r=Path(sys.argv[1]);sys.path.insert(0,str(r/'frozen/harness'));from strict_runtime import load_runtime;n=load_runtime(r);subprocess.run(n['actor_command'](r/'probes/candidate',probe=True),check=True,timeout=100)"
    subprocess.run([str(executable(sys.executable)),'-c',code,str(run)],check=True,timeout=110)
    write(run/'probe-passed.json',{'product_commit':read(run/'plan.json')['product_commit'],'at':time.time(),'model_requests':0,'benchmark_tasks':0})


def summarize(run):
    run=Path(run).resolve();plan=verify_run(run);rows=[]
    for job in plan['jobs']:
        execution=Path(job['source_folder'])/'execution.json';packet=Path(job['judge_folder'])/'judge-bu_v1.json'
        grade=read(packet) if packet.is_file() else None
        valid=bool(grade and grade.get('status')=='judged' and type(grade.get('score')) is int and grade['score'] in (0,1))
        rows.append({'ordinal':job['ordinal'],'task_id':job['task_id'],'state':'pass' if valid and grade['score']==1 else 'fail' if valid else 'unknown' if packet.exists() or execution.exists() or (execution.parent/'agent').exists() else 'pending','judge_status':grade.get('status') if grade else None})
    counts={s:sum(r['state']==s for r in rows) for s in ['pass','fail','unknown','pending']}
    complete=not counts['unknown'] and not counts['pending']
    value={'benchmark':'BU-filter','tasks':87,**counts,'complete':complete,'success_rate':counts['pass']/87 if complete else None,'confirmed_lower_bound':counts['pass']/87,'upper_bound':(counts['pass']+counts['unknown']+counts['pending'])/87,'rows':rows,'note':'Independent reporting only. The frozen original runtime preserves all existing judge packets, including errors; it never merges historical passes.'}
    write(run/'summary.json',value);return value


def runtime_args(p):
    p.add_argument('--config',default=str(HERE/'config.json'))
    p.add_argument('--agent-source',required=True)
    p.add_argument('--agent-python',required=True)
    p.add_argument('--judge-python',required=True)
    p.add_argument('--credentials-file',default=str(HERE.parent/'.private/bu-filter-model.json'))
    p.add_argument('--capacity-file',default=str(HERE.parent/'.private/bu-filter-capacity.json'))


def main():
    p=argparse.ArgumentParser(description=__doc__);subs=p.add_subparsers(dest='command',required=True)
    subs.add_parser('verify')
    q=subs.add_parser('configure');q.add_argument('--credentials-file',default=str(HERE.parent/'.private/bu-filter-model.json'));q.add_argument('--base-url',default='https://litellm.local.lexmount.net/v1')
    for name in ['preflight','prepare','run']:
        q=subs.add_parser(name);runtime_args(q)
        if name!='preflight':q.add_argument('--output',required=True)
    for name in ['probe','resume','summarize']:
        q=subs.add_parser(name);q.add_argument('--output',required=True)
    args=p.parse_args()
    if args.command=='verify':
        from strict_runtime import source_audit
        from legacy.environment_bindings import verify_frozen
        originals=verify_frozen()
        print(json.dumps({'dataset':validate_dataset(),'config':config(),'original_runtime':source_audit(),'verified_package_source_files':len(originals['files'])},ensure_ascii=False,indent=2))
    elif args.command=='configure':
        path=Path(args.credentials_file).expanduser().resolve()
        if path.is_relative_to(HERE):raise ValueError('Credentials must stay outside the package')
        if path.exists():raise FileExistsError(path)
        key=os.environ.get('OPENAI_API_KEY') or getpass.getpass('Model API key (hidden): ')
        if not key:raise ValueError('Missing API key')
        write(path,{'api_key':key,'base_url':args.base_url,'model':'deepseek-v4.1-flash'})
        print('Private credentials saved with mode0600')
    elif args.command=='preflight':print(json.dumps(preflight(args),ensure_ascii=False,indent=2))
    elif args.command in ['prepare','run']:
        run=prepare(args)
        if args.command=='run':
            probe(run)
            subprocess.run([read(run/'settings.json')['controller_python'],str(run/'driver/run.py'),'run'],check=True)
        print(json.dumps({'run':str(run),'prepared_tasks':87,'actor_steps':300,'timeout_seconds':3600}))
    elif args.command=='probe':probe(args.output)
    elif args.command=='resume':
        run=Path(args.output).resolve();verify_run(run)
        subprocess.run([read(run/'settings.json')['controller_python'],str(run/'driver/run.py'),'run'],check=True)
    else:print(json.dumps(summarize(args.output),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
