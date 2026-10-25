# ZIPちゃん Harness v5

**現行構成の保存版：v5-current-20261023。研究中のオフラインRuntimeです。**

記憶α → 既存Base Planner LoRA → Flow→Fact適用 → 新Instruct Surface LoRA → 形式確認 → テキスト履歴・提示進捗 → 次のPlanner、という現在の経路をソースと実験結果ごと保存しています。Semantic Guardは現行発話経路で使用していません。

- [アーキテクチャ全体](v5/ARCHITECTURE.md)
- [現行Runtimeのソース](v5/runtime/)
- [固定モデル・adapterの版とSHA](v5/MODELS.json)
- [現在の条件](v5/PROTOCOL.json)
- [実験結果・未解決事項](v5/STATUS.md)
- [停止までの8発話全文](v5/evidence/speech.txt)／[停止原因](v5/evidence/result.md)
- [復元時の配置とCPU検査](v5/REPRODUCING.md)
- [元ソースとのSHA台帳](SOURCE_MANIFEST.json)

## 現在の到達点

短い発話を実際のテキスト履歴へ戻す経路は動作しています。指定したGold焦点をSurfaceへ届ける4例も確認済みです。学習済みPlannerによる有効な焦点変更や、Bより自然になる効果は未証明です。

最新の約10分相当テストは、8発話429字の時点で9回目PlannerがJSONを閉じられず停止しました。実行は失敗終了で、10分目標は未達です。停止時のコードをそのまま保存し、JSON不正時の継続処理は追加していません。CPU検査251項目の成功と、長時間生成の成功・意味品質は区別しています。

## バージョンの対応

- 既存の`v5`タグ：2026-10-15時点の初回スナップショット。変更しません。
- `v5-20261023`：現在のα・新Surface・漸次Runtimeと既知の失敗を含む保存点。
- `_talk/lora_v4_gemma_runtime/`などは継承した依存・過去Runtimeです。現在の入口は`v5/runtime/run_cpu.py`です。古いディレクトリ名のv4/v5や過去READMEを、現行の品質判定と混同しないでください。
- [2026-10-15版README](docs/history/v5-20261015.md)も保持しています。

このリポジトリはソース・合成fixture・限定した実験証跡の保存です。モデル本体、LoRA重量、tokenizer、量子化cache、教師原文、元配信ZIP、記憶DB、環境・認証情報は含みません。cloneのみで推論は開始できません。外部資産の条件は[DEPENDENCIES.md](DEPENDENCIES.md)を参照してください。

```powershell
python -X utf8 -B v5/tools/verify_snapshot.py
python -X utf8 -B v5/tools/test_snapshot.py -v
```

上の2つは標準ライブラリだけのソース・契約・保存fixture検査で、モデルの生成や学習を実行しません。
