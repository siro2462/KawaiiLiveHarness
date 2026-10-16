# v5 品質評価 Step 1〜3 実装方針

2026-10-16。ユーザーはStep 1〜3の評価基盤実装・CPU検証・新規Gemma AB生成まで明示的に承認した。

## 固定するもの

- v5本体・旧共通推論・学習済みGemma/Planner/Talk・Memory原文・既存runは変更しない。
- 学習、モデル取得、α本体、検索方式のAB、長尺再生成、192token比較は今回行わない。
- 新規コードはeval/、出力は新しいruns/quality_eval_20261016_*。既存結果を上書きしない。

## Step 1

既存100 Planner / 248 Talk候補のschema・事実検査・実再生を再照合し、破棄理由と内容正誤を混同しない。長尺29回の検索をquery全文・上位5件・首位と2位の差・除外ID付きで出力する。保存済みGold / Generated / Planなしの3発話まとまりを一覧にする。

## Step 2

既存MemorySwapのCURRENT_ALWAYS初回20入力と、未使用ケース試験の同初回10入力を固定する。これは既に出力を見たdevelopment資料であり、新しいheldoutではない。入力が同じscene/episode由来なら同じclusterにする。

30入力 × 3seed（20260925/26/27） × 2条件 = 180 Talk呼出し。A=max_new_tokens96/sentence_limit2、B=96/0。raw入力token・Memory・Plan・samplingを完全一致させる。Aの出力がBのprefixになることを検査する。

## Step 3

- 決定論的Plan文字列健全性検査を評価専用に追加する。記号のみ、HTML見出し、Flow全項目が完全同一を検出し、意味的な話題進展とは分ける。通常の採用処理へ接続しない。
- Fact Gateは既存の固定ケースと全候補を再評価。人間の正解ラベルがないものはprecision/recallを算出しない。
- 保存済みfact拒否のうち、根拠に照合してPlanを保持可能とrootが確認した4事象（actual call134/260/294/301）を固定する。rootはAIレビューであり、人間の独立評価とは呼ばない。
- 各事象×3seed×2ポリシー=24 Talk呼出し。共通の保存済み拒否候補とfeedbackを出発点に、Plan破棄/保持の再試行を1回ずつ比較する。初回候補は再生成しない。これは拒否発生後の条件付き診断で、発生率や長尺への因果効果ではない。

新規生成は計204 Talk呼出し、Planner再生成0。CPU検査後、最初の1組をsanityとして予定内で実行し、入力一致/出力prefix/モデル障害を確認して残りへ進む。障害・不一致で停止し自動再起動しない。

## 評価・保存

全raw/decoded入出力、token、seed、停止理由、CPU flag、コスト、対応する元callを保存する。実TTSや通常Event Storeへのcommitは行わない。影のFact Gate通過を事実認定としない。

ブラインド比較用の左右ランダム化HTMLとラベル入力を用意する。自然さ等6軸と事実性を分離し、単発条件では長期的進展をN/Aにできる。人間の評価が未提出なら選好率・採用判定は未測定。seed・評価者を独立ケースとして水増しせず、同scene/episodeでcluster bootstrapする。小cluster数と非盲検root所見は明記する。
