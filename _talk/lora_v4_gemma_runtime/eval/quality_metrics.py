"""Human-label aggregation. Never infer ratings from rule flags."""
import math
import random
import statistics
from collections import defaultdict

AXES = ('naturalness', 'development', 'association', 'rhythm', 'character', 'coherence')


def validate_label(row, known_pairs):
    required = {'pair_id', 'rater_id', 'reviewer_kind', 'winner', 'scores', 'unsupported_claims', 'contradictions', 'notes'}
    if set(row) != required:
        raise ValueError('Label fields differ from the documented contract')
    if row['pair_id'] not in known_pairs or not row['rater_id'].strip():
        raise ValueError('Unknown pair or missing rater')
    if row['reviewer_kind'] not in {'human', 'AI_root'}:
        raise ValueError('Reviewer provenance required')
    if row['winner'] not in {'left', 'right', 'tie', 'abstain'}:
        raise ValueError('Invalid preference')
    if set(row['scores']) != {'left', 'right'}:
        raise ValueError('Both outputs need scores')
    for side in ['left', 'right']:
        if set(row['scores'][side]) != set(AXES):
            raise ValueError('Six axes required; use null when not observable')
        for score in row['scores'][side].values():
            if score is not None and (type(score) is not int or not 0 <= score <= 4):
                raise ValueError('Scores must be integers 0..4 or null')
        for key in ['unsupported_claims', 'contradictions']:
            value = row[key][side]
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError('Claim counts must be nonnegative or null')
    return row


def preference_summary(labels, key, bootstrap_samples=5000, seed=20261016):
    """Equal weight per case; resample scene/episode clusters, not ratings."""
    seen = set()
    cases = defaultdict(list)
    for row in labels:
        validate_label(row, key)
        identity = (row['pair_id'], row['rater_id'], row['reviewer_kind'])
        if identity in seen:
            raise ValueError('Duplicate review')
        seen.add(identity)
        if row['reviewer_kind'] != 'human' or row['winner'] == 'abstain':
            continue
        item = key[row['pair_id']]
        score = .5 if row['winner'] == 'tie' else float(item[row['winner']] == 'B')
        cases[(item['experiment'], item['case_id'], item['cluster_id'])].append(score)
    results = {}
    for experiment in sorted({k[0] for k in cases}):
        selected = {k: statistics.mean(v) for k, v in cases.items() if k[0] == experiment}
        clusters = defaultdict(list)
        for (_, _, cluster), score in selected.items():
            clusters[cluster].append(score)
        estimate = statistics.mean(selected.values())
        interval = None
        if len(clusters) >= 2:
            rng = random.Random(seed)
            names = sorted(clusters)
            estimates = []
            for _ in range(bootstrap_samples):
                sample = [v for name in rng.choices(names, k=len(names)) for v in clusters[name]]
                estimates.append(statistics.mean(sample))
            estimates.sort()
            interval = [estimates[math.floor(.025 * (len(estimates) - 1))],
                        estimates[math.ceil(.975 * (len(estimates) - 1))]]
        results[experiment] = {'B_preference': estimate, 'cluster_CI95': interval,
                               'cases': len(selected), 'clusters': len(clusters),
                               'quality_adoption': 'pending factual review and adequate coverage',
                               'warning': 'development-only; few clusters cannot establish general improvement'}
    return {'human_review_rows': sum(r['reviewer_kind'] == 'human' for r in labels),
            'AI_root_rows': sum(r['reviewer_kind'] == 'AI_root' for r in labels),
            'experiments': results, 'status': 'rated' if results else 'human ratings pending'}
