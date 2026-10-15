"""CPU evidence-bearing experience checks, not a general semantic judge."""
import hashlib
import re
import sys
import unicodedata
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'morphology_dependencies'))
from janome.tokenizer import Tokenizer

VERSION = 'morphological-original-memory-v2'
_TOKENIZER = Tokenizer()
FAMILIES = {
    'make': {'作る', '作れる', '調理', '焼く', '炊く'},
    'eat': {'食べる', '食う', '食べれる'},
    'buy': {'買う', '購入'},
    'carry': {'持つ', '持ってくる', '持ち込む'},
    'go': {'行く', '出かける', '通う'},
    'exit': {'出る'}, 'enter': {'入る'},
    'return': {'返す', '返却'},
    'put': {'入れる', '置く'},
    'take': {'取る', '収穫'},
    'delete': {'消す', '削除'},
    'photo': {'撮る', '撮影'},
    'search': {'探す'}, 'find': {'見つける', '発見'},
    'open': {'開く', '開ける'},
    'wait': {'待つ', '待ち合わせ'},
    'receive': {'もらう', '貰う', '受け取る'},
    'fly': {'飛ばす'}, 'ride': {'乗る'},
    'push': {'押す'}, 'fall': {'落ちる', '転ぶ'},
    'forget': {'忘れる'}, 'mixup': {'間違える', '取り違える'},
    'heat': {'温める', '加熱', '解凍', 'レンチン'},
    'play': {'遊ぶ', 'プレイ', 'やる'},
    'cut': {'切る'}, 'pour': {'かける','掛ける'},
}
ALIASES = {'友達':'友人', 'お友達':'友人', 'ごはん':'ご飯', 'ライス':'ご飯', '白米':'ご飯',
           '卵':'卵', '玉子':'卵', 'たまご':'卵', '写真':'写真', '画像':'写真',
           'フォルダー':'フォルダ', '鰻':'うなぎ', 'ミニトマト':'トマト'}
COLOR = {'赤い':'赤','赤':'赤','青い':'青','青':'青','緑':'緑','緑色':'緑','黄色い':'黄','黄色':'黄',
         '白い':'白','白':'白','黒い':'黒','黒':'黒','灰色':'灰','茶色':'茶'}
GENERAL = {'私','あたし','自分','みんな','人','こと','もの','ところ','感じ','気','気持ち','話',
           '時','とき','時間','時点','瞬間','日','今回','最初','最後','あと','後','前','予定','つもり',
           '理由','失敗','間違い','残り','一口','味','料理','食事','やつ','方','用','手','口','頭','目',
           '腹','お腹','舌','反応','状況','出来事','思い出','経験','問題','ちょっと','誰か','何か','笑い'}
NUMBER = re.compile(r'([0-9０-９一二三四五六七八九十百千万〇零]+(?:[.．][0-9０-９]+)?)(枚|本|人|回|円|分|秒|センチ|cm|mm|ミリ)')
NOW = re.compile(r'(?:いま|現在|今)(?!度|回|後|朝|日)')
QUESTION_END = re.compile(r'(?:かな|かも(?:しれない)?|だろう|かしら|っけ|と思う|と思った|[？?])')
FUTURE_WISH = re.compile(r'したい|してみたい|食べたい|食べてみたい|行きたい|今度|もし|例えば|冗談|たとえ|比喩')
TIME_DIGITS = r'[0-9０-９一二三四五六七八九十百千万〇零]+'
EXPLICIT_TIME = re.compile(r'(?:一昨日|昨日|昨夜|昨晩|今朝|今日|明日|先週|先月|去年|昨年|最近)(?:の?(?:朝|昼|夕方|夜|午前|午後))?|(?:'+TIME_DIGITS+r'年)?'+TIME_DIGITS+r'月'+TIME_DIGITS+r'日|'+TIME_DIGITS+r'時(?:'+TIME_DIGITS+r'分)?|子供の頃|子どもの頃|幼い頃')
SENSORY_PAST = {'美味しい','おいしい','旨い','うまい','まずい','不味い','しょっぱい','甘い','辛い','苦い','楽しい','面白い','怖い'}


def normalized(text):
    return unicodedata.normalize('NFKC', text).replace(' ', '')


def canonical(word):
    word = normalized(word)
    return ALIASES.get(word, word)


