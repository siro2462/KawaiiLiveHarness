# 保存済みSurface候補の実験

- [v2](surface_prompt_v2_20261025/)：元の現行版に対する長い語りの候補。実行runはsurface_prompt_v2_ab_20261025_v2。
- [v3対v2](surface_prompt_v3_vs_v2_20261026/)：中心・評価の進展・事実を盛らない3点を追加した候補。実行runはsurface_prompt_v3_vs_v2_20261026_v1。
- [H06見る角度・段階①](surface_viewpoint_h06_20261026/)：元rendererへ指定角度と根拠引用を追記する独立2生成。実行runはsurface_viewpoint_h06_20261026_v1。既定Runtimeには未採用。

プロンプト版とrun版は別。両候補とも研究保存で、既定Runtimeの採用版ではない。各4地点は元の現行版履歴へ固定し、生成した候補同士を連続させていない。モデル・生成条件は固定。実行に必要なモデル/外部凍結資産は同梱しない。

H06角度比較はoriginal contract_runtimeを基準に、同一H06-3と元履歴で新規2本を生成。v2/v3の続きではない。AngleAttemptsは重複試行と上限を管理するが、意味理解や角度の表現成功を認定しない。発話を受けた次角度選択・記憶想起は未実装。
