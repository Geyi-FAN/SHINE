"""Restore the exact original shallow Git identity after cloning SHINE.

No external services or credentials are used. Run before the original freeze
verifier. Upstream parent history is not included. Never run on an existing
runtime Git repository with local changes.
"""
from pathlib import Path
import subprocess,json,shutil
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'ours/runtime';A=ROOT/'archive/ours930_20261114'
def git(*args,input=None):return subprocess.check_output(['git','-C',str(W)]+list(args),input=input).decode().strip()
c=json.loads((A/'SOURCE_GIT.json').read_text())
assert not(W/'.git').exists(),'Existing runtime repository is preserved; no overwrite'
git('init','-q');git('add','.');actual=git('write-tree')
assert actual==c['tree'],'Source tree mismatch; do not claim exact original identity'
restored=git('hash-object','-t','commit','-w','--stdin',input=(A/'SOURCE_COMMIT.raw').read_bytes());assert restored==c['commit']
git('update-ref','refs/heads/frozen-runtime',restored);git('symbolic-ref','HEAD','refs/heads/frozen-runtime')
(W/'.git/shallow').write_text(restored+'\n');shutil.copy2(A/'RUNTIME_FREEZE.json',W/'FREEZE.json')
assert not git('status','--porcelain'),'Restored snapshot contains unexpected tracked changes'
print('Exact shallow runtime restored:',restored)
