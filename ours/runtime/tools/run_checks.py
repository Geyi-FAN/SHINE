"""Offline regression entry. All cloud/model/robot inference is prohibited."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

W=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(W/'runtime'),str(W/'runtime/g2')]


def main():
    started=time.time()
    (W/'reports').mkdir(exist_ok=True)
    from bootstrap import configure
    with tempfile.TemporaryDirectory() as d:configure(d,0)
    # Allow local mock HTTP servers; forbid all non-loopback networking in this
    # test process, including accidental local inference-pool requests.
    import socket
    original_connect=socket.socket.connect
    def connect(sock,address):
        if isinstance(address,tuple) and (address[0] not in ('127.0.0.1','localhost') or address[1] in (18684,18084,18184,8787,8801)):
            raise RuntimeError('Offline test network guard: '+str(address))
        return original_connect(sock,address)
    socket.socket.connect=connect
    syntax=[]
    for base in ['runtime/unified','runtime/common_fixes','voice/dist','scripts']:
        for p in (W/base).rglob('*.py'):
            ast.parse(p.read_text());syntax.append(str(p.relative_to(W)))
    suite=unittest.defaultTestLoader.discover(str(W/'tests/python'))
    log=W/'reports/python_core_regression.log'
    with log.open('w') as f: result=unittest.TextTestRunner(stream=f,verbosity=2).run(suite)
    python=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),passed=result.wasSuccessful(),models_called=0,robot_actions=0)
    import hashlib
    modules=[]
    for name,module in sorted(sys.modules.items()):
        file=getattr(module,'__file__',None)
        if not file:continue
        path=Path(file).resolve()
        if path.is_file() and str(path).startswith('/mnt/') and W not in path.parents and 'site-packages' not in path.parts:
            modules.append(dict(module=name,path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (W/'reports/IMPORT_BOUNDARY.json').write_text(json.dumps(dict(external_modules=modules),indent=2))
    (W/'reports/PYTHON_CORE_TESTS.json').write_text(json.dumps(python,indent=2))
    node=json.loads((W/'config/model.json').read_text())['node']
    tests=sorted(str(p) for p in (W/'tests/node').glob('*.mjs'))
    with (W/'reports/node_regression.log').open('w') as f:
        r=subprocess.run([node,'--test',*tests],cwd=W,stdout=f,stderr=subprocess.STDOUT,timeout=60)
    import_check=subprocess.run([node,'--input-type=module','-e',"await import('./voice/dist/orchestrator/live-session.js'); console.log('LiveSession import passed')"],cwd=W,capture_output=True,text=True,timeout=20)
    report=dict(passed=python['passed'] and r.returncode==0 and import_check.returncode==0,python=python,node_passed=r.returncode==0,voice_import_passed=import_check.returncode==0,voice_import_output=import_check.stdout+import_check.stderr,syntax_files=len(syntax),elapsed_seconds=time.time()-started,models_called=0,robot_actions=0,real_audio_cases=0)
    (W/'reports/OFFLINE_VALIDATION.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))
    return 0 if report['passed'] else 1

if __name__=='__main__':sys.exit(main())
