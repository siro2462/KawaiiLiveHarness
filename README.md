# ZIPちゃん Harness v5

**現行構成の保存版：v5-current-20261026。研究中のオフラインRuntimeです。**

記憶α → 既存Base Planner LoRA → Flow→Fact適用 → 新Instruct Surface LoRA → 形式確認 → テキスト履歴・提示進捗 → 次のPlanner。不正Planner JSONはRAWを保存・Planを破棄し、元Fact固定順で継続します。Semantic Guardは現行経路で使用していません。

- [現在地・次の問い](v5/progress/CURRENT_STATE.md) ／ [構造化チェックポイント](v5/progress/checkpoint.json)
- [アーキテクチャ](v5/ARCHITECTURE.md) ／ [現行Runtime](v5/runtime/)
- [固定モデル・adapterの版とSHA](v5/MODELS.json) ／ [条件記録](v5/PROTOCOL.json)
- [実験結果・未解決事項](v5/STATUS.md)
- [51発話・2503字の全文](v5/evidence/continuous10_20261024/speech.txt) ／ [結果](v5/evidence/continuous10_20261024/result.md) ／ [全入力・RAW・評価HTML](v5/evidence/continuous10_20261024/comparison.html)
- [人間・既存Memory・AIの3列比較](v5/evidence/human_memory_compare_20261024/comparison.html) ／ [人間原文](v5/evidence/human_memory_compare_20261024/reference/human.txt) ／ [AI全文](v5/evidence/human_memory_compare_20261024/speech.txt) ／ [結果](v5/evidence/human_memory_compare_20261024/result.md)
- [復元条件とCPU検査](v5/REPRODUCING.md) ／ [ソース・証跡SHA台帳](SOURCE_MANIFEST.json)

## Surfaceプロンプト研究の更新（2026-10-26）

[現行版対v2](v5/evidence/surface_prompt_v2_20261025/comparison.html) ／ [v2対v3全文](v5/evidence/surface_prompt_v3_vs_v2_20261026/comparison.html) ／ [結果](v5/evidence/surface_prompt_v3_vs_v2_20261026/result.md) ／ [候補ソース](v5/experiments/surface_prompt_v3_vs_v2_20261026/)

v3は話の中心・根拠を受けた評価・事実を盛らない3点を追加。新規Surface4件、全EOS、v2保存1067字に対しv3は984字。中心や一部の前提は改善したが、全部成功などの改変は残るため採用保留。既定Runtimeのプロンプトは変更していない。1seed/既知素材/設計者AI既知条件/人間0、閉ループの比較ではない。

## 現在の到達点

短い発話を履歴へ戻す経路で51/51発話・2503非空白字を完走。250字/分仮定で約10.01分相当で、実音声時間ではありません。旧17callを全入力/SHA一致で再利用、新規85call。元runのexit1は保全し、継続runはnative/launcher/両Python exit0。不正Plan5件で固定順へ戻り継続できました。意味品質は未保証です。

人間原文比較は4話題1961字→既存逆算Memory416字→AI5発話730字。概要を話すことはできましたが、人間の発見・怒り・自慢の展開は説明へ寄り、全弾成功への強化やバッグの所有関係の誤りが残りました。Memory段階の欠落と生成時の改変を分けて記録しています。

Gold焦点をSurfaceへ届ける例は確認済みですが、学習済みPlannerの有効な再計画や自然さへの優位性は未実証。人間比較のPlannerは構文5/5でも内容崩壊1、適用採用0、順序変更0でした。技術監査passと意味品質合格は別です。

## バージョン

- `v5`：2026-10-15の初回保存点。変更しません。
- `v5-20261023`：不正Planで停止した旧実験とその時点のソース。変更しません。[旧README](docs/history/v5-20261023.md)
- `v5-20261025`：固定順継続修正、完了した10分相当発話・人間比較、現在地の保存点。
- 旧8発話の停止結果は[v5/evidence](v5/evidence/)内に保全。後続完了を元失敗の成功へ書き換えていません。

ソース・合成fixture・許可された比較実験の全文/評価/限定した人間比較原文を保存します。モデル/LoRA重量、tokenizer、量子化cache、全文教材・元配信ZIP、Memory DB、チャットSQLiteや認証情報は含めません。cloneのみで推論は開始できません。[依存資産](DEPENDENCIES.md)

```powershell
python -X utf8 -B v5/tools/verify_snapshot.py
python -X utf8 -B v5/tools/test_snapshot.py -v
python -X utf8 -B v5/tools/test_current.py -v
python -X utf8 -B v5/tools/test_prompt_evidence.py -v
```

これらは標準ライブラリだけのソース・保存証跡・CPU模擬検査で、モデル生成や学習を実行しません。
