// Apply exact edits to the original graph, not the superseded card/page variant.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const input=process.argv[2],output=process.argv[3];
if(!input||!output)throw Error('Pass original.html and a new output.html path.');
if(path.resolve(input)===path.resolve(output)||fs.existsSync(output))throw Error('Use a new output path.');
let text=fs.readFileSync(input,'utf8');const edits=[];
function replace(oldText,newText,label){
 if(text.split(oldText).length!==2)throw Error('Expected one exact match: '+label);
 text=text.replace(oldText,newText);edits.push(label);
}
replace('</style></head>',fs.readFileSync(path.join(__dirname,'inline_graph.css'),'utf8')+'\n</style></head>','shared node styles');
replace('function orderRoute(){',fs.readFileSync(path.join(__dirname,'inline_graph.js'),'utf8')+'\nfunction orderRoute(){','source visual projection');
replace('function buildMap(){','function buildMap(){\n const cores=graphCores(),attrs=graphAttrs();','same renderer, combined graph');
replace("width:1600,height:980,fill:'url(#grid)'","width:sceneBounds().w,height:sceneBounds().h,fill:'url(#grid)'",'graph background bounds');
replace("class:'edge',opacity:'.55'","class:'edge'+(a.unresolved?' edge-unresolved':''),opacity:'.55'",'unresolved edges');
replace("r=core?28:22,clr=core?obj.color:cores[obj.bridge[0]].color;","r=core?28:22,clr=obj.unresolved?'#8190a8':core?obj.color:cores[obj.bridge[0]].color;",'unresolved node color');
replace("class:'node '+(core?'node-core':'node-attr')","class:'node '+(core?'node-core':'node-attr')+(obj.unresolved?' node-unresolved':'')",'same circle nodes');
replace("const t=create('text',{x:obj.x,y:obj.y+r+22,class:'node-title'});t.textContent=obj.label;g.appendChild(t);", "const t=create('text',{x:obj.x,y:obj.y+r+22,class:'node-title'});if(obj.lineNo){const num=create('tspan',{x:obj.x,class:'source-line-id'});num.textContent='L'+obj.lineNo;t.appendChild(num);const label=create('tspan',{x:obj.x,dy:16});label.textContent=obj.label;t.appendChild(label);}else t.textContent=obj.label;g.appendChild(t);",'source line node labels');
replace("'aria-label':obj.label","'aria-label':obj.lineNo?'原文 L'+obj.lineNo+' '+obj.label:obj.label",'source node accessibility');
for(const event of ['pointerenter','pointermove'])replace(
 "g.addEventListener('"+event+"',e=>tipShow(`${core?'コア話題':'属性'}：${obj.label}`,e));",
 "g.addEventListener('"+event+"',e=>tipShow(`${obj.unresolved?(core?'未整理の話題（元見出し）':'未整理の発話 L'+obj.lineNo):core?'コア話題':'属性'}：${obj.note||obj.label}`,e));",
 'node tooltip '+event);
