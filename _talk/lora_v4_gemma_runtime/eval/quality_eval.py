"""Evaluation-only v5 diagnostics. Does not patch or commit into the Runtime."""
import argparse
import copy
import hashlib
import json
import os
import re
import sys
import time
import traceback
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEEDS = [20260925, 20260926, 20260927]
FALLBACK_REVIEWS = {
    134: 'S4B: bought umbrella; two already on shelf; new one in commuting bag. All Plan beats are supported.',
    260: 'S2B: forgot switch, no rice, curry on udon. Last beat is subjective framing, not a new event.',
    294: 'S2B: no rice because switch was not pushed; curry on frozen udon. Repeated but source-consistent.',
    301: 'S2B: switch forgotten, rice not cooked, food on udon. Repeated beat adds no new experience.',
}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def rows(path):
    return [json.loads(s) for s in Path(path).read_text(encoding='utf-8-sig').splitlines() if s.strip()]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write(path, value):
    # Reuse the previously tested Windows atomic writer after bootstrap.
    from atomic_state import write as atomic_write
    atomic_write(path, value)


def jsonl(path, values):
    with Path(path).open('x', encoding='utf-8') as f:
        for value in values:
            f.write(json.dumps(value, ensure_ascii=False) + '\n')


def bootstrap(runtime_root):
    root = Path(runtime_root).resolve(strict=True)
    for path in [root.parent / 'lora_v4_multibase', root / 'dependencies', root / 'morphology_dependencies', root]:
        sys.path.insert(0, str(path))
    return root


def health(plan):
    if plan is None:
        return {'accepted': False, 'issues': ['missing_plan']}
    issues = []
    fields = [plan['topic'], *plan['flow']]
    for text in fields:
        if not any(unicodedata.category(c)[0] in {'L', 'N'} for c in text):
            issues.append('symbol_only_string')
        if re.search(r'<\s*/?\s*(?:h[1-6]|html|body|script)\b', text, re.I):
            issues.append('html_markup')
        if re.search(r'(?m)^\s*#{1,6}\s+\S', text):
            issues.append('markdown_heading')
    normalized = [unicodedata.normalize('NFKC', t).strip() for t in plan['flow']]
    if len(normalized) >= 2 and len(set(normalized)) == 1:
        issues.append('all_flow_beats_identical')
    return {'accepted': not issues, 'issues': sorted(set(issues)),
            'scope': 'deterministic corruption checks only; semantic validity unverified'}


def cluster(case_id):
    return case_id.split('-')[0] if case_id.startswith('H') else case_id[:2]


def source_context(call):
    prompt = call['input_text']
    start, end = call['recent_span']
    assert prompt[start:end] == call['recent']
    assert call.get('context_cut_tokens', 0) == 0, 'Choose uncut development inputs only'
    return {'prompt': prompt, 'recent': call['recent'], 'recent_span': [start, end],
            'grounding': copy.deepcopy(call['original_grounding'])}


def analyze_retrieval(records):
    result = []
    for record in records:
        retrieval = record.get('retrieval')
        if not retrieval:
            continue
        ranked = retrieval['ranked']
        best = ranked[0]
        runner = ranked[1] if len(ranked) > 1 else None
        result.append({'log_turn': record['turn'], 'display_turn': record['turn'] + 1,
                       'query': retrieval['query_text'], 'top5': ranked[:5],
                       'top_id': retrieval['top_id'], 'threshold': retrieval['threshold'],
                       'best_second_gap': best['score'] - runner['score'] if runner else None,
                       'blocked_id': retrieval.get('excluded_id'),
                       'excluded_reason': 'repetition path' if retrieval.get('excluded_id') else 'no exclusion',
                       'alternative_above_threshold': any(r['score'] >= retrieval['threshold'] for r in ranked[1:]),
                       'interpretation': 'ranking observation; changing query was not tested'})
    return result


