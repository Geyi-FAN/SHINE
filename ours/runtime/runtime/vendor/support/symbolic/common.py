import hashlib
import json
import os
from pathlib import Path
from sym_paths import ROOT,WORK,DATA,BASE_CODE

OPENPI=Path(os.environ.get('OPENPI_ROOT',WORK/'openpi'))
VARIANT=os.environ.get('MEMORY_VARIANT','V3R')
if VARIANT not in ('V3R',):raise ValueError(VARIANT)
EVAL_ROOT=WORK/'pi0.5_test_1001/evaluation_portable'

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()

def read_config():
    c=json.loads((ROOT/'configs'/f'{VARIANT}.json').read_text())
    c['initial_checkpoint']=os.environ.get('INITIAL_CHECKPOINT',c['initial_checkpoint'])
    return c

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+f'.{os.getpid()}.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temp.replace(path)

def source_hashes():
    paths=list((ROOT/'src').glob('*.py'))+list((ROOT/'configs').glob('*.json'))+list((ROOT/'scripts').glob('*.sh'))
    paths+=list((OPENPI/'src/openpi').rglob('*.py'))+[OPENPI/'scripts/train.py']
    paths+=[BASE_CODE/'src/dataset.py',BASE_CODE/'src/reference_model.py',BASE_CODE/'configs/token_corrections.json']
    return {str(p):sha256(p) for p in sorted(paths)}

