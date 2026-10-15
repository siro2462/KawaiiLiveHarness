"""Summarize saved CPU review evidence; no model or generation imports."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'audit/review_20261015'


def main():
    tests=json.loads((OUT/'cpu_tests.json').read_text(encoding='utf8'))
    evaluation=json.loads((OUT/'fact_gate_evaluation.json').read_text(encoding='utf8'))
    before,after=evaluation['before'],evaluation['after']
    saved=json.loads((ROOT/'runs/harness_v5_schema_20261014b/results.json').read_text(encoding='utf8'))['records']
    selection={'scope':'saved pre-review Planner format probe; no new model inference',
               'total_cases':len(saved),'schema_valid':sum(r['formal_valid'] for r in saved),
               'declared_use_memory_true':sum(r['plan']['use_memory'] for r in saved),
               'declared_use_memory_false':sum(not r['plan']['use_memory'] for r in saved),
               'candidate_present_cases':sum(bool(r['input']['memory_candidates']) for r in saved),
               'selection_quality':'not established; injected grounding is not model Memory selection'}
    (OUT/'saved_memory_selection_observation.json').write_text(json.dumps(selection,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.py')}
    (OUT/'review_code_hashes.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    residual=[r for r in after['rows'] if r['false_negative']]
    lines=['# v5 ZIPレビュー対応結果 — 2026-10-15','',
           '対象は開発途中のv5。修正前の8ソースと再現結果は同ディレクトリのbefore.jsonおよび対応する.pyに保全した。旧ZIP・モデル・LoRA・元Memory・旧実験は変更していない。','',
           '## 修正と検証','',
           '| 項目 | 実変更 | CPUで確認したこと |','|---|---|---|',
           '| Memory選択 | preview([])はNone。commit(None)で今回の選択を解除。元bankと過去参照は保持 | 検索失敗後のTalkに旧本文が入らない。有効Planを継続する通常turnは新しい検索失敗と混同しない |',
           '| 根拠一致 | Plan検査・Plan採用bundle・実Talk入力・Talk検査の根拠を現在の1件または空に統一 | 過去Aで認めたPlanをBだけのTalkへ渡す経路を拒否。ID/本文/hashを完全比較 |',
           '| 生成例外 | 入力長・保護Context超過・JSON制約・OOM/デバイス障害を分類 | 入力長はRecent左端のみ縮小し1retry。保護本文超過はPlanなしへ、なお入らなければ停止。OOM等は追加生成しない。未知例外は監査して再送出 |',
           '| 拒否後Plan | Talkの事実拒否時に全Planスロットを無効化し、同じ根拠のPlanなしTalkを最大1回。形式候補が全拒否の場合も失効 | 破棄Planがlast_validから復活しない。未再生候補をSQLiteに確定しない |',
           '| CPU事実検査 | 過去の感覚述語による未知物の経験、明示日時、同じ行為/対象の明示否定を追加。時刻の漢数字/数字を正規化 | 拒否例と感想・質問・仮定・冗談・正しい言い換えを固定ケースで比較 |',
           '| α契約 | 初期proposeはMemory IDを正確に1件。waitは0件 | αの受理結果が既存Plannerの候補1件制約も通過する |',
           '| 話題進展 | 直近5PlanのMemory/Topic/Flow/再生成時の一致/実再生を監査ログに追加 | 観測だけ。Plannerへの強制命令や新会話Controllerは追加しない。同義反復の意味判定は未実施 |','',
           '## CPU結果','',
           f"全{tests['tests_run']}テスト: {tests['status']}。failures={tests['failures']}, errors={tests['errors']}, skipped={tests['skipped']}。構文検査{tests['py_compile']}。Gemma生成0、実TTS0。",
           'フェイクPlanner/Talk＋実SQLiteの結合検査を含む。実Gemma tokenizerの入力cut検査もCPUで実施。JSON制約ライブラリがtorchをimportするが、学習・モデル生成を実行した結果ではない。','',
           '| 固定CPUチャレンジセット | 修正前 | 修正後 |','|---|---:|---:|',
           f"| 根拠にない/改変したケースの検出 | {before['detected_unsupported']}/{before['authored_unsupported_cases']} | {after['detected_unsupported']}/{after['authored_unsupported_cases']} |",
           f"| 検出漏れ | {before['false_negatives']} | {after['false_negatives']} |",
           f"| 許容例の誤拒否 | {before['false_positives']}/{before['authored_allowed_cases']} | {after['false_positives']}/{after['authored_allowed_cases']} |",'',
           'これは修正に使った36件の開発者作成CPUケースであり、独立した品質評価ではない。実際のLLM発話の事実正確率・自然さ・誤拒否率を表すものではない。人間ユーザーによる新規ラベル0。','',
           '### 残る検出漏れ','']
    lines.extend('- '+r['text']+'（'+r['id']+'）' for r in residual)
    lines+=['','認識対象外の述語、名詞だけの経験、暗黙の時点などを一般的に解決していない。accepted=trueは候補を通すという制御結果であり、意味的な正しさの証明ではない。全結果にsemantic_verdict=unverifiedを付ける。','',
            '## Memory選択は別評価','',
            f"保存済み形式probeはschema {selection['schema_valid']}/{selection['total_cases']}、use_memory=true {selection['declared_use_memory_true']}、false {selection['declared_use_memory_false']}。Memory候補ありは{selection['candidate_present_cases']}件。これは改修後の選択精度改善とはしない。",
            'Runtimeにはoffered ID、Plannerのuse_memory/ID、実Talkの根拠ID、未評価の選択正誤を別記録する。関連/無関係/Memoryなしの実Gemma比較は未実施。','',
            '## 残る結合・品質評価','',
            '- CPU結合合格後の短い実Gemma接続診断、固定36条件、連続2700字の全文比較は未実施。',
            '- 2700字÷4.5字/秒は600秒の模擬。実TTS・配信の結合ではない。',
            '- 部分再生は模擬prefixだけのDB保存と再オープンを確認した。実TTS ack、実割込み、Runtime再起動・再開の結合は未実施。',
            '- 空再生30回の上限を維持。初期Plan失敗だけではTalkを止めないが、Talkも拒否され続けた場合は未達になる。',
            '- 同じPlanの再生成や同じMemory内の内容進展の品質は観測ログと全文から別途判定する。今回、会話内容を強制する機構は追加しない。',
            '- αのRecall/Association/自発起動の実装とv5接続は未実施。','',
            '結論: レビューで再現した状態管理・根拠の不一致を修正しCPUで確認した。事実検査の網羅性、モデルのMemory選択能力、自然な長時間発話の品質合格はまだ確認していない。','']
    (OUT/'review_response.md').write_text('\n'.join(lines),encoding='utf8')
    print(json.dumps({'tests':tests['tests_run'],'detected':after['detected_unsupported'],
                      'unsupported_cases':after['authored_unsupported_cases'],'remaining_misses':len(residual),
                      'quality_pass':False,'report':str(OUT/'review_response.md')},ensure_ascii=False))


if __name__=='__main__':main()
