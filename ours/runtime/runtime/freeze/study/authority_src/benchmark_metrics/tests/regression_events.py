"""Regression of original close successes and explicitly rejected drop cases."""
import concurrent.futures,gzip,json,pathlib
from benchmark_metrics.config import load_rules
from benchmark_metrics.events import close_event,high_releases
B=pathlib.Path(__file__).resolve().parents[2];A=B/'analysis';RULES=load_rules()
C={x['case_id']:x for x in json.load(open(A/'task_contract_v2_20261021/contracts.json'))}
T={x['case_id']:x for x in json.load(open(A/'offline_calibration_v3r20k_20261021/case_calibration.json'))}

def check(job):
    cid,kind=job;m=json.load(gzip.open(T[cid]['trace_path'],'rt'))['measurements'][:T[cid]['policy_steps']]
    if kind=='close':
        c=next(x for x in C[cid]['clauses'] if x['kind']=='close_event')
        step=close_event([x['source']['articulation'][c['joint']] for x in m],RULES)
        assert step is not None,cid
    else:
        c=next(x for x in C[cid]['clauses'] if x['kind']=='restore_episode_start')
        events=high_releases([x['source'] for x in m],c['reference_position'],RULES)
        assert events,cid;step=events[0]['confirmation']
    return {'case_id':cid,'component':kind,'confirmed_step':step}
if __name__=='__main__':
    jobs=[(cid,'close') for cid,c in C.items() if T[cid]['old']['strict_complete'] and any(x['kind']=='close_event' for x in c['clauses'])]
    previous=json.load(open(A/'restore_release_revision_20261021/trajectory_evidence.json'))
    jobs += [(r['case_id'],'drop') for r in previous if r['label']=='drop_fail']
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:rows=list(pool.map(check,jobs))
    result={'passed':True,'original_close_successes':sum(x['component']=='close' for x in rows),'reviewed_drop_failures':sum(x['component']=='drop' for x in rows),'cases':rows}
    (B/'benchmark_metrics/validation_events.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print({k:v for k,v in result.items() if k!='cases'})
