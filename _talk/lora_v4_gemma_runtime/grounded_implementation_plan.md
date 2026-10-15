# v5 事実・Context・Fallback接続の実装方針

形式段階の保存結果を踏まえた次工程。Gemma Planner v1/Talk v4の最終LoRA、seed、生成設定、元Memoryと旧結果を固定する。前工程は17CPU検査・4Planner生成で形式4/4。事実性とTalk品質は未達。

## 改修

1. **CPU事実検査**: Janome 0.5.0の形態素から行為、対象、数量、時制/予定を抽出する。ひらがなを対象外にしない。疑問/仮定の作用域は行為の後ろで判定し、先行する疑問だけで後続実体験を免除しない。元Memoryの引用とhashを結果へ付ける。
2. **事実と方向付けの分離**: 元MemoryをPlan.use_memoryと独立に保存する。ただし今回の選択と保存を分け、検索候補なしを過去Memoryの自動採用としない。PlanとRecentは事実の根拠にしない。2026-10-15レビュー後は、現在選択した1件だけをPlan検査・Talk入力・Talk検査へ同じ本文/hashで渡す。過去Memoryは監査用に残しても暗黙の根拠にしない。LLMのRecentは3発話、Event Storeは全再生。
3. **Plan管理**: strict schemaと事実検査を通したpendingだけcommit。3turn期限をfallbackで延長しない。反復で破棄したPlanをlast_validから再生しない。期限と既存反復検知を管理し、次の話題の内容はPlannerが決める。
4. **Fallback**: Planner最大2attempt→期限内last_valid→元Memory付きPlanなしTalk。Talkも最大2attempt。未再生候補は全体破棄し、確定イベントへ書かない。
5. **明示的Recent範囲**: token budgetは928。本文の最初の一致検索でMemoryをRecentと誤認しないよう、Recent sectionの明示範囲から左端だけcutする。Memory/Planを落とさない。
6. **既存Runtime継承**: SQLite再生commit、hard failure、E5+文字反復検知、検索式/閾値.6、反復後の現在Memory除外と検索、retrieval用抜粋Compactを元コードから読む。CompactはPlanner/Talkに渡さない。

## 検査の限界

CPU検査は具体的経験の明確な改変を拒否する機構であり、全日本語の意味理解器ではない。感想、一般的連想、仮定、冗談を許容する。曖昧な省略や一般知識を一律拒否して台本化しない。意味が未確認の部分はログとrootの全文確認で扱い、「検出なし」を事実性合格としない。新LLM検証器・新会話進捗DBは追加しない。

## 比較と実行順

- 保存済みうなぎPlan/発話、数字・方角・時点・予定の誤りと、対応する許容例をCPU回帰検査。
- CPU fake modelでPlan採用、根拠、fallback、反復破棄、partial playback、Recent3とSQLiteを検査。
- 固定36出力は元の3場面(S1A/S2A/S3B)×3turn×4条件。条件はContext＋Plannerのみ、Gold＋検査、Planner＋検査、Planなし＋検査。新しいRuntime差分を評価し、旧Gemma36出力を全文で併記。旧v3等を同条件で再生成しない。
- 短い接続sanity後、固定36→検査付きRuntime2700字(4.5字/秒で10分相当)を1回実行。既知原因の修正を伴わない品質再実行はしない。
- 全実入力、全Plan、候補、拒否理由、確定再生、Memory参照/Plan期限/履歴cut、SQLiteと凍結hashを保存。rootが全件を読む。

固定36の少量差だけで連続発話の改善としない。短期目標を通すまでαを実会話へ統合しない。

形態素解析の公式資料: [Janome](https://janome.mocobeta.dev/ja/)。依存はmorphology_dependenciesに分離し、既存venvとJSON制約依存を変更しない。
