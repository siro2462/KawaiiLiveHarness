"""Pure JSON projection of authored candidates; no persistent DB or model calls."""
import copy
import json
from v5.memory_db.normalize import normalize_document, digest
from v5.memory_db.projection import PROJECTION_VERSION


def make_snapshot(candidates, authored_sources):
    episodes = []
    normalized = []
    for item in candidates:
        doc = item['document']
        n = normalize_document(doc, 'fiction_structure_candidate', 'fictional')
        normalized.append(copy.deepcopy(n))
        mid = n['external_id']
        rid = 'rev_' + digest(n)
        by = {a['local_id']: rid + ':' + a['local_id'] for a in n['atoms']}
        atoms = [dict(copy.deepcopy(a), atom_id=by[a['local_id']], revision_id=rid,
                      evidence=copy.deepcopy(a['attributes']['創作仕様根拠'])) for a in n['atoms']]
        links = [dict(copy.deepcopy(x), src=by[x['src']], dst=by[x['dst']], revision_id=rid,
                      review_status='explicit_validated_unreviewed') for x in n['links']]
        episodes.append(dict(copy.deepcopy(n), episode_id='candidate_' + mid, revision_id=rid,
                             version=1, review_status='unreviewed',
                             review={'actor': 'root_ai_manual', 'human_quality_labels': 0,
                                     'scope': 'candidate authoring review, not persisted DB acceptance'},
                             content_sha256=digest(n), raw_sha256=digest(doc), atoms=atoms, links=links,
                             sources=[{'source_id': 'authored_' + mid, 'kind': 'authored_fiction_specification',
                                       'document': copy.deepcopy(authored_sources[mid])}]))
    snapshot = dict(mode='validation', namespace='fiction_structure_candidate',
                    projection_version=PROJECTION_VERSION, episodes=episodes)
    snapshot['snapshot_id'] = 'standalone_' + digest(snapshot)
    return snapshot, normalized
