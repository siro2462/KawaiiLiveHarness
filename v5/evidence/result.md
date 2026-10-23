# 連続発話は未完了：8発話・429字で停止

9回目のPlanner（R0017、買い物メモの最後のFactを話す前）で、出力が `flow_id_flow_2_topic_flow_2...` と反復し、256 token上限までにJSONの文字列・オブジェクトを閉じられなかった。strict parserがUnterminated stringとして拒否し、設計通り停止した。履歴の切り詰めは0。controllerとGPU workerのPython終了は両方1。GPU側の「Controller requested stop」はこれを受けた終了であり、OOMやSemantic Guardの保留ではない。

- Surface8件は全件テキスト履歴へ採用、14Factを単回提示。429字＝250字/分なら約1.72分相当。10分目標未達、実TTSなし。
- αは手袋→二冊のノート→買い物メモを提案。初期種以後は実生成本文cueで、ここまでbroad fallbackなし。
- 有効な8Planのうち3件が既存元文対応で適用されたが順序変更0。残りは棄権2件、source契約なし2件、Flow未対応1件の固定順。再計画の優位性は示さない。
- 本文では手袋を探す→発見→安堵の継続が成立。一方、話題切替は「そういえば」、語尾も「んだよね」に偏る。ノートの「残した」→「残してる」には現在まで続く状態への含みがあり、意味品質を合格とはしない。
- F08-5「次回からスマホにもメモを保存することにした」は未提示のまま停止し、未発話分を補っていない。

発話8件とPlanner本文9件・停止ログは今回全文確認した。全実入力の意味レビューや完了時の全件品質評価は未実施。CPUの部分整合検査は、元runの成功・意味品質を保証しない。1seed/合成3件まで/設計者AI既知条件/人間評価0/比較対照なし。新規生成・再試行・モデル変更は行っていない。

## 時間

{
  "surface": 8,
  "delivered": 8,
  "planner": 9,
  "valid_plans": 8,
  "invalid_plans": 1,
  "source_fact_targets": 14,
  "delivered_chars": 429,
  "estimated_minutes_at_250chars": 1.716,
  "target_chars": 2500,
  "target_met": false,
  "planner_applied": 3,
  "planner_order_changes": 0,
  "topic_sequence": [
    "F01",
    "F20",
    "F08"
  ],
  "controller_wall_seconds": 1827.886303,
  "model_generation_seconds": 1279.965,
  "surface_generation_seconds": 344.24,
  "planner_generation_seconds": 935.725,
  "semantic_guard_calls": 0,
  "training_updates": 0,
  "quality_retries": 0,
  "actual_tts": false,
  "human_quality_labels": 0
}

実測生成時間、処理全体の経過時間、文字数からの発話推定時間は別物。
