// Offline structure/behavior checks; no browser rendering is claimed.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {boot}=require('./dom_harness.cjs');
const original=fs.readFileSync(process.argv[2],'utf8'),updated=fs.readFileSync(process.argv[3],'utf8');
const beforeScript=original.slice(original.indexOf('<script>')+8,original.indexOf('</script>'));
const baseline=vm.runInNewContext(beforeScript.slice(0,beforeScript.indexOf('function orderRoute()'))+';({source:ORIGINAL_SOURCE,rows:SOURCE_ROWS,cores,attrs})',{document:{getElementById:()=>({})}},{timeout:1000});
const app=boot(updated),{doc,evaluate,window}=app,checks=[];
function check(name,fn){fn();checks.push(name);}
function click(id){const node=doc.getElementById(id);assert(node);assert(!node.disabled);node.fire('click');}
function goLine(n){const row=doc.getElementById('line-'+(n-1));assert(row);row.fire('click');}
const pending=baseline.rows.filter(r=>r.kind==='speech'&&(!r.cores.length||!r.attrs.length));
check('source and every curated mapping remain exact',()=>{
 assert.equal(window.__fullTrace.getRawSource(),baseline.source);
 for(const name of ['SOURCE_ROWS','cores','attrs'])assert.equal(evaluate('JSON.stringify('+name+')'),JSON.stringify(name==='SOURCE_ROWS'?baseline.rows:baseline[name]));
 assert.equal(JSON.stringify(doc.body.querySelectorAll('.speechText').map(n=>n.textContent)),JSON.stringify(baseline.rows.filter(r=>r.kind==='speech').map(r=>r.raw)));
});
check('all unresolved lines are permanent circle nodes in the existing graph node group',()=>{
 const nodes=doc.getElementById('nodes').querySelectorAll('.node');
 assert.equal(nodes.length,475);assert.equal(doc.getElementById('map').querySelectorAll('rect').length,1);
 const unknown=nodes.filter(n=>n.classList.contains('node-attr')&&n.classList.contains('node-unresolved'));
 assert.equal(unknown.length,pending.length);assert.equal(new Set(unknown.map(n=>n.dataset.id)).size,pending.length);
 for(const row of pending){const node=unknown.find(n=>n.dataset.id==='unresolved_L'+row.lineNo);assert(node);assert(node.querySelector('.node-circle'));}
});
check('no card, separate list, paging or added HTML controls',()=>{
 const markup=original.slice(original.indexOf('<body>')+6,original.indexOf('<script>'));
 const ids=[...markup.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]).sort();
 const liveIds=doc.body.querySelectorAll('[id]').map(n=>n.id).filter(id=>!id.startsWith('line-')&&!['grid','edges','nodes'].includes(id)).sort();
 assert.equal(JSON.stringify(liveIds),JSON.stringify(ids));
 assert.equal(doc.getElementById('pendingLayer'),null);assert.equal(doc.getElementById('pendingBtn'),null);
});
check('unresolved clicks use the original node navigation and transcript selection',()=>{
 const examples=[pending[0],pending.find(r=>r.cores.length),pending.at(-1)];
 for(const row of examples){const node=doc.getElementById('nodes').querySelectorAll('.node').find(n=>n.dataset.id==='unresolved_L'+row.lineNo);node.fire('click');
  assert.equal(evaluate('index'),row.lineNo-1);assert(doc.getElementById('line-'+(row.lineNo-1)).classList.contains('current'));assert(node.classList.contains('current'));
  const count=doc.getElementById('nodes').querySelectorAll('.node-attr').filter(n=>n.classList.contains('node-unresolved')).length;assert.equal(count,432);
 }
});
check('transcript rows select the same circle nodes without paging',()=>{
 for(const row of [pending[2],pending[Math.floor(pending.length/2)],pending.at(-2)]){
  goLine(row.lineNo);const node=doc.getElementById('nodes').querySelectorAll('.node').find(n=>n.dataset.id==='unresolved_L'+row.lineNo);assert(node?.classList.contains('current'));
 }
});
check('curated node highlighting remains intact',()=>{
 const row=baseline.rows.find(r=>r.kind==='speech'&&r.attrs.length);goLine(row.lineNo);
 const active=doc.getElementById('nodes').querySelectorAll('.node').filter(n=>n.classList.contains('current')).map(n=>n.dataset.id);
 assert(row.attrs.every(id=>active.includes(id)));assert(active.every(id=>!id.startsWith('unresolved_L')));
});
check('all added links terminate at graph nodes and preserve source affiliation',()=>{
 const graph=JSON.parse(evaluate('JSON.stringify({cores:inlineGraph.cores,attrs:inlineGraph.attrs,mappings:inlineGraph.rowMappings})'));
 for(const row of pending){const id='unresolved_L'+row.lineNo,attr=graph.attrs[id];assert(attr);assert(attr.bridge.length);
  assert(attr.bridge.every(core=>graph.cores[core]));assert.equal(attr.note,row.raw);assert.equal(attr.lineNo,row.lineNo);
  if(row.cores.length)assert.equal(JSON.stringify(attr.bridge),JSON.stringify(row.cores));
 }
 const edges=doc.getElementById('edges').querySelectorAll('.edge-unresolved');assert.equal(edges.length,pending.reduce((n,r)=>n+(r.cores.length||1),0));
});
check('graph nodes have nonoverlapping circles and positive finite canvas positions',()=>{
 const nodes=JSON.parse(evaluate('JSON.stringify([...Object.values(inlineGraph.cores),...Object.values(inlineGraph.attrs)])'));
 for(const n of nodes)assert(Number.isFinite(n.x)&&Number.isFinite(n.y)&&n.x>0&&n.y>0);
 for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++)assert(Math.hypot(nodes[i].x-nodes[j].x,nodes[i].y-nodes[j].y)>56,'circle collision');
 click('fitBtn');assert(evaluate('target.w===inlineGraph.bounds.w&&target.h===inlineGraph.bounds.h'));
 click('trackBtn');assert(evaluate('Number.isFinite(target.x)&&target.x>=0&&target.y>=0'));
});
check('source exact search and keyboard node selection work',()=>{
 const row=pending[0];doc.getElementById('searchInput').value=row.raw;click('searchBtn');assert.equal(evaluate('SOURCE_ROWS[index].raw'),row.raw);
 const node=doc.getElementById('nodes').querySelectorAll('.node').find(n=>n.dataset.id==='unresolved_L'+pending.at(-1).lineNo);node.fire('keydown',{key:'Enter'});assert.equal(evaluate('index'),pending.at(-1).lineNo-1);
});
check('demo mode retains only the original 32 nodes and original routes',()=>{
 click('demoBtn');assert.equal(doc.getElementById('nodes').querySelectorAll('.node').length,32);assert.equal(doc.body.querySelectorAll('.node-unresolved').length,0);
 assert.equal(evaluate('items.length'),19);click('oldBtn');click('routeDetour');assert.equal(evaluate('items.length'),23);
 click('sourceBtn');assert.equal(doc.getElementById('nodes').querySelectorAll('.node').length,475);
});
const report={status:'pass',scope:'Offline DOM/logic and graph geometry only; no actual browser visual QA.',checks,
 unresolved_circle_nodes:432,new_heading_topic_nodes:11,total_source_graph_nodes:475,existing_graph_node_group:true,
 cards:0,added_html_controls:0,paging:false,source_sha256:crypto.createHash('sha256').update(window.__fullTrace.getRawSource()).digest('hex'),
 output_sha256:crypto.createHash('sha256').update(updated).digest('hex'),new_model_calls:0};
if(process.argv[4])fs.writeFileSync(process.argv[4],JSON.stringify(report,null,2)+'\n','utf8');
console.log(JSON.stringify(report,null,2));
