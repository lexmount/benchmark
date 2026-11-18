"""Mount the Agent publisher's runtime with either suite's original bwrap command."""
from functools import wraps
import hashlib
import json
import os
import re
from pathlib import Path


def binding(manifest, commit):
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Actor runtime needs a full product commit')
    path = Path(manifest).resolve(strict=True)
    blob = path.read_bytes()
    release = json.loads(blob)
    if path.name != 'actor-runtime.json' or path.parent.name != commit or release['product_commit'] != commit:
        raise ValueError('Actor runtime and requested product commit differ')
    if hashlib.sha256((path.parent / 'uv.lock').read_bytes()).hexdigest() != release['uv_lock_sha256']:
        raise ValueError('Actor runtime lockfile differs from the release manifest')
    for name in ('.venv/bin/python', 'src/lexmount_browser_agent/__init__.py', 'cpython/bin/python3', 'chrome/chrome'):
        if not (path.parent / name).is_file():
            raise FileNotFoundError(path.parent / name)
    return {'manifest': str(path), 'sha256': hashlib.sha256(blob).hexdigest()}


def select_release(source, commit, explicit=None):
    """Find the Agent-owned release before a suite creates a run directory."""
    if explicit is not None:
        return binding(explicit, commit)
    local = Path(source) / 'actor-runtime.json'
    store = Path(os.environ.get('LEXMOUNT_ACTOR_RUNTIME_STORE', '/data/wf/sxh/workspace/lexmount/agent-runtimes'))
    manifest = local if local.is_file() else store / commit / 'actor-runtime.json'
    if not manifest.is_file():
        raise FileNotFoundError(f'Publish Agent {commit} with its runtime publisher or pass --actor-runtime: {manifest}')
    return binding(manifest, commit)


def bind_actor(scope, frozen):
    if binding(frozen['manifest'], scope['COMMIT']) != frozen:
        raise ValueError('Actor runtime manifest changed after preparation')
    root = Path(frozen['manifest']).parent
    scope['ENV'] = root / '.venv'
    scope['SOURCE'] = root / 'src'
    original = scope['actor_command']

    @wraps(original)
    def command(*args, **kwargs):
        argv = original(*args, **kwargs)
        # Preserve the evaluator's namespace, workspace and isolation. Only the two system
        # runtime mounts need substituting: the original uses the host's Chrome and uv store.
        for expected, source, destination in (
            ('/opt/google/chrome', str(root / 'chrome'), '/opt/google/chrome'),
            ('/home/wf/.local/share/uv/python', str(root / 'cpython'), str(root / 'cpython')),
        ):
            matches = [i for i in range(len(argv) - 2) if argv[i:i + 3] == ['--ro-bind', expected, expected]]
            if len(matches) != 1:
                raise ValueError(f'Expected one read-only runtime mount for {expected}')
            i, = matches
            argv[i+1:i+3] = [source, destination]
        return argv
    scope['actor_command'] = command
