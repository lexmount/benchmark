"""Run the frozen observer with a one-task plan; this process never loads evaluator data."""
import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

from browser_use import Browser
import full_benchmarks as baseline

folder = Path(sys.argv[1])
job = json.loads((folder / 'actor-config.json').read_text())

def verify_runtime():
    import hashlib
    from importlib.metadata import distribution, version
    import browser_use
    import lexmount_browser_agent
    expected = job['product']
    engine = Path(browser_use.__file__).resolve().parent
    package = Path(lexmount_browser_agent.__file__).resolve().parent
    project = package.parents[1]
    actual = {}
    for name, digest in expected['source_sha256'].items():
        if not name.startswith('src/') or not name.endswith('.py'):
            continue
        path = project / name
        actual[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual[name] == digest, name
    assert engine == distribution('browser-use').locate_file('browser_use').resolve()
    assert engine.is_relative_to(Path(sys.prefix)) and version('browser-use') == '1.0.4'
    assert hashlib.sha256((engine / 'agent/loop.py').read_bytes()).hexdigest() == '1ec7859d76e3eb4bf0b8ddffebb835dd310bd4785ea5ae979f1d91c1faf5a135'
    assert hashlib.sha256((engine / 'repl/worker.py').read_bytes()).hexdigest() == '79172a7c6907d3a7efbda61eef64c0aff7b1c369c1d237ecec980663cb01af28'
    assert version('browser-use') == expected['engine_version']
    baseline.write(folder / 'runtime-provenance.json', {
        'product_commit': expected['commit'], 'engine_version': version('browser-use'),
        'engine_source': str(engine), 'launcher_source': str(package),
        'python_executable': sys.executable, 'verified_source_sha256': actual,
        'all_matched': True,
    })

verify_runtime()

policy = ('Evaluation on public websites. If a site shows an access denial, CAPTCHA, region or login restriction, record the blocker. '
          'Use other permitted public sources or continue independent requirements. Do not bypass access controls, use proxies or third-party solvers, or inspect private endpoints. '
          'Use only this task workspace for local data, its attached browser, and authorized public content. Never access benchmark/evaluator materials, other tasks or system credentials. '
          'Do not contact people, send email, sign third parties up, place real orders or pay; stop before final submission and describe the observed state.')

async def main():
    from browser_use.agent import loop
    source_config = json.load(sys.stdin)
    original_read = baseline.read
    def read(path):
        return source_config if path == baseline.ROOT / '.private/model.json' else original_read(path)
    context = None
    start = Browser.start
    async def start_with_viewport(browser):
        nonlocal context
        result = await start(browser)
        if context is None:
            from bu_lexmount_viewport import FixedViewport
            context = FixedViewport(browser, folder / 'viewport.json')
        await context.start()
        return result
    with patch.object(baseline, 'read', read), patch.object(loop, 'SYSTEM_PROMPT', loop.SYSTEM_PROMPT + '\n\n' + policy), patch.object(Browser, 'start', start_with_viewport if job['fixed_viewport'] else start):
        try:
            await baseline.worker(folder, job['max_steps'], job['timeout_seconds'], {'jobs':[job], 'browser_executable':'/opt/google/chrome/chrome'})
        finally:
            if context and context.client:
                try: await context.close()
                except Exception: pass

if __name__ == '__main__':
    if os.environ.get('PROBE_ONLY') == '1':
        from browser_harness import helpers
        async def probe():
            import subprocess
            from lexmount_browser_agent import AgentConfig
            from browser_use.agent import loop
            assert hasattr(loop, 'SYSTEM_PROMPT')
            from browser_use.repl import Repl
            browser = Browser('chromium', headless=True, executable_path='/opt/google/chrome/chrome')
            repl = None
            try:
                env = await browser.start()
                repl = Repl(folder/'work', env, mode='ultrafast')
                out = await repl.call('exec', "goto_url('data:text/html,<title>Probe</title><p>example row</p>'); wait_for_element('p'); print(find_text('example') if 'find_text' in globals() else page_info())", 45)
                print(out['error'] or out['output'], flush=True)
                assert not out['error'] and 'Probe' in out['output']
                assert not (baseline.ROOT/'.private/model.json').exists()
                assert not (baseline.ROOT/'full-600-20261114').exists()
                check = await repl.call('exec', "import hashlib, browser_use; from pathlib import Path; print(hashlib.sha256((Path(browser_use.__file__).parent/'repl/worker.py').read_bytes()).hexdigest())", 20)
                assert '79172a7c6907d3a7efbda61eef64c0aff7b1c369c1d237ecec980663cb01af28' in check['output'], check
                assert AgentConfig(api_key='offline', base_url='http://localhost').reasoning_effort == 'max'
                print('isolated browser probe passed',os.environ['EXPECTED_ARM'],flush=True)
            finally:
                if repl: await repl.close()
                await browser.stop()
        asyncio.run(probe())
    else:
        asyncio.run(main())
