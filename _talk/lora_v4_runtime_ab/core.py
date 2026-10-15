"""Runtime-only interventions. Authoritative speech is never rewritten."""
import re
import unicodedata
from difflib import SequenceMatcher

POLICY = {
    'history_window': 12, 'minimum_sentence_chars': 8,
    'semantic_cosine': .965, 'semantic_minimum_bigram_dice': .35,
    'near_text_ratio': .90, 'compact_chars': 240,
    'compact_max_utterances': 8, 'collapse_consecutive_candidates': 3,
}

def normal(text):
    return re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', text)).lower()

def sentences(text):
    return [s for s in re.findall(r'[^。！？!?\n]+[。！？!?]?|\n', text) if s.strip()]

def cosine(a, b):
    return sum(x*y for x,y in zip(a,b))

def dice(a,b):
    a={a[i:i+2] for i in range(len(a)-1)}
    b={b[i:i+2] for i in range(len(b)-1)}
    return 2*len(a&b)/(len(a)+len(b)) if a and b else 0.

def detect(text, vector, played, hard_reason=None):
    evidence=[]
    if hard_reason=='repetition':
        evidence.append({'kind':'within_output_exact','matched_turn':None})
    fresh=[normal(s) for s in sentences(text) if len(normal(s))>=POLICY['minimum_sentence_chars']]
    for old in played[-POLICY['history_window']:]:
        prior=[normal(s) for s in sentences(old['text']) if len(normal(s))>=POLICY['minimum_sentence_chars']]
        exact=next((s for s in fresh if s in prior),None)
        ratio=SequenceMatcher(None,normal(text),normal(old['text']),autojunk=False).ratio()
        sim=cosine(vector,old['vector'])
        overlap=dice(normal(text),normal(old['text']))
        kind=('exact_sentence' if exact else 'near_text' if ratio>=POLICY['near_text_ratio']
              and min(len(normal(text)),len(normal(old['text'])))>=POLICY['minimum_sentence_chars']
              else 'semantic_proxy' if sim>=POLICY['semantic_cosine']
              and overlap>=POLICY['semantic_minimum_bigram_dice']
              and min(len(normal(text)),len(normal(old['text'])))>=12 else None)
        if kind:
            evidence.append({'kind':kind,'matched_turn':old['turn'],'exact_sentence':exact,
                             'cosine':sim,'bigram_dice':overlap,'text_ratio':ratio})
    return {'loop':bool(evidence),'evidence':evidence,
            'semantic_interpretation':'E5 + lexical proxy; root reading required for true same-meaning judgment'}

def compact(initial,played,excluded):
    """Extract only recorded text; do not turn speech claims into facts."""
    selected=[];size=0
    for old in reversed(played):
        if old['turn'] in excluded or old.get('loop'):continue
        if len(selected)>=POLICY['compact_max_utterances']:break
        for s in reversed(sentences(old['text'])):
            if len(selected)>=POLICY['compact_max_utterances']:break
            added=len(s)+(1 if selected else 0)
            if size+added>POLICY['compact_chars']:continue
            selected.append({'turn':old['turn'],'text':s});size+=added
    selected.reverse()
    text='\n'.join(x['text'] for x in selected) if selected else initial
    return text,{'method':'extractive; no LLM summary; no new claims','sources':selected,
                 'excluded_turns':sorted(excluded),'claims_verified':False}

def ranked_candidate(bank,vectors,query,exclude=None,threshold=.6):
    scores=sorted([{'id':m['id'],'score':cosine(query,v)} for m,v in zip(bank,vectors)],
                  key=lambda x:x['score'],reverse=True)
    eligible=[x for x in scores if x['score']>=threshold and x['id']!=exclude]
    selected=eligible[0] if eligible else None
    return ([next(m for m in bank if m['id']==selected['id'])] if selected else []),{
        'ranked':scores,'excluded_id':exclude,'threshold':threshold,
        'top_id':selected['id'] if selected else None,'count':int(selected is not None),
        'transition_unavailable':exclude is not None and selected is None}
