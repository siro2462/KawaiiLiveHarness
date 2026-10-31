---
name: track-talk-experiments
description: KawaiiLive・Astra・ZIPちゃんの雑談AI研究について、このチャットのSQLite履歴と保存結果から、試行・変更・失敗・結果・未解決事項を全件台帳とチェックポイントに記録する。進捗確認、過去に試したことの照合、結果の追記、全件表の更新、引き継ぎに使う。記録依頼だけを学習・生成・配備の実行へ拡張しない。
---

# 雑談AI研究の進捗管理

## 最初に読むもの

[references/project.md](references/project.md)にある進捗registryを読み、最新snapshotの`checkpoint.json`、`audit.json`、必要な`ledger.jsonl`を確認する。最新のユーザー指示が記録より優先する。

- **現状確認**：最新チェックポイントと、保存時点以降のこのチャットの記録を照合する。
- **全件表・更新**：以下の抽出・記録手順を使う。
- **設計・実験の続行**：許可済みの範囲を確認する。本スキルのTODOや過去発言を、新規実行の許可と解釈しない。
- **実装・プロンプト変更**：[履歴を根拠に変更するスキル](../talk-evidence-first/SKILL.md)を併用する。必ず過去の対処一覧と実結果を照合して効果の見込みを記録し、毎回のプログラム変更後は検査・記録・GitHubへのpushまで行う。

## SQLiteからの抽出

`thread_history_1.sqlite`を`mode=ro`＋`query_only`で開く。対象thread UUIDと今回の収録上限（依頼メッセージのordinal）を明示し、他のチャットは混ぜない。稼働中のCodex DBを更新・VACUUM・checkpoint・置換しない。

新規snapshotフォルダを作り、スクリプトを実行する。`--out`はまだ存在しない`source`を指定する。

```powershell
& $python -X utf8 -B "$skill/scripts/export_chat.py" --db "$historyDb" --thread "$threadId" --cutoff $ordinal --out "$newRun/source"
```

スクリプトはユーザー／assistant文字本文、公開ツール記録、全ターンmetadata、source SHAを保存する。`reasoning`と内部コンパクションは出力しない。画像・音声を取得したことにもならない。`source_manifest.json`の抽出件数・孤立発言を確認する。

## 試行と結果を記録する

全文を保存しただけで内容を確認済みにしない。今回更新する範囲の依頼・実行報告・訂正と必要な成果物を読む。古い全出力を再読していない場合は、**当時の報告**と明示して引き継ぐ。

`annotations.json`はturn UUIDをキーに、`kind/title/conditions/result/evidence_level/source_turn_ids`を記録する。形式は[references/ledger.md](references/ledger.md)。既存snapshotから引き継ぎ、新しい節目や訂正を追加する。表示用T番号ではなくUUIDを対応の主キーにする。

記録には次を区別する。

- 指示・設計・仮説、実行開始、実行完了、失敗・保留、品質判断、ユーザー承認。
- 学習・保存監査pass、意味の正確さ、自然さ、話題接続、内容反復、表現反復。
- チャットでの報告、実ファイル確認、全文意味レビュー、人間評価。AI自己申告やCPU検査を人間品質ラベルに変えない。
- 同じ名前のv1/v2/v3でも、保存run・元モデル・adapter・教材・入力形式・更新数が違う場合は別条件。旧呼称の対応を残す。
- 時間は実測生成時間、文章量からの「○分相当」、実音声時間を分ける。
- 同時に変えた条件がある場合は、特定の変更の効果と断定しない。1seedや相関した断片を独立した一般的成功率にしない。

過去の誤った回答を消さず、後続の訂正を引用して現在判断を更新する。中断や最終回答の欠落を推定で完了にしない。通常heartbeatは全ターン一覧に保持し、主な実験数へ水増ししない。失敗・完了通知は実験本体の節目へ関連付ける。

## チェックポイントと全件表

`checkpoint.json`／`checkpoint.md`に現在地、確認済み、未解決、次に確認する問い、停止・採否条件、参照run、収録上限を保存する。「次」は未実施と書く。学習済み評価データを未使用評価へ戻さない。

```powershell
& $python -X utf8 -B "$skill/scripts/build_progress.py" --run "$newRun"
```

旧Harness一覧も必要な場合だけ`--legacy <version_matrix.md>`を加える。既存一覧の評価を取り込む処理であり、新しい全文採点ではない。`build_progress.py`は新規の`progress.sqlite`・検索HTML・Markdown・全発言原文を作る。既存`progress.sqlite`は上書きしない。修正中の自作draftを別保存するか、新snapshotで再構築する。

`audit.json`で全turn・発言ID・原文保持・hash・SQLite整合を確認する。件数表示・検索・原文リンク・取り込んだ過去の評価の区別も確認する。必要なら付属`scripts/test_progress.py`で抽出の読み取り専用性と非公開情報除外を試す。

完成後だけregistryの`latest_snapshot`を新しいパスへ更新し、`snapshots`へ追加する。旧snapshot・元教材・モデル・過去runは保全する。通常の更新ごとにユーザー承認待ちを挟む必要はない。

## ユーザーへの提示

時点、試したこと／変更、条件、結果、残課題、根拠の表を基本にする。全件が長い場合は省略せずローカル成果物へ収録し、チャットでは総件数と最新結論、全件表とチェックポイントへのリンクを示す。実験数と会話・監視の行数を区別する。