replace('function jumpToNode(id,core){','function jumpToNode(id,core){\n const cores=graphCores(),attrs=graphAttrs();','node navigation lookup');
replace("(core?r.cores.includes(id):r.attrs.includes(id))","(core?sourceMapping(r).cores.includes(id):sourceMapping(r).attrs.includes(id))",'source node to transcript');
replace("const accent=cores[r.cores[0]]?.color||'#8190a8';","const accent=graphCores()[sourceMapping(r).cores[0]]?.color||'#8190a8';",'source accent lookup');
replace("topic.textContent=r.cores.map(c=>NAMES[c]).join(' / ')||(r.section||'マップ未登録の話題');", "topic.textContent=sourceMapping(r).cores.map(c=>graphCores()[c].label).join(' / ')+(!r.cores.length?'（話題未整理）':!r.attrs.length?'（属性未整理）':'');",'existing metadata text only');
replace("return {cores:new Set(r.cores),attrs:new Set(r.attrs)};","return {cores:new Set(sourceMapping(r).cores),attrs:new Set(sourceMapping(r).attrs)};",'transcript to same graph nodes');
replace('function paint(){','function paint(){\n const cores=graphCores(),attrs=graphAttrs();','graph selection lookup');
replace("if(isSource){r.cores.forEach(v=>visitedCores.add(v));r.attrs.forEach(v=>visitedAttrs.add(v));}","if(isSource){const mapped=sourceMapping(r);mapped.cores.forEach(v=>visitedCores.add(v));mapped.attrs.forEach(v=>visitedAttrs.add(v));}",'visited visual nodes');
replace("r.cores.map(c=>NAMES[c]).join(' / ')||'マップ未対応の区間'","sourceMapping(r).cores.map(c=>cores[c].label).join(' / ')||'原文'",'source graph title');
replace("$('graphPath').textContent=r.attrs.length?r.attrs.map(a=>attrs[a].label).join(' ・ '):`${r.section||'原文'}｜${r.kind==='speech'?'属性未対応':'編集上の見出し・空行'}`;", "$('graphPath').textContent=r.attrs.length?r.attrs.map(a=>attrs[a].label).join(' ・ '):`${r.section||'原文'}｜${r.kind==='speech'?'未整理の発話 L'+r.lineNo:'編集上の見出し・空行'}`;",'unresolved source caption');
replace("for(const n of list.querySelectorAll('.current'))n.classList.remove('current');", "for(const n of list.querySelectorAll('.current')){n.classList.remove('current');n.removeAttribute('aria-current');}",'current row accessibility');
replace("function position(){\n if(showAll){target={x:0,y:0,w:1600,h:980};return;}", "function position(){\n const cores=graphCores(),attrs=graphAttrs(),bounds=sceneBounds();\n if(showAll){target={x:0,y:0,w:bounds.w,h:bounds.h};return;}",'fit combined graph');
replace("if(!obj){target={x:0,y:0,w:1600,h:980};return;}", "if(!obj){target={x:0,y:0,w:bounds.w,h:bounds.h};return;}",'empty selection bounds');
replace("target={x:clamp(obj.x-630,0,470),y:clamp(obj.y-350,0,220),w:1130,h:760};", "target=displayMode==='source'?{x:clamp(obj.x-565,0,Math.max(0,bounds.w-1130)),y:clamp(obj.y-330,0,Math.max(0,bounds.h-760)),w:1130,h:760}:{x:clamp(obj.x-630,0,470),y:clamp(obj.y-350,0,220),w:1130,h:760};",'follow all graph nodes');
replace('function viewFrame(){','function viewFrame(){\n svg.classList.toggle(\'overview\',displayMode===\'source\'&&view.w>2700);','zoom-dependent labels');
replace("items=orderRoute();sidebar();$('speechList').scrollTop=0;setIndex(0,{scroll:false});", "items=orderRoute();sidebar();buildMap();$('speechList').scrollTop=0;setIndex(0,{scroll:false});",'preserve original demo graph');
replace("${SOURCE_ROWS.length}行 / ${new TextEncoder().encode(ORIGINAL_SOURCE).length.toLocaleString('ja-JP')}バイト（UTF-8）", "${SOURCE_ROWS.length}行 / 未整理の発話 ${inlineGraph.unresolved}行（点線ノード）",'coverage in existing label');
replace('グラフの関連づけは部分的・人手ルールであり、未対応区間を無理に接続していません。','未整理の発話も同じグラフの点線ノードで表示。点線は原文・元見出しへの所属を表し、意味分類が確定したことにはしません。','source affiliation explanation');
replace('原文をそのまま表示。グラフに対応する箇所だけ接続を強調します。','原文をそのまま表示。未整理の話題・発話も同じグラフ内の点線ノードで追跡します。','existing graph hint');
replace("target.x=clamp(pointerDown.vx-dx,0,1600-target.w);target.y=clamp(pointerDown.vy-dy,0,980-target.h);", "target.x=clamp(pointerDown.vx-dx,0,Math.max(0,sceneBounds().w-target.w));target.y=clamp(pointerDown.vy-dy,0,Math.max(0,sceneBounds().h-target.h));",'pan full graph');
replace("newW=clamp(oldW*(e.deltaY<0?.9:1.1),600,1600)","newW=clamp(oldW*(e.deltaY<0?.9:1.1),600,sceneBounds().w)",'zoom full graph');
replace("target.x=clamp(target.x+(oldW-newW)/2,0,1600-newW);target.y=clamp(target.y+(target.h-target.h*ratio)/2,0,980-target.h*ratio);", "target.x=clamp(target.x+(oldW-newW)/2,0,Math.max(0,sceneBounds().w-newW));target.y=clamp(target.y+(target.h-target.h*ratio)/2,0,Math.max(0,sceneBounds().h-target.h*ratio));",'zoom origin bounds');
replace(" getRawSource:()=>ORIGINAL_SOURCE,", " getGraphSummary:()=>({unresolved:inlineGraph.unresolved,topicMissing:inlineGraph.topicMissing,attributeOnly:inlineGraph.attributeOnly,newTopics:inlineGraph.newTopics,nodes:Object.keys(graphCores()).length+Object.keys(graphAttrs()).length}),\n getRawSource:()=>ORIGINAL_SOURCE,",'read-only graph coverage');
fs.writeFileSync(output,text,'utf8');
console.log(JSON.stringify({status:'written',edits:edits.length,output,sha256:crypto.createHash('sha256').update(text).digest('hex')}));
