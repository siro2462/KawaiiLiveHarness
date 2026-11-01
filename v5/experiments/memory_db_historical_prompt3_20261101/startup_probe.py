from common import *
import run_cpu,gpu_worker,observe_cpu
assert callable(run_cpu.main) and callable(gpu_worker.main) and callable(observe_cpu.main)
verify()
write(OUT/'startup_probe.json',dict(status='pass',model_calls=0,imports=['run_cpu','gpu_worker','observe_cpu'],pid=os.getpid(),checked_jst=now()))
