# ZIPちゃん Harness v5 / α — 実コード対応と開発方針

2026-10-14。貼付された設計を採用。Libraryの277行仕様書そのものは未取得。以下のインターフェース案は取得後に照合する。

## 責務

- v5は既存Runtimeの改修。Plannerが話題と展開を決め、Talkが発話する。
- αは上流の追加機能。Memoryから想起候補を探し、提案するか待つかを判断する。
- αはFlow・台本・発話本文を作らない。提案は義務的な話題変更にならない。
- 元Memory、再生確定全文のEvent Store、Planner/Talk分離、LoRAと検索の成果を継承する。
- モデル・Planner v1/Talk v4 LoRAは固定。追加学習はこのRuntime比較に含めない。

## 実ファイル対応

起点は `C:/NodeJS/KawaiiLive/work/astra/_talk/`。旧実験のコードは凍結したまま、このディレクトリにv5改修版を追加する。

| 仕様の変更対象 | 実際の旧ファイル・関数 | 確認した問題 | v5の改修 |
|---|---|---|---|
| Planner制約付き生成 | lora_v4_multibase/inference_models.py: Models.generate / plan_control | Stop callbackはJSONを認識するだけ。token制約なし | inference_v5.py: constrained_planで毎tokenのallowlistをgenerateへ渡す |
| Plan解析 | lora_v4_runtime_bc/policy.py: balanced_objects / rescue_plan / get_plan、lora_v4_planner_talk/contracts.py: parse_plan | 壊れた外側や説明文の中の部分JSONも採用 | planner_policy.py: 出力全体をstrict parse。部分救出・補完なし |
| Plan採用 | lora_v4_runtime_bc/policy.py: PlanStore.stage / commit | schemaが主な採用条件 | schema→Memory事実検査→pending→commit。形式probeを本Runtimeへ採用しない |
| Memory照合 | lora_v4_runtime_bc/consistency.py: check_plan / issues | うなぎの蒲焼き等を字句検査が通す | 対象・行為・否定・時点・因果を区別。一般的感想/連想の一律拒否はしない |
| Context Builder | contracts.py: talk_prompt / fallback_prompt、BC policy.py: speech_prompt | use_memory=falseで根拠を渡さず、Flow内の経験が残る | canonical Memoryと方向付けPlanを別枠にし、use_memoryだけで根拠を消さない |
| Active Plan | BC policy.py: PlanStore.fallback、engine.py: install / step | last_validを繰り返し復帰でき、検出後も古いPlanが残る | 現行3発話期限を基準に期限・Memory本文hash・介入時無効化を管理。fallbackで期限をリセットしない |
| Talk形式・反復 | lora_v4_planner_talk/runtime.py: hard_failure、lora_v4_runtime_ab/core.py: detect | 形式/文字列反復中心 | 既存検知を継承し、無根拠な具体経験の検査と別の結果として記録 |
| Fallback | BC engine.py: can_speak、policy.py: get_plan / fallback | 初期valid PlanなしではTalkを呼ばず30空再生 | 最大2attempt→有効last_valid→根拠Memoryを保持したPlanなしTalk。固定台詞を生成しない |
| Recent / Event Store | BC policy.py: recent_window、runtime.py: commit_playback | Recent3と全再生保存は既存Cの成果 | 継承。未再生破棄は確定履歴に入れず、再生記録のfacts_verified=falseを維持 |
| α→v5 | 現行に該当機構なし | 外部きっかけからの自発想起未実装 | 別モジュールの提案契約。Memory IDを原DBへ照合し、v5 Plannerに候補として渡す |

## 実装順と検証

