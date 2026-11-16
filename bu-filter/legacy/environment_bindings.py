"""Bind frozen evaluation modules to BU-filter paths without rewriting functions.

The actor, worker, judge, evidence and transport source files remain verbatim.
The original source verification used the retired 100-task/other-benchmark
paths; this adapter verifies the bundled frozen sources instead.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

LEGACY = Path(__file__).resolve().parent


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_frozen():
    manifest = json.loads((LEGACY / "provenance.json").read_text())
    for relative, entry in manifest["files"].items():
        path = (LEGACY / relative).resolve()
        if not path.is_relative_to(LEGACY):
            raise RuntimeError("Frozen source path escapes the legacy package")
        if _sha(path) != entry["sha256"]:
            raise RuntimeError("Frozen evaluation source changed: " + relative)
    return manifest


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _source_record(manifest):
    return {"bu-filter/legacy/" + name: entry["sha256"] for name, entry in manifest["files"].items()}


def _write_source_record(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if json.loads(path.read_text()) != record:
            raise RuntimeError("Support source record differs from the frozen package")
        return
    with tempfile.NamedTemporaryFile("w", dir=path.parent, encoding="utf-8", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def install(run, support_root, code, judge_python):
    """Return the original full_benchmarks module with path/check bindings only.

    Callers provide one-run task selection separately. This function does not
    load dataset rows, choose tasks, request a model or change judge parameters.
    support_root/.private/model.json is prepared by the external controller.
    """
    run, support_root, code = map(lambda p: Path(p).resolve(), (run, support_root, code))
    judge_python = Path(judge_python).expanduser().absolute()
    if code != LEGACY / "code":
        raise ValueError("code must be this package's frozen legacy/code directory")
    manifest = verify_frozen()
    sys.path.insert(0, str(code))
    # Explicitly load the frozen modules even when a test or launcher imported
    # similarly named modules previously. Each real Judge is a fresh process.
    modules = {}
    for name in ("continue_evaluate", "evidence_ranges", "evidence_adapter", "eval_billing",
                 "judge_refusals_dedup", "image_transport", "full_benchmarks"):
        modules[name] = _module(name, code / (name + ".py"))
    upstream = LEGACY / "upstream"
    source_record = _source_record(manifest)
    _write_source_record(support_root / "sources.json", source_record)

    def verify():
        verify_frozen()
        if json.loads((support_root / "sources.json").read_text()) != source_record:
            raise RuntimeError("Frozen source record changed")

    for name in ("continue_evaluate", "judge_refusals_dedup", "full_benchmarks"):
        module = modules[name]
        for key, value in {
            "ROOT": support_root, "EVAL": LEGACY, "PYTHON": judge_python,
            "LEGACY_PYTHON": judge_python, "BU": upstream, "OD": upstream / "unused-odysseys",
            "SOURCES": [LEGACY / name for name in manifest["files"]],
            "verify": verify,
        }.items():
            setattr(module, key, value)
    modules["eval_billing"].PRIVATE_CONFIG_PATH = support_root / ".private/model.json"
    full = modules["full_benchmarks"]
    full._bu_filter_bindings = {
        "run": str(run), "support_root": str(support_root), "code": str(code),
        "judge_python": str(judge_python), "source_record": source_record,
        "function_bodies_modified": False,
    }
    verify()
    return full
