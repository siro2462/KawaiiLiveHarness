"""Exactly one short, isolated Gemma Planner generation pass. No training/Talk."""
import hashlib
import argparse
import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent / 'lora_v4_multibase'
OUT = ROOT / 'runs/harness_v5_schema_20261014b'
sys.path.insert(0, str(OLD))
from atomic_state import write
from multibase_common import Lock, SEED, now
sys.path.insert(0, str(ROOT))
from planner_policy import obtain_plan


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    global OUT
    parser = argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=OUT)
    OUT = parser.parse_args().out.resolve()
    assert OUT.is_relative_to((ROOT / 'runs').resolve()), 'Probe output outside v5 runs'
    manifest = OUT / 'manifest.json'
    assert not manifest.exists(), 'Existing inference manifest; do not duplicate or rerun'
    protocol = read(OUT / 'protocol.json')
    assert read(OUT / 'cpu_preflight.json')['status'] == 'pass'
    for path, digest in {**protocol['code_hashes'], **protocol['source_hashes'], **protocol['dependency_hashes']}.items():
        assert sha(Path(path)) == digest, path
    import psutil
    state = {'status': 'running', 'stage': 'Planner schema only', 'phase': 'load_models',
             'pid': os.getpid(), 'parent_pid': os.getppid(),
             'create_time': psutil.Process().create_time(), 'started': now(),
             'model': 'gemma4_26b_a4b', 'completed_cases': 0, 'total_cases': 4,
             'quality_pass': False, 'Talk_calls': 0, 'root_review': 'pending'}
    write(manifest, state)
    records = []
    try:
        with Lock(OLD / 'gpu.lock'), Lock(ROOT.parent / 'lora_v4_planner_talk/gpu.lock'):
            from inference_v5 import V5Models
            models = V5Models(planner_only=True)
            assert models.hashes['planner'] == protocol['planner_adapter_sha256']
            for index, case in enumerate(read(OUT / 'cases.json')):
                state.update(phase='generate', current_case=case['id'], updated=now())
                write(manifest, state)
                def generate(prompt, recent, retry):
                    return models.constrained_plan(prompt, recent,
                        [m['id'] for m in case['input']['memory_candidates']], SEED + retry)
                selected, attempts = obtain_plan(generate, case['input'])
                records.append({'case_id': case['id'], 'input': case['input'],
                                'baseline_schema_valid': case['baseline_schema_valid'],
                                'plan': selected, 'attempts': attempts, 'formal_valid': selected is not None,
                                'factuality': 'root review required; schema acceptance is not factuality proof'})
                write(OUT / 'results.json', {'status': 'running', 'records': records})
                state.update(completed_cases=index+1, updated=now())
                write(manifest, state)
            state.update(status='outputs_ready', phase='complete', finished=now(),
                         formal_valid_cases=sum(r['formal_valid'] for r in records),
                         generation_calls=sum(len(r['attempts']) for r in records),
                         actual_adapter_hashes=models.hashes)
            write(OUT / 'results.json', {'status': 'complete', 'records': records,
                                        'quality': 'Planner schema stage; Talk not generated, root review pending'})
            write(manifest, state)
    except BaseException as exc:
        state.update(status='failed', error=str(exc), traceback=traceback.format_exc(), finished=now())
        write(manifest, state)
        raise


if __name__ == '__main__':
    main()
