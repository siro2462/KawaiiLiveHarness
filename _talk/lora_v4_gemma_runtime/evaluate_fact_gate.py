"""Fixed authored CPU challenge set; never reports model/human factual accuracy."""
import argparse
import importlib.util
import json
from pathlib import Path
from fact_gate import check_text

A={'id':'cpu:food','body':'カレーを作った。ご飯がなかった。冷凍うどんにかけて食べた。'}
B={'id':'cpu:station','body':'駅の西口で友人を待つ予定だった。東口に出てしまった。'}
C={'id':'cpu:photo','body':'ゲームで青い屋根の家を撮影しようとした。同じ看板の写真を十枚消した。'}
D={'id':'cpu:dated','body':'昨日の朝にカレーを作った。'}

# Fixed review regressions plus deliberately retained blind spots. The latter
# count as detection misses, not as passing tests or accepted factual claims.
CASES=[
 ('entity-action','改変','うなぎを食べた。',A,False),
 ('entity-retrospective','改変','うなぎも美味しかったなあ。',A,False),
 ('entity-retrospective-kanji','改変','鰻が美味しかった。',A,False),
 ('new-episode','改変','そのあと風呂に入った。',A,False),
 ('added-yesterday','時点','昨日カレーを作った。',A,False),
 ('added-morning','時点','昨日の朝にカレーを作った。',A,False),
 ('added-clock','時点','七時にカレーを作った。',A,False),
 ('added-date','時点','10月14日にカレーを作った。',A,False),
 ('past-now','時点','今カレーを作っている。',A,False),
 ('time-from-childhood','時点','昨日カレーを作った。',{'id':'cpu:child','body':'子供の頃にカレーを作った。'},False),
 ('direction','改変','西口に出てしまった。',B,False),
 ('number','改変','看板の写真を百枚消した。',C,False),
 ('participants','改変','三人にカレーを作った。',A,False),
 ('planned-done','改変','青い屋根の家を撮影した。',C,False),
 ('application','改変','うどんをカレーにかけて食べた。',A,False),
 ('absence','改変','ご飯はちゃんとあった。',A,False),
 ('unlisted-watch','検出限界','昨日映画を見た。',A,False),
 ('noun-only-episode','検出限界','映画館での思い出だったね。',A,False),
 ('negated-source-action','検出限界','カレーを作らなかった。',A,False),
 ('implicit-time','検出限界','日が昇る前にカレーを作った。',A,False),
 ('paraphrase-food','正しい言い換え','カレーうどんにした。',A,True),
 ('original-food','正しい言い換え','冷凍うどんにカレーをかけて食べた。',A,True),
 ('source-sensory','感想','カレーは美味しかったなあ。',A,True),
 ('opinion-question','感想','甘めだったかな？',A,True),
 ('new-food-question','自然な想像','うなぎって美味しいのかな？',A,True),
 ('hypothetical','自然な想像','うなぎを乗せたらどうなるんだろう？',A,True),
 ('wish','自然な想像','うなぎを食べたいね。',A,True),
 ('past-wish','自然な想像','うなぎを食べたかったんだよね。',A,True),
 ('joke','自然な想像','冗談だけど宇宙でうなぎを食べた。',A,True),
 ('metaphor','自然な想像','湯気を見るとお風呂みたいだね。',A,True),
 ('generic-opinion','感想','うなぎも美味しいと思う。',A,True),
 ('supported-date','正しい言い換え',D['body'],D,True),
 ('conditional-time','自然な想像','昨日の朝カレーを作ったらどうだったかな？',A,True),
 ('known-direction','正しい言い換え','東口に出てしまった。',B,True),
 ('known-number','正しい言い換え','看板の写真を10枚消した。',C,True),
 ('known-intent','正しい言い換え','青い屋根の家を撮影しようとした。',C,True),
]


def measure(checker):
    rows=[]
    for case_id,category,text,memory,allowed in CASES:
        result=checker(text,[memory])
        rows.append({'id':case_id,'category':category,'text':text,'source':memory,
                     'authored_expected_allow':allowed,'actual_allow':result['accepted'],
                     'issue_codes':[x['code'] for x in result['issues']],
                     'false_negative':not allowed and result['accepted'],
                     'false_positive':allowed and not result['accepted']})
    negatives=[r for r in rows if not r['authored_expected_allow']]
    positives=[r for r in rows if r['authored_expected_allow']]
    return {'cases':len(rows),'authored_unsupported_cases':len(negatives),
            'authored_allowed_cases':len(positives),
            'detected_unsupported':sum(not r['actual_allow'] for r in negatives),
            'false_negatives':sum(r['false_negative'] for r in rows),
            'false_positives':sum(r['false_positive'] for r in rows),
            'coverage':'fixed authored challenge set, not LLM output factual accuracy',
            'rows':rows}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline-module',type=Path)
    args=parser.parse_args();after=measure(check_text)
    result={'labels':'developer-authored CPU fixtures; human-user labels=0',
            'quality_pass':False,'after':after}
    if args.baseline_module:
        spec=importlib.util.spec_from_file_location('review_original_fact_gate',args.baseline_module)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        result['before']=measure(module.check_text)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'fact_gate_evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    lines=['# 事実検査の固定CPU評価','',result['labels'],'',
           '検出漏れは残す。検査通過率を実発話の事実正確率と解釈しない。','',
           '| ケース | 区分 | 発話 | 元Memory | 期待 | 検査 | 判定 |','|---|---|---|---|---|---|---|']
    for r in after['rows']:
        verdict='検出漏れ' if r['false_negative'] else '誤検出' if r['false_positive'] else '期待どおり'
        lines.append('| '+' | '.join([r['id'],r['category'],r['text'],r['source']['body'],
                     '許容' if r['authored_expected_allow'] else '拒否','許容' if r['actual_allow'] else '拒否',verdict])+' |')
    (args.output/'fact_gate_evaluation.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps({stage:{k:v for k,v in values.items() if k!='rows'} for stage,values in result.items() if stage in {'before','after'}},ensure_ascii=False))


if __name__=='__main__':main()
