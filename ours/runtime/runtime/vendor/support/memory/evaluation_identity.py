"""A portable identity covers frozen cases, protocol, executed code and sim versions."""
import hashlib,json,importlib.metadata
from common import ROOT,OPENPI,sha256
from schema import ROOT as DATA,WORK

def protocol_id():
 paths=[]
 for root in [ROOT/'src',OPENPI/'src/openpi',WORK/'memory_dataset_v5_fast60_20261013/pipeline/src']:
  paths.extend(p for p in root.rglob('*') if p.suffix in ('.py','.json') and '__pycache__' not in p.parts)
 paths.extend(ROOT/'configs'/f'{v}.json' for v in 'ABCD')
 paths.append(WORK/'pi05_revision_p1/goal_new_state_test_p0_3750_v2_stratified/src/sim_state.py')
 evidence={'files':{str(p.relative_to(WORK)):sha256(p) for p in sorted(set(paths))},
  'sim_versions':{n:importlib.metadata.version(n) for n in ['numpy','mujoco','robosuite']}}
 code=hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest()
 return sha256(DATA/'mini/protocol.json')+':'+sha256(DATA/'mini/cases.jsonl')+':'+code