def replay(source, out):
    from fact_gate import check_plan, check_text
    calls = {r['call_id']: r for r in rows(source / 'all_calls.jsonl')}
    candidates, plans, fixed = [], [], []
    seen = set()
    for path in sorted(source.rglob('io.jsonl')):
        for record in rows(path):
            for attempt in record.get('planner_attempts', []):
                call_id = attempt.get('actual_generation_call_id')
                if call_id is None or call_id in seen:
                    continue
                seen.add(call_id)
                plan = json.loads(attempt['text']) if attempt['schema_valid'] else None
                plans.append({'source_call_id': call_id, 'source_record': str(path.relative_to(source)),
                              'schema_valid': attempt['schema_valid'], 'plan': plan,
                              'health': health(plan), 'saved_fact_check': attempt['factual_validation'],
                              'semantic_label': None, 'reviewer_kind': None})
            if 'fixed36' in path.parts:
                fixed.append({'source_record': str(path.relative_to(source)), 'turn': record['turn'],
                              'plan': record['plan'], 'played_text': record['played_text']})
    # Single-shot diagnostics do not store Planner attempts in io.jsonl.
    for call_id, call in calls.items():
        if call['role'] == 'planner' and call_id not in seen:
            from planner_policy import parse_plan
            ids = re.findall(r'"id"\s*:\s*"([^"]+)"', call['input_text'])
            try:
                plan = parse_plan(call['text'], ids)
                valid = True
            except (ValueError, TypeError, KeyError):
                plan, valid = None, False
            plans.append({'source_call_id': call_id, 'schema_valid': valid, 'plan': plan,
                          'health': health(plan), 'semantic_label': None, 'reviewer_kind': None})
        if call['role'] == 'talk':
            grounding = call['original_grounding']
            sources = [{k: grounding[k] for k in ['id', 'body']}] if grounding else []
            candidates.append({'source_call_id': call_id, 'stage': call['stage'], 'case': call['case'],
                               'text': call['text'], 'source_memory': sources,
                               'rule_result': check_text(call['text'], sources),
                               'content_label': None, 'gate_reason_label': None, 'reviewer_kind': None})
    assert len(plans) == 100 and len(candidates) == 248
    jsonl(out / 'saved_planner_replay.jsonl', sorted(plans, key=lambda r: r['source_call_id']))
    jsonl(out / 'saved_candidate_replay.jsonl', candidates)
    jsonl(out / 'saved_fixed36.jsonl', fixed)
    retrieval = analyze_retrieval(rows(source / 'long2700/retrieval/GUARDED/io.jsonl'))
    jsonl(out / 'retrieval29.jsonl', retrieval)
    from evaluate_fact_gate import CASES
    cases = [{'id': c[0], 'category': c[1], 'text': c[2], 'expected_allowed': c[4],
              'actual_allowed': check_text(c[2], [c[3]])['accepted']} for c in CASES]
    write(out / 'authored_gate_regressions.json', {'scope': 'known development cases, not model factual accuracy', 'records': cases})
    long = rows(source / 'long2700/retrieval/GUARDED/io.jsonl')
    attempts = [p for r in long for p in r['planner_attempts']]
    write(out / 'baseline_audit.json', {
        'Planner_calls': len(plans), 'Talk_calls': len(candidates), 'long_Planner_calls': len(attempts),
        'long_Planner_commits': sum(bool(r['pending_bundle']) for r in long),
        'long_schema_rejected': sum(not p['schema_valid'] for p in attempts),
        'long_fact_rejected': sum(p['schema_valid'] and not p['factual_validation']['accepted'] for p in attempts),
        'retrieval_count': len(retrieval), 'top_ids': dict(Counter(r['top_id'] for r in retrieval)),
        'alternatives_above_threshold': sum(r['alternative_above_threshold'] for r in retrieval),
        'human_labels': 0, 'quality_improvement': None})


