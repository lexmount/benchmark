"""Small bridge to the pinned OSWorld environment and the unchanged guest product.

The official task setup, postconfig, getters and metrics remain authoritative.
Only this process's single owned VM is created and closed.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from numbers import Real
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
from uuid import uuid4

UPSTREAM_COMMIT = "5123bfdbbc34b947bcffcff564abc62d0ab7072d"
DOCKER_IMAGE_DIGEST = "happysixd/osworld-docker@sha256:0e6497a9295647cf05bf2b2af522fdd79bdeba2737595259cab310a3bcf6baa9"
LEGAL_ACTOR_STATUSES = {"completed", "max_steps", "timeout"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


def _write_json(path: Path, value: dict, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if exclusive:
        with path.open("x") as stream:
            stream.write(text)
    else:
        temporary = path.with_name(path.name + ".tmp-" + uuid4().hex)
        temporary.write_text(text)
        temporary.replace(path)


def _redact(message: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return message


def _event(folder: Path, kind: str, **values) -> None:
    with (folder / "events.jsonl").open("a") as stream:
        stream.write(json.dumps({"at": _now(), "event": kind, **values}, ensure_ascii=False) + "\n")


def _metadata(run_dir: Path) -> dict:
    value = _json(run_dir / "run.json")
    if value.get("upstream_commit") != UPSTREAM_COMMIT or value.get("task_count") != 76:
        raise ValueError("Run metadata must pin the confirmed 76 tasks and OSWorld commit")
    return value


def _tasks(metadata: dict) -> list[dict]:
    return _json(Path(metadata["harness_root"]) / "data/manifest.json")["tasks"]


@contextmanager
def _lock(run_dir: Path):
    path = run_dir / "runtime.lock"
    owner = {"pid": os.getpid(), "hostname": socket.gethostname(), "started_at": _now()}
    try:
        _write_json(path, owner, exclusive=True)
    except FileExistsError:
        previous = _json(path)
        if previous.get("hostname") != socket.gethostname():
            raise RuntimeError("Run lock belongs to another host; inspect it before resuming")
        try:
            os.kill(int(previous["pid"]), 0)
        except ProcessLookupError:
            path.rename(run_dir / ("runtime.lock.stale-" + uuid4().hex))
            _write_json(path, owner, exclusive=True)
        else:
            raise RuntimeError("This run already has a live runtime process")
    try:
        yield
    finally:
        if path.exists() and _json(path).get("pid") == os.getpid():
            path.unlink()


@contextmanager
def _environment(metadata: dict, folder: Path, receipt: dict):
    # Relative evaluator resources, settings and gold files resolve in this complete
    # frozen checkout, never in the Actor's filesystem or an abbreviated reference copy.
    upstream = Path(metadata["osworld_root"]).resolve()
    previous_cwd = Path.cwd()
    sys.path.insert(0, str(upstream))
    os.chdir(upstream)
    env = None
    original_create = None
    try:
        from desktop_env.desktop_env import DesktopEnv
        from desktop_env.providers.docker.provider import DockerProvider

        if metadata["config"]["runtime"]["provider"] != "docker":
            raise ValueError("This initial bridge supports only the pinned Docker provider")
        # Keep unauthenticated guest APIs and credential uploads on loopback. This
        # changes host transport binding only, not task or evaluator behavior.
        original_create = DockerProvider._create_container

        def create_owned(provider, **kwargs):
            kwargs["ports"] = {port: ("127.0.0.1", published) if isinstance(published, int)
                               else published for port, published in kwargs["ports"].items()}
            kwargs["labels"] = {**kwargs.get("labels", {}),
                                "lexmount-evaluation": "OSWorld-Verified-filter",
                                "lexmount-run": run_name(metadata),
                                "lexmount-task": receipt.get("task_id", "probe")}
            container = original_create(provider, **kwargs)
            image = container.image
            image.reload()
            digests = image.attrs.get("RepoDigests", [])
            expected = metadata["config"]["runtime"].get("docker_image_digest", DOCKER_IMAGE_DIGEST)
            if expected not in digests:
                # Creation happened in this call and start_emulator has not started
                # it yet. Remove only this owned, unstarted container.
                container.remove(v=True)
                raise RuntimeError("Created Docker image differs from the frozen expected digest")
            receipt["docker_image"] = {"id": image.id, "repo_digests": digests,
                                       "required_repo_digest": expected}
            return container

        DockerProvider._create_container = create_owned
        settings = metadata["config"]["runtime"]
        env = DesktopEnv(provider_name="docker", path_to_vm=metadata["vm_image"],
                         headless=True, action_space="pyautogui", require_a11y_tree=True,
                         screen_size=tuple(settings["screen_size"]),
                         cache_dir=str(folder / "official-cache"),
                         enable_proxy=settings.get("enable_proxy", False),
                         recording_update=settings.get("recording_update", "off"))
        receipt["vm"] = {"host": env.vm_ip, "server_port": env.server_port,
                         "chromium_port": env.chromium_port,
                         "container_id": getattr(env.provider.container, "id", None)}
        yield env
    finally:
        if env is not None:
            try:
                env.close()
                receipt["owned_vm_closed"] = True
            except Exception as error:
                receipt.setdefault("evidence_errors", []).append("owned_vm_cleanup: " + str(error))
                receipt["owned_vm_closed"] = False
        if original_create is not None:
            DockerProvider._create_container = original_create
        os.chdir(previous_cwd)
        sys.path.remove(str(upstream))


def run_name(metadata: dict) -> str:
    return Path(metadata["guest_root"]).name


def _execute(env, code: str, *, timeout: float = 30) -> dict:
    import requests

    response = requests.post(env.controller.http_server + "/execute",
                             json={"command": ["python3", "-c", code], "shell": False},
                             timeout=timeout, allow_redirects=False)
    response.raise_for_status()
    result = response.json()
    if result.get("status") != "success" or result.get("returncode") != 0:
        # Do not include arbitrary guest stderr or a private job in this exception.
        raise RuntimeError("Guest short command failed; exit=" + str(result.get("returncode")))
    return json.loads(result["output"])


def _upload(env, source: Path, destination: str) -> None:
    env.setup_controller._upload_file_setup([{"local_path": str(source), "path": destination}])


def _save_screenshot(env, folder: Path, name: str, receipt: dict) -> None:
    try:
        data = env.controller.get_screenshot()
        if not data:
            raise RuntimeError("Guest returned no screenshot")
        (folder / name).write_bytes(data)
    except Exception as error:
        receipt["evidence_errors"].append(name + ": " + str(error))


def _ensure_cdp(env, metadata: dict) -> dict:
    # Inspect the guest's actual browser ports, not the provider's published host
    # port. Official task setup commonly uses Chrome :1337 plus socat :9222.
    root = metadata["guest_root"]
    code = r'''
import json,os,pathlib,re,shutil,subprocess,time,urllib.request
root=pathlib.Path(ROOT);root.mkdir(parents=True,exist_ok=True);root.chmod(0o700)
active=None
if shutil.which('xdotool'):
 p=subprocess.run(['xdotool','getactivewindow'],capture_output=True,text=True)
 if p.returncode==0:active=p.stdout.strip()
processes=[];ports=[]
for directory in pathlib.Path('/proc').iterdir():
 if not directory.name.isdigit():continue
 try:args=(directory/'cmdline').read_bytes().split(b'\0');args=[x.decode(errors='replace') for x in args if x]
 except (OSError,PermissionError):continue
 if not args or pathlib.Path(args[0]).name not in ('chrome','google-chrome','chromium','chromium-browser'):continue
 if any(x.startswith('--type=') for x in args):continue
 processes.append(int(directory.name))
 for index,arg in enumerate(args):
  if arg.startswith('--remote-debugging-port='):ports.append(int(arg.split('=',1)[1]))
  elif arg=='--remote-debugging-port' and index+1<len(args):ports.append(int(args[index+1]))
def detect():
 for port in list(dict.fromkeys(ports+[9222,1337])):
  if port<1:continue
  try:
   with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/json/version',timeout=1) as response:v=json.load(response)
   if v.get('webSocketDebuggerUrl'):return {'endpoint':'http://127.0.0.1:'+str(port),'browser':v.get('Browser'),'port':port}
  except Exception:pass
 return None
result=detect();started=False
if result is None:
 if processes:raise RuntimeError('Existing Chrome has no reachable CDP; refusing to restart it')
 if not shutil.which('xdotool'):raise RuntimeError('xdotool is required to preserve the initial foreground window')
 executable=shutil.which('google-chrome') or shutil.which('chromium') or shutil.which('chromium-browser')
 if not executable:raise RuntimeError('Original guest Chrome executable is unavailable')
 with (root/'chrome-start.log').open('ab') as log:
  p=subprocess.Popen([executable,'--remote-debugging-port=9222','--remote-allow-origins=*'],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
 started=True
 for _ in range(30):
  result=detect()
  if result:break
  time.sleep(1)
 if result is None:raise RuntimeError('Original Chrome did not expose CDP')
restored=None
if started and active:
 p=subprocess.run(['xdotool','windowactivate','--sync',active],capture_output=True,text=True,timeout=10)
 restored=p.returncode==0
 if not restored:raise RuntimeError('Failed to restore initial foreground window')
result.update(started_additional_original_chrome=started,initial_active_window=active,foreground_restored=restored,existing_browser_pids=processes)
(root/'cdp.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
'''.replace("ROOT", repr(root), 1)
    return _execute(env, code, timeout=90)


def _launch_job(env, metadata: dict, folder: Path, kind: str, cdp: dict,
                actor_config: dict | None, instruction: str | None) -> int:
    root = metadata["guest_root"]
    settings = metadata["config"]["runtime"]
    bundle = Path(metadata["bundle_path"])
    job = {"schema_version": 1, "kind": kind, "guest_root": root,
           "bundle_sha256": _digest(bundle), "uv_binary_sha256": metadata["uv_binary_sha256"],
           "guest_python": settings["guest_python"],
           "bootstrap_timeout_seconds": settings["bootstrap_timeout_seconds"],
           "actor_grace_seconds": settings["actor_grace_seconds"],
           "cdp_url": cdp["endpoint"]}
    if kind == "actor":
        job.update(actor_config=actor_config, instruction=instruction)
    _upload(env, bundle, root + "/runtime-bundle.tar.gz")
    _upload(env, Path(metadata["harness_root"]) / "guest_bootstrap.py", root + "/guest_bootstrap.py")
    if (folder / "initial.png").exists():
        _upload(env, folder / "initial.png", root + "/initial.png")
    with tempfile.TemporaryDirectory(prefix="osworld-private-job-") as temporary:
        path = Path(temporary) / "job.json"
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
            json.dump(job, stream)
        _upload(env, path, root + "/job.json")
    # Start exactly once. A lost launch response is a transport failure, never a
    # reason to replay an operation that may already have started the Actor.
    code = '''import json,os,pathlib,subprocess
root=pathlib.Path(ROOT);root.chmod(0o700);(root/'job.json').chmod(0o600)
with (root/'bootstrap.log').open('ab') as log:
 process=subprocess.Popen(['python3',str(root/'guest_bootstrap.py'),str(root/'job.json')],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
(root/'bootstrap.pid').write_text(str(process.pid))
print(json.dumps({'pid':process.pid}))
'''.replace("ROOT", repr(root), 1)
    return int(_execute(env, code)["pid"])


def _wait_job(env, metadata: dict, pid: int, kind: str, folder: Path) -> dict:
    settings = metadata["config"]["runtime"]
    limit = settings["bootstrap_timeout_seconds"] + (
        300 if kind == "probe" else metadata["config"]["actor"]["timeout_seconds"]
    ) + settings["actor_grace_seconds"] + 60
    deadline = time.monotonic() + limit
    previous_stage = None
    root = metadata["guest_root"]
    code = '''import json,os,pathlib
root=pathlib.Path(ROOT);state=root/'bootstrap-state.json'
value=json.loads(state.read_text()) if state.exists() else {'stage':'starting'}
try:os.kill(PID,0);alive=True
except ProcessLookupError:alive=False
print(json.dumps({'alive':alive,'state':value}))
'''.replace("ROOT", repr(root), 1).replace("PID", str(pid), 1)
    while time.monotonic() < deadline:
        result = _execute(env, code)
        state = result["state"]
        if state.get("stage") != previous_stage:
            previous_stage = state.get("stage")
            _event(folder, "guest_stage", stage=previous_stage)
        # The final timestamp is written only after evidence archiving completes.
        if state.get("finished_at_epoch") is not None:
            return state
        if not result["alive"]:
            raise RuntimeError("Guest bootstrap exited without a final completion receipt")
        time.sleep(settings["poll_interval_seconds"])
    raise TimeoutError("Guest bootstrap exceeded the frozen outer deadline")


def _download(env, remote: str, destination: Path) -> None:
    data = env.controller.get_file(remote, strict=True)
    if data is None:
        raise FileNotFoundError("Guest evidence file missing: " + destination.name)
    destination.write_bytes(data)


def _collect(env, metadata: dict, folder: Path, state: dict, receipt: dict, kind: str) -> dict:
    root = metadata["guest_root"]
    _write_json(folder / "bootstrap-state.json", state)
    name = "probe-result.json" if kind == "probe" else "actor-result.json"
    result = None
    try:
        _download(env, root + "/" + name, folder / name)
        result = _json(folder / name)
    except Exception as error:
        receipt["evidence_errors"].append(name + ": " + str(error))
    try:
        _download(env, root + "/actor-output.tar.gz", folder / "actor-output.tar.gz")
    except Exception as error:
        receipt["evidence_errors"].append("actor-output.tar.gz: " + str(error))
    if result is None:
        raise RuntimeError("Guest did not produce a readable product result")
    return result


def _finish_task(env, actor: dict, receipt: dict) -> None:
    result = actor.get("result", {})
    status = result.get("status")
    receipt.update(actor_status=status, agent_success=result.get("agent_success"))
    if actor.get("status") != "finished" or status not in LEGAL_ACTOR_STATUSES:
        raise RuntimeError("Actor did not finish with a valid product outcome")
    action = None
    if status == "completed" and result.get("agent_success") is False:
        action = "FAIL"
    elif status == "completed" and result.get("agent_success") is True:
        action = "DONE"
    receipt["official_terminal_action"] = action
    if action is not None:
        env.step(action, 0)
    # Reaching an Actor budget is a real task outcome. Evaluate its actual state,
    # but never convert a budget stop into FAIL (especially for infeasible tasks).
    raw_value = env.evaluate()
    if isinstance(raw_value, bool) or not isinstance(raw_value, Real):
        raise RuntimeError("Official evaluator returned a non-numeric score")
    value = float(raw_value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise RuntimeError("Official evaluator returned an invalid score")
    receipt.update(status="scored", score=value)


def probe(run_dir: Path) -> dict:
    run_dir = Path(run_dir).resolve()
    metadata = _metadata(run_dir)
    with _lock(run_dir):
        folder = run_dir / "probe-attempts" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S-") + uuid4().hex[:8])
        folder.mkdir(parents=True)
        receipt = {"schema_version": 1, "status": "failed", "started_at": _now(),
                   "run_metadata_sha256": _digest(run_dir / "run.json"),
                   "evidence_errors": [], "attempt_dir": str(folder)}
        try:
            with _environment(metadata, folder, receipt) as env:
                env.reset()
                _save_screenshot(env, folder, "initial.png", receipt)
                cdp = _ensure_cdp(env, metadata)
                _write_json(folder / "cdp.json", cdp)
                pid = _launch_job(env, metadata, folder, "probe", cdp, None, None)
                state = _wait_job(env, metadata, pid, "probe", folder)
                result = _collect(env, metadata, folder, state, receipt, "probe")
                if state.get("stage") != "finished" or result.get("status") != "passed":
                    raise RuntimeError("Guest product probe failed; inspect the attempt evidence")
                receipt.update(status="passed", product_probe=result, cdp=cdp)
        except Exception as error:
            receipt.update(error_type=type(error).__name__, error=str(error))
        if receipt.get("owned_vm_closed") is False:
            receipt["status"] = "failed"
        receipt["finished_at"] = _now()
        _write_json(folder / "receipt.json", receipt, exclusive=True)
        _write_json(run_dir / "probe.json", receipt)
        return receipt


def run_tasks(run_dir: Path, model_config: Path, task_ids: list[str] | None = None) -> dict:
    run_dir = Path(run_dir).resolve()
    metadata = _metadata(run_dir)
    checked = _json(run_dir / "probe.json")
    if checked.get("status") != "passed" or checked.get("run_metadata_sha256") != _digest(run_dir / "run.json"):
        raise RuntimeError("A passing model-free probe for this frozen run is required")
    private = _json(Path(model_config))
    allowed = {"base_url", "api_key", "model_proxy", "model_extra_body"}
    if set(private) - allowed or not {"base_url", "api_key"} <= private.keys():
        raise ValueError("Model config needs base_url/api_key; optional model_proxy/model_extra_body only")
    actor_config = private | metadata["config"]["actor"]
    secrets = [str(private.get(key, "")) for key in ("api_key", "model_proxy")]
    tasks = _tasks(metadata)
    selected = set(task_ids) if task_ids is not None else {task["task_id"] for task in tasks}
    unknown = selected - {task["task_id"] for task in tasks}
    if unknown:
        raise ValueError("Task IDs are outside the frozen 76-task manifest: " + ",".join(sorted(unknown)))
    counts = {"scored": 0, "invalid": 0, "skipped_existing": 0}
    with _lock(run_dir):
        for task in tasks:
            task_id = task["task_id"]
            if task_id not in selected:
                continue
            folder = run_dir / "tasks" / task_id
            destination = folder / "receipt.json"
            if destination.exists():
                counts["skipped_existing"] += 1
                continue
            if folder.exists() and any(folder.iterdir()):
                _write_json(destination, {"schema_version": 1, "task_id": task_id,
                            "status": "interrupted", "score": None, "finished_at": _now(),
                            "error": "Preserved an earlier attempt with no completion receipt"}, exclusive=True)
                counts["invalid"] += 1
                continue
            folder.mkdir(parents=True, exist_ok=True)
            receipt = {"schema_version": 1, "task_id": task_id, "category": task["category"],
                       "source_domain": task["source_domain"], "task_sha256": task["sha256"],
                       "started_at": _now(), "status": "setup_error", "score": None,
                       "budget": metadata["config"]["actor"], "evidence_errors": []}
            started = time.monotonic()
            phase = "setup_error"
            interrupted = False
            try:
                source = Path(metadata["harness_root"]) / task["task_path"]
                if _digest(source) != task["sha256"]:
                    raise ValueError("Frozen task JSON hash mismatch")
                example = _json(source)
                _event(folder, "task_started", task_id=task_id)
                with _environment(metadata, folder, receipt) as env:
                    env.reset(task_config=example)
                    _save_screenshot(env, folder, "initial.png", receipt)
                    recording = False
                    try:
                        env.controller.start_recording()
                        recording = True
                    except Exception as error:
                        receipt["evidence_errors"].append("recording_start: " + str(error))
                    try:
                        cdp = _ensure_cdp(env, metadata)
                        _write_json(folder / "cdp.json", cdp)
                        phase = "transport_error"
                        pid = _launch_job(env, metadata, folder, "actor", cdp, actor_config, example["instruction"])
                        state = _wait_job(env, metadata, pid, "actor", folder)
                        phase = ("bootstrap_error" if state.get("stage") == "failed"
                                 and state.get("phase") in (None, "install") else "actor_error")
                        actor = _collect(env, metadata, folder, state, receipt, "actor")
                        if state.get("stage") != "finished":
                            raise RuntimeError("Guest bootstrap/Actor process failed; inspect preserved evidence")
                        _save_screenshot(env, folder, "final.png", receipt)
                        native = actor.get("result", {})
                        receipt.update(actor_status=native.get("status"), agent_success=native.get("agent_success"))
                        if actor.get("status") != "finished" or native.get("status") not in LEGAL_ACTOR_STATUSES:
                            raise RuntimeError("Actor process returned no legal task outcome")
                        phase = "evaluation_error"
                        _finish_task(env, actor, receipt)
                    finally:
                        if recording:
                            try:
                                env.controller.end_recording(str(folder / "recording.mp4"))
                                if not (folder / "recording.mp4").is_file():
                                    raise RuntimeError("Recording was not saved")
                            except Exception as error:
                                receipt["evidence_errors"].append("recording_end: " + str(error))
            except KeyboardInterrupt:
                interrupted = True
                receipt.update(status="interrupted", error_type="KeyboardInterrupt", score=None)
            except Exception as error:
                receipt.update(status=phase, error_type=type(error).__name__,
                               error=_redact(str(error), secrets), score=None)
            receipt.update(finished_at=_now(), elapsed_seconds=time.monotonic() - started)
            receipt["evidence_errors"] = [_redact(message, secrets) for message in receipt["evidence_errors"]]
            _write_json(destination, receipt, exclusive=True)
            _event(folder, "task_finished", status=receipt["status"], score=receipt["score"])
            counts["scored" if receipt["status"] == "scored" else "invalid"] += 1
            if interrupted:
                raise KeyboardInterrupt
            if receipt.get("owned_vm_closed") is False:
                raise RuntimeError("Owned VM cleanup failed; inspect the receipt before dispatching another task")
    return {"schema_version": 1, "task_count": 76, "selected_count": len(selected), **counts}