@lru_cache(maxsize=512)
def tokens(text):
    return tuple({'surface': t.surface, 'base': t.base_form if t.base_form != '*' else t.surface,
                  'pos': t.part_of_speech.split(','), 'form': t.infl_form} for t in _TOKENIZER.tokenize(text))


def pieces(text):
    return [s.strip() for s in re.findall(r'[^。！？!?\n]+[。！？!?]?', text) if s.strip()]


def entities(items):
    out = []
    for token in items:
        pos = token['pos']
        word = canonical(token['base'])
        if pos[0] != '名詞' or pos[1] in {'非自立','代名詞','数','接尾','副詞可能'} or word in GENERAL:
            continue
        if pos[1] == 'サ変接続' and any(word in v for v in FAMILIES.values()):
            continue
        out.append(word)
    return list(dict.fromkeys(out))


def numeric(value):
    value = normalized(value)
    if re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', value):
        return float(value)
    total = group = current = 0
    digits = dict(zip('〇零一二三四五六七八九', [0,0,1,2,3,4,5,6,7,8,9]))
    for part in re.findall(r'[0-9]+|.', value):
        if part.isdigit(): current = int(part)
        elif part in digits: current = digits[part]
        elif part in {'十','百','千'}:
            group += (current or 1) * {'十':10,'百':100,'千':1000}[part]; current = 0
        elif part == '万':
            total += (group + current or 1) * 10000; group = current = 0
        else: return None
    return float(total + group + current)


def quantities(text):
    return [{'value': numeric(m[1]), 'unit': m[2], 'span': m[0]} for m in NUMBER.finditer(text)]


def time_key(text):
    text=normalized(text).replace('昨夜','昨日の夜').replace('昨晩','昨日の夜').replace('子ども','子供')
    return re.sub('('+TIME_DIGITS+r')(?=[年月日時分])',lambda m:str(int(numeric(m[0]))),text)


def application(body):
    """One unambiguous cooked material applied to a named target; original quote retained."""
    match = re.search(r'([^。、]{1,30}?)にかけて食べた', body)
    made = [f for f in frames(body,source=True) if f['family']=='make' and f['mode']=='asserted']
    material = list(dict.fromkeys(x for f in made for x in f['entities']))
    targets = entities(tokens(match[1])) if match else []
    return {'material':material[0],'target':targets[-1],'quote':match[0]} if len(material)==1 and targets else None


def attributes(text):
    ts = tokens(text); out = []
    for i,token in enumerate(ts):
        value = COLOR.get(token['base'])
        if not value: continue
        anchor = None
        # Adnominal color: 青い屋根 / 緑の靴下. Do not cross a verb to attach
        # an intended ripening color to a later, actually harvested fruit.
        for next_token in ts[i+1:i+5]:
            if next_token['pos'][0]=='動詞': break
            if next_token['pos'][0]=='名詞' and next_token['pos'][1] not in {'非自立','数'} and next_token['base'] not in COLOR:
                anchor=canonical(next_token['base']);break
        if anchor is None and i and ts[i-1]['surface'] in {'が','は','も'}:
            previous = entities(ts[:i-1])
            anchor = previous[-1] if previous else None
        if anchor: out.append({'anchor':anchor,'value':value,'quote':text})
    return out


def causal_edges(text):
    def signature(part):
        ts=tokens(part)
        values=set(entities(ts))
        values.update('verb:'+f['family'] for f in frames(part))
        values.update('state:'+canonical(t['base']) for t in ts if t['pos'][0]=='形容詞' or t['base'] in {'いっぱい','満杯','同じ','違い'})
        return values
    return [{'cause':signature(m[1]),'effect':signature(m[2]),'quote':m[0]} for m in
            re.finditer(r'([^。]+?)(?:ので|から|ため)、?([^。]+)',text)]


