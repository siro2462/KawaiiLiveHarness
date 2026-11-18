# Preserve the original memory graph appearance

The supplied memory graph now uses its original stylesheet, static markup, curated node positions, and initial viewport. It adds the 432 unresolved speech lines on the same SVG, to the right of the original nodes. The existing fit control includes the added region. Dashed edges show affiliation with source headings or existing topics.

The offline DOM check compared the original and revised markup, all 32 curated nodes and their edges, and the starting and curated selection viewports. It also checked all 432 added line nodes, selection, fit, and demo switching. Browser rendering was not checked. The supplied transcript and the revised HTML are stored locally.

Build and check with local inputs:

`node build_inline.cjs original.html updated.html`

`node test_inline.cjs original.html updated.html`
