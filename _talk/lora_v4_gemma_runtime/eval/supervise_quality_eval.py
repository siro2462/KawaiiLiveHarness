"""One hidden worker; native exit receipt and no automatic retry."""
import argparse
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from quality_eval import bootstrap, read, write, verify_protocol


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--runtime-root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    root = bootstrap(args.runtime_root); out = args.out.resolve()
    assert out.is_relative_to(root / 'runs')
    assert read(out / 'cpu_preflight.json')['status'] == 'pass'
    assert not (out / 'supervisor.json').exists()
    verify_protocol(out)
    from supervise_real_evaluation import observation, observer_type
    state = {'status': 'running', **observation(os.getpid()), 'exit_code': None,
             'automatic_restart': False, 'started_unix': time.time()}
    write(out / 'supervisor.json', state)
    try:
        env = dict(os.environ)
        env['PYTHONPATH'] = os.pathsep.join([str(root), str(root.parent / 'lora_v4_multibase'), str(Path(__file__).parent)])
        env['PYTHONIOENCODING'] = 'utf-8'; env['PYTHONUNBUFFERED'] = '1'
        cmd = [sys.executable, '-X', 'utf8', '-u', str(root.parent / 'lora_v4_multibase/child_guard.py'),
               '--receipt', str(out / 'python_outcome.json'), str(Path(__file__).with_name('quality_eval.py')),
               'run', '--runtime-root', str(root), '--out', str(out)]
        with (out / 'inference.stdout.log').open('x', encoding='utf8') as stdout, (out / 'inference.stderr.log').open('x', encoding='utf8') as stderr:
            child = subprocess.Popen(cmd, cwd=root, env=env, stdout=stdout, stderr=stderr,
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            state['launcher_pid'] = child.pid; write(out / 'supervisor.json', state)
            native = None
            while True:
                if native is None and (out / 'manifest.json').exists():
                    manifest = read(out / 'manifest.json'); worker = observation(manifest['pid'])
                    assert worker['created_unix'] == manifest['create_time']
                    assert any('child_guard.py' in a for a in worker['command_line'])
                    assert any('quality_eval.py' in a for a in worker['command_line'])
                    native = observer_type()(worker['pid'], worker)
                    write(out / 'launch_observation.json', {'supervisor': observation(os.getpid()),
                          'worker': worker, 'launcher': observation(child.pid)})
                if native is not None and native.poll() is not None:
                    state['native_exit_code'] = native.returncode; break
                if child.poll() is not None:
                    state['native_exit_code'] = native.poll() if native else None; break
                time.sleep(10)
            state['launcher_exit_code'] = child.wait(timeout=60)
        receipt = read(out / 'python_outcome.json') if (out / 'python_outcome.json').exists() else None
        manifest = read(out / 'manifest.json') if (out / 'manifest.json').exists() else {}
        success = (state.get('native_exit_code') == 0 and state['launcher_exit_code'] == 0 and
                   receipt and receipt['exit_code'] == 0 and manifest.get('status') == 'outputs_ready')
        state.update(status='complete' if success else 'failed', exit_code=0 if success else 1,
                     python_outcome=receipt, finished_unix=time.time())
        write(out / 'supervisor.json', state)
        from build_quality_report import build
        build(out)
        if not success:
            raise SystemExit(1)
    except BaseException as exc:
        if not isinstance(exc, SystemExit):
            state.update(status='failed', exit_code=1, error=str(exc), traceback=traceback.format_exc())
            write(out / 'supervisor.json', state)
        raise


if __name__ == '__main__':
    main()