def frames(text, source=False):
    result = []
    for clause in pieces(text):
        ts = tokens(clause)
        for index, token in enumerate(ts):
            if token['pos'][0] != '動詞' or token['pos'][1] != '自立':
                continue
            word = token['base']
            if word == 'する' and index and ts[index-1]['pos'][0] == '名詞':
                word = ts[index-1]['base']
            family = next((k for k, vals in FAMILIES.items() if word in vals), None)
            if family is None:
                continue
            auxiliaries = {'あげる','くれる','もらう','みる','いる','しまう','いく','くる','おく','やる'}
            stop = next((j for j in range(index+1,len(ts)) if ts[j]['pos'][0] == '動詞' and ts[j]['pos'][1] == '自立'
                         and not (ts[j]['base'] in auxiliaries and ts[j-1]['surface'] in {'て','で'})
                         and not (ts[j]['base']=='する' and ts[j-1]['surface']=='と' and token['form']=='未然ウ接続')), len(ts))
            tail_tokens = ts[index+1:stop]
            tail = ''.join(t['surface'] for t in tail_tokens)
            past = any(t['base'] == 'た' and t['pos'][0] == '助動詞' for t in tail_tokens)
            progressive = any(t['base'] == 'いる' and t['pos'][0] == '動詞' for t in tail_tokens)
            intended = bool(re.search(r'予定|つもり|ようと|うと', tail)) or token['form'] == '未然ウ接続'
            purpose = bool(tail_tokens and tail_tokens[0]['surface'] == 'に' and stop < len(ts) and ts[stop]['base'] == '行く')
            nonassertive = bool(QUESTION_END.search(tail) or re.search(r'たら|れば|なら|時って|ときって|場合', tail))
            desired = any(t['base'] == 'たい' for t in tail_tokens)
            figurative = bool(re.search(r'冗談|比喩|例えば|たとえば', ''.join(t['surface'] for t in ts[:index])))
            if FUTURE_WISH.search(clause) and not past: nonassertive = True
            if desired or figurative: mode = 'uncertain'
            elif intended or purpose: mode = 'intended'
            elif nonassertive: mode = 'uncertain'
            elif past or (progressive and (source or NOW.search(clause))): mode = 'asserted'
            elif source and re.search(r'時|とき', tail) and re.search(r'た[。！!?]?$', clause): mode = 'background'
            else: mode = 'generic'
            # Clausal modifiers such as '重複していた' are not new physical
            # objects in the following delete frame. Keep nearest argument scope.
            begin = next((j+1 for j in range(index-1,-1,-1) if ts[j]['surface'] == '、' or
                          ts[j]['pos'][0] == '動詞' and ts[j]['pos'][1] == '自立'),0)
            before = ts[begin:index]
            names = entities(before)
            if family=='pour' and any(w in {'迷惑','声','手間','世話','心配','愛情'} for w in names):
                continue
            locations = []
            for j in range(1,len(before)):
                if before[j]['surface'] in {'に','へ','で'} and before[j-1]['pos'][0] == '名詞':
                    locations.append(canonical(before[j-1]['base']))
            result.append({'family':family,'verb':word,'mode':mode,'past':past,'progressive':progressive,
                           'negated':any(t['base'] in {'ない','ぬ','ん'} and t['pos'][0]=='助動詞' for t in tail_tokens),
                           'entities':names,'locations':locations,'clause':clause,
                           'predicate':token['surface']+tail,'quantities':quantities(clause)})
    return result


def references(memories):
    result = []
    for memory in memories:
        if set(memory) != {'id','body'}: raise ValueError('Only original Memory references are accepted')
        body = memory['body']
        source_frames=frames(body,source=True)
        applied=application(body)
        if applied:
            source_frames.append({'family':'pour','mode':'asserted','entities':[applied['material'],applied['target']],
                                  'locations':[],'clause':applied['quote'],'predicate':applied['quote'],
                                  'past':True,'progressive':False,'quantities':[]})
        result.append({**memory,'sha256':hashlib.sha256(body.encode('utf8')).hexdigest(),
                       'entities':entities(tokens(body)),'frames':source_frames,
                       'quantities':quantities(body),'application':applied,'attributes':attributes(body),
                       'causal_edges':causal_edges(body)})
    return result


def supported_entity(word, refs):
    if word in GENERAL: return True
    for ref in refs:
        body = normalized(ref['body'])
        if word == '出口' and ('西口' in body or '東口' in body): return True
        if word == '待ち合わせ' and any(f['family']=='wait' for f in ref['frames']): return True
        if word in body or any(word == v or (len(word)>=2 and len(v)>=2 and (word in v or v in word)) for v in ref['entities']):
            return True
    return False


