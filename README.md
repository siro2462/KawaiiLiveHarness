# ZIPちゃん Harness

Gemma 4 26B-A4BのPlanner / Talkを接続するHarness v5のソースです。`v5`タグを現在の実装の基準点とします。

## 構成

| 場所 | 内容 |
|---|---|
| [`_talk/lora_v4_gemma_runtime/`](./_talk/lora_v4_gemma_runtime/) | v5本体、CPUテスト、設計資料、実モデル評価用スクリプト |
| `_talk/lora_v4_planner_talk/` | 継承したPlanner / Talk契約、Event Store、評価処理 |
| `_talk/lora_v4_runtime_ab/` | 継承した検索・反復検知・CPU embedding接続 |
| `_talk/lora_v4_runtime_bc/` | 変更前のB / C / BCの比較用Runtime |
| `_talk/lora_v4_multibase/` | 既存の推論・オフロード・tokenizer・プロセス監視の参照コード |
| `_talk/src/e5-embed.py` | CPU E5の呼び出し元が参照するスクリプト |
| [`SOURCE_MANIFEST.json`](./SOURCE_MANIFEST.json) | 元ソースと同じバイト列を保存したファイルのサイズとSHA-256 |

既存コードの相対参照を保つため、元のディレクトリ名を維持しています。旧モデル名を含む共通コードもありますが、モデル本体・LoRAは含みません。

## v5の主な処理

- PlannerのJSON Schema制約付き生成と、出力全体の厳密検証。部分JSONの救出は行いません。
- pending / active / last valid Planの分離、期限管理、根拠MemoryのID・本文・ハッシュ照合。
- Memoryの保存と今回の発話への選択を分離。検証とTalk入力で同じ根拠を使用。
- Planner / Talkへ渡すRecentは直近3発話。再生確定の全文はEvent Storeに保存し、事実確認済みとは扱いません。
- 生成例外の分類、限定した再試行、PlanなしFallback、反復・異常出力・一部の事実改変の検知。
- 未再生の破棄候補は確定発話履歴に追加しません。現在の評価は模擬再生です。

会話内容の選択はPlannerが担当します。CPUの事実検査は限定的な字句・形態素ルールであり、通過しても事実性を保証しません。

## 現在の検証状況（2026-10-15）

- 元環境のCPUテストは62件成功。
- 今回のGit用コピーでもCPU検査32件を実行し、31件成功・実tokenizer未同梱の1件をskip。元環境の分離済み依存を利用し、環境変更は行っていません。
- 固定Gemma / LoRAによる短い結合試験、固定36条件、Memory選択、MemorySwap、未使用ケース、追加seed、2,700字の長尺生成を実行済み。
- 長尺は63ターン、模擬再生62件・2,700字。4.5字/秒換算の600秒相当で、実TTSの10分試験ではありません。
- 全入出力を保存し、全文レビューは途中です。学習・生成の完了と、雑談品質の合格を区別しています。意味反復や根拠のない具体的経験は残っています。
- αは入力契約のみです。Recall / Association / 自発的な提案・待機判断の本体は未実装です。

設計文書は作成時点の記録です。「未実施」などの記述は、このREADMEの状況より古い場合があります。

## 実行条件

これは**ソースのみのスナップショット**です。モデル、LoRA、tokenizer、量子化cache、Memory DB、学習素材、保存済み実験、生成ログ、第三者依存、認証情報は含みません。

推論コードには既存資産の配置・ハッシュ・保存runを確認する処理が残っています。cloneだけでは実推論を開始できません。詳細は[`DEPENDENCIES.md`](./DEPENDENCIES.md)を参照してください。

### 外部モデル資産を使わないCPU検査

リポジトリのルートで専用環境を用意します。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-cpu.txt
cd _talk/lora_v4_gemma_runtime
..\..\.venv\Scripts\python.exe -X utf8 -m unittest test_review_integration test_runtime_state test_evaluation_plumbing -v
```

実Gemma tokenizerを必要とする1件は、未配置なら明示的にskipします。他の回帰テストは元の保存runやtokenizerが必要です。全62件をこのリポジトリ単独で再現できるという意味ではありません。

## 主な設計資料

- [v5 / α設計](./_talk/lora_v4_gemma_runtime/design_v5_alpha.md)
- [根拠・Context・Fallbackの実装方針](./_talk/lora_v4_gemma_runtime/grounded_implementation_plan.md)
- [レビュー修正方針](./_talk/lora_v4_gemma_runtime/review_fix_plan.md)
- [CPU事実検査ケースと限界](./_talk/lora_v4_gemma_runtime/fact_validation_cases.md)

初回登録では元のRuntimeソースを変更していません。学習・推論の追加実行も行っていません。
