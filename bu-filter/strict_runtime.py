"""Run the frozen df93 controller with the approved 87-task count adaptation.

The original function ASTs are loaded from the preserved reference. The task count and Actor profile assertions use the current fixed configuration. Runtime paths are bound to the
new self-contained run; no scheduling, timeout, retry, or prompt logic is added.
"""
from __future__ import annotations

import ast
import asyncio
from collections import Counter
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REFERENCE = HERE / "legacy" / "reference" / "df93-run.py.txt"
REFERENCE_SHA256 = "c64d11096834dcf3550b4009ab76d4c9e81d9ca957284897d90ad97cad4e6fc0"
FUNCTIONS = ("read", "write", "sha", "actor_command", "invoke", "grade", "run")


def _hash_ast(node: ast.AST) -> str:
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def _extracted_module() -> tuple[ast.Module, dict]:
    raw = REFERENCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != REFERENCE_SHA256:
        raise ValueError("Frozen df93 controller reference checksum mismatch")
    source = ast.parse(raw.decode(), filename=str(REFERENCE))
    original = {node.name: node for node in source.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if not set(FUNCTIONS) <= original.keys():
        raise ValueError("Frozen df93 controller function set is incomplete")
    selected = [copy.deepcopy(original[name]) for name in FUNCTIONS]
    run = next(node for node in selected if node.name == "run")
    changes = []
    for node in ast.walk(run):
        if (isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq)
                and len(node.comparators) == 1 and isinstance(node.comparators[0], ast.Constant)
                and node.comparators[0].value == 100
                and isinstance(node.left, ast.Call) and isinstance(node.left.func, ast.Name)
                and node.left.func.id == "len" and len(node.left.args) == 1
                and isinstance(node.left.args[0], ast.Subscript)
                and isinstance(node.left.args[0].value, ast.Name)
                and node.left.args[0].value.id == "plan"
                and isinstance(node.left.args[0].slice, ast.Constant)
                and node.left.args[0].slice.value == "jobs"):
            node.comparators[0] = ast.copy_location(ast.Constant(value=87), node.comparators[0])
            changes.append({"function": "run", "line": node.lineno,
                            "expression": "len(plan['jobs'])", "before": 100, "after": 87})
    if len(changes) != 1:
        raise ValueError("Expected exactly one approved df93 100-to-87 task-count adaptation")
    # Keep the original scheduler, admission and resume logic. Bind only the product profile checks.
    bindings = {
        "plan['review_answer'] and plan['request_budget_includes_answer_review']":
            "plan['feature_config'] == {} and plan['agent_reasoning'] == 'max'",
        "public_config.get('reasoning_effort', 'high') == 'high'":
            "public_config['reasoning_effort'] == 'max'",
        "public_config.get('mode', 'ultrafast') == 'ultrafast'":
            "public_config['mode'] == 'default'",
    }
    for statement in run.body:
        if isinstance(statement, ast.Assert) and (expression := ast.unparse(statement.test)) in bindings:
            new = ast.parse(bindings[expression], mode="eval").body
            statement.test = ast.copy_location(new, statement.test)
            changes.append({"function": "run", "line": statement.lineno,
                            "before": expression, "after": bindings[expression]})
    if len(changes) != 4:
        raise ValueError("Expected the task count and three Actor profile checks")
    extracted = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    audit = {
        "reference_sha256": REFERENCE_SHA256,
        "approved_ast_changes": changes,
        "functions": {
            node.name: {"original_ast_sha256": _hash_ast(original[node.name]),
                        "runtime_ast_sha256": _hash_ast(node),
                        "unchanged": _hash_ast(original[node.name]) == _hash_ast(node)}
            for node in selected
        },
    }
    return extracted, audit


def source_audit() -> dict:
    """Return code-identity evidence without executing the controller or a task."""
    return _extracted_module()[1]


def _install_environment(run: Path, root: Path, code: Path, legacy: Path) -> None:
    from legacy.environment_bindings import install
    install(run, root, code, legacy)


def load_runtime(run_dir) -> dict:
    """Bind the preserved original functions to one prepared BU-filter run."""
    run = Path(run_dir).expanduser().absolute()
    settings = json.loads((run / "settings.json").read_bytes())
    plan = json.loads((run / "plan.json").read_bytes())
    # Do not resolve interpreter symlinks: the virtualenv path selects its packages.
    agent_python = Path(os.path.abspath(os.path.expanduser(settings["agent_python"])))
    judge_python = Path(os.path.abspath(os.path.expanduser(settings["judge_python"])))
    root = run / "support"
    code = run / "frozen" / "harness" / "legacy" / "code"
    product = run / "product"
    namespace = {
        "__name__": "bu_filter_original_df93_controller",
        "__file__": str(run / "driver" / "run.py"),
        "asyncio": asyncio, "fcntl": fcntl, "hashlib": hashlib, "json": json,
        "os": os, "signal": signal, "subprocess": subprocess, "sys": sys,
        "time": time, "Counter": Counter, "Path": Path,
        "RUN": run, "ROOT": root, "PRODUCT": product,
        "ENV": agent_python.parent.parent, "CODE": code,
        "SOURCE": product / "src", "LEGACY": judge_python,
        "DEPENDENCIES": code, "OLD": root / "previous-capacity",
        "COMMIT": plan["product_commit"],
    }
    tree, audit = _extracted_module()
    exec(compile(tree, str(REFERENCE), "exec"), namespace)
    _install_environment(run, root, code, judge_python)
    namespace["SOURCE_AUDIT"] = audit
    return namespace


def main(run_dir) -> None:
    """Retain the original positional run/judge subprocess interface."""
    namespace = load_runtime(run_dir)
    command = sys.argv[1] if len(sys.argv) > 1 else None
    if command == "judge":
        job = next(job for job in namespace["read"](namespace["RUN"] / "plan.json")["jobs"]
                   if (job["suite"], job["task_id"]) == tuple(sys.argv[2:4]))
        asyncio.run(namespace["grade"](job))
    elif command == "run":
        with (namespace["RUN"] / "controller.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            asyncio.run(namespace["run"]())
    else:
        raise ValueError("The prepared controller supports only run or judge <suite> <task_id>")
