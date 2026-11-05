> 2026-10-28追記：役割制御・A〜G・32操作Surface・CPU選択10素材の研究候補を追加。下記は以前の保存状態。最新の到達点と未解決事項は[現在地](progress/CURRENT_STATE.md)、研究経路は[CPU操作選択](STRIPE_CONTROL.md)を参照。既定Runtimeは変更していない。

# 実験結果と未解決事項（2026-10-26保存版）

|検証|観測|判断|
|---|---|---|
|新教材Base/Instruct|79組=61学習/8validation/10test、両新LoRA各8更新|現行Surfaceは新Instruct。旧751の継続ではない|
|Gold焦点到達|2素材×2焦点、実Surface4/4が分岐|Runtimeは別焦点を実行可能。Planner判断力の証拠ではない|
|Planner少数対照|recentのみ変えた6条件、構文6/6、適用0/6|入力の読み取りとFlow対応の両方に課題|
|旧10分相当run|8発話429字、Planner R0017未終端JSON、exit1|失敗を保全。旧タグに対応|
|固定順継続修正|元17call全入力一致再利用。CPU154チェックは当時pass|不正Planを保存・破棄し次へ。追加学習なし|
|継続run完了|51発話2503字、102論理call=17再利用+85新規、不正Plan5、全終了0|約10.01分相当。そういえば13/んだよね47、意味改変例が残る|
|人間原文比較|原文1961字/Memory416字/AI730字・5発話、全終了0|概要へ圧縮。全弾成功の追加/バッグを見る人→持つ人の改変|
|人間比較Planner|構文5/5、内容崩壊1、use_memory true1だが未対応sidecar|適用採用0・順序変更0。再計画の優位性は未実証|

[10分相当の全文・評価](evidence/continuous10_20261024/comparison.html) ／ [人間/Memory/AI全文比較](evidence/human_memory_compare_20261024/comparison.html) ／ [現在地](progress/CURRENT_STATE.md)

## 重要な区別

- 継続runの正常終了は、旧失敗runが正常だったという意味ではない。再利用17callと新規85callを分ける。
- 2503字は250字/分仮定の換算。実測run約2時間11分15秒、モデル内生成時間5286.599秒、実TTSなし。
- 人間比較runは約19分14秒、モデル内生成時間808.569秒。人間の原音声/タイムスタンプ未確認で、同時間の対決ではない。
- Memoryですでに抜けた数量・所有者・主観の区別と、Surfaceが新たに変えた意味を分ける。
- 提示済み/履歴採用/CPU整合passは意味品質合格ではない。構文が正しくてもtopic/flowが壊れる例がある。

1seed/限定素材/設計者AI既知条件・人間品質ラベル0。現行Surface61教材とPlanner学習にLuna話者はないが、元corpusの旧trainラベルと派生testを区別し、過去評価利用・基盤事前学習不明を開示。人間らしい語りと有効な次焦点判断は課題のまま。公開配信へ品質採用していない。

## Surface v2/v3の少数対照（追加記録）

- 現行版→v2：保存3素材4地点で559→1067字。反応は増えたが全部成功・心理・位置・架空既出などの追加が残り採用保留（当時のrootレビューを継承）。
- v2→v3：同じFact/元履歴/LoRA/seed/384条件、新規Surface4件。全EOS、上限0。1067→984字。
- H06後半は景品の多さ→9000円→購入比較→悔しさが少し直接的に。H04の架空前話、H06の事前期待、H07の気まずさ/隣は削減。
- H04/H07の全部成功、H07の架空既出、天井の確実性の変化は残る。評価の段階の一貫した増加は未実証。v3は採用保留。
- 既知素材とv2結果から設計した3点の一括追加。設計者AI既知条件評価・人間0、H06は固定元履歴で独立。技術passを意味品質合格にしない。

[全文v2/v3・実入力RAW](evidence/surface_prompt_v3_vs_v2_20261026/comparison.html) ／ [根拠と限界](evidence/surface_prompt_v3_vs_v2_20261026/result.md)

## H06の見る角度・段階①（追加記録）

同一H06後半のFact/元履歴/LoRA/seed/384条件。現行保存99字に対して、景品の食い違い92字、普通の購入との比較110字。新規Surface2、Planner/Guard/学習/品質再生成/TTS0、全EOS・全終了0。角度と根拠の実入力到達は確認したが、全条件の展開順はほぼ同じで評価の厚み改善は未実証。新規2本に未支持の「目の前」があり採用保留。

元Factが両角度を含み全内容を話す制約であるため、同じ材料の語り直しになった可能性はあるが原因未確定。設計者指定の既知1地点/1seed、固定元履歴、閉ループなし、人間品質ラベル0。rootの完了時全文レビューを保存し、今回はその記録と実コードを照合して公開する。過去全出力の新しい採点は行わない。

