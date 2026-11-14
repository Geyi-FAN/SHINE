import hashlib
import json
from sym_paths import ROOT,BASE_DATA,BASE_CODE,DATA
from common import sha256

def protocol_id():
    files=[BASE_DATA/'mini/protocol.json',BASE_DATA/'mini/cases.jsonl',DATA/'mini_plans.json']
    files += [ROOT/'src'/n for n in ['sym_contract.py','sym_geometry.py','sym_online.py','mini_runner.py','v3_markers.py']]
    files += [BASE_CODE/'src'/n for n in ['eval_inputs.py','sim_runtime.py','restore_metrics.py','schema.py']]
    files += sorted((BASE_CODE/'src/revision_eval').rglob('*.py'))
    digest=hashlib.sha256(json.dumps({('model/'+str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else 'data/'+str(p.relative_to(BASE_DATA)) if p.is_relative_to(BASE_DATA) else 'plans/'+p.name if p==DATA/'mini_plans.json' else 'base/'+str(p.relative_to(BASE_CODE))):sha256(p) for p in files},sort_keys=True).encode()).hexdigest()
    return 'visual_marker_v3_'+digest[:20]
