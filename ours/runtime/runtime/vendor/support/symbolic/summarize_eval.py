"""Validate case identity and summarize the unchanged and stricter metrics separately."""
import argparse
import json
from collections import Counter
from pathlib import Path
from sym_paths import BASE_DATA
from common import write_json

def summarize(directory, smoke=False):
    directory=Path(directory)
    cases=[json.loads(x) for x in (BASE_DATA/'mini/cases.jsonl').read_text().splitlines()]
    if smoke:
        groups=['new_training_scene','legacy_explicit_return','current_bowl_location',
                'close_then_switch','direct_switch','normal_libero']
        cases=[next(c for c in cases if c['group']==g) for g in groups]
    expected={c['case_id'] for c in cases}
    rows=[json.loads(p.read_text()) for p in sorted(directory.glob('shard_*/*.json'))]
    rows=[r for r in rows if 'case_id' in r]
    counts=Counter(r['case_id'] for r in rows)
    duplicates=[k for k,v in counts.items() if v!=1]
    missing=sorted(expected-set(counts));unexpected=sorted(set(counts)-expected)
    errors=[r['case_id'] for r in rows if r['status']=='runtime_error']
    identities={json.dumps(r['server_metadata'],sort_keys=True) for r in rows}
    groups={}
    for group in sorted({r['group'] for r in rows}):
        selected=[r for r in rows if r['group']==group]
        groups[group]=dict(cases=len(selected),**{key:sum(bool(r.get(key)) for r in selected)
            for key in ['native_success','sgs','legacy_complete','strict_complete','restore25','withdraw']})
    result=dict(complete=not(missing or unexpected or duplicates or errors) and len(identities)==1,
        smoke_only=smoke,expected_cases=len(expected),completed_cases=len(rows),
        missing=missing,unexpected=unexpected,duplicates=duplicates,runtime_errors=errors,
        server_identities=len(identities),groups=groups,
        interpretation='Short execution validation only; not a success-rate experiment.' if smoke else
          'Primary legacy_complete matches the prior mini scorer; strict_complete additionally enforces declared invariants.')
    write_json(directory/'summary.json',result)
    return result,rows

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--smoke',action='store_true');a=p.parse_args()
    result,_=summarize(a.directory,a.smoke);print(json.dumps(result,ensure_ascii=False,indent=2))
    if not result['complete']:raise SystemExit(1)
