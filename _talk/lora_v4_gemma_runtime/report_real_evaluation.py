"""CPU-only, partial-safe full output tables. Never assigns semantic quality labels."""
import argparse
import html
import json
from pathlib import Path
from evaluation_support import ROOT,TALK,read


def rows(path):
    if not path.exists():return []
    return [json.loads(s) for s in path.read_text(encoding='utf8').splitlines() if s.strip()]


def build(out):
    out=Path(out);manifest=read(out/'manifest.json') if (out/'manifest.json').exists() else {'status':'not_started'}
    tables=[]
    def table(title,heads,values):tables.append((title,heads,values))
    old=TALK/'lora_v4_multibase/runs/offload_20261009/gemma4_26b_a4b'
    baseline=read(old/'evaluation/comparison.json')['records']
    for sid in ['S1A','S2A','S3B']:
        values=[]
        for turn in range(3):
            oldrow=next(r for r in baseline if r['scenario']==sid and r['arm']=='C_planner_v4' and r['turn']==turn)
            cells=[str(turn+1),oldrow['accepted']['text'] if oldrow['accepted'] else '[再生なし]']
            for arm in ['CONTEXT','GOLD','GUARDED','PLANLESS']:
                records=rows(out/'fixed36'/sid/arm/'io.jsonl');r=next((r for r in records if r.get('turn')==turn and 'played_text' in r),None)
                cells.append(r['played_text'] if r and r['played_text'] else '[再生なし: '+str(r.get('failure'))+']' if r else '[未実行]')
            values.append(cells)
        table('固定36 / '+sid,['表示turn','保存済み旧Planner＋Talk v4','Contextのみ','Gold＋検査','v5 Planner＋検査','Planなし＋検査'],values)
    if (out/'selection18.json').exists():
        records=read(out/'selection18.json')['records']
        table('新規REL/NONE/IRREL — 形式と選択',['ケース','期待use_memory','形式成功','実use_memory / ID','選択正誤','全Planner出力'],[
            [r['id'],str(r['case']['expected_use_memory']),str(r['schema_success']),json.dumps({k:r['plan'][k] for k in ['use_memory','memory_id']},ensure_ascii=False) if r['plan'] else '取得なし',str(r['selection_correct']),
             '\n\n'.join(a.get('text') or json.dumps(a.get('generation_error'),ensure_ascii=False) for a in r['attempts'])] for r in records])
    for stage in ['memory_swap','heldout_speech','seed_check']:
        path=out/(stage+'.json')
        if not path.exists():continue
        records=read(path)['records'];values=[]
        keys=list(dict.fromkeys((r['id'],r['seed']) for r in records))
        for cid,seed in keys:
            found=[r for r in records if r['id']==cid and r['seed']==seed]
            cells=[cid,str(seed),found[0]['case']['recent'],json.dumps(found[0]['case']['candidate'],ensure_ascii=False)]
            for policy in ['CURRENT_ALWAYS','DECLARED_ONLY']:
                r=next((r for r in found if r['context_policy']==policy),None)
                cells.append(r['played_text'] if r and r['played_text'] else '[再生なし: '+str(r['failure'])+']' if r else '[未実行]')
            values.append(cells)
        table(stage+' — 全再生本文',['ケース','seed','開始文','提示Memory','常時表示','Planner選択時のみ表示'],values)
        table(stage+' — 全候補（破棄含む）',['ケース','方式','attempt','確定再生','本文／例外','検査理由'],[
            [r['id']+'/'+str(r['seed']),r['context_policy'],str(a.get('attempt')),str(a.get('playback_committed')),a.get('text') or json.dumps(a.get('generation_error'),ensure_ascii=False),
             json.dumps({'format':a.get('hard_failure'),'facts':a.get('memory_consistency',{}).get('issues')},ensure_ascii=False)]
            for r in records for a in r['speech_attempts']])
    oldlong=rows(old/'runtime_bc_10m/BC/io.jsonl');newlong=rows(out/'long2700/retrieval/GUARDED/io.jsonl')
    table('2,700字 — 全文（turnごとの入力・話題は分岐し、同一ではない）',['表示turn','保存済み旧Gemma BC','v5 GUARDED'],[
        [str(i+1),oldlong[i].get('played_text','') if i<len(oldlong) else '',newlong[i].get('played_text','') if i<len(newlong) else '[未実行]']
        for i in range(max(len(oldlong),len(newlong)))])
    def md(value):return str(value).replace('|','\\|').replace('\r','').replace('\n','<br>')
    lines=['# Harness v5 実Gemma評価 — 全出力比較','',
           '状態: '+manifest['status']+'。実音声/TTSではなく模擬再生。rootの全文品質レビューは別。','',
           '空欄・再生なしと未実行を区別する。候補拒否率は品質合格率ではない。固定条件も介入後の入力は分岐する。','']
    page=['<!doctype html><html lang="ja"><meta charset="utf-8"><title>ZIPちゃん v5 全出力</title>',
          '<style>body{font:15px system-ui;margin:24px}table{border-collapse:collapse;width:100%;margin:20px 0}td,th{border:1px solid #aaa;padding:10px;vertical-align:top;white-space:pre-wrap;overflow-wrap:anywhere}th{background:#eee}</style>',
          '<h1>Harness v5 実Gemma評価</h1><p>状態: '+html.escape(manifest['status'])+' / 模擬再生・品質レビュー別</p>']
    for title,heads,values in tables:
        lines+=['## '+title,'','| '+' | '.join(heads)+' |','|'+'---|'*len(heads)]
        lines+=['| '+' | '.join(md(x) for x in row)+' |' for row in values];lines.append('')
        page+=['<h2>'+html.escape(title)+'</h2><table><tr>'+''.join('<th>'+html.escape(h)+'</th>' for h in heads)+'</tr>']
        page+=['<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in values];page.append('</table>')
    (out/'full_output_table.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    (out/'comparison.html').write_text('\n'.join(page)+'</html>',encoding='utf8')
    calls=rows(out/'all_calls.jsonl');io=['# 全実生成 — 入出力・token記録','']
    for call in calls:
        io+=['## '+str(call['call_id'])+' / '+call['role']+' / '+str(call['stage'])+' / '+str(call['case']),'',
             '### 実decoded入力','','```text',call.get('decoded_input',call.get('input_text','')),'```','',
             '### 出力','','```text',call.get('text') or json.dumps(call.get('generation_error'),ensure_ascii=False,indent=2),'```','']
    (out/'all_generation_io.md').write_text('\n'.join(io),encoding='utf8')
    totals={'Planner_calls':sum(c['role']=='planner' for c in calls),'Talk_calls':sum(c['role']=='talk' for c in calls),
            'all_actual_calls':len(calls),'root_quality_review':'pending','actual_TTS':False}
    speech=[]
    for path in [out/'sanity',out/'fixed36',out/'long2700']:
        for p in path.rglob('io.jsonl') if path.exists() else []:
            for r in rows(p):speech.extend(r.get('speech_attempts',[]))
    for stage in ['memory_swap','heldout_speech','seed_check']:
        path=out/(stage+'.json')
        if path.exists():
            for r in read(path)['records']:speech.extend(r['speech_attempts'])
    totals.update(Talk_candidates_logged=len(speech),unplayed_candidates=sum(not a.get('playback_committed',False) for a in speech),
                  fact_rejected_candidates=sum(a.get('memory_consistency',{}).get('accepted') is False for a in speech),
                  semantic_false_rejections=None,source_unsupported_claims=None)
    (out/'metrics.json').write_text(json.dumps(totals,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':manifest['status'],'tables':len(tables),'calls':len(calls),'out':str(out)},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);build(parser.parse_args().out)