def prepare(root, source, out):
    out.mkdir(parents=True, exist_ok=False)
    calls = {r['call_id']: r for r in rows(source / 'all_calls.jsonl')}
    fixtures = []
    for file, count in [('memory_swap.json', 20), ('heldout_speech.json', 10)]:
        selected = [r for r in read(source / file)['records'] if r['context_policy'] == 'CURRENT_ALWAYS'][:count]
        assert len(selected) == count
        for record in selected:
            first = record['speech_attempts'][0]
            call = calls[first['actual_generation_call_id']]
            context = source_context(call)
            fixtures.append({'id': record['id'], 'cluster_id': cluster(record['id']),
                             'source_call_id': call['call_id'], 'context': context, 'input_ids': call['input_ids'],
                             'source_plan': record['plan_adopted_for_first_attempt'],
                             'split': 'development', 'previously_observed': True})
    assert len(fixtures) == 30 and len({r['id'] for r in fixtures}) == 30
    jsonl(out / 'stop_fixtures.jsonl', fixtures)
    from context_runtime import speech_context
    from fact_gate import check_plan
    fallback = []
    for file in ['memory_swap.json', 'heldout_speech.json']:
        for record in read(source / file)['records']:
            for a in record['speech_attempts']:
                call_id = a['actual_generation_call_id']
                if call_id not in FALLBACK_REVIEWS:
                    continue
                call = calls[call_id]
                fallback.append({'id': 'rejection-' + str(call_id), 'source_call_id': call_id,
                                 'cluster_id': cluster(record['id']), 'context': source_context(call),
                                 'plan': a['plan_used'], 'feedback': a['memory_consistency']['feedback']})
    for record in rows(source / 'long2700/retrieval/GUARDED/io.jsonl'):
        for a in record['speech_attempts']:
            call_id = a['actual_generation_call_id']
            if call_id in FALLBACK_REVIEWS:
                call = calls[call_id]
                fallback.append({'id': 'rejection-' + str(call_id), 'source_call_id': call_id,
                                 'cluster_id': 'S2', 'context': source_context(call),
                                 'plan': a['plan_used'], 'feedback': a['memory_consistency']['feedback']})
    assert {r['source_call_id'] for r in fallback} == set(FALLBACK_REVIEWS)
    for fixture in fallback:
        ref = fixture['context']['grounding']
        memory = {k: ref[k] for k in ['id', 'body']}
        assert check_plan(fixture['plan'], [memory])['accepted']
        expected = speech_context(fixture['context']['recent'], [], memory, fixture['plan'])
        assert expected['prompt'] == fixture['context']['prompt']
        fixture['plan_review'] = {'reviewer_kind': 'AI_root', 'independent_of_CPU_gate': True,
                                  'human_label': False, 'verdict': 'source_supported_plan',
                                  'reason': FALLBACK_REVIEWS[fixture['source_call_id']]}
    jsonl(out / 'fallback_fixtures.jsonl', fallback)
    replay(source, out)
    old = read(source / 'protocol.json')
    protected = [p for p in root.glob('*.py')]
    protected += [root.parent / 'lora_v4_multibase' / n for n in
                  ['inference_models.py', 'load_offloaded.py', 'offload_backend.py', 'model_layout.py',
                   'multibase_common.py', 'prepare_data.py', 'probe.py', 'atomic_state.py', 'child_guard.py']]
    identities = {str(p): sha(p) for p in protected}
    for p, digest in old['source_hashes'].items():
        assert sha(p) == digest, 'Old reference identity changed: ' + p
    protocol = {'created_unix': time.time(), 'runtime_root': str(root), 'source_run': str(source),
                'model': 'gemma4_26b_a4b', 'adapter_hashes': old['adapter_hashes'],
                'seeds': SEEDS, 'stop_pairs': 90, 'fallback_pairs': 12, 'expected_Talk_calls': 204,
                'new_Planner_calls': 0, 'training': False, 'automatic_restart': False,
                'max_new_tokens': 96, 'input_budget': 928, 'sampling': old['generation'],
                'runtime_code_hashes': identities,
                'eval_code_hashes': {str(p): sha(p) for p in HERE.glob('*.py')},
                'input_hashes': {str(p): sha(p) for p in [source / 'all_calls.jsonl', source / 'protocol.json',
                     out / 'stop_fixtures.jsonl', out / 'fallback_fixtures.jsonl']},
                'human_review_status': 'pending; AI_root is not human',
                'scope': 'fixed single-output stop AB and event-conditional retry AB; no long-session causal claim',
                'limits': ['observed development inputs', 'shared scene/episode clusters',
                           'fallback Plan labels are unblinded AI_root review', 'no production playback']}
    write(out / 'protocol.json', protocol)
    print(json.dumps({'prepared': str(out), 'Talk_calls': 204, 'human_ratings': 'pending'}))


