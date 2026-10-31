"""Build auditable Surface inputs only. No model calls and no memory writes."""
import copy
import json

from .projection import content_hash
from .selector_adapter import validate_plan

VERSION = 'memory-db-surface-v1'


def render_surface(sample, plan, history=None):
    validate_plan(sample, plan)
    if not plan['steps']:
        raise ValueError('No eligible operations; do not request a Surface utterance')
    recent = []
    for item in reversed(history or []):
        if not isinstance(item, dict) or not isinstance(item.get('text'), str):
            raise ValueError('Invalid history item')
        if len(recent) == 2 or sum(len(x['text']) for x in recent) + len(item['text']) > 800:
            break
        recent.insert(0, copy.deepcopy(item))
    by = {n['id']: n for n in sample['nodes']}
    operations = []
    for step in plan['steps']:
        node = by[step['memory_id']]
        operations.append({**copy.deepcopy(step), 'original_kind': node['original_kind'],
                           'origin': node['sidecar']['origin'], 'world_scope': node['sidecar']['world_scope'],
                           'original_epistemic': node['original_epistemic'], 'execution_status': node['sidecar']['execution_status'],
                           'certainty_text': node['sidecar']['attributes'].get('確かさ'),
                           'execution_text': node['sidecar']['attributes'].get('状態'),
                           'utterance_hint': node['sidecar']['utterance_hint']})
    payload = dict(contract=VERSION, provenance=copy.deepcopy(sample['provenance']), title=sample['title'],
                   context=copy.deepcopy(sample['context']), central_theme=copy.deepcopy(sample['central_theme']),
                   history=recent, history_authority='unverified generated text; not new facts',
                   unknowns=copy.deepcopy(sample['unknowns']), prohibitions=copy.deepcopy(sample['prohibitions']),
                   operations=operations)
    prompt = ('雑談配信中の自然な口語で、操作列を順に発話へ変換する。操作名・ID・見出しは読まない。\n'
              '指定の出来事・数量・人物・否定を変えず、未指定の出来事や感情を追加しない。\n'
              '創作世界の設定と現実の実体験を区別し、希望・予定・仮定を実行済みにしない。不明は不明のままにする。\n'
              '短い言葉は反応の表現候補で逐語的な実録ではない。履歴は流れだけに使い、新事実の根拠にしない。\n'
              'REVISITは既出内容の再言及。関係は必ずしも因果関係ではない。発話本文だけを出す。\n\n'
              '【記憶と操作の入力】\n' + json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
    return dict(user_prompt=prompt, payload=payload, payload_sha256=content_hash(payload),
                generated=False, model_calls=0, contract=VERSION)