1. strict JSON解析＋生成制約。保存済み失敗、壊れた外側、複数object、重複key、未知ID、配列数、Unicode、EOSをCPUで検査。固定4入力の実生成を一度確認する。
2. Memory事実・Context Builder。既知うなぎ改変、数値追加、方角交換、過去→現在を反例にし、感想/仮定/冗談/自然な脱線の許容例も確認。
3. 期限付きPlanと根拠付きFallback・反復時更新。Runtimeは期限と検証を担当し、次の話題の内容はPlannerが決める。新Active Episode DBは作らない。
4. 固定36条件と長尺の新比較。全入力/Plan/未再生/再生本文を横並び保存し、旧BCより自然さと事実保持を悪化させていないか目視する。
5. αを独立にRecall→Association→提案/待機で開発。検索と契約の検査は進められるが、v5検証前に実会話へ統合しない。
6. v5＋α統合。自発的想起が成立しても発話の義務・強制話題遷移・二重Plannerにはしない。

## JSON制約の範囲

LM Format Enforcer 0.11.3をv5専用dependenciesに固定。4必須key、型、候補ID/null、Flow2〜4要素を生成中に制約する。boolean constの実装に限界があるため、use_memoryとmemory_idの相互条件と文字列非空白は**採用時にstrict parserで検証**する。token上限までにJSONを閉じなかった場合も不採用。schema通過はMemory整合性の証明ではない。

Gemmaの特殊tokenと単独で復号不能なbyte tokenはallowlistから除外。JSON Unicode escapeは使用可能。入力tokenizationは変更しない。この出力制約の範囲を比較結果に記録する。

公式資料: [LM Format Enforcer](https://github.com/noamgat/lm-format-enforcer)。tokenごとの制約を導入しても意味の正しさは別に検証する。

## αインターフェース案（詳細仕様書との照合前）

```json
{
  "version": "alpha.v0.1",
  "decision": "propose",
  "trigger": {"kind": "external_event", "event_id": "event-123"},
  "memory_ids": ["memory-42"],
  "topic_hint": "橋を見て思い出した探索ゲームの話"
}
```

waitはmemory_ids空・topic_hint=null。topic_hintは候補であり事実の根拠ではない。実体験の根拠は指定IDから読み出した元Memoryのみ。v5 Plannerは待機や別の方向を判断できる。Flow/発話本文のフィールドは拒否する。例のIDは契約説明用で、検索の実出力ではない。

## 形式probe完了時点の到達点（2026-10-14）

実コード調査と改修設計を完了。strict parser・JSON token制約を追加し、17CPU検査を通過。Context Builder、期限を延長しないPlanStore、α提案契約もCPU部品検査を通過したが、既存の本Runtimeにはまだ接続していない。

固定4入力のGemma Planner実生成は1回のみ実行し、各1attempt・計4callで4件ともstrict schemaを通過。旧B/改善版の初回形式失敗も、救出せずに生成できた。全実入力・旧/new全出力をrootが読んだ。

ただし全4件がuse_memory=false。MemoryありRELでは旧出力のtrue/mem:15からfalse/nullに変わった。これはMemoryの採否を改善した結果ではない。元MemoryをPlanフラグと独立に保持する次工程が必要。「冷凍うどんをかけた」等の曖昧な関係や「嬉しさ」等の文脈との感情のずれも残る。Memory事実検査、RuntimeへのContext/Fallback接続、Talk/長尺、α検索/待機、実発話品質は未完了。

[固定4入力の全文比較](runs/harness_v5_schema_20261014b/comparison.md) / [HTML](runs/harness_v5_schema_20261014b/comparison.html)

最初の未実行準備版harness_v5_schema_20261014は15CPU検査521.764秒の証跡として保持。実GPU検証は後継bの1回だけ。Unicode初期化と文字列内token探索を修正し、同じ文字列を別の台詞へ置き換える処理は追加していない。キャッシュはquote/escapeを含むtokenも元parserで検査し、構文外の自由な発話制御には使わない。

## ZIPレビュー後（2026-10-15）

[限定修正計画](review_fix_plan.md)に従い、検索候補なしの暗黙継続を廃止、検査とTalkの根拠を現在選択1件に統一、生成例外の分類とCPU結合検査を追加。α→v5のproposeは1Memoryだけを受理する。内部Recallの複数候補と外部の1件選択を区別する。最新の実測結果と残る検出漏れは `audit/review_20261015/review_response.md` を参照。
