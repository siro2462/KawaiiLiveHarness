"""Record Python outcome and bypass native interpreter teardown after completion/error."""
import argparse
import os
import runpy
import sys
import traceback
from atomic_state import write

def main():
    p=argparse.ArgumentParser();p.add_argument('--receipt',required=True);p.add_argument('script');p.add_argument('args',nargs=argparse.REMAINDER)
    a=p.parse_args();sys.argv=[a.script,*a.args];code=0;error=None
    try:
        runpy.run_path(a.script,run_name='__main__')
    except SystemExit as exc:
        code=exc.code if isinstance(exc.code,int) else int(exc.code is not None)
    except BaseException:
        code=1;error=traceback.format_exc();sys.stderr.write(error)
    try:
        write(a.receipt,{'pid':os.getpid(),'exit_code':code,'python_error':error,
            'exit_scope':'observed Python outcome; immediate process exit after stream flush',
            'script':a.script,'args':a.args})
        sys.stdout.flush();sys.stderr.flush()
    except BaseException:
        code=1
    os._exit(code)

if __name__=='__main__':main()
