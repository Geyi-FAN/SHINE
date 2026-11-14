"""Read-only hash validation of the Git-frozen code and configuration files."""
import hashlib
import json
from pathlib import Path
import subprocess
import os


def verify(root):
    manifest=json.loads((root/'provenance/FROZEN_FILES.json').read_text())
    failures=[]
    for row in manifest['files']:
        p=root/row['path']
        if row.get('kind')=='symlink':
            valid=p.is_symlink() and hashlib.sha256(os.readlink(p).encode()).hexdigest()==row['sha256']
        else:
            valid=p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
        if not valid:
            failures.append(row['path'])
    external=json.loads((root/'provenance/EXTERNAL_CODE_HASHES.json').read_text())['files']
    for file,digest in external.items():
        p=Path(file)
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
            failures.append('external dependency changed: '+file)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    expected=json.loads((root/'FREEZE.json').read_text())['git_commit']
    if commit!=expected:failures.append('git HEAD differs from freeze identity')
    untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=root,text=True).splitlines()
    failures.extend('untracked: '+p for p in untracked)
    dirty=subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=root,text=True).splitlines()
    failures.extend('modified: '+p for p in dirty)
    return dict(passed=not failures,files=len(manifest['files']),git_commit=commit,failures=failures)


if __name__=='__main__':
    result=verify(Path(__file__).resolve().parents[1]);print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 1)
