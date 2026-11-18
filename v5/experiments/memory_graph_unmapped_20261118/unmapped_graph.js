// Presentation-only projection. Source rows and curated mappings remain unchanged.
function makePendingModel(rows) {
 const sections=[];let section=null;
 rows.forEach((row,rowIndex)=>{
  if(!section||row.kind==='heading'){
   section={id:'pending-section-'+row.lineNo,title:row.section||'見出しのない原文',startLine:row.lineNo,rowIndices:[],members:[]};
   sections.push(section);
  }
  section.rowIndices.push(rowIndex);
  if(row.kind==='speech'&&(!row.cores.length||!row.attrs.length))
   section.members.push({rowIndex,lineNo:row.lineNo,status:row.cores.length?'attribute':'topic'});
 });
 const groups=sections.filter(s=>s.members.length);
 const rowGroups=new Map(),memberGroups=new Map();
 groups.forEach(g=>{g.rowIndices.forEach(i=>rowGroups.set(i,g));g.members.forEach(m=>memberGroups.set(m.rowIndex,g));});
 const members=groups.flatMap(g=>g.members).sort((a,b)=>a.rowIndex-b.rowIndex);
 return {groups,rowGroups,memberGroups,members,topicMissing:members.filter(m=>m.status==='topic').length,
  attributeOnly:members.filter(m=>m.status==='attribute').length};
}
const pendingModel=makePendingModel(SOURCE_ROWS),PENDING_PAGE_SIZE=12;
let pendingExpanded=null,pendingPage=0;
function sceneBounds(){return displayMode==='source'?{w:3300,h:1300}:{w:1600,h:980};}
function pendingGroup(){return pendingModel.groups.find(g=>g.id===pendingExpanded);}
function pendingPageMembers(){return pendingGroup()?.members.slice(pendingPage*PENDING_PAGE_SIZE,(pendingPage+1)*PENDING_PAGE_SIZE)||[];}
function pendingCardPosition(slot){return {x:1740+(slot%3)*510,y:230+Math.floor(slot/3)*225,w:480,h:155};}
function pendingFocus(){
 if(displayMode!=='source'||!pendingExpanded)return null;
 const group=pendingGroup(),slot=pendingPageMembers().findIndex(m=>m.rowIndex===index);
 if(!group)return null;
 const card=pendingCardPosition(Math.max(0,slot));return {x:card.x+card.w/2,y:card.y+card.h/2};
}
function syncPendingSelection(){
 if(displayMode!=='source')return;
 const group=pendingModel.rowGroups.get(index),row=SOURCE_ROWS[index];
 if(!group||(row.kind==='speech'&&!pendingModel.memberGroups.has(index))){if(pendingExpanded){pendingExpanded=null;pendingPage=0;buildPendingLayer();}return;}
 const memberIndex=group.members.findIndex(m=>m.rowIndex===index);
 const page=memberIndex<0?0:Math.floor(memberIndex/PENDING_PAGE_SIZE);
 if(group.id!==pendingExpanded||page!==pendingPage){pendingExpanded=group.id;pendingPage=page;buildPendingLayer();}
}
function pendingText(parent,text,x,y,maxChars=26,maxLines=2,css='pending-label'){
 const chars=Array.from(text),limit=maxChars*maxLines,shown=chars.slice(0,limit);
 if(chars.length>limit)shown[shown.length-1]='…';
 const node=create('text',{x,y,class:css});
 for(let i=0;i<shown.length;i+=maxChars){const span=create('tspan',{x,dy:i?21:0});span.textContent=shown.slice(i,i+maxChars).join('');node.appendChild(span);}
 parent.appendChild(node);return node;
}
function pendingButton(parent,at,label,action,classes){
 const node=create('g',{...at,class:classes,role:'button',tabindex:0,'aria-label':label});
 node.addEventListener('click',action);
 node.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();action();}});
 parent.appendChild(node);return node;
}
function openPendingGroup(group){
 stop();tracking=true;showAll=false;pendingExpanded=group.id;pendingPage=0;buildPendingLayer();
 setIndex(group.members[0].rowIndex);$('fitBtn').textContent='全体表示';
}
function pendingOverview(){
 stop();if(displayMode!=='source')setDisplay('source');pendingExpanded=null;pendingPage=0;
 showAll=false;tracking=false;buildPendingLayer();paintPendingLayer();
 target={x:1690,y:0,w:1610,h:1300};$('trackBtn').textContent='◎ 発話へ戻る';$('fitBtn').textContent='全体表示';
}
function movePendingPage(delta){
 const group=pendingGroup();if(!group)return;
 const pages=Math.ceil(group.members.length/PENDING_PAGE_SIZE),page=clamp(pendingPage+delta,0,pages-1);
 stop();tracking=true;showAll=false;setIndex(group.members[page*PENDING_PAGE_SIZE].rowIndex);
}
function nextPending(){
 if(displayMode!=='source')setDisplay('source');
 const next=pendingModel.members.find(m=>m.rowIndex>index)||pendingModel.members[0];
 if(next){stop();tracking=true;showAll=false;setIndex(next.rowIndex);}
}
function buildPendingLayer(){
 svg.querySelector('#pendingLayer')?.remove();
 if(displayMode!=='source'){$('pendingBack').hidden=true;$('pendingPager').hidden=true;return;}
 const layer=create('g',{id:'pendingLayer'});svg.appendChild(layer);
 const title=create('text',{x:1740,y:38,class:'pending-zone-title'});title.textContent='整理待ちの原文';layer.appendChild(title);
 const group=pendingGroup();
 if(!group){
  pendingModel.groups.forEach((g,i)=>{
   const x=1740+(i%3)*510,y=75+Math.floor(i/3)*195;
   const topicMissing=g.members.some(m=>m.status==='topic');
   const node=pendingButton(layer,{'data-pending-group':g.id},`${g.title}：未整理発話${g.members.length}行。開く`,()=>openPendingGroup(g),'pending-group');
   node.appendChild(create('rect',{x,y,width:480,height:160,rx:16,class:'pending-group-bg'}));
   pendingText(node,g.title,x+18,y+27,23,2,'pending-heading');
   const state=create('text',{x:x+18,y:y+77,class:'pending-state'});state.textContent=topicMissing?'話題・属性を整理待ち（元見出し）':'既存話題あり・属性を整理待ち';node.appendChild(state);
   node.appendChild(create('path',{d:`M ${x+28} ${y+86} V ${y+105}`,class:'pending-edge'}));
   node.appendChild(create('rect',{x:x+14,y:y+103,width:452,height:43,rx:10,class:'pending-count-box'}));
   const count=create('text',{x:x+28,y:y+130,class:'pending-count'});count.textContent=`未整理 ${g.members.length}行 · L${g.members[0].lineNo}–L${g.members.at(-1).lineNo}  ›`;node.appendChild(count);
  });
 }else{
  const header=pendingButton(layer,{'data-pending-group':group.id},`${group.title}。原文の見出しへ`,()=>{stop();tracking=true;setIndex(group.rowIndices[0]);},'pending-group pending-detail-heading');
  header.appendChild(create('rect',{x:1740,y:65,width:1500,height:110,rx:18,class:'pending-group-bg'}));
  pendingText(header,group.title,1764,98,55,2,'pending-heading');
  const description=create('text',{x:1764,y:151,class:'pending-state'});description.textContent=`元見出しの中の未整理発話 ${group.members.length}行 · 破線は原文上の所属`;header.appendChild(description);
  pendingPageMembers().forEach((member,slot)=>{
   const row=SOURCE_ROWS[member.rowIndex],p=pendingCardPosition(slot),nodeId='pending-line-'+row.lineNo;
   layer.appendChild(create('path',{d:`M ${p.x+p.w/2} 175 V ${p.y}`,class:'pending-edge'}));
   const node=pendingButton(layer,{id:nodeId,'data-row-index':member.rowIndex,'data-source-line':row.lineNo},`原文L${row.lineNo} ${member.status==='topic'?'話題・属性未整理':'属性未整理'}：${row.raw}`,()=>{stop();tracking=true;showAll=false;setIndex(member.rowIndex);},'pending-line '+(member.status==='topic'?'pending-topic-missing':'pending-attribute-missing'));
   node.appendChild(create('rect',{x:p.x,y:p.y,width:p.w,height:p.h,rx:13,class:'pending-line-bg'}));
   const status=create('text',{x:p.x+17,y:p.y+26,class:'pending-line-status'});status.textContent=`L${String(row.lineNo).padStart(3,'0')} · ${member.status==='topic'?'話題・属性未整理':'属性未整理'}`;node.appendChild(status);
   pendingText(node,row.raw,p.x+17,p.y+53,28,4,'pending-line-text');
   const tip=create('title');tip.textContent=row.raw;node.appendChild(tip);
  });
 }
 paintPendingLayer();
}
function paintPendingLayer(){
 const source=displayMode==='source',group=pendingGroup(),row=SOURCE_ROWS[index];
 $('pendingBtn').disabled=!source;$('nextPendingBtn').hidden=!source;
 $('pendingBack').hidden=!source||!group;
 const pages=group?Math.ceil(group.members.length/PENDING_PAGE_SIZE):0;
 $('pendingPager').hidden=!source||pages<2;
 $('pendingPageText').textContent=group?`${pendingPage+1} / ${pages}ページ`:'';
 $('pendingPrevPage').disabled=pendingPage===0;$('pendingNextPage').disabled=!group||pendingPage>=pages-1;
 const activeGroup=source?(pendingModel.memberGroups.get(index)||(row.kind!=='speech'?pendingModel.rowGroups.get(index):null)):null;
 svg.querySelectorAll('[data-pending-group]').forEach(n=>n.classList.toggle('current',n.dataset.pendingGroup===activeGroup?.id));
 svg.querySelectorAll('.pending-line').forEach(n=>{const current=source&&Number(n.dataset.rowIndex)===index;n.classList.toggle('current',current);if(current)n.setAttribute('aria-current','step');else n.removeAttribute('aria-current');});
 if(!source)return;
 if(group){
  $('graphTitle').textContent=group.title;
  $('graphNote').textContent='未整理の発話を行ごとのノードで表示。クリックで原文へ移動。破線は見出し内の所属です。';
  if(pendingModel.memberGroups.has(index))$('graphPath').textContent=`L${row.lineNo}｜${row.cores.length?'属性未整理':'話題・属性未整理'}｜原文のまま保留`;
 }else if(svg.querySelector('#pendingLayer')){
  $('graphNote').textContent=`未整理 ${pendingModel.members.length}行を元見出しごとに表示。カードを開くと発話ノードへ進めます。`;
 }
}
