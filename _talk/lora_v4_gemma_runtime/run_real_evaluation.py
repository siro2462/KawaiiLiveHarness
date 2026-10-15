"""One frozen Gemma evaluation; no training, model search, or automatic reruns."""
import argparse
import copy
import json
import os
import sqlite3
import sys
import time
import traceback
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'lora_v4_multibase'
sys.path.insert(0,str(OLD))
from atomic_state import write
from multibase_common import Lock, now
sys.path.insert(0,str(ROOT))
from evaluation_support import read,sha,embedder_type,LoggedModels
from context_runtime import planner_input,speech_context,shrink_recent_context
from fact_gate import check_plan,check_text
from planner_policy import obtain_plan
from generation_errors import audit_error,classify
from runtime_engine import Arm,SHORT_FILLER,SEED
from original_runtime import Runtime,hard_failure,normal,detect


def diagnostic_plan(models,case):
    candidate=case['candidate'];memory=candidate[0] if candidate else None
    inp=planner_input(case['recent'],candidate,None,memory,'fixed_diagnostic')
    ids=[m['id'] for m in candidate]
    plan,attempts=obtain_plan(lambda prompt,recent,retry:models.planner(prompt,recent,ids,retry),inp)
    if any(a.get('generation_error',{}).get('action')=='halt_no_further_generation' for a in attempts):
        raise RuntimeError('Model execution failure in fixed Planner diagnostic; no subsequent GPU calls')
    for attempt in attempts:
        attempt['evaluation_role']='Planner direction; human review distinguishes directions from utterance assertions'
    first=next((a for a in attempts if a.get('schema_valid')),None)
    first_plan=json.loads(first['text']) if first else None
    return {'id':case['id'],'case':case,'input':inp,'plan':plan,'attempts':attempts,
            'schema_success':plan is not None,
            'first_schema_valid_selection_correct':bool(first_plan is not None and first_plan['use_memory']==case.get('expected_use_memory') and
                (not first_plan['use_memory'] or first_plan['memory_id'] in ids)) if 'expected_use_memory' in case else None,
            'selection_correct':bool(plan is not None and plan['use_memory']==case['expected_use_memory'] and
                (not plan['use_memory'] or plan['memory_id'] in ids)) if 'expected_use_memory' in case else None,
            'semantic_quality':'root review pending; schema and selection are separate'}


