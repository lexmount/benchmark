"""Reuse the BU-filter path-binding approach; keep legacy function bodies intact."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent


def install(run, support, code, judge_python):
    from dataset import sha
    support, code = Path(support).resolve(), Path(code).resolve()
    provenance = json.loads((PACKAGE / 'provenance.json').read_bytes())
    originals = provenance['original_files_sha256']
    for relative, expected in originals.items():
        if sha(PACKAGE / relative) != expected:
            raise ValueError('Frozen original changed: ' + relative)
    record = {name: digest for name, digest in originals.items()}
    source_file = support / 'sources.json'
    if source_file.exists() and json.loads(source_file.read_bytes()) != record:
        raise ValueError('Frozen source record changed')
    if not source_file.exists():
        source_file.write_text(json.dumps(record, indent=2) + '\n')
    sys.path.insert(0, str(code))
    modules = {}
    for name in ('continue_evaluate', 'evidence_ranges', 'evidence_adapter', 'eval_billing',
                 'judge_refusals_dedup', 'image_transport', 'full_benchmarks'):
        path = code / (name + '.py')
        if sha(path) != originals['legacy/code/' + name + '.py']:
            raise ValueError('Runtime copy differs from original: ' + name)
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        modules[name] = module

    def verify():
        for relative, expected in originals.items():
            if sha(PACKAGE / relative) != expected:
                raise ValueError('Frozen original changed: ' + relative)
        if json.loads(source_file.read_bytes()) != record:
            raise ValueError('Source record changed')

    for name in ('continue_evaluate', 'judge_refusals_dedup', 'full_benchmarks'):
        module = modules[name]
        for key, value in {'ROOT': support, 'EVAL': PACKAGE, 'PYTHON': Path(judge_python),
                           'LEGACY_PYTHON': Path(judge_python), 'OD': PACKAGE / 'legacy/upstream',
                           'BU': PACKAGE / 'legacy/unused-bu', 'verify': verify}.items():
            setattr(module, key, value)
    modules['eval_billing'].PRIVATE_CONFIG_PATH = support / '.private/model.json'
    return modules['full_benchmarks']
