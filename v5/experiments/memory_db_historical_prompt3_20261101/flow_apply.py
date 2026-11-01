"""Apply existing four-key Plans to source IDs without similarity ranking.

The sidecar contains source quotations and explicit ordering constraints. It is
not sent to the Planner/Surface and is not a semantic evaluator of speech.
"""
import json
import re
import unicodedata
from pathlib import Path


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text) if c.isalnum()).lower()


def validate_contract(facts, contract):
    ids = [f['id'] for f in facts]
    if contract['facts'] != facts or len(set(ids)) != len(ids):
        raise ValueError('Source Fact contract mismatch')
    if set(contract['anchors']) != set(ids):
        raise ValueError('Incomplete anchor manifest')
    claims = {f['id']: normalize(f['claim']) for f in facts}
    for fid, anchors in contract['anchors'].items():
        for text in anchors:
            anchor = normalize(text)
            if len(anchor) < 8 or anchor not in claims[fid]:
                raise ValueError('Anchor is not a sufficiently long exact source span')
            if sum(anchor in s for s in claims.values()) != 1:
                raise ValueError('Anchor is not unique to a source Fact')
    edges = contract['dependencies']
    if len({tuple(e) for e in edges}) != len(edges):
        raise ValueError('Duplicate dependency')
    for a, b in edges:
        if a not in ids or b not in ids or a == b:
            raise ValueError('Invalid dependency ID')
    constrained_order(ids, edges)
    return ids


def constrained_order(priority, edges):
    """Stable topological order: free nodes may move, prerequisites may not."""
    remaining = set(priority)
    result = []
    while remaining:
        ready = [fid for fid in priority if fid in remaining and
                 not any(b == fid and a in remaining for a, b in edges)]
        if not ready:
            raise ValueError('Cyclic dependencies')
        fid = ready[0]
        remaining.remove(fid)
        result.append(fid)
    return result


def apply_plan(plan, facts, contract):
    ids = validate_contract(facts, contract)
    base = dict(method='unique exact source spans or explicit IDs; constrained stable order',
                semantic_grounding=False, source_contract=True)

    def fallback(reason, steps=None):
        return ids, dict(base, adopted=False, changed=False, reason=reason, steps=steps or [])

    if not plan or not plan['use_memory']:
        return fallback('Planner abstained; fixed source order')
    if any(not fid.startswith(str(plan['memory_id']) + '-') for fid in ids):
        return fallback('Plan memory ID does not match source')
    ordered = []
    steps = []
    for index, flow in enumerate(plan['flow']):
        explicit = re.findall(r'(?<![A-Za-z0-9_\-])([A-Za-z][A-Za-z0-9_]*-\d+)(?![A-Za-z0-9_\-])', flow)
        if any(fid not in ids for fid in explicit):
            return fallback('Unknown explicit Fact ID', steps)
        text = normalize(flow)
        anchors = [(fid, a) for fid, aa in contract['anchors'].items()
                   for a in aa if normalize(a) in text]
        matched = set(explicit) | {fid for fid, _ in anchors}
        steps.append(dict(flow_index=index, flow=flow, explicit_ids=explicit,
                          source_spans=[dict(fact_id=fid, span=a) for fid, a in anchors],
                          matched_ids=sorted(matched)))
        if len(matched) != 1:
            return fallback('Ambiguous or unbound Flow step; fixed source order', steps)
        fid = next(iter(matched))
        if fid in ordered:
            return fallback('Repeated Fact binding; fixed source order', steps)
        ordered.append(fid)
    if not ordered:
        return fallback('Empty Flow binding')
    # Unmentioned Facts keep their slots. Only positively bound source IDs may
    # exchange priority; the dependency graph then protects event order.
    queue = iter(ordered)
    proposed = [next(queue) if fid in ordered else fid for fid in ids]
    result = constrained_order(proposed, contract['dependencies'])
    blocked = [e for e in contract['dependencies'] if proposed.index(e[0]) > proposed.index(e[1])]
    assert set(result) == set(ids) and len(result) == len(ids)
    return result, dict(base, adopted=True, changed=result != ids,
                        reason='Apply grounded source-ID priorities under dependencies',
                        steps=steps, proposed_order=proposed, constrained_order=result,
                        dependency_conflicts=blocked,
                        unmentioned_ids=[fid for fid in ids if fid not in ordered])


def plan_order(plan, facts):
    ids = [f['id'] for f in facts]
    # Preserve the pre-intervention initial prompt exactly for cache replay.
    if not plan or not plan['use_memory']:
        return ids, dict(adopted=False, reason='Planner abstained; fixed source order',
                         method='no semantic interpretation')
    manifest = json.loads(Path(__file__).with_name('fact_contract.json').read_text(encoding='utf-8'))
    mid = plan.get('memory_id')
    if mid not in manifest['memories']:
        return ids, dict(adopted=False, changed=False, reason='No audited source contract; fixed source order',
                         method='source-ID/dependency application, not semantic grounding')
    return apply_plan(plan, facts, manifest['memories'][mid])
