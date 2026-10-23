# 保存版の確認（2026-10-23）

- ソース89件を元環境のファイルとSHA-256/サイズ/bytes一致で確認。
- コピーしたPython74ファイルの構文を確認。モデル・ネット・GPUを使わず実施。
- 保存データを使うCPU回帰検査12件、成功12/失敗0/skip0。
- 対象：20合成fixture94Fact、実8発話の履歴受け渡し・Surface入力一致、14対象の単回提示、unverified状態、Flowの発見→安堵依存順、未知IDの固定順、保存された不正JSONの拒否、正常Plan四キー、最終call後DONE終了、形式採用と実験未完了の区別。
- ソース台帳の全ファイルを資格情報パターン・禁止バイナリ混入について検査。

これはpush用スナップショットの整合確認。学習・モデル生成・元環境CPU251項目の再実行・実TTS・人間品質評価は行っていない。最新長尺実験は8発話で失敗終了したまま。

実行：

```powershell
python -X utf8 -B v5/tools/verify_snapshot.py --source-talk <元の_talk>
python -X utf8 -B v5/tools/test_snapshot.py -v
```

Git登録は元のCRLFと末尾空行も保持する`.gitattributes`方針を継承。ステージされた40ファイルも作業コピーとbyte一致。コピー元由来の末尾空行3件は改変せず保持した。
