// Offline logic/DOM simulation; not a browser rendering or visual-layout test.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');

class Element {
 constructor(tag, owner, type=1, value='') {
  this.tagName=tag.toUpperCase();this.owner=owner;this.nodeType=type;this.value=value;
  this.attributes={};this.children=[];this.parentNode=null;this.events={};this.scrollTop=0;this.clientHeight=600;
  this.style={setProperty:(k,v)=>{this.style[k]=v;}};
  this.classList={contains:c=>this.className.split(/\s+/).includes(c),
   add:c=>{this.className=[...new Set(this.className.split(/\s+/).filter(Boolean).concat(c))].join(' ');},
   remove:c=>{this.className=this.className.split(/\s+/).filter(v=>v!==c).join(' ');},
   toggle:(c,force)=>{const on=force===undefined?!this.classList.contains(c):force;on?this.classList.add(c):this.classList.remove(c);return on;}};
 }
 get id(){return this.attributes.id||'';}set id(v){this.attributes.id=String(v);}
 get className(){return this.attributes.class||'';}set className(v){this.attributes.class=String(v);}
 get hidden(){return 'hidden' in this.attributes;}set hidden(v){v?this.setAttribute('hidden',''):this.removeAttribute('hidden');}
 get disabled(){return 'disabled' in this.attributes;}set disabled(v){v?this.setAttribute('disabled',''):this.removeAttribute('disabled');}
 get textContent(){return this.nodeType===3?this.value:this.children.map(n=>n.textContent).join('');}
 set textContent(v){this.replaceChildren();if(String(v))this.appendChild(new Element('#text',this.owner,3,String(v)));}
 set innerHTML(v){this.replaceChildren();parseInto(this,String(v),this.owner);}
 get dataset(){return Object.fromEntries(Object.entries(this.attributes).filter(([k])=>k.startsWith('data-')).map(([k,v])=>[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase()),v]));}
 setAttribute(k,v){this.attributes[k]=String(v);}removeAttribute(k){delete this.attributes[k];}
 getAttribute(k){return this.attributes[k]??null;}
 appendChild(node){if(node.nodeType===11){for(const child of [...node.children])this.appendChild(child);node.children=[];return node;}node.remove();node.parentNode=this;this.children.push(node);return node;}
 append(...nodes){for(const n of nodes)this.appendChild(typeof n==='string'?new Element('#text',this.owner,3,n):n);}
 replaceChildren(...nodes){this.children.forEach(n=>n.parentNode=null);this.children=[];this.append(...nodes);}
 remove(){if(this.parentNode){this.parentNode.children=this.parentNode.children.filter(n=>n!==this);this.parentNode=null;}}
 addEventListener(type,handler){(this.events[type]??=[]).push(handler);}
 fire(type,event={}){const e={target:this,preventDefault(){},...event};for(const handler of this.events[type]||[])handler(e);if(this['on'+type])this['on'+type](e);}
 matches(selector){return selector.split(',').some(s=>{s=s.trim();if(s.startsWith('#'))return this.id===s.slice(1);if(s.startsWith('.'))return this.classList.contains(s.slice(1));if(s.startsWith('['))return s.slice(1,-1) in this.attributes;return this.tagName.toLowerCase()===s;});}
 querySelectorAll(selector){const result=[];const visit=n=>{for(const child of n.children){if(child.nodeType===1&&child.matches(selector))result.push(child);visit(child);}};visit(this);return result;}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
 closest(selector){for(let p=this;p;p=p.parentNode)if(p.nodeType===1&&p.matches(selector))return p;return null;}
 getBoundingClientRect(){return {top:0,left:0,width:1000,height:800};}
 scrollTo(options){this.scrollTop=options.top||0;}
}