ユーザーと、発話の役割・語った角度・終了をコード側で管理する方向を検討。追加プロンプトを重ねる方針はいったん止める。長さ自体が悪化原因かは未検証。[制御案](progress/NEXT_CONTROL_PLAN.md)は未実装で、新しい生成は行っていない。

[現行/G01/G02全文](evidence/surface_viewpoint_h06_20261026/comparison.html) ／ [結果](evidence/surface_viewpoint_h06_20261026/result.md)


## 2026-11-02 — Full v2 condition reproduction

Original four-call order, full v2 instructions, facts, saved histories, LoRA and complete generation settings are preserved. CPU 54+42, dependencies 8, synthetic report 5, startup exit 0. Source prepared; new generation not yet launched or evaluated. See experiments/surface_v2_replay_20261102. Full experimental content remains local.


### Full v2 reproduction: launched

Source056a638 pushed/remote exact, then one hidden bounded4 launch. Initial metadata check: CPU initialization, calls0, controller/wrapper identity match, GPU not yet recorded. Own 15-minute brief CPU heartbeat active; no resident waiting, new outputs unread. Progress source/audit passed. Completion/full-text quality review and abstract result publication remain pending.


## 2026-11-03 — Original v2 output reproduced exactly

Four new Surface generations exactly matched all saved v2 output tokens, RAW and bodies under identical full requests and generation settings. Current exits all0, technical/full-text review and local eight-body/input report checks passed. Conversational style and existing semantic problems both reproduced; quality not adopted. Current DB material adaptation remains untested. Abstract results only are published; own brief-check heartbeat deletion follows the result push.


### Reproduction record closed

Abstract result0457dfb pushed/remote exact, local full report and progress audit passed, only ownv2-4-15 heartbeat deleted. No additional generation, current-DB adaptation or default adoption.


## 2026-11-03 — Full v2 transferred to unchanged DB3 materials

Baseline selected by user: saved listener-enhanced group4. Keep all data, CPU40/deferred1, grouping11, LoRA, seed and config1536. Change full original v2 instructions and plain five-section Fact/Flow presentation, preserving source qualifiers. CPU305/dep8/report5/real startup0 passed, source DB2 hashes unchanged. Maximum11 new Surface pending one hidden launch; outputs and quality unread. Generic source/abstract records only.


### DB3 full-v2 transfer: launched

Sourcef9a1766 pushed/remote exact, one bounded hidden11 launch, initial completed0/triple process identity matched/DB2 unchanged. Progress source/audit passed. Own fifteen-minute brief CPU heartbeat active, no resident waiting; new outputs unread and quality pending.


## 2026-11-03 — DB3 full-v2 transfer completed

New11 EOS/all exits0/sourceDB2 unchanged, root full review/manual105 actual-text units/localHTML22 exact. Listener-directed language returned, but output1451->3788 nonspace characters with longer explanation/repetition and unsupported specifics; not adopted. Full reports local, abstract conclusions/counts only published. Own monitor deletion follows result push.


### DB3 full-v2 transfer records closed

Abstract result5dc5406 pushed/remote exact, local full22-body/input report and progress audit passed; only owndb3-v2-15 heartbeat deleted. Listener-address improvement remains distinct from semantic approval. No additional generation or default adoption.


## 2026-11-03 — Memory structure candidate prepared

Root manually reviewed five known edited reference topics / 145 existing fragments and authored three independent fictional candidates / 36 fragments. A reusable recipe preserves personal stakes, concrete cues and changing appraisals without mandatory lessons. CPU118 technical checks passed; original DBs preserved. No operation selection, Surface generation or import was run, so speech-quality improvement is untested. Generic recipe/checker and abstract results only: experiments/v_memory_structure_20261103. Full material remains local.


## 2026-11-03 — Authored-memory Surface experiment prepared

Three fixed authored candidates / 36 fragments are mechanically projected with the existing rhythm selector: 40 operations, zero deferred, maximum12 full-v2 Surface calls in groups up to4. Same LoRA/revision/seed/full config1536 and actual adopted last2/800 history rules. CPU301/dependencies8/three synthetic report variants/real startup-import exit0 passed. New generation is not yet launched or assessed. Only generic source and abstract records are published; actual materials remain local. See experiments/v_memory_surface3_20261103.


## 2026-11-05 — Authored-memory Surface experiment completed

New12 EOS/all current exits0/technical pass. Root read all3 specifications/36 fragments/full CPU traces/all12 actual inputs, RAW, bodies and histories. Cited12/3 review and93 manually classified prose spans reconstruct every body; independent local report-presence check passed. Listener address and reactions appeared, but unsupported additions/mental-certainty strengthening and long repetition remain. Not adopted. Totals2998 nonspace characters/1836 output tokens/2006.343 model seconds. One seed/known manual3/designer AI known conditions/human0/TTS0/no matched old baseline. Only generic helpers, abstract result and numbers published; full content local. Own heartbeat deletion follows verified result push. See experiments/v_memory_surface3_20261103/result.md.
