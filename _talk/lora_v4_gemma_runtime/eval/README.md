# v5品質評価（通常Runtimeから独立）

`implementation_plan.md`のStep 1〜3用。既存Runtimeのソースとモデルを変更しない。

## CPU

`python -X utf8 -B -m unittest test_quality_eval -v`

## 元資産を指定した準備・実行

```text
python quality_eval.py prepare --runtime-root <元v5ディレクトリ> --source <保存済み実評価run> --out <新run>
python supervise_quality_eval.py --runtime-root <元v5ディレクトリ> --out <新run>
python build_quality_report.py --out <新run>
```

監視起動の前に元62検査と新規CPU検査の成功、fixtureの入力復号、元adapter/tokenizer/根拠の一致を確認してcpu_preflight.jsonを保存する。preparedだけでは実行可能扱いにしない。

GitHubのソース単独にはモデル・元run・Memory DBがない。`--runtime-root`は必要な資産が配置された元環境を指す。

## 評価者

- `blind_review.html`は左右を匿名化した候補、元Memoryと直前の文脈を表示する。
- 評価者ID、評価者区分、選好、6軸0〜4またはN/A、根拠なし主張・矛盾の件数を記録する。
- 未評価の欄を0として保存しない。AI_rootを人間評価に混ぜない。
- 保存したJSONLを`human_review.jsonl`として新runに置き、CPU reportを再実行する。複数評価者はJSONL行を結合し、同じpair/raterの重複は除く。
- `blind_key.private.json`は集計用。採点前の評価者には渡さない。
- source caseごとにseed/評価者の平均を取り、scene/episode clusterでbootstrapする。観測済みdevelopment資料と少数clusterから本番採用を確定しない。

Fact Gateのflagは正誤ラベルではない。原子的claimの全件ラベルがないため、捏造件数/1000字、precision/recall、誤拒否率を自動的には算出しない。自然さの選好と事実性の採否は別である。

通常Event Store・実TTSへ候補をcommitしない。長尺への作用と検索方式変更はStep 4以降であり今回の102組からは分からない。