function decode(text){return text.replace(/&(#x[\da-f]+|#\d+|amp|lt|gt|quot|apos);/gi,(_,v)=>({amp:'&',lt:'<',gt:'>',quot:'"',apos:"'"}[v]??String.fromCodePoint(v[1]?.toLowerCase()==='x'?parseInt(v.slice(2),16):Number(v.slice(1)))));}
function parseInto(parent,markup,doc){
 const stack=[parent],voids=new Set(['input','br','hr','img','meta','link']);
 for(const token of markup.match(/<!--[\s\S]*?-->|<[^>]+>|[^<]+/g)||[]){
  if(token.startsWith('<!--'))continue;
  if(token.startsWith('</')){if(stack.length>1)stack.pop();continue;}
  if(token.startsWith('<')){
   const match=token.match(/^<([\w-]+)/);if(!match)continue;
   const node=doc.createElement(match[1]),rest=token.slice(match[0].length,-1);
   const attrs=/([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g;
   for(const a of rest.matchAll(attrs))node.setAttribute(a[1],decode(a[2]??a[3]??a[4]??''));
   stack.at(-1).appendChild(node);if(!voids.has(match[1].toLowerCase())&&!token.endsWith('/>'))stack.push(node);
  }else stack.at(-1).appendChild(doc.createTextNode(decode(token)));
 }
}

function boot(html){
 const doc={createElement:t=>new Element(t,doc),createElementNS:(_,t)=>new Element(t,doc),
  createTextNode:t=>new Element('#text',doc,3,t),createDocumentFragment:()=>new Element('#fragment',doc,11)};
 doc.body=doc.createElement('body');doc.activeElement=doc.body;
 doc.getElementById=id=>doc.body.querySelector('#'+id);
 parseInto(doc.body,html.slice(html.indexOf('<body>')+6,html.indexOf('<script>')),doc);
 const timers=new Map();let timerId=0;
 const window={innerWidth:1440,innerHeight:900,addEventListener(){}};
 const context=vm.createContext({document:doc,window,console,TextEncoder,requestAnimationFrame(){},
  setInterval:fn=>{timers.set(++timerId,fn);return timerId;},clearInterval:id=>timers.delete(id)});
 const script=html.slice(html.indexOf('<script>')+8,html.indexOf('</script>'));
 new vm.Script(script).runInContext(context,{timeout:5000});
 return {doc,context,window,timers,evaluate:code=>vm.runInContext(code,context,{timeout:5000})};
}

const filename=process.argv[2];if(!filename)throw Error('Pass the local HTML path.');
const html=fs.readFileSync(filename,'utf8'),app=boot(html),{doc,evaluate,window}=app;
const checks=[];
function check(name,fn){fn();checks.push(name);}
function click(id){const node=doc.getElementById(id);assert(node,'missing '+id);assert(!node.disabled,'disabled '+id);node.fire('click');}
function goLine(number){const row=doc.getElementById('line-'+(number-1));assert(row);row.fire('click');}
const expected=evaluate('SOURCE_ROWS.flatMap((r,i)=>r.kind==="speech"&&(!r.cores.length||!r.attrs.length)?[i]:[])');
check('all source speech text is exact in simulated DOM',()=>{
 const expectedText=evaluate('SOURCE_ROWS.filter(r=>r.kind==="speech").map(r=>r.raw)');
 assert.equal(JSON.stringify(doc.body.querySelectorAll('.speechText').map(n=>n.textContent)),JSON.stringify(expectedText));
});
check('unmapped node click synchronizes transcript and current state',()=>{
 const node=doc.body.querySelector('.pending-line');assert(node);const rowIndex=Number(node.dataset.rowIndex);node.fire('click');
 assert.equal(evaluate('index'),rowIndex);assert(doc.getElementById('line-'+rowIndex).classList.contains('current'));
 assert.equal(doc.body.querySelectorAll('.pending-line').filter(n=>n.getAttribute('aria-current')==='step').length,1);
});
check('next unresolved control advances to actual source line',()=>{
 const old=evaluate('index');click('nextPendingBtn');assert(evaluate('index')>old);assert(evaluate('pendingModel.memberGroups.has(index)'));
});
const allReached=[];
check('every unresolved line is rendered once across all overview groups/pages',()=>{
 const groups=JSON.parse(evaluate('JSON.stringify(pendingModel.groups.map(g=>({id:g.id,count:g.members.length})))'));
 for(const group of groups){
  click('pendingBtn');assert.equal(doc.body.querySelectorAll('[data-pending-group]').length,groups.length);
  const node=doc.body.querySelectorAll('[data-pending-group]').find(n=>n.dataset.pendingGroup===group.id);assert(node);node.fire('click');
  for(let page=0;page<Math.ceil(group.count/12);page++){
   if(page)click('pendingNextPage');
   const visible=doc.body.querySelectorAll('.pending-line');assert(visible.length>0&&visible.length<=12);
   for(const line of visible){const i=Number(line.dataset.rowIndex);allReached.push(i);assert.equal(evaluate('SOURCE_ROWS['+i+'].kind'),'speech');}
  }
  assert(doc.getElementById('pendingNextPage').disabled);
  if(group.count>12){click('pendingPrevPage');assert.equal(evaluate('pendingPage'),Math.ceil(group.count/12)-2);}
 }
 assert.equal(new Set(allReached).size,expected.length);assert.equal(allReached.length,expected.length);
 assert.equal(JSON.stringify(allReached.sort((a,b)=>a-b)),JSON.stringify(expected));
});
check('curated attribute row keeps its original graph highlight',()=>{
 const i=evaluate('SOURCE_ROWS.findIndex(r=>r.kind==="speech"&&r.attrs.length)');goLine(i+1);
 assert.equal(evaluate('pendingExpanded'),null);const ids=evaluate('SOURCE_ROWS[index].attrs');
 const active=doc.body.querySelectorAll('.node').filter(n=>n.classList.contains('current')).map(n=>n.dataset.id);
 assert(ids.every(id=>active.includes(id)));
});
check('attribute-only unresolved row has distinct node state',()=>{
 const i=evaluate('SOURCE_ROWS.findIndex(r=>r.kind==="speech"&&r.cores.length&&!r.attrs.length)');goLine(i+1);
 const current=doc.body.querySelectorAll('.pending-line').find(n=>n.classList.contains('current'));assert(current?.classList.contains('pending-attribute-missing'));
});
check('search still locates an exact original string',()=>{
 const text=evaluate('SOURCE_ROWS[pendingModel.members[0].rowIndex].raw');doc.getElementById('searchInput').value=text;click('searchBtn');assert(evaluate('SOURCE_ROWS[index].raw')===text);
});
check('fit all and tracking use source scene bounds',()=>{
 click('fitBtn');assert.equal(evaluate('target.w'),3300);assert.equal(evaluate('target.h'),1300);assert.equal(evaluate('pendingExpanded'),null);
 click('trackBtn');assert(evaluate('pendingExpanded')!==null);assert(evaluate('Number.isFinite(target.x)&&target.x>=0&&target.y>=0'));
});
check('pending node does not initiate background drag',()=>{
 const node=doc.body.querySelector('.pending-line');assert(node);doc.getElementById('map').fire('pointerdown',{target:node,clientX:10,clientY:10});assert.equal(evaluate('pointerDown'),null);
});
check('demo mode, CPU order and detour remain usable',()=>{
 click('demoBtn');assert.equal(evaluate('displayMode'),'demo');assert.equal(doc.body.querySelector('#pendingLayer'),null);assert(doc.getElementById('pendingBtn').disabled);
 assert.equal(evaluate('items.length'),19);click('oldBtn');assert.equal(evaluate('cpu'),'old');click('routeDetour');assert.equal(evaluate('items.length'),23);
 click('sourceBtn');assert.equal(evaluate('displayMode'),'source');assert(!doc.getElementById('pendingBtn').disabled);
});
check('source replay advances only selection',()=>{
 const old=evaluate('index');click('playBtn');assert.equal(app.timers.size,1);[...app.timers.values()][0]();assert.equal(evaluate('index'),old+1);click('playBtn');assert.equal(app.timers.size,0);
});
const source=window.__fullTrace.getRawSource();
const report={status:'pass',scope:'Offline DOM/logic simulation only; browser file-URL navigation was denied; no visual/layout/browser test claimed.',
 checks,source_sha256:crypto.createHash('sha256').update(source).digest('hex'),source_rows:window.__fullTrace.getState().sourceLineCount,
 unresolved_nodes_reached:allReached.length,unique_unresolved_nodes:new Set(allReached).size,
 summary:window.__fullTrace.getPendingSummary(),external_network:0};
if(process.argv[3])fs.writeFileSync(process.argv[3],JSON.stringify(report,null,2)+'\n','utf8');
console.log(JSON.stringify(report,null,2));
