# Place unresolved speech near its topic

The 432 unresolved speech lines now sit around their associated topics in the same graph. The 101 lines with an existing mapping use that curated node as their anchor. Lines without a curated mapping use their original section heading. The original stylesheet, static HTML, curated node and edge coordinates, and initial viewport match the supplied original.

The offline checks cover all 432 lines, four-quadrant placement around the curated anchor, original node and edge geometry, and fit, zoom, and transcript navigation across the enlarged canvas. Browser rendering was not checked. Full transcript and HTML remain local.

Build and check with local inputs:

`node build_inline.cjs original.html updated.html`

`node test_inline.cjs original.html updated.html`
