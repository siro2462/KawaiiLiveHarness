// Source-only visual nodes use the same renderer as curated nodes.
// Original source rows and curated semantic mappings are never modified.
function makeInlineGraph(baseCores,baseAttrs,rows){
 const cores={},attrs={},rowMappings={},sections=[];let section=null;
 const transform=p=>({x:8000+(p.x-1000)*8,y:8000+(p.y-550)*8});
 Object.entries(baseCores).forEach(([id,c])=>cores[id]={...c,...transform(c)});
 Object.entries(baseAttrs).forEach(([id,a])=>attrs[id]={...a,bridge:[...a.bridge],...transform(a)});
 rows.forEach(r=>{
  if(!section||r.kind==='heading'){
   section={lineNo:r.lineNo,title:r.section||'見出しなし',rows:[],core:r.cores[0]||null};sections.push(section);
  }
  section.rows.push(r);
 });
 const missing=sections.filter(s=>!s.core);
 missing.forEach((s,i)=>{
  const angle=-Math.PI/2+i*2*Math.PI/missing.length,id='unresolved_topic_L'+s.lineNo;
  s.core=id;cores[id]={label:s.title,x:8000+6800*Math.cos(angle),y:8000+6800*Math.sin(angle),color:'#8190a8',unresolved:true,note:'元資料の見出し（話題の意味分類は未整理）'};
 });
 const counts={};let unresolved=0,topicMissing=0,attributeOnly=0;
 sections.forEach(s=>s.rows.forEach(r=>{
  const context=r.cores.length?[...r.cores]:[s.core];
  rowMappings[r.lineNo]={cores:context,attrs:[...r.attrs]};
  if(r.kind!=='speech'||(r.cores.length&&r.attrs.length))return;
  const parent=context[0],n=counts[parent]||0;counts[parent]=n+1;
  const id='unresolved_L'+r.lineNo,angle=n*Math.PI*(3-Math.sqrt(5));
  const spacing=cores[parent].unresolved?90:80,radius=spacing*Math.sqrt(n+1)+70;
  const excerpt=Array.from(r.raw.trim());
  attrs[id]={label:excerpt.slice(0,10).join('')+(excerpt.length>10?'…':''),
   x:cores[parent].x+Math.cos(angle)*radius,y:cores[parent].y+Math.sin(angle)*radius,
   bridge:context,color:'#8190a8',unresolved:true,lineNo:r.lineNo,
   note:r.raw,status:r.cores.length?'attribute':'topic'};
  rowMappings[r.lineNo].attrs.push(id);unresolved++;r.cores.length?attributeOnly++:topicMissing++;
 }));
 const all=[...Object.values(cores),...Object.values(attrs)];
 const minX=Math.min(...all.map(p=>p.x))-350,minY=Math.min(...all.map(p=>p.y))-350;
 all.forEach(p=>{p.x-=minX;p.y-=minY;});
 const bounds={w:Math.ceil(Math.max(...all.map(p=>p.x))+400),h:Math.ceil(Math.max(...all.map(p=>p.y))+400)};
 return {cores,attrs,rowMappings,bounds,unresolved,topicMissing,attributeOnly,newTopics:missing.length};
}
const inlineGraph=makeInlineGraph(cores,attrs,SOURCE_ROWS);
function graphCores(){return displayMode==='source'?inlineGraph.cores:cores;}
function graphAttrs(){return displayMode==='source'?inlineGraph.attrs:attrs;}
function sourceMapping(row){return inlineGraph.rowMappings[row.lineNo];}
function sceneBounds(){return displayMode==='source'?inlineGraph.bounds:{w:1600,h:980};}
