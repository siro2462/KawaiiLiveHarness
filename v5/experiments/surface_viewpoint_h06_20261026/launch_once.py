from common import *
import subprocess,psutil

def main():
 cfg=verify()
 assert not (OUT/'launch.json').exists() and not (OUT/'controller.json').exists() and not (OUT/'inference').exists(), 'Already launched'
 assert not list((OUT/'requests').glob('R*.json')), 'Request already exists'
 pre=read(OUT/'cpu_preflight.json');dep=read(OUT/'dependency_probe.json');start=read(OUT/'startup.python_outcome.json')
 assert pre['status']==dep['status']==read(OUT/'startup_probe.json')['status']=='pass' and start['exit_code']==0
 assert pre['new_model_calls']==dep['model_calls']==0
 assert sha(OUT/'prepared_inputs.json')==pre['prepared_inputs_sha256']
 for lock in [MULTI/'gpu.lock',TALK/'lora_v4_planner_talk/gpu.lock']:
  assert not lock.exists(), 'Existing GPU lock: '+str(lock)
 for p in psutil.process_iter(['pid','cmdline']):
  try:
   if p.pid!=os.getpid() and any(str(x).endswith(('gpu_worker.py','run_cpu.py')) for x in (p.info['cmdline'] or [])):
    raise RuntimeError('Existing runtime process '+str(p.pid))
  except(psutil.NoSuchProcess,psutil.AccessDenied):pass
 env=dict(os.environ,ZIP_INCREMENTAL_RUN=str(OUT),PYTHONPATH=os.pathsep.join(map(str,[HERE,BETA,MULTI,GEMMA])),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1')
 command=[cfg['gpu_python'],'-X','utf8','-B','-u',str(MULTI/'child_guard.py'),'--receipt',str(OUT/'controller.python_outcome.json'),str(HERE/'run_cpu.py')]
 with (OUT/'controller.stdout.log').open('x',encoding='utf-8') as so,(OUT/'controller.stderr.log').open('x',encoding='utf-8') as se:
  child=subprocess.Popen(command,cwd=BETA,env=env,stdout=so,stderr=se,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  launch=dict(**obs(child.pid),run=str(OUT),automation_id='h06',background_hidden=True,agent_waits_for_generation=False,environment={k:env[k] for k in ['ZIP_INCREMENTAL_RUN','PYTHONPATH','HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE','PYTHONIOENCODING','PYTHONUNBUFFERED']},cpu_preflight_sha256=sha(OUT/'cpu_preflight.json'),protocol_sha256=sha(OUT/'protocol.json'),setup_validation_sha256=sha(OUT/'setup_validation.json'),started_jst=now())
  write(OUT/'launch.json',launch)
 print(json.dumps(dict(status='launched',pid=child.pid,created_unix=launch['created_unix'],run=str(OUT),automation_id='h06',new_surface_max=2,waiting=False),ensure_ascii=False))
if __name__=='__main__':main()
