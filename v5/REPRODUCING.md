# 保存内容と復元条件（2026-10-25）

## モデルなしのCPU検査

```powershell
python -X utf8 -B v5/tools/verify_snapshot.py
python -X utf8 -B v5/tools/test_snapshot.py -v
python -X utf8 -B v5/tools/test_current.py -v
```

旧停止証跡12検査を保ち、現行の不正Plan固定順継続・保存51発話/人間比較5発話の履歴と入力・意味未検証状態を追加検査する。モデル/ネット/GPUを使わない。元のCPU154や44+11の全再実行ではない。

`verify_snapshot.py --source-talk C:/NodeJS/KawaiiLive/work/astra/_talk`で、byte保持ソースと保存証跡の元ファイルSHAも照合できる。

## 推論を復元する場合の条件（今回のpushでは実行しない）

1. `_talk/lora_v4_gemma_runtime/`、`_talk/lora_v4_multibase/`等を元と同じ相対構造に置く。
2. `v5/runtime/`は`current_continuous10_fallback_20261024_v1/executed_source/`の実行済みソースをbyte保持で保存している。新runの`executed_source/`へ配置し、元runを書き換えない。
3. `ZIP_INCREMENTAL_RUN`を新runへ指定する。PYTHONPATHには新run/executed_source、harness_beta、lora_v4_multibase、lora_v4_gemma_runtimeを含める。pwsh7/UTF8、Python `-X utf8 -B`。
4. `PROTOCOL.json`と各`protocol_export.json`は条件・来歴の公開記録で、そのまま実行用protocolには使えない。実行用の外部資産/SHA凍結、同一入力prefixの元出力/全journal、モデル・adapter・tokenizer・NF4 cacheの配置が必要。元17出力は再生成で埋めない。
5. Alpha.populateが読む元reference ZIPは含めていない。合成fixtureと違い、人間実験では既存逆算Memoryを隔離namespaceへ投影している。synthetic_fixtureは検証用の権威区分で、元の人間経験を創作したという意味ではない。
6. 人間比較を復元する場合、標準runtimeに`v5/experiments/human_memory_compare/`をoverlayし、同実験evidenceのreferenceを新run/referenceへ置く。変更はcue/4Memory/比較補助・観測ラベル。モデル/Planner prompt/Surface契約/生成条件は同一。原文は生成へ見せず最大5発話で一巡し、水増ししない。
7. CPU公式Processor/実child_guard startupの検査を済ませてから起動する。起動後は定期確認へ戻し、エージェントが終了まで常駐しない。
8. 不正JSONはRAWを保存し`planner_delivery.resolve`がPlanを破棄、固定元Fact順で継続。構文合格の意味不良を検査済みへ昇格しない。全実入力/RAW/履歴を保存し、終了0・技術監査の後に全文を読む。

モデル重量/LoRA/tokenizer/reference ZIP/全文教材/Memory DB/チャットSQLite/環境や認証情報は同梱しない。モデル詳細は[MODELS.json](MODELS.json)。元環境と外部資産を要するためcloneのみで推論開始できる版ではない。

## 研究候補プロンプトの保存

`v5/experiments/surface_prompt_v2_20261025`と`surface_prompt_v3_vs_v2_20261026`は実行済み比較ソースのbyte保持保存。v3の追加は版名と3点節だけ。既定`v5/runtime/contract_runtime.py`やLoRA/alpha/Plannerは変更しない。各evidenceのreview_packetに全実入力・RAW・元Fact履歴・参照を保存する。A保存出力を新規生成と数えない。

`python -X utf8 -B v5/tools/test_prompt_evidence.py -v`は保存4地点の入力再現・v2の正確な再利用・条件固定・HTML全文・レビューSHAをCPUのみで検査する。元の公式Processor54チェックをモデルなしで再実行したことにはならない。公開exportは外部凍結ファイルを除くためそのまま生成を起動できない。

## H06見る角度・段階①の保存

`v5/experiments/surface_viewpoint_h06_20261026/`は元実行ソースのbyte保持保存。元contract_runtimeを呼び、その出力末尾へ指定角度・元Fact引用・共通規則を追加する。元のv5/runtimeは変更しない。各条件は元履歴から独立に1回生成し、新規発話を次条件へ戻さない。

`python -X utf8 -B v5/tools/test_viewpoint_evidence.py -v`は保存済み実入力のrenderer一致、元の人間比較runからの正確な参照、条件固定、EOS、全出力とRAWのHTML保全、レビューSHAと意味未検証状態をCPUだけで照合する。元の公式Processorを伴うCPU62チェックは保存実績であり、ここで再実行したとはしない。protocol_exportは条件と来歴の記録で、外部凍結資産を含む実行用protocolではない。
