"""Isolated CPU adapters; semantic association never silently becomes prerequisite."""
import collections
import copy
import hashlib
import importlib.util
from pathlib import Path

from .projection import content_hash

ROOT = Path(__file__).resolve().parent
VERSION = 'memory-db-selector-v1'


def load_module(path):
    spec = importlib.util.spec_from_file_location('isolated_memory_selector', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _eligible(sample):
    nodes = copy.deepcopy(sample['nodes'])
    by = {n['id']: n for n in nodes}
    if len(by) != len(nodes):
        raise ValueError('duplicate IDs')
    deferred = {n['id']: n['projection_deferred'] for n in nodes if n.get('projection_deferred')}
    if sample['provenance']['world_scope'] != 'fictional':
        deferred.update({n['id']: 'Reference/unknown world is not ZIP personal speech' for n in nodes})
    # Never merge two distinct source atoms solely because prose is identical.
    groups = collections.defaultdict(list)
    for n in nodes:
        groups[content_hash([n['title'], n['kind'], n['epistemic']])].append(n['id'])
    for ids in groups.values():
        if len(ids) > 1:
            deferred.update({mid: 'duplicate engine content needs explicit disambiguation' for mid in ids})
    changed = True
    while changed:
        changed = False
        for n in nodes:
            if any(x not in by for x in n['requires']):
                raise ValueError('unknown prerequisite')
            if n['id'] not in deferred and set(n['requires']) & set(deferred):
                deferred[n['id']] = 'required context was deferred';changed = True
    return [n for n in nodes if n['id'] not in deferred], deferred


def select_episode(sample, backend='rhythm', max_same_kind=3):
    if backend not in {'rhythm', 'h06'}:
        raise ValueError('Unknown backend')
    nodes, deferred = _eligible(sample)
    present = {n['id'] for n in nodes}
    edges = [e for e in sample['edges'] if e['src'] in present and e['dst'] in present]
    if not nodes:
        result = dict(steps=[], deferred_nodes=[], stop_reason='no_eligible_atoms')
    elif backend == 'rhythm':
        module = load_module(ROOT / 'vendor/adapted_selector.py')
        incoming = collections.defaultdict(list)
        for e in edges:
            incoming[e['dst']].append(e)
        def constraints(ns):
            rows = [dict(before=e['src'], after=e['dst'], rule='explicit_requires_context', priority=110,
                         relation='requires_context', verification=e['review_status']) for e in edges if e['relation'] == 'requires_context']
            # A schema-valid dependency may still be semantically unreviewed.
            pending = {n['id'] for n in ns};done = set()
            while pending:
                ready = {mid for mid in pending if all(e['before'] in done for e in rows if e['after'] == mid)}
                if not ready:
                    raise ValueError('explicit dependency cycle')
                done |= ready;pending -= ready
            return rows, [], []
        def anchor(n, used, order):
            links = [e for e in incoming[n['id']] if e['src'] in used and e['relation'] in {'reaction', 'appraisal', 'about', 'answer', 'comparison', 'requires_context'}]
            if links:
                chosen = max(links, key=lambda e: order.index(e['src']))
                # This flag means provided association, not verified truth.
                return chosen['src'], 'explicit_' + chosen['relation'], list(dict.fromkeys(e['src'] for e in links)), True
            return (order[-1] if order else None), 'continuity_only_not_causal', [], False
        def penalty(n, used):
            links = [e for e in incoming[n['id']] if e['relation'] in {'reaction', 'appraisal', 'answer'}]
            return .8 if links and not any(e['src'] in used for e in links) else 0.0
        module.compile_relations = constraints
        module.memory_db_anchor = anchor
        module.memory_db_soft_penalty = penalty
        result = module.select(dict(nodes=nodes), model=None, max_same_kind=max_same_kind)
        # Vendor validation includes coverage, exact content, anchors and rhythm.
        module.validate_plan(dict(nodes=nodes), result)
    else:
        path = ROOT.parents[0] / 'evidence/stripe_surface_abc_h06_20261027/reference/stripe_engine/engine.py'
        module = load_module(path)
        for n in nodes:
            n['tags'] = [t for t in n['tags'] if t != 'entry']
        roots = [n for n in nodes if not n['requires']]
        if not roots:
            raise ValueError('No entry without prerequisites')
        min(roots, key=lambda n: (n['kind'] != 'F', content_hash([n['title'], n['kind'], n['epistemic']])))['tags'].append('entry')
        module.MEM = dict(nodes=nodes, edges=edges)
        module.N = {n['id']: n for n in nodes}
        module.OUT = collections.defaultdict(list);module.INC = collections.defaultdict(list)
        for e in edges:
            # Old H06 consumes rel, with known operations only. Extra semantic
            # relations remain associations; no constraint inferred here.
            module.OUT[e['src']].append(e);module.INC[e['dst']].append(e)
        trace = module.Engine(seed=17, mode='state', allow_cross=False).run(sample['id'])
        steps = [dict(index=t['index'], memory_id=t['node_id'], operation=t['operation'], kind=t['color'],
                      content=t['title'], epistemic=t['epistemic'], relation=t['relation'], anchor_id=t['source_anchor']) for t in trace]
        emitted = {s['memory_id'] for s in steps}
        result = dict(steps=steps, trace=trace, deferred_nodes=[dict(memory_id=n['id'], reason='legacy H06 stopped before selection') for n in nodes if n['id'] not in emitted], stop_reason='legacy_h06_policy')
    result['deferred_nodes'].extend(dict(memory_id=mid, reason=why) for mid, why in deferred.items())
    result.update(backend=backend, adapter_version=VERSION, provenance=copy.deepcopy(sample['provenance']),
                  semantic_status='unverified', model_calls=0, ranker='existing generic prior; no fitted ranking weights',
                  semantic_link_policy='explicit associations are soft; requires_context only is a hard order')
    validate_plan(sample, result)
    return result


def validate_plan(sample, plan):
    by = {n['id']: n for n in sample['nodes']};seen = set();first = {}
    if plan['provenance'] != sample['provenance']:
        raise ValueError('Plan provenance mismatch')
    for i, step in enumerate(plan['steps'], 1):
        if step['index'] != i or step['memory_id'] not in by:
            raise ValueError('Bad step identity')
        node = by[step['memory_id']]
        if (step['content'], step['kind'], step['epistemic']) != (node['title'], node['kind'], node['epistemic']):
            raise ValueError('Changed memory content')
        if node.get('projection_deferred') or sample['provenance']['world_scope'] != 'fictional':
            raise ValueError('Unusable atom selected')
        if step.get('anchor_id') and step['anchor_id'] not in seen:
            raise ValueError('Future anchor')
        if step['operation'] == 'REVISIT' and step['memory_id'] not in seen:
            raise ValueError('Unseen revisit')
        if step['memory_id'] in seen and step['operation'] != 'REVISIT':
            raise ValueError('Repeat without new-purpose revisit')
        if not set(node['requires']) <= seen:
            raise ValueError('Missing required context')
        first.setdefault(step['memory_id'], i);seen.add(step['memory_id'])
    deferred = {r['memory_id'] for r in plan['deferred_nodes']}
    if seen & deferred or seen | deferred != set(by):
        raise ValueError('Omitted atom without explicit deferral')
    if plan['backend'] == 'rhythm':
        limit = plan.get('rhythm_policy', {}).get('max_same_kind', 3)
        last, streak = None, 0
        for step in plan['steps']:
            streak = streak + 1 if step['kind'] == last else 1;last = step['kind']
            if streak > limit:
                raise ValueError('Rhythm bound violated')
    return True
