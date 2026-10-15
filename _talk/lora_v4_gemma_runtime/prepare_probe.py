"""CPU preparation and regression admission for one four-input Planner probe."""
import hashlib
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from planner_policy import CONTRACT, SCHEMA_INSTRUCTION

ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent / 'lora_v4_multibase'
OUT = ROOT / 'runs/harness_v5_schema_20261014b'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    global OUT
    parser = argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=OUT)
    OUT = parser.parse_args().out.resolve()
    assert OUT.is_relative_to((ROOT / 'runs').resolve()), 'Probe output outside v5 runs'
    assert not OUT.exists(), 'Existing probe directory; do not overwrite or repeat'
    test = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'unittest', 'discover', '-s', str(ROOT), '-p', 'test_*.py', '-v'],
                          capture_output=True, text=True, encoding='utf-8')
    assert test.returncode == 0, test.stdout + test.stderr
    cases = []
    source_hashes = {}
    for arm in ['B_CONTROL', 'BC_IMPROVED']:
        path = OLD / 'runs/offload_20261009/gemma4_26b_a4b/runtime_bc_10m' / arm / 'io.jsonl'
        source_hashes[str(path)] = sha(path)
        rec = json.loads(path.read_text(encoding='utf-8').splitlines()[0])
        previous = rec['planner_attempts'][0]
        state = json.loads(previous['input_text'].split('【現在状態】\n', 1)[1].split('\n\n【Memory候補】', 1)[0])
        inp = {'recent': rec['recent_input_text'], 'current_state': state,
               'memory_candidates': rec['candidate'], 'previous_plan': rec['active_bundle_before']['plan']}
        assert CONTRACT['planner_prompt'](inp) == previous['input_text']
        cases.append({'id': 'initial_' + arm, 'input': inp, 'baseline_schema_valid': previous['schema_valid'],
                      'baseline_first_call': previous, 'source': str(path), 'source_log_turn': 0})
    path = OLD / 'runs/offload_20261009/gemma4_26b_a4b/planner_evaluation/planner_test.json'
    source_hashes[str(path)] = sha(path)
    records = read(path)['records']
    for condition in ['REL', 'NONE']:
        rec = next(r for r in records if r['condition'] == condition and r['parse_valid'])
        previous = rec['attempts'][0]
        assert CONTRACT['planner_prompt'](rec['input']) == previous['input_text']
        cases.append({'id': 'heldout_' + rec['id'], 'input': rec['input'], 'baseline_schema_valid': rec['parse_valid'],
                      'baseline_first_call': previous, 'source': str(path), 'source_record_id': rec['id']})
    assert len(cases) == 4
    selection = read(OLD / 'model_selection.json')
    assert selection['primary_candidate']['key'] == 'gemma4_26b_a4b'
    adapter = Path(selection['primary_candidate']['adapters']['planner']['directory']) / 'adapter_model.safetensors'
    assert sha(adapter) == selection['primary_candidate']['adapters']['planner']['sha256']
    OUT.mkdir(parents=True)
    (OUT / 'executed_code').mkdir()
    code_paths = [ROOT / name for name in ['planner_policy.py', 'planner_probe.py', 'inference_v5.py',
                 'schema_constraints.py', 'runtime_state.py', 'alpha_contract.py',
                 'test_runtime_state.py', 'test_planner_policy.py', 'test_schema_constraints.py', 'prepare_probe.py']]
    code_paths += [OLD / name for name in ['inference_models.py', 'load_offloaded.py', 'offload_backend.py', 'model_layout.py',
                                          'prepare_data.py', 'multibase_common.py', 'probe.py', 'child_guard.py', 'atomic_state.py']]
    code_paths += [ROOT.parent / 'lora_v4_runtime_bc/policy.py', ROOT.parent / 'lora_v4_planner_talk/contracts.py']
    hashes = {str(path): sha(path) for path in code_paths}
    dependency_hashes = {str(path): sha(path) for path in (ROOT / 'dependencies').rglob('*')
                         if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc'}
    for i, path in enumerate(code_paths):
        shutil.copy2(path, OUT / 'executed_code' / f'{i:02d}_{path.name}')
    protocol = {'stage': 'Planner schema only', 'goal': 'facts-preserving natural speech; this stage does not certify it',
                'model': 'gemma4_26b_a4b', 'planner_adapter_sha256': sha(adapter),
                'cases': 4, 'maximum_attempts_per_case': 2, 'maximum_generation_calls': 8,
                'fixed_generation': {'do_sample': False, 'max_new_tokens': 192, 'budget': 928, 'seed': 20260925},
                'changes': ['JSON Schema token mask', 'whole-object-only strict adoption; no substring rescue',
                            'specific format feedback before the single retry'],
                'schema_instruction': SCHEMA_INSTRUCTION, 'Memory_recent_previous_Plan_unchanged': True,
                'Talk_calls': 0, 'training_runs': 0, 'new_model_downloads': 0,
                'automatic_restart': False, 'same_configuration_quality_rerun': False,
                'source_hashes': source_hashes, 'code_hashes': hashes, 'dependency_hashes': dependency_hashes,
                'constraint_backend': 'lm-format-enforcer==0.11.3; isolated dependencies',
                'constraint_scope': 'JSON keys/types/ID enum or null/flow bounds during decoding; boolean-ID relation at adoption',
                'comparison_limit': 'stored baseline outputs; same input payload/adapter/greedy, changed prompt/token mask/adoption; fact gate not implemented; no Talk quality claim'}
    for name, value in [('cases.json', cases), ('protocol.json', protocol),
                        ('cpu_preflight.json', {'status': 'pass', 'test_exit_code': test.returncode,
                                                'test_output': test.stdout + test.stderr, 'real_model_outputs_in_CPU_test': False})]:
        (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'prepared', 'out': str(OUT), 'cases': 4, 'max_calls': 8}, ensure_ascii=False))


if __name__ == '__main__':
    main()
