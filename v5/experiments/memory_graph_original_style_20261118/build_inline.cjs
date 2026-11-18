const fs = require('node:fs');
const path = require('node:path');

const [input, output] = process.argv.slice(2);
if (!input || !output) throw new Error('Pass the original HTML and a new output path.');
const original = fs.readFileSync(input, 'utf8');
const start = original.indexOf('<script>');
const end = original.indexOf('</script>', start);
if (start < 0 || end < 0) throw new Error('Expected the original graph script.');
let script = original.slice(start, end);
function replace(before, after) {
 if (script.split(before).length !== 2) throw new Error('Expected one matching edit: ' + before);
 script = script.replace(before, () => after);
}

replace('function orderRoute(){', fs.readFileSync(path.join(__dirname, 'inline_graph.js'), 'utf8') + '\nfunction orderRoute(){');
replace('function buildMap(){', 'function buildMap(){\n const cores=graphCores(),attrs=graphAttrs();');
replace("width:1600,height:980,fill:'url(#grid)'", "width:sceneBounds().w,height:sceneBounds().h,fill:'url(#grid)'");
replace("Object.entries(attrs).forEach(([aid,a])=>a.bridge.forEach(cid=>edges.appendChild(create('path',{d:pathBetween(cores[cid],a),stroke:cores[cid].color,'data-core':cid,'data-attr':aid,class:'edge',opacity:'.55'}))));svg.appendChild(edges);",
 `const additions=create('g',{id:'sourceAffiliationEdges',visibility:'hidden'});
 Object.entries(attrs).forEach(([aid,a])=>a.bridge.forEach(cid=>{
  const line=create('path',{d:pathBetween(cores[cid],a),stroke:a.unresolved?a.color:cores[cid].color,'data-core':cid,'data-attr':aid,class:'edge',opacity:'.55'});
  if(a.unresolved){line.setAttribute('stroke-dasharray','5 6');additions.appendChild(line);}
  else edges.appendChild(line);
 }));
 if(displayMode==='source')edges.appendChild(additions);
 svg.appendChild(edges);`);
replace('r=core?28:22,clr=core?obj.color:cores[obj.bridge[0]].color;', 'r=core?28:22,clr=core||obj.unresolved?obj.color:cores[obj.bridge[0]].color;');
replace("'aria-label':obj.label", "'aria-label':obj.lineNo?'原文 L'+obj.lineNo+' '+obj.label:obj.label");
for (const event of ['pointerenter', 'pointermove']) {
 const prefix = "g.addEventListener('" + event + "',e=>tipShow(";
 replace(prefix + "${core?'コア話題':'属性'}：${obj.label}".replace(/^/,'`') + "`,e));",
  prefix + "obj.unresolved?(core?'未整理の話題（元見出し）':'未整理の発話 L'+obj.lineNo)+'：'+(obj.note||obj.label):(core?'コア話題':'属性')+'：'+obj.label,e));");
}
replace('function jumpToNode(id,core){', 'function jumpToNode(id,core){\n const cores=graphCores(),attrs=graphAttrs();');
replace('(core?r.cores.includes(id):r.attrs.includes(id))', '(core?sourceMapping(r).cores.includes(id):sourceMapping(r).attrs.includes(id))');
replace("if(step>=0){stop();setIndex(step);return;}", "if(step>=0){stop();\n  if((core?cores[id]:attrs[id]).unresolved){showAll=false;tracking=true;$('fitBtn').textContent='全体表示';$('trackBtn').textContent='◎ 発話を追跡中';}\n  setIndex(step);return;\n }");
replace('return {cores:new Set(r.cores),attrs:new Set(r.attrs)};', 'const mapped=sourceMapping(r);return {cores:new Set(mapped.cores),attrs:new Set(mapped.attrs)};');
replace('function paint(){', 'function paint(){\n const cores=graphCores(),attrs=graphAttrs();');
replace('if(isSource){r.cores.forEach(v=>visitedCores.add(v));r.attrs.forEach(v=>visitedAttrs.add(v));}', 'if(isSource){const mapped=sourceMapping(r);mapped.cores.forEach(v=>visitedCores.add(v));mapped.attrs.forEach(v=>visitedAttrs.add(v));}');
replace("r.cores.map(c=>NAMES[c]).join(' / ')||'マップ未対応の区間'", "sourceMapping(r).cores.map(c=>cores[c].label).join(' / ')||'マップ未対応の区間'");
replace("r.kind==='speech'?'属性未対応':'編集上の見出し・空行'", "r.kind==='speech'?'未整理の発話 L'+r.lineNo:'編集上の見出し・空行'");
replace("function position(){\n if(showAll){target={x:0,y:0,w:1600,h:980};return;}", "function position(){\n const cores=graphCores(),attrs=graphAttrs(),bounds=sceneBounds();\n if(showAll){target={x:0,y:0,w:bounds.w,h:bounds.h};return;}");
replace("target={x:clamp(obj.x-630,0,470),y:clamp(obj.y-350,0,220),w:1130,h:760};",
 `if(obj.unresolved){
  target={x:clamp(obj.x-565,0,bounds.w-1130),y:clamp(obj.y-380,0,bounds.h-760),w:1130,h:760};
 }else{
  target={x:clamp(obj.x-630,0,470),y:clamp(obj.y-350,0,220),w:1130,h:760};
 }`);
replace(" svg.setAttribute('viewBox',", ` const affiliationEdges=$('sourceAffiliationEdges');
 if(affiliationEdges){
  const value=view.x+view.w>inlineGraph.addedAreaX?'visible':'hidden';
  if(affiliationEdges.getAttribute('visibility')!==value)affiliationEdges.setAttribute('visibility',value);
 }
 svg.setAttribute('viewBox',`);
replace("items=orderRoute();sidebar();$('speechList').scrollTop=0;setIndex(0,{scroll:false});",
 `items=orderRoute();sidebar();buildMap();$('speechList').scrollTop=0;
 tracking=true;showAll=false;$('fitBtn').textContent='全体表示';$('trackBtn').textContent='◎ 発話を追跡中';
 setIndex(0,{scroll:false});`);
replace('1600-target.w);target.y=clamp(pointerDown.vy-dy,0,980-target.h);','Math.max(0,sceneBounds().w-target.w));target.y=clamp(pointerDown.vy-dy,0,Math.max(0,sceneBounds().h-target.h));');
replace('newW=clamp(oldW*(e.deltaY<0?.9:1.1),600,1600)','newW=clamp(oldW*(e.deltaY<0?.9:1.1),600,sceneBounds().w)');
replace('1600-newW);target.y=clamp(target.y+(target.h-target.h*ratio)/2,0,980-target.h*ratio);',
 'Math.max(0,sceneBounds().w-newW));target.y=clamp(target.y+(target.h-target.h*ratio)/2,0,Math.max(0,sceneBounds().h-target.h*ratio));');
replace('グラフの関連づけは部分的・人手ルールであり、未対応区間を無理に接続していません。',
 '点線は未整理の発話と、元の話題または見出しとの対応を示します。');

fs.writeFileSync(output, original.slice(0, start) + script + original.slice(end), {encoding:'utf8',flag:'wx'});
