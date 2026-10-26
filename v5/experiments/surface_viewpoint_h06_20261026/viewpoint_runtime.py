"""Stage 1: explicit, grounded angle -> unchanged Surface case + angle section.

This checks identifiers and source quotation, not semantic truth. A recorded
attempt never means the requested angle was understood or expressed.
"""
import copy
from contract_runtime import validate as validate_case, render as render_current, digest

SECTION = '\n\n【今回の見る角度：事実の追加ではなく語る観点】\n'
RULE = ('今回話す内容はすべて扱い、その中で次の角度に重心を置いて語る。'
        '角度の指示は新しい事実の根拠ではない。根拠にある悔しさや比較を、'
        '別の出来事・購入の実行・確定した価格・相手の意図へ変えない。'
        '同じ結論の言い換えだけを増やさず、根拠のどの点からその評価になるのかを語る。'
        '根拠のない理由・感情・新しい経験は追加しない。\n')

def validate_angle(case, angle):
    validate_case(case)
    if set(angle) != {'schema', 'angle_id', 'label', 'instruction', 'basis'}:
        raise ValueError('Unexpected angle fields')
    if angle['schema'] != 'surface-viewpoint-1':
        raise ValueError('Unsupported angle schema')
    for key, limit in [('angle_id', 64), ('label', 100), ('instruction', 300)]:
        value = angle[key]
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError('Invalid angle text: ' + key)
    facts = {f['id']: f['claim'] for f in case['facts']}
    if not isinstance(angle['basis'], list) or not angle['basis']:
        raise ValueError('Missing source basis')
    seen = set()
    for basis in angle['basis']:
        if set(basis) != {'fact_id', 'quote'}:
            raise ValueError('Unexpected basis fields')
        fid, quote = basis['fact_id'], basis['quote']
        if fid not in facts or fid in seen:
            raise ValueError('Unknown or duplicate target fact')
        if not isinstance(quote, str) or not quote.strip() or quote not in facts[fid]:
            raise ValueError('Source quote does not match the target Fact')
        seen.add(fid)
    return angle

def apply_angle(case, angle):
    validate_angle(case, angle)
    return {'schema': 'surface-viewpoint-request-1', 'case': copy.deepcopy(case),
            'viewpoint': copy.deepcopy(angle), 'case_sha256': digest(case)}

def render(case, angle=None):
    base = render_current(case)
    if angle is None:
        return base
    packet = apply_angle(case, angle)
    v = packet['viewpoint']
    basis = '\n'.join('[' + b['fact_id'] + '] ' + b['quote'] for b in v['basis'])
    return base + SECTION + RULE + '根拠（元Factの引用）：\n' + basis + '\n見る角度：' + v['label'] + '\n指示：' + v['instruction']

class AngleAttempts:
    """Bounded attempts, separated from frozen Fact presentation progress."""
    def __init__(self, limit):
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError('Positive attempt limit required')
        self.limit, self.records = limit, []

    def begin(self, case, angle):
        packet = apply_angle(case, angle)
        key = packet['case_sha256'] + ':' + angle['angle_id']
        if any(x['key'] == key for x in self.records):
            raise ValueError('Angle already attempted for this fixed case')
        if len(self.records) >= self.limit:
            raise ValueError('Attempt budget exceeded')
        self.records.append({'key': key, 'angle_id': angle['angle_id'],
                             'case_sha256': packet['case_sha256'], 'status': 'started',
                             'semantic_status': 'unverified'})
        return key

    def finish(self, key, call_id, delivered):
        row = next(x for x in self.records if x['key'] == key)
        if row['status'] != 'started' or not call_id or type(delivered) is not bool:
            raise ValueError('Invalid attempt completion')
        row.update(status='text_delivered' if delivered else 'format_held',
                   call_id=call_id, semantic_status='unverified')
