"""Owned process groups with bounded stdin/output and cancellation for P03 tools."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def run_worker(values,seconds,*,cancelled=lambda:False,browser_path=None):
    root=Path(__file__).resolve().parents[3]
    browser_path=browser_path or root/'.tools'/'playwright'/'1.65.2'
    env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'LANG':'C.UTF-8','PYTHONPATH':str(root/'src'),
         'PYTHONNOUSERSITE':'1','PYTHONPYCACHEPREFIX':os.environ.get('PYTHONPYCACHEPREFIX','/tmp/xti-brand-worker-pycache'),
         'PLAYWRIGHT_BROWSERS_PATH':str(browser_path)}
    # Windows is not currently an advertised managed process platform.
    if os.name!='posix':return {'status':'unsupported_process_platform'}
    process=None
    payload=json.dumps(values,ensure_ascii=True).encode()
    if len(payload)>18*1024*1024:return {'status':'input_too_large'}
    deadline=time.monotonic()+min(40,max(.1,seconds))
    try:
        process=subprocess.Popen([sys.executable,'-m','xti.adapters.brand_protection_worker'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True,env=env)
        first=True
        while True:
            if cancelled():return {'status':'cancelled'}
            remaining=deadline-time.monotonic()
            if remaining<=0:return {'status':'timeout'}
            try:
                output,_=process.communicate(input=payload if first else None,timeout=min(.2,remaining))
                break
            except subprocess.TimeoutExpired:first=False
        if len(output)>5*1024*1024:return {'status':'output_too_large'}
        value=json.loads(output)
        return value if isinstance(value,dict) else {'status':'invalid_response'}
    except (OSError,ValueError,RecursionError):return {'status':'tool_unavailable'}
    finally:
        if process is not None:
            # Chromium descendants belong to this invocation even after its parent exits.
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.wait(timeout=10)
