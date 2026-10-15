"""Fixed Planner test, A/B/C/D comparison, legacy diagnostics and runtime test.

Never trains, rewrites an old fixture, or picks a checkpoint by output quality.
"""
import argparse
from collections import Counter
import html
import importlib.util
import re
import subprocess
import time
import traceback
from tokenizers import Tokenizer
from common import *
from contracts import planner_prompt,talk_prompt,fallback_prompt
from runtime import Runtime,obtain_plan,obtain_speech,hard_failure

GOLD={
 'S1A':{'use_memory':True,'memory_id':'S1A','topic':'待ち合わせで駅の出口を間違えた話',
         'flow':['友人との西口での待ち合わせ','東口へ出てしまった失敗','パン屋の前で地図を開いて気づく']},
 'S2A':{'use_memory':True,'memory_id':'S2A','topic':'卵焼きで塩と砂糖を間違えた話',
         'flow':['卵焼きで塩と砂糖を取り違えた','味見で間違いに気づいた','残りを細かく切っておにぎりに入れた']},
 'S3B':{'use_memory':True,'memory_id':'S3B','topic':'ゲームの写真フォルダを整理した話',
         'flow':['青い家を撮ろうとして写真フォルダが満杯だった','重複していた看板の写真を十枚消した','写真を撮るための整理を振り返る']}}

def protected_ids(tok,prompt,recent,budget=928):
    enc=tok.encode(prompt,add_special_tokens=False);start=prompt.index(recent);end=start+len(recent)
    removable=[i for i,(a,b) in enumerate(enc.offsets) if a>=start and b<=end]
    cut=max(0,len(enc.ids)-budget)
    if cut>len(removable):raise ValueError('Protected Memory/Plan/state exceed inference budget')
    gone=set(removable[:cut]);return [x for i,x in enumerate(enc.ids) if i not in gone],cut

class Models:
    def __init__(self,planner_only=False):
        import torch
        from peft import PeftModel
        self.torch=torch;self.tok=Tokenizer.from_file(str(MODEL/'tokenizer.json'))
        planner=read(RUN/'planner/training_result.json')
        assert planner['status']=='complete' and sha(Path(planner['final_adapter'])/'adapter_model.safetensors')==planner['final_adapter_sha256']
        base=load_base(torch,False)
        self.model=PeftModel.from_pretrained(base,planner['final_adapter'],adapter_name='planner',is_trainable=False)
        self.hashes={'planner':planner['final_adapter_sha256']}
        if not planner_only:
            talk=read(RUN/'talk/training_result.json');assert talk['status']=='complete'
            assert sha(Path(talk['final_adapter'])/'adapter_model.safetensors')==talk['final_adapter_sha256']
            self.model.load_adapter(talk['final_adapter'],adapter_name='v4',is_trainable=False)
            self.model.load_adapter(str(V3),adapter_name='v3',is_trainable=False)
            self.hashes.update(v4=talk['final_adapter_sha256'],v3=sha(V3/'adapter_model.safetensors'))
        self.model.eval()

    def generate(self,adapter,prompt,recent,seed,planner=False,reseed=True,raw_ids=None,generation=None,budget=928,sentence_limit=2):
        from transformers import StoppingCriteria,StoppingCriteriaList
        torch=self.torch;self.model.set_adapter(adapter);self.model.eval()
        ids,cut=protected_ids(self.tok,prompt,recent,budget) if raw_ids is None else (list(raw_ids[-budget:]),max(0,len(raw_ids)-budget))
        if reseed:torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)
        n=len(ids);tok=self.tok
        class Stop(StoppingCriteria):
            def __call__(self,input_ids,scores,**kw):
                generated=input_ids[0,n:].tolist();text=tok.decode(generated,skip_special_tokens=True)
                if planner:
                    try:return isinstance(json.loads(text),dict)
                    except ValueError:return False
                return len(generated)>=8 and sentence_limit>0 and len(re.findall(r'[。！？!?]',text))>=sentence_limit
        cfg=generation or {'max_new_tokens':192 if planner else 96,'temperature':.8,'top_p':.95,'top_k':50,'repetition_penalty':1.05}
        options={'max_new_tokens':cfg['max_new_tokens'],'do_sample':not planner,'eos_token_id':1,'pad_token_id':1,'use_cache':True}
        if not planner:options.update({k:cfg[k] for k in ['temperature','top_p','top_k','repetition_penalty']})
        if planner or sentence_limit:options['stopping_criteria']=StoppingCriteriaList([Stop()])
        t0=time.perf_counter()
        with torch.inference_mode():
            inp=torch.tensor([ids],device='cuda:0');out=self.model.generate(input_ids=inp,attention_mask=torch.ones_like(inp),**options)
        gen=out[0,n:].cpu().tolist();text=tok.decode(gen,skip_special_tokens=True)
        rec={'text':text,'input_text':prompt,'decoded_input':tok.decode(ids,skip_special_tokens=False),
            'input_ids':ids,'output_ids':gen,'input_tokens':len(ids),'output_tokens':len(gen),'context_cut_tokens':cut,
            'seed':seed,'generation':cfg,'sentence_limit':sentence_limit,'adapter':adapter,'adapter_sha256':self.hashes[adapter],
            'seconds':round(time.perf_counter()-t0,3),
            'stop_reason':'eos' if gen and gen[-1]==1 else 'token_cap' if len(gen)>=cfg['max_new_tokens'] else 'structured_or_sentence_stop'}
        log('generated',adapter=adapter,tokens=len(gen),seconds=rec['seconds']);return rec

    def plan(self,inp,retry=0):return self.generate('planner',planner_prompt(inp),inp['recent'],SEED+retry,True)

