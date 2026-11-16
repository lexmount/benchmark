"""Evaluation environment only: native per-page CDP viewport initialization.

Adapts Browser Use 0.13.14 TabCreatedEvent/_cdp_set_viewport and its synchronous
CDP callback -> asyncio task pattern. Does not touch Agent prompts or its loop.
"""
import asyncio, json, time
from pathlib import Path
from cdp_use.client import CDPClient

class FixedViewport:
    def __init__(self,browser,receipt):
        self.browser=browser;self.receipt=Path(receipt);self.client=None;self.ws=None
        self.ready={};self.tasks=set();self.rows=[];self.errors=[]

    async def start(self):
        ws=self.browser._daemon_env['BU_CDP_WS']
        if self.client and self.ws==ws:return
        if self.client:await self.close()
        self.ws=ws;self.client=CDPClient(ws);await self.client.start()
        def attached(event,session_id=None):
            task=asyncio.create_task(self.configure(event));self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        self.client.register.Target.attachedToTarget(attached)
        # Chrome pauses new page targets until their environment is configured;
        # only this connection's own sessions are used. No focus/session rewrite.
        await self.client.send_raw('Target.setAutoAttach',{'autoAttach':True,
            'waitForDebuggerOnStart':True,'flatten':True,
            'filter':[{'type':'page','exclude':False},{'exclude':True}]})
        pages=(await self.client.send_raw('Target.getTargets'))['targetInfos']
        for page in pages:
            if page['type']=='page':
                await asyncio.wait_for(self.ready.setdefault(page['targetId'],asyncio.Event()).wait(),10)
        if self.errors:raise RuntimeError('Viewport initialization failed')

    async def configure(self,event):
        info=event['targetInfo'];sid=event['sessionId'];tid=info['targetId'];started=time.time()
        try:
            if info['type']=='page':
                await self.client.send_raw('Emulation.setDeviceMetricsOverride',
                    {'width':1440,'height':900,'deviceScaleFactor':1,'mobile':False},sid)
                self.rows.append({'target_id':tid,'session_id':sid,'started_at':started,
                    'configured_at':time.time(),'width':1440,'height':900,'device_scale_factor':1,
                    'waiting_for_debugger':event.get('waitingForDebugger',False)})
                self.ready.setdefault(tid,asyncio.Event()).set()
        except Exception as exc:
            self.errors.append({'target_id':tid,'error_type':type(exc).__name__})
        finally:
            try:await self.client.send_raw('Runtime.runIfWaitingForDebugger',session_id=sid)
            except Exception:pass
            self.save()

    def save(self):
        self.receipt.parent.mkdir(parents=True,exist_ok=True)
        self.receipt.write_text(json.dumps({'implementation':'native Target auto-attach + Emulation + resume',
            'required_viewport':[1440,900],'device_scale_factor':1,'rows':self.rows,'errors':self.errors},indent=2))

    async def close(self):
        if not self.client:return
        try:await asyncio.wait_for(self.client.send_raw('Target.setAutoAttach',
            {'autoAttach':False,'waitForDebuggerOnStart':False,'flatten':True}),2)
        except Exception:pass
        if self.tasks:await asyncio.gather(*list(self.tasks),return_exceptions=True)
        await self.client.stop();self.client=None

async def fixture():
    import os,struct
    from browser_use import Browser
    from browser_use.browser.browser import _daemon_request
    from browser_harness import helpers as h
    browser=Browser('chromium',headless=True,executable_path='/opt/google/chrome/chrome')
    env=await browser.start();os.environ.update(env);h.NAME=browser.name
    root=Path('/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/tmp/bu103-helpers-20261114/bu-lexmount-20261114/viewport-fixture')
    controller=FixedViewport(browser,root/'environment.json');checks=[]
    def measure(label):
        info=h.page_info();path=root/(str(len(checks))+'.png');h.capture_screenshot(str(path))
        with path.open('rb') as f:header=f.read(24)
        pixels=list(struct.unpack('>II',header[16:24]));assert [info['w'],info['h']]==[1440,900],info
        assert pixels==[1440,900],pixels
        checks.append({'label':label,'css_viewport':[info['w'],info['h']],
                       'png_pixels':pixels,'target_id':h.current_tab()['targetId']})
    try:
        await controller.start()
        await asyncio.to_thread(measure,'initial')
        ids=[]
        for i in range(12):
            def new():
                tid=h.new_tab('about:blank');measure('immediate_new_tab_'+str(i));return tid
            ids.append(await asyncio.to_thread(new))
        for tid in ids[::3]:
            def switch():
                h.switch_tab(tid);measure('switch_tab')
                h.goto_url('data:text/html,<title>Viewport fixture</title><body>real navigation</body>')
                h.wait_for_load()
                measure('navigation')
            await asyncio.to_thread(switch)
        def popup():
            before={t['targetId'] for t in h.list_tabs()}
            h.cdp('Runtime.evaluate',expression="window.open('about:blank','_blank')",userGesture=True)
            created={t['targetId'] for t in h.list_tabs()}-before
            assert len(created)==1,created
            tid=created.pop();h.switch_tab(tid);measure('js_popup_immediate')
        await asyncio.to_thread(popup)
        result={'passed':True,'actual_actor_or_judge_requests':0,'checks':checks,
                'environment_receipt':str(root/'environment.json'),'new_tab_checks':12,
                'browser_window_bounds':await asyncio.to_thread(_daemon_request,browser.name,
                    {'method':'Browser.getWindowForTarget','params':{}},timeout=5)}
        (root/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    finally:
        await controller.close();await browser.stop()

if __name__=='__main__':asyncio.run(fixture())