def single_speech(models,embed,case,raw_plan,policy,seed,directory):
    """One paired context diagnostic using frozen v5 builders/checks, not a new Runtime policy."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    if policy not in {'CURRENT_ALWAYS','DECLARED_ONLY'}:raise ValueError('Unknown context diagnostic')
    memory=copy.deepcopy(case['candidate'][0]) if case['candidate'] and (
        policy=='CURRENT_ALWAYS' or raw_plan is not None and raw_plan['use_memory']) else None
    refs=[memory] if memory else []
    validation=check_plan(raw_plan,refs) if raw_plan else None
    plan=copy.deepcopy(raw_plan) if validation and validation['accepted'] else None
    context=speech_context(case['recent'],[],memory,plan)
    expected=[context['grounding']] if context['grounding'] else []
    if plan:assert validation['source_references']==expected
    rt=Runtime(directory/'events.sqlite',case['recent']);attempts=[];accepted=None;retry_note='';failure=None
    try:
        for retry in range(2):
            try:record=models.talk(context,seed+retry*10000,retry_note)
            except Exception as exc:
                error=audit_error(exc,retry_note+context['prompt'],context['recent'],[m['id'] for m in refs])
                attempts.append({'text':None,'generation_error':error,'playback_committed':False})
                write(directory/'result.json',{'status':'generation_error','id':case['id'],'attempts':attempts})
                if classify(exc) is None or not error['retry'] or retry==1:raise
                if error['action']=='shrink_recent_only':context=shrink_recent_context(context)
                continue
            reason=hard_failure(record['text'])
            if reason=='too_short' and normal(record['text']) in SHORT_FILLER:reason=None
            vector=embed.embed('passage',[record['text']])[0]
            repetition=detect(record['text'],vector,[],reason)
            facts=check_text(record['text'],refs)
            assert facts['source_references']==expected
            record.update(attempt=retry,plan_used=copy.deepcopy(plan),hard_failure=reason,
                memory_consistency=facts,loop=repetition,playback_committed=False,
                factual_source_bindings=copy.deepcopy(expected),evaluation_role='Talk actual utterance')
            attempts.append(record)
            if repetition['loop']:failure='repetition';break
            if reason:failure=reason;retry_note='【発話形式】\n説明や見出しではなく、雑談の発話だけを続ける。\n\n';continue
            if not facts['accepted']:
                failure='memory_consistency';plan=None;context=speech_context(case['recent'],[],memory,None)
                retry_note='【出来事の扱い】\n'+facts['feedback']+'\n\n';continue
            accepted=record;failure=None;break
        played=accepted['text'] if accepted else ''
        if accepted:
            accepted['played_event_id']=rt.commit_playback(played,len(played));accepted['playback_committed']=True
        events=[json.loads(body)['played_text'] for body, in rt.db.execute("SELECT body FROM events WHERE kind='played_speech' ORDER BY id")]
        assert events==([played] if played else [])
        assert len(events)==rt.db.execute('SELECT COUNT(*) FROM memory').fetchone()[0]
        assert all(json.loads(body)['facts_verified'] is False for body, in rt.db.execute('SELECT body FROM memory'))
        result={'status':'complete','id':case['id'],'case':case,'context_policy':policy,'seed':seed,
                'raw_Planner_plan':raw_plan,'plan_validation_against_actual_Talk_sources':validation,
                'plan_adopted_for_first_attempt':raw_plan if validation and validation['accepted'] else None,
                'speech_context_after_retry':context,'speech_attempts':attempts,'played_text':played,
                'played_chars':len(played),'failure':failure,'actual_TTS':False,'Event_Store_integrity':'pass',
                'comparison_limit':'same cached Planner output; policy can change fact admission as well as Talk context'}
        write(directory/'result.json',result)
        return result
    finally:rt.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    out=parser.parse_args().out.resolve();assert out.is_relative_to(ROOT/'runs')
    assert not (out/'manifest.json').exists(),'Never duplicate or restart an admitted evaluation'
    cfg=read(out/'protocol.json');assert read(out/'cpu_preflight.json')['status']=='pass'
    for group in ['code_hashes','source_hashes','dependency_hashes']:
        for path,digest in cfg[group].items():assert sha(path)==digest,'Admitted identity changed: '+path
    import psutil
    state={'status':'running','phase':'load_models','pid':os.getpid(),'parent_pid':os.getppid(),
           'create_time':psutil.Process().create_time(),'started':now(),'quality_pass':False,
           'completed_stages':[],'model':'gemma4_26b_a4b','training_calls':0}
    write(out/'manifest.json',state)
    models=None;embedding=None
    def progress(stage,case=None,**extra):
        state.update(phase=stage,current_case=case,updated=now(),**extra)
        if models:state['actual_generation_counts']=copy.deepcopy(models.counts);models.stage=stage;models.case=case
        write(out/'manifest.json',state)
    def completed(stage):
        state['completed_stages'].append(stage);progress(stage+'_complete')
    def run_arm(stage,sid,name,initial,bank,turns=None,target=2700,gold=None):
        progress(stage,sid+'/'+name)
        arm=Arm(name,out/stage/sid/name,initial,bank,write,
                fixed_id=sid if sid in {m['id'] for m in bank} and stage!='long2700' else None,gold=gold,target=target)
        try:
            while arm.status=='running' and (turns is None or arm.turn<turns):
                rec=arm.step(models,embedding,bank,embedding.embed('passage',[m['body'] for m in bank]))
                progress(stage,sid+'/'+name,arm_state=arm.state())
                if rec['generation_halt']:raise RuntimeError('Runtime halted generation; no GPU restart')
            if arm.status not in {'running','complete','stalled_zero_playback','turn_limit_unmet'}:
                raise RuntimeError('Unexpected Runtime state: '+arm.status)
            if stage=='sanity' and not arm.played:raise RuntimeError('Sanity produced no playback; preserve outputs and do not tune or retry')
        finally:arm.close(diagnostic=turns is not None)
        return copy.deepcopy(arm.state())
    try:
        with Lock(OLD/'gpu.lock'),Lock(ROOT.parent/'lora_v4_planner_talk/gpu.lock'):
            from inference_runtime import RuntimeModels
            native=RuntimeModels()
            for role,digest in cfg['adapter_hashes'].items():assert native.hashes[role]==digest
            models=LoggedModels(native,out,write)
            embedding=embedder_type()(out)
            assert embedding.ready['profile_sha256']==cfg['E5_profile_sha256']
            bank=cfg['memory_bank'];fixtures={c['case_id']:c for c in read(out/'original_fixtures.json')['cases']}
            gold=read(out/'gold_plans.json')
            run_arm('sanity','S2B','GUARDED',cfg['initial'],bank,turns=3);completed('sanity')
            fixed=[]
            for sid in ['S1A','S2A','S3B']:
                for name in ['CONTEXT','GOLD','GUARDED','PLANLESS']:
                    fixed.append(run_arm('fixed36',sid,name,fixtures[sid]['context'],bank,turns=3,gold=gold[sid] if name=='GOLD' else None))
            write(out/'fixed36_summary.json',fixed);completed('fixed36')
            selection=[]
            for case in read(out/'heldout_cases.json'):
                progress('selection18',case['id']);selection.append(diagnostic_plan(models,case))
                write(out/'selection18.json',{'status':'running','records':selection})
            write(out/'selection18.json',{'status':'complete','records':selection});completed('selection18')
            swap=[]
            for case in read(out/'swap_cases.json'):
                progress('memory_swap',case['id']);planned=diagnostic_plan(models,case)
                for policy in ['CURRENT_ALWAYS','DECLARED_ONLY']:
                    progress('memory_swap',case['id']+'/'+policy)
                    row=single_speech(models,embedding,case,planned['plan'],policy,SEED,out/'memory_swap'/case['id']/policy)
                    row['planner_diagnostic']=planned;swap.append(row)
                    write(out/'memory_swap.json',{'status':'running','records':swap})
            write(out/'memory_swap.json',{'status':'complete','records':swap});completed('memory_swap')
            fresh=[]
            for planned in selection:
                for policy in ['CURRENT_ALWAYS','DECLARED_ONLY']:
                    case=planned['case'];progress('heldout_speech',case['id']+'/'+policy)
                    fresh.append(single_speech(models,embedding,case,planned['plan'],policy,SEED,out/'heldout_speech'/case['id']/policy))
                    write(out/'heldout_speech.json',{'status':'running','records':fresh})
            write(out/'heldout_speech.json',{'status':'complete','records':fresh});completed('heldout_speech')
            long=run_arm('long2700','retrieval','GUARDED',cfg['initial'],bank)
            write(out/'long2700_summary.json',long);completed('long2700')
            seeds=[]
            for seed in cfg['additional_Talk_seeds']:
                for planned in selection[:3]:
                    for policy in ['CURRENT_ALWAYS','DECLARED_ONLY']:
                        case=planned['case'];progress('seed_check',str(seed)+'/'+case['id']+'/'+policy)
                        seeds.append(single_speech(models,embedding,case,planned['plan'],policy,seed,out/'seed_check'/str(seed)/case['id']/policy))
                        write(out/'seed_check.json',{'status':'running','records':seeds})
            write(out/'seed_check.json',{'status':'complete','records':seeds});completed('seed_check')
            state.update(status='outputs_ready',phase='root_review_pending',finished=now(),adapter_hashes=models.hashes)
            write(out/'manifest.json',state)
    except BaseException as exc:
        state.update(status='failed',error=str(exc),traceback=traceback.format_exc(),finished=now())
        write(out/'manifest.json',state);raise
    finally:
        if models:models.close()
        if embedding:embedding.close()


if __name__=='__main__':main()