def planner_test(models,out):
    records=[]
    for ex in rows(DATA/'examples.jsonl'):
        if ex['split']!='test':continue
        plan,attempts=obtain_plan(models.plan,ex['planner_input'])
        expected=ex['condition']=='REL'
        rec={'id':ex['id'],'condition':ex['condition'],'input':ex['planner_input'],'gold':ex['plan_target'],
             'future':ex['future_trajectory'],'prediction':plan,'attempts':attempts,
             'parse_valid':plan is not None,'selection_correct':plan is not None and plan['use_memory']==expected,
             'semantic_quality':'requires root reading, not string equality'}
        records.append(rec);write(out/'planner_test.json',{'status':'running','records':records})
    stats={kind:{'count':len(part),'parse_valid':sum(x['parse_valid'] for x in part),'selection_correct':sum(x['selection_correct'] for x in part)}
           for kind in ['REL','NONE','IRREL'] for part in [[x for x in records if x['condition']==kind]]}
    write(out/'planner_test.json',{'status':'complete','records':records,'counts':stats,'G2':'machine evidence only; root semantic review pending'})

def main_comparison(models,out):
    fixture_path=TALK/'memory_talk_lora_abc_v2/evaluation/memory_swap_abc_v2/audit/fixtures.json'
    fixture=read(fixture_path);cases={x['case_id']:x for x in fixture['cases']}
    records=[]
    for sid in ['S1A','S2A','S3B']:
        case=cases[sid];candidate=[{'id':sid,'body':case['memory']}]
        for arm in ['A_v3','B_v4_gold','C_planner_v4','D_v4_no_plan']:
            rt=Runtime(out/(sid+'-'+arm+'.sqlite'),case['context'])
            if arm=='B_v4_gold':rt.set_plan(GOLD[sid],candidate)
            for turn in range(3):
                plan_attempts=[]
                if arm=='C_planner_v4' and rt.needs_plan():
                    inp={'recent':rt.recent(),'current_state':{},'memory_candidates':candidate,'previous_plan':rt.plan}
                    plan,plan_attempts=obtain_plan(models.plan,inp)
                    if plan:rt.set_plan(plan,candidate)
                recent=rt.recent().rstrip('\n');plan=rt.plan if arm in ['B_v4_gold','C_planner_v4'] else None
                if arm=='A_v3':prompt='【記憶】\n'+case['memory']+'\n\n【直前の発話】\n'+recent+'\n';adapter='v3'
                else:
                    prompt=talk_prompt(recent,candidate,plan) if plan else fallback_prompt(recent,case['memory']);adapter='v4'
                accepted,attempts,failure=obtain_speech(lambda retry:models.generate(adapter,prompt,recent,SEED+turn+retry*10000))
                rec={'scenario':sid,'arm':arm,'turn':turn,'memory_candidates':candidate,'plan':plan,'planner_attempts':plan_attempts,
                     'speech_attempts':attempts,'accepted':accepted,'hard_failure':failure,
                     'playback':'simulated complete; generated candidates recorded only in diagnostic file'}
                if accepted:rt.commit_playback(accepted['text'],len(accepted['text']))
                else:rt.plan=None;rt.remaining=0
                rec['authoritative_recent']=rt.recent();records.append(rec)
                write(out/'comparison.json',{'status':'running','fixture_sha256':sha(fixture_path),'records':records})
            rt.close()
    write(out/'comparison.json',{'status':'complete','fixture_sha256':sha(fixture_path),'records':records,
        'generation':read(ROOT/'baseline/manifest.json')['speech_generation'],
        'interpretation':'same starting contexts/Memory/seed. Histories then diverge by arm; no claim of per-turn equal prompts',
        'gold_plans':GOLD,'quality':'root reading pending'})
    lines=['# v3 / v4 出力比較','小規模学習・合成Memory・模擬再生。品質は原文を読んで判定する。']
    page=['<!doctype html><meta charset="utf-8"><title>v4 Planner Talk比較</title><style>body{font:16px system-ui;margin:24px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:12px;vertical-align:top;white-space:pre-wrap}</style>']
    headers=['v3','v4＋Gold Plan','Planner＋v4','v4 Planなし']
    for sid in ['S1A','S2A','S3B']:
        lines+=['## '+sid,'| 発話 | '+' | '.join(headers)+' |','|---|'+'---|'*4]
        page+=['<h2>'+sid+'</h2><table><tr>'+''.join('<th>'+s+'</th>' for s in headers)+'</tr>']
        for turn in range(3):
            values=[]
            for arm in ['A_v3','B_v4_gold','C_planner_v4','D_v4_no_plan']:
                rec=next(x for x in records if x['scenario']==sid and x['arm']==arm and x['turn']==turn)
                values.append(rec['accepted']['text'] if rec['accepted'] else '[hard failure: '+str(rec['hard_failure'])+']')
            lines.append('| T'+str(turn)+' | '+' | '.join(v.replace('|','\\|').replace('\n','<br>') for v in values)+' |')
            page.append('<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in values)+'</tr>')
        page.append('</table>')
    (out/'comparison.md').write_text('\n\n'.join(lines),encoding='utf8')
    (out/'comparison.html').write_text('\n'.join(page),encoding='utf8')

def legacy_diagnostics(models,out):
    abc=TALK/'memory_talk_lora_abc_v2/evaluation'
    references=[('memory_probe',abc/'memory_probe/results.json'),('memory_swap',abc/'memory_swap_abc_v2/short/results.json')]
    baseline=models.hashes['v3']
    for name,path in references:
        records=[]
        source=[r for r in read(path)['results'] if r.get('adapter_sha256')==baseline]
        assert len(source)==(8 if name=='memory_probe' else 20)
        for ref in source:
            outrow=models.generate('v4',ref.get('input_text',ref.get('decoded_input','')),ref.get('context_text',''),ref['seed'],
                raw_ids=ref['input_ids'],generation=ref['generation_config'],budget=1792,sentence_limit=0)
            assert outrow['input_ids']==ref['input_ids']
            records.append({'reference':ref,'v4':outrow,'comparison':'exact stored input IDs, seed and generation; old empty Memory preserved'})
            write(out/(name+'.json'),{'status':'running','source_sha256':sha(path),'records':records})
        write(out/(name+'.json'),{'status':'complete','source_sha256':sha(path),'records':records,'quality':'root reading pending'})
    path=abc/'t0_new/new_series.json';series=[]
    for ref in read(path)['series']:
        assert ref['adapter_sha256']==baseline
        torch=models.torch;torch.manual_seed(ref['seed']);torch.cuda.manual_seed_all(ref['seed'])
        history=[];calls=[]
        for index in range(ref['requested_calls']):
            row=models.generate('v4',ref['context_text'],ref['context_text'],ref['seed'],reseed=False,
                raw_ids=ref['initial_input_ids']+history,generation=ref['generation_config'],budget=ref['context_budget'],sentence_limit=0)
            if index==0:assert row['input_ids']==ref['initial_input_ids'][-ref['context_budget']:]
            calls.append(row);history+=row['output_ids']
            if row['stop_reason']=='eos':break
        series.append({'fixture_id':ref['fixture_id'],'stage':ref['stage'],'seed':ref['seed'],
            'requested_calls':ref['requested_calls'],'reference':ref,'v4_calls':calls,
            'protocol':'raw legacy continuation, identical initial tokens, seed once per series, generated-token history; not Plan runtime'})
        write(out/'t0.json',{'status':'running','source_sha256':sha(path),'series':series})
    write(out/'t0.json',{'status':'complete','source_sha256':sha(path),'series':series,'quality':'root reading pending'})

class Retriever:
    def __init__(self,out,bank):
        self.out=out;self.bank=bank;self.profile=read(TALK/'models/multilingual-e5-small-onnx/profile.json');self.index=0
        self.vectors=self.embed('passage',[m['body'] for m in bank])
    def embed(self,kind,texts):
        stem=self.out/('embed-'+str(self.index));self.index+=1
        req=stem.with_suffix('.request.json');res=stem.with_suffix('.response.json');write(req,{'kind':kind,'texts':texts})
        proc=subprocess.run([self.profile['python'],'-X','utf8','-B',str(TALK/'src/e5-embed.py'),str(req),str(res)],
            capture_output=True,text=True,encoding='utf8',timeout=180)
        stem.with_suffix('.stderr.log').write_text(proc.stderr,encoding='utf8')
        if proc.returncode:raise RuntimeError('E5 CPU exit '+str(proc.returncode)+': '+proc.stderr[-1000:])
        data=read(res)
        assert data['request_sha256']==sha(req) and data['model_profile_sha256']==sha(TALK/'models/multilingual-e5-small-onnx/profile.json')
        return data['vectors']
    def retrieve(self,recent):
        query=self.embed('query',[recent[-1500:]])[0]
        scored=sorted([(sum(a*b for a,b in zip(query,v)),m) for m,v in zip(self.bank,self.vectors)],key=lambda pair:pair[0],reverse=True)
        score,candidate=scored[0]
        return ([candidate] if score>=.6 else []),{'top_id':candidate['id'],'score':score,'threshold':.6,'count':1 if score>=.6 else 0}

def rollout(models,out):
    path=TALK/'memory_talk_lora_abc_v2/evaluation/memory_swap_abc_v2/audit/fixtures.json'
    f=read(path);bank=[{'id':c['case_id'],'body':c['memory']} for c in f['cases'] if c['condition'] in ['A','B']]
    directory=out/'rollout';directory.mkdir();retriever=Retriever(directory,bank)
    initial=next(c['context'] for c in f['cases'] if c['case_id']=='S2A')
    rt=Runtime(directory/'events.sqlite',initial);records=[];voiced_seconds=0;state={}
    started=time.perf_counter()
    for turn in range(36):
        if turn==6:
            rt.strong_event('comment',{'text':'その料理の失敗したところから聞きたいな。','source':'synthetic scheduled interrupt test'})
            state={'comment':'その料理の失敗したところから聞きたいな。'}
        candidate=rt.candidates;retrieval=None;plan_attempts=[]
        if rt.needs_plan():
            candidate,retrieval=retriever.retrieve(rt.recent())
            inp={'recent':rt.recent(),'current_state':state,'memory_candidates':candidate,'previous_plan':rt.plan}
            plan,plan_attempts=obtain_plan(models.plan,inp)
            if plan:rt.set_plan(plan,candidate)
        recent=rt.recent().rstrip('\n');plan=rt.plan if rt.remaining else None
        prompt=talk_prompt(recent,candidate,plan) if plan else fallback_prompt(recent)
        accepted,attempts,failure=obtain_speech(lambda retry:models.generate('v4',prompt,recent,SEED+turn+retry*10000))
        played=0
        if accepted:
            # One partial cancellation, then future inputs contain only this prefix.
            played=len(accepted['text'])//2 if turn==9 else len(accepted['text'])
            rt.commit_playback(accepted['text'],played);voiced_seconds+=played/4.5
        else:rt.plan=None;rt.remaining=0
        records.append({'turn':turn,'retrieval':retrieval,'candidate':candidate,'plan':plan,'planner_attempts':plan_attempts,
            'speech_attempts':attempts,'accepted':accepted,'hard_failure':failure,'played_chars':played,
            'recent_after_playback':rt.recent(),'plan_remaining':rt.remaining})
        write(directory/'results.json',{'status':'running','records':records,'modeled_speech_seconds':voiced_seconds})
        if voiced_seconds>=360 and turn>=10:break
    count=rt.db.execute("SELECT COUNT(*) FROM events WHERE kind='played_speech'").fetchone()[0]
    assert count==rt.db.execute('SELECT COUNT(*) FROM memory').fetchone()[0]
    assert rt.db.execute("SELECT COUNT(*) FROM events WHERE kind IN ('plan','generated_speech')").fetchone()[0]==0
    for body,event_id in rt.db.execute('SELECT memory.body,event_id FROM memory'):
        m=json.loads(body);event=json.loads(rt.db.execute('SELECT body FROM events WHERE id=?',(event_id,)).fetchone()[0])
        assert m['played_text']==event['played_text'] and m['source_event_id']==event_id
    rt.close()
    write(directory/'results.json',{'status':'complete','records':records,'wall_seconds':time.perf_counter()-started,
        'modeled_speech_seconds':voiced_seconds,'modeled_duration_target_met':voiced_seconds>=300,
        'playback':'simulation only; no OBS/TTS used, 4.5 characters per second estimated duration',
        'speech_memory_kind':'record of words played, not verified factual claims','G5_invariants':'pass',
        'real_5_to_10_minute_audio_acceptance':'not performed','quality':'root reading pending'})

def main():
    p=argparse.ArgumentParser();p.add_argument('--planner-only',action='store_true');args=p.parse_args()
    out=RUN/('planner_evaluation' if args.planner_only else 'evaluation');out.mkdir(exist_ok=False)
    try:
        with Lock(ROOT/'gpu.lock'):
            verify_dataset();models=Models(args.planner_only)
            if args.planner_only:planner_test(models,out)
            else:
                main_comparison(models,out);legacy_diagnostics(models,out);rollout(models,out)
            write(out/'manifest.json',{'status':'complete','finished':now(),'pid':os.getpid(),'adapter_hashes':models.hashes,
                'scope':'Planner heldout test' if args.planner_only else 'A/B/C/D, exact-token legacy MemoryProbe/Memory swap/T0, simulated runtime',
                'quality':'root semantic review pending; no formal quality gate is auto-passed'})
    except Exception as exc:
        write(out/'manifest.json',{'status':'failed','finished':now(),'error':str(exc),'traceback':traceback.format_exc()});raise

if __name__=='__main__':main()
