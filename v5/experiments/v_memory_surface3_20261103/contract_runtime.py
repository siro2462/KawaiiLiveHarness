"""Frozen semantic Surface interface. Source and review fields stay outside prompts."""
import hashlib
import json

VERSION = 'surface-contract-1'
OPERATIONS = {'start', 'continue', 'related_shift', 'topic_shift'}
RELATIONS = {'sequence', 'detail', 'cause', 'contrast', 'discovery', 'correction', 'association', 'none'}

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()

def validate(row):
    assert row['schema'] == VERSION
    assert 1 <= len(row['facts']) <= 6
    ids = [f['id'] for f in row['facts']]
    assert len(set(ids)) == len(ids)
    assert all(f['claim'].strip() and f['kind'] in {'event','state','intent','judgment','uncertain','question','hypothetical','metaphor','emotion','speech_act'} for f in row['facts'])
    assert len(row['history']) <= 2
    assert sum(len(x['text']) for x in row['history']) <= 800, 'Do not silently truncate history'
    assert all(x['text'].strip() for x in row['history'])
    assert row['operation'] in OPERATIONS
    assert row['relation']['type'] in RELATIONS
    used = []
    for step in row['flow']:
        assert step['relation'] in RELATIONS
        assert step['fact_ids'] and set(step['fact_ids']) <= set(ids)
        used.extend(step['fact_ids'])
    assert used == ids, 'Each target fact appears once, in source order'
    assert row['operation'] != 'start' or not row['history']
    return row

def render(row):
    validate(row)
    operation = {'start':'話を始める','continue':'同じ出来事の続きを話す','related_shift':'関連する別の話題へ移る','topic_shift':'別の話題へ切り替える'}[row['operation']]
    history = '\n\n'.join(f'[{i+1}] {x["text"]}' for i,x in enumerate(row['history'])) or 'なし'
    facts = '\n'.join(f'[{f["id"]}] {f["claim"]}' for f in row['facts'])
    flow = ' → '.join(f'{s["label"]}（{", ".join(s["fact_ids"])}）' for s in row['flow'])
    return ('雑談配信で、その場で話しているような自然な日本語の発話にする。\n'
            '出来事、考え、感情、問い、比喩、仮定の区別を保つ。数量・否定・時点・確実性・決定と実行を変えない。\n'
            '必要なところだけ自然に言い淀みや言い直しを使う。語尾やつなぎを同じ形にそろえる必要はない。\n'
            '新しい事実・理由・感情を足さず、発話本文だけを出す。ID、見出し、説明、注記は出さない。\n\n'
            '【直前の発話：最大2回、文脈用】\n'+history+'\n\n'
            '【今回の会話操作】\n'+operation+'\n\n'
            '【話題の関係】\n'+row['relation']['summary']+'\n\n'
            '【今回話す内容】\n'+facts+'\n\n'
            '【話の展開】\n'+flow+'\n\n'
            '直前の発話を受け、今回の内容へ進む。履歴にある話を丸ごと説明し直さない。'
            '関係のない出来事を同じ日や因果で結ばない。履歴の未検証の内容を新事実の根拠にしない。')
