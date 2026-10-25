# 保存版の検査（2026-10-25）

- 旧停止runを使う標準ライブラリ検査：12/12 pass、失敗0・skip0。
- 現行継続版と保存完了結果を使う追加検査：15/15 pass、失敗0・skip0。
- 実際に保存された不正R0017をstrict parserが拒否し、Planを破棄して元Fact順へ継続する。CPU模擬Driver/α/Planner入力組立で、実rollout・Progress・履歴の経路を確認する。
- 保存された51＋5発話すべての履歴、Surface契約入力、元Fact単回提示、意味状態unverified、終了0、旧prefix17と新規85の区別、人間比較の素材切れ正常終了を検査。
- 人間比較に元発話を履歴として渡さず、4Memory9項目を投影したことと、Plan適用0を成功に数えないことを保存証跡で確認。
- HTMLと本文に全51/5発話・人間参照・Memoryが残り、元生成順が変わっていないことを検査。

初回の追加検査では検査用Planner入力組立が任意Janome依存へ到達したため、CPU mockの範囲を明示しSQLiteをfinallyで閉じるよう修正。実行済みRuntimeの修正や環境インストールはしていない。

ソース・証跡のbyte保持とSHA/サイズ、全Python構文、禁止バイナリ/資格情報パターンは`verify_snapshot.py --source-talk <元_talk>`で確認する。正本は[SOURCE_MANIFEST](../SOURCE_MANIFEST.json)と[検査記録](validation_checks.json)。

元のCPU154/44+11の実績は当時の保存記録。今回は全再実行していない。モデル・GPU・TTS・追加学習・新しい意味品質採点を行わず、設計者AIの既存全文レビュー・人間品質ラベル0をそのまま引き継ぐ。技術合格を意味品質合格へ変えない。
