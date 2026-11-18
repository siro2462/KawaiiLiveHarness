# Inline unresolved memory graph correction

The user rejected the previous separate card/list/page presentation. This variant starts from the original HTML and projects unresolved source material into the same circle-node/edge renderer and SVG node group as the curated graph. No added cards, lists, paging or HTML controls. [Result](result.md) / [counts](numeric_summary.json). Full source/HTML remain local.

```text
node build_inline.cjs original.html updated.html
node test_inline.cjs original.html updated.html audit.json
```

The exact-edit builder requires the original template and new output path; adjacent JS/CSS are embedded. The test harness is an offline DOM simulation, not an actual browser or visual/layout approval.
