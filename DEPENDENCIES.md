# 依存と外部資産

## CPU検査

`requirements-cpu.txt`はJanome、tokenizersとv5専用JSON生成制約の依存です。第三者パッケージ本体は管理対象に含めません。

元環境では`lora_v4_gemma_runtime/dependencies/`と`morphology_dependencies/`へ依存を分離しています。コードは通常のPython環境に導入された同パッケージも参照できます。

READMEに掲載した3つのCPUテストモジュールはフェイクPlanner / Talkと実SQLiteを使います。生成品質やTTSの試験ではありません。実tokenizerがない場合、その1件をskipします。

`test_planner_policy.py`と`test_fact_gate.py`は保存済みの旧Gemma / BCログ・Memoryを参照します。`test_schema_constraints.py`は実Gemma tokenizerとgeneration configが必要です。これらの資産は含めていません。

## 元の推論環境

元環境の主な固定バージョンは以下です。推論環境を自動構築するrequirementsではありません。

| 依存 | バージョン |
|---|---|
| PyTorch | 2.9.1+rocm7.2.1 |
| Transformers | 5.17.0 |
| PEFT | 0.21.0 |
| bitsandbytes | 0.50.2 |
| tokenizers | 0.23.2 |
| psutil | 7.2.2 |
| Janome | 0.5.0 |

JSON制約の固定バージョンは[`requirements-v5.txt`](./_talk/lora_v4_gemma_runtime/requirements-v5.txt)にあります。CPU E5には別途NumPy、ONNX Runtimeと元のembedding profileが必要です。

## 同梱していない外部資産

- Gemma 4 26B-A4B本体・tokenizer・生成config・量子化cache。
- 同じGemmaから学習したPlanner v1 / Talk v4、およびローダーが確認するTalk v3の最終adapterと結果メタデータ。
- 元Memory DB、E5モデル・profile、学習split / donor / maskの照合資料、保存済み旧runと参照ハッシュ。
- 元のPython環境、GPUドライバ、第三者依存、認証情報。

`inference_models.py` / `multibase_common.py` / `probe.py`は元配置を前提とした共通ローダーです。`prepare_data.py`はtokenizer処理の参照元として含めています。学習データの再構築や旧multi-base pipeline全体を動かすためのソース・素材一式は含みません。

`supervise_real_evaluation.py`は旧監視コードから`ObservedProcess`をASTで取り出して利用するため、その参照ファイルも保存しています。旧監視pipelineそのものを起動する用途ではありません。

既存コード内のローカルパスを別環境へ対応させる変更は、この初回スナップショットの範囲に含めていません。

## レポートの既知の注意点

凍結した`report_real_evaluation.py`の`fact_rejected_candidates`は、一部の観測用fact flagも含めて数える実装です。候補の実拒否数とは一致しないため、値をそのまま拒否率・正確率に使わないでください。元実験の最終集計では、保存された実再生・未再生と候補検査を別に照合しています。この登録では推論・集計ソースを変更していません。