def verify_protocol(out):
    cfg = read(out / 'protocol.json')
    for group in ['runtime_code_hashes', 'eval_code_hashes', 'input_hashes']:
        for path, digest in cfg[group].items():
            assert sha(path) == digest, 'Frozen identity changed: ' + path
    return cfg


def run(root, out):
    import psutil
    from multibase_common import Lock
    from context_runtime import protected_ids, speech_context
    from fact_gate import check_text
    from inference_runtime import RuntimeModels
    from original_runtime import hard_failure
    cfg = verify_protocol(out)
    assert read(out / 'cpu_preflight.json')['status'] == 'pass'
    assert not (out / 'manifest.json').exists(), 'Never restart or overwrite an admitted run'
    state = {'status': 'running', 'phase': 'load_models', 'pid': os.getpid(),
             'create_time': psutil.Process().create_time(), 'parent_pid': os.getppid(),
             'actual_Talk_calls': 0, 'completed_pairs': 0, 'started_unix': time.time(), 'quality_pass': False}
    write(out / 'manifest.json', state)
    model = None
    try:
        with Lock(root.parent / 'lora_v4_multibase/gpu.lock'), Lock(root.parent / 'lora_v4_planner_talk/gpu.lock'):
            model = RuntimeModels()
            assert model.hashes == cfg['adapter_hashes']
            with (out / 'all_calls.jsonl').open('x', encoding='utf-8') as log, (out / 'comparisons.jsonl').open('x', encoding='utf-8') as pairs:
                def generate(context, seed, sentence_limit, experiment, case_id, side):
                    ids, audit = protected_ids(model.tok, context['prompt'], context['recent'], context['recent_span'])
                    state.update(phase=experiment, current_case=case_id, side=side, seed=seed, updated_unix=time.time())
                    write(out / 'manifest.json', state)
                    record = model.generate('v4', context['prompt'], context['recent'], seed,
                                            raw_ids=ids, budget=928, sentence_limit=sentence_limit)
                    assert record['generation']['max_new_tokens'] == 96
                    assert model.tok.decode(record['input_ids'], skip_special_tokens=False) == record['decoded_input']
                    assert model.tok.decode(record['output_ids'], skip_special_tokens=True) == record['text']
                    assert record['input_ids'] == ids
                    grounding = context['grounding']
                    sources = [{k: grounding[k] for k in ['id', 'body']}] if grounding else []
                    state['actual_Talk_calls'] += 1
                    record.update(call_id=state['actual_Talk_calls'], experiment=experiment, case_id=case_id,
                                  side=side, input_text=context['prompt'], source_grounding=grounding,
                                  fact_observation=check_text(record['text'], sources),
                                  hard_failure=hard_failure(record['text']), context_audit=audit,
                                  production_playback_committed=False, semantic_correctness=None)
                    log.write(json.dumps(record, ensure_ascii=False) + '\n'); log.flush()
                    print(json.dumps({'event': 'generated', 'call': record['call_id'], 'experiment': experiment,
                                      'case': case_id, 'side': side, 'tokens': record['output_tokens'],
                                      'stop': record['stop_reason'], 'seconds': record['seconds']}), flush=True)
                    return record

                def save_pair(experiment, fixture, seed, left, right):
                    assert left['input_ids'] == right['input_ids'] if experiment == 'stop' else True
                    if experiment == 'stop':
                        assert right['output_ids'][:len(left['output_ids'])] == left['output_ids'], 'Paired seeded prefix differs; preserve and stop'
                        assert left['input_ids'] == fixture['input_ids']
                    item = {'pair_id': f"{experiment}:{fixture['id']}:{seed}", 'experiment': experiment,
                            'case_id': fixture['id'], 'cluster_id': fixture['cluster_id'], 'seed': seed,
                            'source_call_id': fixture['source_call_id'], 'A_call': left['call_id'], 'B_call': right['call_id'],
                            'A_text': left['text'], 'B_text': right['text'], 'source_grounding': fixture['context']['grounding'],
                            'A_stop': left['stop_reason'], 'B_stop': right['stop_reason'],
                            'A_tokens': left['output_tokens'], 'B_tokens': right['output_tokens'],
                            'A_seconds': left['seconds'], 'B_seconds': right['seconds'],
                            'A_fact_flag': not left['fact_observation']['accepted'],
                            'B_fact_flag': not right['fact_observation']['accepted'],
                            'human_preference': None, 'quality_pass': False,
                            'context_recent': fixture['context']['recent'],
                            'causal_scope': 'single-output stop effect' if experiment == 'stop' else 'retry conditional on a stored rejected candidate'}
                    pairs.write(json.dumps(item, ensure_ascii=False) + '\n'); pairs.flush()
                    state['completed_pairs'] += 1
                    if state['completed_pairs'] == 1:
                        write(out / 'sanity.json', {'status': 'pass', 'included_in_planned_calls': True,
                                                  'input_parity': True, 'output_prefix_parity': True})
                    write(out / 'manifest.json', state)

                for fixture in rows(out / 'stop_fixtures.jsonl'):
                    for seed in cfg['seeds']:
                        a = generate(fixture['context'], seed, 2, 'stop', fixture['id'], 'A')
                        b = generate(fixture['context'], seed, 0, 'stop', fixture['id'], 'B')
                        save_pair('stop', fixture, seed, a, b)
                for fixture in rows(out / 'fallback_fixtures.jsonl'):
                    ref = fixture['context']['grounding']
                    memory = {k: ref[k] for k in ['id', 'body']}
                    contexts = [speech_context(fixture['context']['recent'], [], memory, plan)
                                for plan in [None, fixture['plan']]]
                    note = '【出来事の扱い】\n' + fixture['feedback'] + '\n\n'
                    for context in contexts:
                        context['prompt'] = note + context['prompt']
                        context['recent_span'] = [x + len(note) for x in context['recent_span']]
                    for seed in cfg['seeds']:
                        a = generate(contexts[0], seed, 2, 'fallback', fixture['id'], 'A')
                        b = generate(contexts[1], seed, 2, 'fallback', fixture['id'], 'B')
                        save_pair('fallback', fixture, seed, a, b)
            assert state['actual_Talk_calls'] == cfg['expected_Talk_calls'] == 204
            assert state['completed_pairs'] == 102
            verify_protocol(out)
            state.update(status='outputs_ready', phase='root_and_human_review_pending', finished_unix=time.time())
            write(out / 'manifest.json', state)
    except BaseException as exc:
        state.update(status='failed', error=str(exc), traceback=traceback.format_exc(), finished_unix=time.time())
        write(out / 'manifest.json', state)
        raise
    finally:
        if model:
            model.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['prepare', 'run'])
    p.add_argument('--runtime-root', type=Path, default=HERE.parent)
    p.add_argument('--source', type=Path)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    root = bootstrap(args.runtime_root)
    out = args.out.resolve()
    assert out.is_relative_to(root / 'runs') and out != root / 'runs'
    if args.command == 'prepare':
        prepare(root, args.source.resolve(strict=True), out)
    else:
        run(root, out)


if __name__ == '__main__':
    main()
