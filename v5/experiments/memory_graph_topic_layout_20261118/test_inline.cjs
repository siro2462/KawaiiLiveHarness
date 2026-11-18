const fs = require('node:fs');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const {boot} = require('./dom_harness.cjs');

const original = fs.readFileSync(process.argv[2], 'utf8');
const revised = fs.readFileSync(process.argv[3], 'utf8');
const originalApp = boot(original);
const app = boot(revised);
const {doc, evaluate} = app;
const baseline = JSON.parse(originalApp.evaluate('JSON.stringify({cores,attrs,rows:SOURCE_ROWS})'));
const pending = baseline.rows.filter(r => r.kind === 'speech' && (!r.cores.length || !r.attrs.length));
const findNode = (dom, id) => dom.getElementById('nodes').querySelectorAll('.node').find(n => n.dataset.id === id);
const click = id => doc.getElementById(id).fire('click');

// The entire static HTML, including the stylesheet and the original SVG viewBox, is exact.
assert.equal(revised.slice(0, revised.indexOf('<script>')), original.slice(0, original.indexOf('<script>')));
assert.equal(revised.slice(revised.indexOf('</script>')), original.slice(original.indexOf('</script>')));
assert.equal(app.window.__fullTrace.getRawSource(), originalApp.window.__fullTrace.getRawSource());
assert.equal(evaluate('JSON.stringify(SOURCE_ROWS)'), JSON.stringify(baseline.rows));

for (const collection of ['cores', 'attrs']) {
 for (const [id, data] of Object.entries(baseline[collection])) {
  assert.equal(evaluate('JSON.stringify(inlineGraph.' + collection + '[' + JSON.stringify(id) + '])'), JSON.stringify(data));
  const a = findNode(originalApp.doc, id), b = findNode(doc, id);
  assert.deepEqual(b.attributes, a.attributes);
  assert.deepEqual(b.children.map(el => [el.attributes, el.textContent]), a.children.map(el => [el.attributes, el.textContent]));
 }
}
const oldEdges = originalApp.doc.getElementById('edges').querySelectorAll('.edge');
const newEdges = doc.getElementById('edges').querySelectorAll('.edge');
assert.deepEqual(newEdges.filter(e => e.getAttribute('stroke-dasharray') === null).map(e => e.attributes), oldEdges.map(e => e.attributes));
assert.equal(evaluate('JSON.stringify(target)'), originalApp.evaluate('JSON.stringify(target)'));
assert.equal(doc.getElementById('sourceAffiliationEdges').querySelectorAll('.edge').length, pending.reduce((n,r)=>n+(r.cores.length||1),0));
const graph = JSON.parse(evaluate('JSON.stringify(inlineGraph)'));

assert.equal(doc.getElementById('nodes').querySelectorAll('.node').length, 475);
const occupied = [];
for (const r of pending) {
 const id = 'unresolved_L'+r.lineNo;
 const node = findNode(doc, id);
 assert(node?.querySelector('.node-circle'));
 const circle = node.querySelector('.node-circle');
 const x = Number(circle.getAttribute('cx')), y = Number(circle.getAttribute('cy'));
 const parent = graph.cores[graph.attrs[id].bridge[0]];
 const distance = Math.hypot(x - parent.x, y - parent.y);
 assert(Number.isFinite(distance));
 assert(distance <= (r.cores.length ? 780 : 1020));
 assert(!occupied.some(([xx, yy]) => Math.hypot(x-xx, y-yy) < 44));
 occupied.push([x, y]);
 assert.equal(evaluate('inlineGraph.attrs.'+id+'.note'), r.raw);
 const links = newEdges.filter(e => e.dataset.attr === id);
 assert.deepEqual(links.map(e => e.dataset.core), r.cores.length ? r.cores : Array.from(evaluate('inlineGraph.attrs.'+id+'.bridge')));
 assert(links.every(e => e.getAttribute('stroke-dasharray') === '5 6'));
}
click('fitBtn');
assert(evaluate('target.x===inlineGraph.bounds.x && target.y===inlineGraph.bounds.y && target.w===inlineGraph.bounds.w && target.h===inlineGraph.bounds.h'));
const home = baseline.cores.kimetsu;
const attached = Object.values(graph.attrs).filter(n => n.unresolved && n.bridge[0] === 'kimetsu');
const quadrants = attached.filter(n=>n.x!==home.x&&n.y!==home.y).map(n => [Math.sign(n.x-home.x), Math.sign(n.y-home.y)].join(','));
assert.equal(new Set(quadrants).size, 4);
assert(Object.values(graph.cores).some(n => n.unresolved && n.x < 0));
const left = evaluate('target.x');
doc.getElementById('map').fire('wheel',{deltaY:-1,preventDefault(){}});
assert(evaluate('target.x') >= left && evaluate('target.x') < 0);

for (const r of [pending[0], pending.find(r => r.cores.length), pending.at(-1)]) {
 const node = findNode(doc, 'unresolved_L'+r.lineNo);
 node.fire('click');
 assert.equal(evaluate('index'), r.lineNo-1);
 assert(node.classList.contains('current'));
 assert(evaluate('!showAll && tracking && target.w===1130 && target.h===760'));
 const p = graph.attrs['unresolved_L'+r.lineNo];
 const viewport = JSON.parse(evaluate('JSON.stringify(target)'));
 assert(p.x >= viewport.x && p.x <= viewport.x+viewport.w && p.y >= viewport.y && p.y <= viewport.y+viewport.h);
}
const curated = baseline.rows.find(r => r.kind === 'speech' && r.attrs.length);
app.window.__fullTrace.jumpToLine(curated.lineNo);
originalApp.window.__fullTrace.jumpToLine(curated.lineNo);
assert.equal(evaluate('JSON.stringify(target)'), originalApp.evaluate('JSON.stringify(target)'));
click('demoBtn');
originalApp.doc.getElementById('demoBtn').fire('click');
assert.equal(doc.getElementById('nodes').querySelectorAll('.node').length, 32);
assert.equal(evaluate('JSON.stringify(target)'), originalApp.evaluate('JSON.stringify(target)'));
click('sourceBtn');
assert.equal(doc.getElementById('nodes').querySelectorAll('.node').length, 475);

const sha = s => crypto.createHash('sha256').update(s).digest('hex');
const report = {
 status: 'pass', original_css_and_static_markup_exact: true, original_nodes_and_edges_exact: true,
 original_initial_and_curated_viewports_exact: true, all_unresolved_line_nodes: pending.length,
 source_graph_nodes: 475, demo_graph_nodes: 32, full_view_and_node_navigation: 'pass',
 source_sha256: sha(app.window.__fullTrace.getRawSource()), output_sha256: sha(revised),
 known_topic_lines: attached.length,
 known_topic_max_distance: Math.ceil(Math.max(...attached.map(n => Math.hypot(n.x-home.x,n.y-home.y)))),
 verification: 'Offline DOM and SVG coordinates'
};
if (process.argv[4]) fs.writeFileSync(process.argv[4], JSON.stringify(report, null, 2)+'\n', 'utf8');
console.log(JSON.stringify(report, null, 2));
