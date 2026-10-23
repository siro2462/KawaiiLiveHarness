# 依存と外部資産

## 現行v5（2026-10-23）

[MODELS.json](v5/MODELS.json)に固定したBase Plannerと新Instruct Surfaceのrevision、adapter SHA、Surface生成設定・学習条件を記載する。Surfaceは新教材61学習組/1epoch8更新で、旧751組adapterではない。

- Planner: Gemma 4 26B-A4B Base＋既存Planner checkpoint0040。
- Surface: Gemma 4 26B-A4B Instruct＋新Surface LoRA。
- GPU: 既存NF4 CPUストレージ＋有界GPU staging。adapter tensorを読み込んだ実体とディスクで照合。
- α: NumPy、scikit-learn、PyYAML。今回は文字TF-IDF代理検索。任意E5 backendは使わない。
- CPU: 公式Processor用CPU専用torch/Transformersとtokenizers、psutil。GPUのtorchをCPU観測へ混ぜない。
- JSON制約: `_talk/lora_v4_gemma_runtime/requirements-v5.txt`の固定依存。

元推論環境の記録：PyTorch2.9.1+rocm7.2.1、Transformers5.17.0、PEFT0.21.0、bitsandbytes0.50.2、tokenizers0.23.2、psutil7.2.2。これは環境を自動構築するrequirementsではない。

## 同梱しない資産

モデル・tokenizer・生成config原本・量子化cache・LoRA重量・旧ローダーが参照する旧adapterとメタデータ、教師原文、reference ZIP、Memory DB、旧実験フルログ、元Python環境、ドライバ、第三者パッケージ、環境変数や認証情報。

`v5/runtime`は元の実行ソースを変更せず保存するため、元の配置やprotocol照合を前提としたコードがある。実行条件は[REPRODUCING.md](v5/REPRODUCING.md)を参照する。cloneだけで実推論を開始できるとは主張しない。

## CPU検査

`v5/tools/verify_snapshot.py`と`test_snapshot.py`は標準ライブラリだけで実行でき、モデル・ネット・GPU・依存インストールを使わない。

従来の`requirements-cpu.txt`と旧v5テスト群も保持する。旧`test_review_integration/test_runtime_state/test_evaluation_plumbing`は分離した形態素・tokenizer依存を要し、実tokenizer未配置の検査はskipとなる。保存済み旧runを必要とする他の検査は、このrepoだけでは再現できない。過去の57/62件などの実績と、今回の保存ソース検査を混同しない。
