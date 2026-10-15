"""CPU-only freeze/admission for the one planned real Gemma evaluation suite."""
import argparse
import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime,timezone,timedelta
from evaluation_cases import heldout_cases,challenge_cases
from evaluation_support import ROOT,TALK,read,sha,embedder_type
from fact_gate import check_text


def write(path,data):Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    out=parser.parse_args().out.resolve();assert out.is_relative_to(ROOT/'runs') and not out.exists()
    out.mkdir(parents=True);cpu=out/'cpu';cpu.mkdir()
    frozen=read(ROOT/'audit/review_20261015/review_code_hashes.json')
    core_names=['alpha_contract.py','context_runtime.py','fact_gate.py','generation_errors.py','inference_runtime.py',
                'inference_v5.py','original_runtime.py','planner_policy.py','runtime_engine.py','runtime_state.py','schema_constraints.py']
    assert all(sha(ROOT/name)==frozen[name] for name in core_names),'Functional core changed after review'
    test=subprocess.run([sys.executable,'-X','utf8','-m','unittest','discover','-s',str(ROOT),'-p','test_*.py','-v'],
                        cwd=ROOT,capture_output=True,text=True,encoding='utf8')
    (cpu/'tests.log').write_text(test.stdout+test.stderr,encoding='utf8')
    assert test.returncode==0,test.stdout+test.stderr
    import psutil,time
    from supervise_real_evaluation import observer_type,observation
    probe=cpu/'native_exit_smoke.py';identity=cpu/'native_exit_identity.json'
    probe.write_text('import os,time,json,sys\nfrom pathlib import Path\nimport psutil\n'
        'Path(sys.argv[1]).write_text(json.dumps({"pid":os.getpid()}),encoding="utf8")\n'
        'time.sleep(2)\nraise SystemExit(7)\n',encoding='utf8')
    child=subprocess.Popen([sys.executable,'-X','utf8',str(probe),str(identity)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    deadline=time.monotonic()+10
    while not identity.exists() and child.poll() is None and time.monotonic()<deadline:time.sleep(.05)
    actual_pid=read(identity)['pid'];observed=observer_type()(actual_pid,observation(actual_pid))
    native_code=observed.wait(timeout=10);launcher_code=child.wait(timeout=10)
    assert native_code==launcher_code==7
    write(cpu/'native_exit_observation.json',{'scope':'independent CPU smoke, expected exit 7','native_pid':actual_pid,
          'native_exit_code':native_code,'launcher_exit_code':launcher_code,'status':'pass','source_sha256':sha(probe)})
    old=TALK/'lora_v4_multibase';selection=read(old/'model_selection.json')['primary_candidate']
    assert selection['key']=='gemma4_26b_a4b'
    adapter_hashes={}
    sources=[old/'model_selection.json',TALK/'lora_v4_runtime_bc/runs/bc_consistency_10m_20261008/protocol.json',
             TALK/'lora_v4_runtime_bc/runs/bc_consistency_10m_20261008/memory_bank.sqlite',
             TALK/'memory_talk_lora_abc_v2/evaluation/memory_swap_abc_v2/audit/fixtures.json',
             old/'runs/offload_20261009/gemma4_26b_a4b/runtime_bc_10m/BC/io.jsonl',
             old/'runs/offload_20261009/gemma4_26b_a4b/evaluation/comparison.json',
             old/'runs/offload_20261009/gemma4_26b_a4b/evaluation/memory_swap.json']
    for name,role in [('planner','planner'),('talk_v3','v3'),('talk_v4','v4')]:
        item=selection['adapters'][name];path=Path(item['directory'])/'adapter_model.safetensors'
        assert sha(path)==item['sha256'];adapter_hashes[role]=item['sha256']
        sources.extend(p for p in path.parent.iterdir() if p.is_file())
    base=Path(selection['base_weights']);sources.extend(base/p for p in ['config.json','generation_config.json','tokenizer.json','tokenizer_config.json'])
    profile=TALK/'models/multilingual-e5-small-onnx/profile.json';sources.append(profile)
    for item in read(profile)['files']:
        path=profile.parent/item['local'];assert sha(path)==item['sha256'];sources.append(path)
    old_cfg=read(sources[1]);bank=old_cfg['memory_bank']
    fixture=read(TALK/'memory_talk_lora_abc_v2/evaluation/memory_swap_abc_v2/audit/fixtures.json')
    write(out/'original_fixtures.json',fixture)
    swap=[{'id':c['case_id'],'condition':c['condition'],'recent':c['context'],
           'candidate':[{'id':c['memory_id'],'body':c['memory']}] if c['memory_id'] else [],
           'expected_use_memory':c['condition'] in {'A','B'},'source_fixture':c} for c in fixture['cases']]
    assert len(swap)==20
    write(out/'heldout_cases.json',heldout_cases());write(out/'unused_challenge_cases.json',challenge_cases());write(out/'swap_cases.json',swap)
    tree=ast.parse((TALK/'lora_v4_planner_talk/evaluate.py').read_text(encoding='utf8'))
    gold=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='GOLD' for t in n.targets)))
    write(out/'gold_plans.json',gold)
    shutil.copy2(TALK/'lora_v4_runtime_bc/runs/bc_consistency_10m_20261008/memory_bank.sqlite',out/'memory_bank.sqlite')
    worker=embedder_type()(cpu)
    try:
        request=read(TALK/'lora_v4_runtime_ab/runs/runtime_30m_20261007/embedding_parity.request.json')
        expected=read(TALK/'lora_v4_runtime_ab/runs/runtime_30m_20261007/embedding_parity.response.json')['vectors']
        actual=worker.embed(request['kind'],request['texts'])
        delta=max(abs(a-b) for va,vb in zip(actual,expected) for a,b in zip(va,vb))
        assert len(actual)==len(expected)==11 and delta==0,delta
        embedding_audit={'status':'pass','vectors':len(actual),'max_absolute_difference':delta,'ready':worker.ready}
    finally:worker.close()
    embedding_audit['worker_exit_code']=worker.proc.returncode;assert worker.proc.returncode==0
    write(cpu/'embedding_parity.json',embedding_audit)
    challenge=[{**c,'rule_result':check_text(c['text'],c['candidate'])} for c in challenge_cases()]
    write(cpu/'unused_challenge_observation.json',{'scope':'heldout authored CPU cases; results do not modify rules and are not a launch quality gate','records':challenge})
    codes=list(ROOT.glob('*.py'))
    for directory in ['lora_v4_multibase','lora_v4_planner_talk','lora_v4_runtime_ab']:
        codes.extend((TALK/directory).glob('*.py'))
    code_hashes={str(p.resolve()):sha(p) for p in codes}
    executed=out/'executed_code';executed.mkdir()
    for index,path in enumerate(codes):shutil.copy2(path,executed/f'{index:03d}_{path.parent.name}_{path.name}')
    dependencies={str(p.resolve()):sha(p) for directory in [ROOT/'dependencies',ROOT/'morphology_dependencies']
                  for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    for p in out.glob('*.json'):sources.append(p)
    sources.append(out/'memory_bank.sqlite')
    protocol={'created_at':datetime.now(timezone(timedelta(hours=9))).isoformat(),'model':'gemma4_26b_a4b',
              'adapter_hashes':adapter_hashes,'seed':20260925,'additional_Talk_seeds':[20260926,20260927],
              'initial':old_cfg['initial'],'memory_bank':bank,'E5_profile_sha256':sha(profile),
              'generation':{'planner_max_tokens':192,'planner_sampling':'greedy','Talk_max_tokens':96,'temperature':.8,'top_p':.95,'top_k':50,'repetition_penalty':1.05,'budget':928},
              'stages':['sanity3','fixed36','selection18_REL_NONE_IRREL','MemorySwap20_paired_contexts','heldout18_paired_contexts','long2700','two_additional_Talk_seeds_H01_triplet'],
              'long_target':{'chars':2700,'characters_per_second':4.5,'modeled_seconds':600,'max_turns':1200,'consecutive_zero_limit':30,'actual_TTS':False},
              'comparison':'saved old Gemma BC 2700 chars and old fixed/MemorySwap; no baseline GPU rerun',
              'limits':['1 seed long run','additional seeds only H01 REL/NONE/IRREL single-shot paired prompts','authored synthetic Memory','root review pending; user labels=0','CPU detector not semantic verifier','paired context policy can change Plan factual admission','Planner direction and Talk assertions must be reviewed separately'],
              'production_Runtime_core_changed':False,'frozen_core_sha256':{name:frozen[name] for name in core_names},
              'evaluation_context_ablation':True,'rule_tuning':False,'training':False,'automatic_restart':False,'same_configuration_quality_rerun':False,
              'code_hashes':code_hashes,'source_hashes':{str(p.resolve()):sha(p) for p in sources},'dependency_hashes':dependencies}
    write(out/'protocol.json',protocol)
    write(out/'cpu_preflight.json',{'status':'pass','test_exit_code':0,'test_log':str(cpu/'tests.log'),'embedding':embedding_audit,
          'functional_core_frozen':True,'fresh_cases_frozen_before_model_outputs':True,'GPU_generation_calls':0})
    print(json.dumps({'out':str(out),'status':'prepared','code_files':len(code_hashes),'sources':len(protocol['source_hashes']),'E5_max_difference':delta},ensure_ascii=False))


if __name__=='__main__':main()
