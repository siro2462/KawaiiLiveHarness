# 4操作ずつの比較候補
同じM06/M17/M23・40 CPU操作・保留1を順序不変で4件ずつ束ねる。新規上限11call、LoRA・Memory・スタイル・生成条件固定。残りは2操作。

CPU199/依存8/実child_guard startup exit0済み。公開時は生成前、意味品質は未評価。履歴と実出力の照合を維持し、後で1操作40件と新11件の全文を比較する。既定v5/runtimeやLoRAを置換しない。

ソースは研究runのbyte保存。ローカルのモデル/adapter/依存ライブラリ/元DB/validation snapshotは含めない。実行にはprotocolのローカル研究レイアウトと非公開資材が必要。prepared_inputsの数値tokenは公開省略し、入力到達のCPU証拠と固定samples/選択は保存する。元の全資材は研究runに保全。

変更前の判断はhistory_decision.md、過去の実測は../../evidence/utterance_unit_history_20261031/result.md。現在地は../../progress/CURRENT_STATE.md。今回のスキル方針は../../research_skills/talk-evidence-first/SKILL.md。

## 完了結果
新11call全EOS/終了0・技術監査pass。まとまりの改善例がある一方、内容の欠落や意味変化が残り品質未採用。[公開結果要約](../../evidence/memory_db_group4_20261101/result_summary.md)。全文比較はローカル成果物。実行ソースは起動時から不変。
