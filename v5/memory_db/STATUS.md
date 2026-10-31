# 現在地：Memory DB初回実装と30件CPU確認

2026-10-29。新しい記憶DB・互換投影・CPU選択・Surface入力・別発話ログを実装。既定Runtimeへの採用はしていない。

- 単体検査34件pass。訂正時の承認リセット、旧版再現、取込途中失敗の全rollback、異namespace拒否、希望を出来事にしない処理、元H06の32操作再現、発話ログ再open/二重登録拒否/履歴反映を含む。発話ログ検査の本文は明示したCPU用の模擬文字列であり、モデル生成結果ではない。
- 凍結30記憶・359断片・314関係を取込。元JSONへの再出力は30/30一致、再取込重複0。
- 元記憶由来109・創作補完250を区別。30件中、既存の内容確認済み8／修正待ち2／未確認20の状態は維持。今回のCPU合格で内容を承認していない。
- 新rhythmは389操作、7断片保留。同色最大3。旧H06は359操作、14断片保留。操作数にはREVISITを含み、記憶件数とは別。
- 新rhythmの保留は元ID21/22/23/26/27/29/30のP断片。内容は「話に何を添えたいか」という語り方の意向。状態文字列の共通コード対応が未定義なので保留し、本文は原形で保存。過去の出来事へ変換したり削除したりしていない。
- α検索30件とsnapshot内への候補解決、公式CPU Processorによる30入力の全文復元を確認。入力3447〜4130token、切詰0。生成は0。
- 追加の夏祭りfixtureは44断片・50参照。30件とは別namespace。希望と実行済み、疑問と答えの向きを検査。
- 発話入力には版・由来・確かさ・状態・場面・話の中心を保持。新接続専用rendererであり、以前のSurface条件との同一性比較や発話品質評価ではない。
- 初回単体検査の2errorは検査側のパス/SQLite close漏れを修正。統合v1はscikit-learn参照不足で終了1。v1を保全し、保存済み依存先を明示したv2が終了0。ダウンロード・GPU推論・学習・TTSは0。

## まだ確認していないこと

実モデルの発話品質、長い閉ループ、複数エピソードをまたぐ自律的な話題選択、大規模負荷。本結果の色はCPUが決めた操作で、実発話を分類した色ではない。新接続は既存rhythmの一般priorと明示リンクを使い、既知10素材用の調整済み順位重みを使っていない。

## 保存先

- `memory_v2.sqlite`：本体（30件＋別namespaceの夏祭り1件）
- `alpha_projection.sqlite`：30件専用検索投影
- `comparison.html`：30件の元情報・保存断片・CPU操作・Surface入力
- `test_results.txt` / `technical_audit.json`：実検査結果
- `review_packet.json` / `prepared_inputs.json`：全保存情報・両CPU操作・全実入力
- `implementation_manifest.json` / `implementation_source/`：検証時の新実装

この検証のための監視や常駐プロセスは作成していない。

検証run: C:\NodeJS\KawaiiLive\work\astra\_talk\harness_beta\runs\memory_db_validation_20261029_v2
