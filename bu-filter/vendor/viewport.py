"""Fixed viewport using the existing 5090 CDP target-auto-attach implementation."""
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
