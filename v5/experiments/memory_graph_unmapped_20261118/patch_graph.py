"""Add an unresolved-source graph layer without changing embedded source data."""
import argparse
import hashlib
import json
from pathlib import Path


def patch(text, directory):
    edits = []

    def replace(old, new, label):
        nonlocal text
        count = text.count(old)
        if count != 1:
            raise ValueError(f"{label}: expected one exact match, found {count}")
        text = text.replace(old, new, 1)
        edits.append(label)

    replace('</style></head>', (directory / 'unmapped_graph.css').read_text(encoding='utf-8') + '\n</style></head>', 'styles')
    replace('<button class="chip" id="demoBtn">発話例（デモ）</button>', '<button class="chip" id="demoBtn">発話例（デモ）</button><button class="chip" id="pendingBtn">未整理を表示</button>', 'overview navigation')
    replace('<button class="mapButton" id="resetBtn">最初に戻る</button>', '<button class="mapButton" id="resetBtn">最初に戻る</button><button class="mapButton" id="pendingBack" hidden>← 未整理の一覧</button><span id="pendingPager" hidden><button id="pendingPrevPage" aria-label="前の未整理ページ">‹</button><span id="pendingPageText"></span><button id="pendingNextPage" aria-label="次の未整理ページ">›</button></span>', 'graph navigation')
    replace('<button id="jumpKimetsu">鬼滅へ</button>', '<button id="jumpKimetsu">鬼滅へ</button><button id="nextPendingBtn">次の未整理</button>', 'next unresolved line')
    replace('function orderRoute(){', (directory / 'unmapped_graph.js').read_text(encoding='utf-8') + '\nfunction orderRoute(){', 'unresolved presentation model')
    replace("svg.appendChild(create('rect',{x:0,y:0,width:1600,height:980,fill:'url(#grid)','pointer-events':'none'}));", "svg.appendChild(create('rect',{x:0,y:0,width:sceneBounds().w,height:sceneBounds().h,fill:'url(#grid)','pointer-events':'none'}));", 'scene background')
    replace("Object.keys(cores).forEach(id=>gn.appendChild(draw(id,true)));Object.keys(attrs).forEach(id=>gn.appendChild(draw(id,false)));svg.appendChild(gn);", "Object.keys(cores).forEach(id=>gn.appendChild(draw(id,true)));Object.keys(attrs).forEach(id=>gn.appendChild(draw(id,false)));svg.appendChild(gn);buildPendingLayer();", 'unresolved graph layer')
    replace('meta.append(topic,num);content.appendChild(meta);', "meta.append(topic,num);if(!r.cores.length||!r.attrs.length){const badge=document.createElement('span');badge.className='pending-badge'+(r.cores.length?' attribute':'');badge.textContent=r.cores.length?'属性未整理':'話題・属性未整理';meta.appendChild(badge);}content.appendChild(meta);", 'transcript state badges')
    replace("for(const n of list.querySelectorAll('.current'))n.classList.remove('current');", "for(const n of list.querySelectorAll('.current')){n.classList.remove('current');n.removeAttribute('aria-current');}", 'current row accessibility')
    replace("const row=$('line-'+index);if(row){row.classList.add('current');row.setAttribute('aria-current','step');}\n}", "const row=$('line-'+index);if(row){row.classList.add('current');row.setAttribute('aria-current','step');}paintPendingLayer();\n}", 'unresolved selection highlight')
    old_position = """function position(){
 if(showAll){target={x:0,y:0,w:1600,h:980};return;}
 const active=activeMapping();const first=active.attrs.values().next().value;
 const c=active.cores.values().next().value;const obj=first?attrs[first]:c?cores[c]:null;
 if(!obj){target={x:0,y:0,w:1600,h:980};return;}
 target={x:clamp(obj.x-630,0,470),y:clamp(obj.y-350,0,220),w:1130,h:760};
}"""
    new_position = """function position(){
 const bounds=sceneBounds();if(showAll){target={x:0,y:0,w:bounds.w,h:bounds.h};return;}
 const pending=pendingFocus();if(pending){target={x:clamp(pending.x-565,1690,2170),y:clamp(pending.y-330,0,540),w:1130,h:760};return;}
 const active=activeMapping();const first=active.attrs.values().next().value;
 const c=active.cores.values().next().value;const obj=first?attrs[first]:c?cores[c]:null;
 if(!obj){target={x:0,y:0,w:bounds.w,h:bounds.h};return;}
 target={x:clamp(obj.x-630,0,470),y:clamp(obj.y-350,0,220),w:1130,h:760};
}"""
    replace(old_position, new_position, 'tracking bounds')
    replace("if(tracking&&!showAll)position();paint();", "syncPendingSelection();if(tracking&&!showAll)position();paint();", 'source to graph tracking')
    replace("items=orderRoute();sidebar();$('speechList').scrollTop=0;setIndex(0,{scroll:false});", "items=orderRoute();sidebar();buildMap();$('speechList').scrollTop=0;setIndex(0,{scroll:false});", 'display-mode graph rebuilding')
    replace("${SOURCE_ROWS.length}行 / ${new TextEncoder().encode(ORIGINAL_SOURCE).length.toLocaleString('ja-JP')}バイト（UTF-8）", "${SOURCE_ROWS.length}行・発話${SOURCE_ROWS.filter(r=>r.kind==='speech').length}行｜既存属性あり${SOURCE_ROWS.filter(r=>r.kind==='speech'&&r.attrs.length).length}行\\n話題・属性未整理 ${pendingModel.topicMissing}行 ／ 属性のみ未整理 ${pendingModel.attributeOnly}行", 'coverage counts')
    replace('グラフの関連づけは部分的・人手ルールであり、未対応区間を無理に接続していません。', '既存の関連づけは部分的・人手ルールです。未整理の発話もグラフへ表示し、破線は元見出しの中にあることだけを表します。話題や属性を確定した意味の線ではありません。', 'source footer explanation')
    replace("$('sourceBtn').onclick=()=>setDisplay('source');$('demoBtn').onclick=()=>setDisplay('demo');", "$('sourceBtn').onclick=()=>setDisplay('source');$('demoBtn').onclick=()=>setDisplay('demo');\n$('pendingBtn').textContent=`未整理 ${pendingModel.members.length}行`;$('pendingBtn').onclick=pendingOverview;\n$('nextPendingBtn').onclick=nextPending;$('pendingBack').onclick=pendingOverview;\n$('pendingPrevPage').onclick=()=>movePendingPage(-1);$('pendingNextPage').onclick=()=>movePendingPage(1);", 'navigation handlers')
    replace("$('fitBtn').onclick=()=>{showAll=!showAll;if(showAll)stop();position();$('fitBtn').textContent=showAll?'発話を追跡':'全体表示'};", "$('fitBtn').onclick=()=>{if(showAll){showAll=false;tracking=true;setIndex(index,{scroll:false});}else{showAll=true;stop();pendingExpanded=null;buildPendingLayer();position();}$('fitBtn').textContent=showAll?'発話を追跡':'全体表示'};", 'fit all unresolved groups')
    replace("$('trackBtn').onclick=()=>{showAll=false;tracking=true;position();", "$('trackBtn').onclick=()=>{showAll=false;tracking=true;syncPendingSelection();position();", 'resume tracking')
    replace("target.x=clamp(pointerDown.vx-dx,0,1600-target.w);target.y=clamp(pointerDown.vy-dy,0,980-target.h);", "target.x=clamp(pointerDown.vx-dx,0,Math.max(0,sceneBounds().w-target.w));target.y=clamp(pointerDown.vy-dy,0,Math.max(0,sceneBounds().h-target.h));", 'drag world limits')
    replace("if(e.target.closest('.node'))return;", "if(e.target.closest('.node,.pending-group,.pending-line'))return;", 'node pointer interaction')
    replace("newW=clamp(oldW*(e.deltaY<0?.9:1.1),600,1600)", "newW=clamp(oldW*(e.deltaY<0?.9:1.1),600,sceneBounds().w)", 'zoom limits')
    replace("target.x=clamp(target.x+(oldW-newW)/2,0,1600-newW);target.y=clamp(target.y+(target.h-target.h*ratio)/2,0,980-target.h*ratio);", "target.x=clamp(target.x+(oldW-newW)/2,0,Math.max(0,sceneBounds().w-newW));target.y=clamp(target.y+(target.h-target.h*ratio)/2,0,Math.max(0,sceneBounds().h-target.h*ratio));", 'zoom origin limits')
    replace(" getRawSource:()=>ORIGINAL_SOURCE,", " getPendingSummary:()=>({total:pendingModel.members.length,topicMissing:pendingModel.topicMissing,attributeOnly:pendingModel.attributeOnly,groups:pendingModel.groups.map(g=>({id:g.id,title:g.title,lines:g.members.map(m=>m.lineNo)})),expanded:pendingExpanded,page:pendingPage}),\n getRawSource:()=>ORIGINAL_SOURCE,", 'read-only coverage diagnostics')
    return text, edits


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        raise ValueError('Use a separate output path; keep the original for review.')
    if args.output.exists():
        raise ValueError('Output already exists; inspect it instead of overwriting.')
    original = args.input.read_text(encoding='utf-8')
    result, edits = patch(original, Path(__file__).parent)
    args.output.write_text(result, encoding='utf-8')
    print(json.dumps(dict(status='written', exact_edits=edits, output=str(args.output),
        original_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
        output_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest()), ensure_ascii=False))


if __name__ == '__main__':
    main()