def check_text(text, memories, planner=False):
    refs = references(memories)
    issues = []
    analyzed = frames(text)
    def add(code, span, evidence=None):
        issues.append({'code':code,'span':span,'evidence':evidence or
                       [{'memory_id':r['id'],'sha256':r['sha256'],'source_quote':r['body']} for r in refs]})
    for frame in analyzed:
        if frame['mode'] in {'generic','uncertain'}:
            continue
        # A future wish is permitted; a retold intended episode is still grounded.
        if frame['mode'] == 'intended' and not frame['past']:
            continue
        unknown = [word for word in frame['entities'] if not supported_entity(word, refs)]
        if unknown:
            add('unsupported_experience_entity', frame['clause'], {'unknown_entities':unknown,'sources':[r['body'] for r in refs]})
        matching = [f for r in refs for f in r['frames'] if f['family'] == frame['family']]
        if frame['mode'] == 'asserted' and not frame.get('negated') and matching and all(f['mode'] == 'intended' for f in matching):
            add('intention_became_completed', frame['predicate'])
        # Only explicit polarity on the same named action/object; no general
        # negation entailment or inference from an intended event is claimed.
        same_event=[f for f in matching if f['mode']=='asserted' and frame['entities'] and
                    set(f['entities']) & set(frame['entities'])]
        if frame['mode']=='asserted' and same_event and all(bool(f.get('negated'))!=bool(frame.get('negated')) for f in same_event):
            add('source_action_polarity_changed',frame['clause'])
        if not matching and frame['mode'] == 'asserted':
            contextual = (frame['family'] == 'play' and any('ゲーム' in r['body'] for r in refs))
            # General handling words in an already-grounded event are not forced
            # into a prescribed narration. Specific new actions remain checked.
            if not contextual and frame['family'] not in {'put','carry','go','open','forget','mixup'}:
                add('unsupported_completed_action', frame['predicate'])
            elif not refs:
                add('ungrounded_completed_experience', frame['predicate'])
        if matching and frame['locations'] and frame['family'] in {'go','exit','enter','wait'}:
            known = {x for f in matching for x in f['locations']}
            explicit = [x for x in frame['locations'] if x.endswith(('口','駅','館','店'))]
            if known and any(x not in known for x in explicit):
                add('event_location_changed', frame['clause'], {'expected_locations':sorted(known)})
        if NOW.search(frame['clause']) and frame['progressive'] and matching:
            if not any(NOW.search(r['body']) for r in refs):
                add('past_event_recast_as_now', frame['clause'])
    for clause in pieces(text):
        clause_frames = [f for f in analyzed if f['clause'] == clause]
        definite = any(f['mode'] == 'asserted' for f in clause_frames)
        nonassertive = (QUESTION_END.search(clause) or any(t['base']=='たい' for t in tokens(clause)) or
                       re.search(r'冗談|比喩|例えば|たとえば|たら|れば|なら',clause)) and not definite
        ts=tokens(clause)
        sensory = any(t['pos'][0]=='形容詞' and t['base'] in SENSORY_PAST and
                      any(a['base']=='た' and a['pos'][0]=='助動詞' for a in ts[i+1:i+3])
                      for i,t in enumerate(ts))
        # A retrospective sensory claim about a named new object implies an
        # experience even without a listed action verb. Generic opinions,
        # questions, wishes and explicit hypotheticals remain permitted.
        if sensory and not nonassertive:
            unknown=[word for word in entities(ts) if not supported_entity(word,refs)]
            if unknown:add('unsupported_retrospective_entity',clause,{'unknown_entities':unknown})
        if not nonassertive and (definite or sensory):
            source_times={time_key(m[0]) for r in refs for m in EXPLICIT_TIME.finditer(r['body'])}
            added=[m[0] for m in EXPLICIT_TIME.finditer(clause) if time_key(m[0]) not in source_times]
            if added:add('unsupported_explicit_time',clause,{'added_time_mentions':added})
        for amount in quantities(clause):
            if nonassertive or FUTURE_WISH.search(clause) and not definite: continue
            known = {q['value'] for r in refs for q in r['quantities'] if q['unit'] == amount['unit']}
            derived_sum = re.search(r'合わせ|合計|全部で|増え|になった',clause) and any(
                amount['value']==sum(q['value'] for q in r['quantities'] if q['unit']==amount['unit'])
                and len([q for q in r['quantities'] if q['unit']==amount['unit']])==2 for r in refs)
            if amount['value'] not in known and not derived_sum:
                add('unsupported_concrete_quantity', amount['span'])
        if nonassertive: continue
        for ref in refs:
            body = ref['body']
            for absent in re.finditer(r'([^。、、]{1,12}?)(?:が|は)なかった', body):
                name = absent[1]
                if re.search(re.escape(name)+r'(?:が|は)(?:ちゃんと|たっぷり)?あった', clause):
                    add('absence_reversed', clause, {'memory_id':ref['id'],'source_quote':absent[0]})
            swap = re.search(r'([^。、]{1,12}?)を入れたつもりが([^。、で]{1,12})', body)
            if swap and re.search(re.escape(swap[1])+r'を入れ(?:た|ていた)', clause) and not re.search(r'つもり|と思|なら|たら', clause):
                add('intended_object_as_actual', clause, {'memory_id':ref['id'],'source_quote':swap[0]})
            if 'しょっぱ' in body and re.search(r'甘かった|甘くなった', clause):
                add('source_taste_reversed', clause, {'memory_id':ref['id'],'source_quote':body})
            for attr in attributes(clause):
                same=[a for a in ref['attributes'] if a['anchor']==attr['anchor']]
                if same and attr['value'] not in {a['value'] for a in same} and (definite or re.search(r'かった|だった',clause)):
                    add('source_color_changed',clause,{'memory_id':ref['id'],'source_quote':body,'expected':same})
            applied=ref['application']
            if applied and definite:
                if re.search(re.escape(applied['target'])+r'を'+re.escape(applied['material'])+r'にかけ(?:た|て)', clause):
                    add('source_application_reversed', clause, {'memory_id':ref['id'],'source_quote':applied['quote']})
                elif re.search(re.escape(applied['target'])+r'をかけた',clause):
                    add('unsupported_application_material',clause,{'memory_id':ref['id'],'source_quote':applied['quote']})
            for proposed in causal_edges(clause):
                for edge in ref['causal_edges']:
                    if (len(proposed['cause'] & edge['effect'])>=2 and len(proposed['effect'] & edge['cause'])>=2
                            and any(x.startswith('verb:') for x in proposed['cause'] & edge['effect'])):
                        add('source_cause_effect_reversed',clause,{'memory_id':ref['id'],'source_quote':edge['quote']})
    unique = {(x['code'],x['span']):x for x in issues}
    result = {'accepted':not unique,'issues':list(unique.values()),'analyzed_frames':analyzed,
              'source_references':[{'id':r['id'],'sha256':r['sha256'],'body':r['body']} for r in refs],
              'version':VERSION,'scope':'listed physical actions, retrospective sensory predicates, explicit time strings and selected state/quantity conflicts; not a full semantic proof',
              'rule_verdict':'detected_conflict' if unique else 'no_conflict_detected',
              'semantic_verdict':'unverified',
              'known_blind_spots':['unlisted predicates and noun-only experiences','implicit dates and event coreference','negation/sarcasm scope','general causal and semantic entailment']}
    notes=[]
    codes={i['code'] for i in unique.values()}
    if 'unsupported_experience_entity' in codes:
        unknown=sorted({word for issue in unique.values() if issue['code']=='unsupported_experience_entity' for word in issue['evidence']['unknown_entities']})
        notes.append('元Memoryにない'+ '・'.join(unknown[:4])+'を使った具体的経験を追加しない。')
    if codes & {'source_application_reversed','unsupported_application_material'}:
        notes.append('かけた物と、かけられた物を入れ替えず、元Memoryの行為と対象を保つ。')
    if 'past_event_recast_as_now' in codes: notes.append('過去の出来事を今起きている出来事に変えない。')
    if 'unsupported_concrete_quantity' in codes: notes.append('元Memoryにない具体的な数値を事実として足さない。')
    if 'unsupported_explicit_time' in codes: notes.append('元Memoryにない日付や時刻を経験に付け足さない。')
    if 'unsupported_retrospective_entity' in codes: notes.append('元Memoryにない物を体験した感想として付け足さない。一般的な連想は自由。')
    if 'intention_became_completed' in codes: notes.append('予定や試みを完了した経験に変えない。')
    if not notes and codes: notes.append('元Memoryの物・否定・時間・理由を保ち、新しい具体的経験を追加しない。')
    result['feedback']=''.join(notes)+'感想・一般的連想・質問や仮定は自由。' if codes else ''
    return result


def check_plan(plan, memories):
    return check_text('\n'.join([plan['topic']]+plan['flow']), memories, planner=True)
