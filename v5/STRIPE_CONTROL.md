# CPU操作選択とSurfaceの研究経路

研究候補を既定Runtimeと分けて保存する。固定Surface LoRAは新Instruct61例8更新。Plannerやalphaを外した限定実験であり、既定の長尺運転を置き換えた証拠ではない。

```mermaid
flowchart LR
 M[固定Memory断片・事実/評価/確実性] --> G[共通CPU文字規則で関係と重要度を作る]
 G --> E[H06と同一Engineで操作・順番・終了を選ぶ]
 E --> P[操作列をそのままSurface入力へ]
 P --> S[固定Instruct Surface LoRA]
 S --> L[本文・RAW・実入力・状態を保存]
```

新10素材は一括・独立空履歴であり、発話を受けて操作を選び直す閉ループではない。Memory内の評価や感情も元はrootの手作業。文字リンクは意味関係の検証ではなく、requiresは空。入力完全一致は発話の意味や実行順を保証しない。

|保存候補|実験ソース|全文比較|
|---|---|---|
|役割/角度/終了|[role_runtime.py](experiments/surface_role_control_h06_20261027/role_runtime.py)|[2新発話](evidence/surface_role_control_h06_20261027/comparison.html)|
|A〜G機械制御|[ag_runtime.py](experiments/mechanical_ag_h06_20261027/ag_runtime.py)|[7条件](evidence/mechanical_ag_h06_20261027/comparison.html)|
|H06・CPU32操作A/B/C|[stripe_runtime.py](experiments/stripe_surface_abc_h06_20261027/stripe_runtime.py)|[4列比較](evidence/stripe_surface_abc_h06_20261027/comparison.html)|
|手作業32操作10素材|[stripe_runtime.py](experiments/stripe_surface_ten_20261027/stripe_runtime.py)|[全10素材](evidence/stripe_surface_ten_20261027/comparison.html)|
|CPU選択10素材＋直接反応|[cpu_selector.py](experiments/cpu_select_surface_ten_20261027/cpu_selector.py)|[前回／今回20本文](evidence/cpu_select_surface_ten_20261027/comparison.html)|

H06 A/B/Cは全条件の上限を旧384から1536へ統一変更し、AとB/Cには情報量の差がある。Cは固定32列を4操作ずつ切り出す逐次実現で、次の操作の適応的選び直しではない。新10素材も1536上限、seed20260925で固定。反応few-shotには3例を追加しており、CPU選択の単独効果ではない。

元H06のCPUコードとMemory graphはreferenceにbyte保持。新10素材の補助graphは共通文字規則から派生し、旧操作列や原文行順を選択に渡していない。詳細な全候補scoreと未選択断片、実prompt/decoded/RAWは各review_packetとHTMLにある。

過去の完了監査と全文レビューを継承。人間品質ラベル0、実TTSなし、追加学習や品質リトライなし。今回の保存チェックはモデルを呼ばず、実験の再生成や新しい意味評価をしていない。
