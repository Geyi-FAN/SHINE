"""Explicit integration check against reviewed artifacts (run from repo root).
No dependency on historical functions: only evidence/expected component outcomes.
"""
import gzip,json,pathlib
from benchmark_metrics import evaluate_episode,load_rules
from benchmark_metrics.predicates import region_contains
B=pathlib.Path(__file__).resolve().parents[2];A=B/'analysis'
C={x['case_id']:x for x in json.load(open(A/'task_contract_v2_20261021/contracts.json'))}
T={x['case_id']:x for x in json.load(open(A/'offline_calibration_v3r20k_20261021/case_calibration.json'))}
P=B/'modelscope_datasets/OutlierFaye/pi05-hard880-v1-local/small722/pi05_small722_20261016/work/pi05_small722_data_v1/mini/cases.jsonl'
CASES={x['case_id']:x for x in map(json.loads,open(P))}
expected=json.load(open(A/'boundary_agreement_20261021/case_checks.json'));rules=load_rules();rows=[]
for e in expected:
 cid=e['case_id'];trace=json.load(gzip.open(T[cid]['trace_path'],'rt'));r=evaluate_episode(trace,CASES[cid],C[cid],rules)
 assert r['components']['restore']['success']==e['restore_candidate_pass'],cid
 assert r['target_native']['success']==T[cid]['old']['native_success'],cid
 rows.append({'case_id':cid,'restore_matches':True,'native_matches':True})
# Target geometry: actual replay-extracted native evidence, no fabricated position.
geometry=[]
for p in (A/'disputed_cases_visual_20261021').glob('V2*.json'):
 e=json.load(open(p))
 if e['kind']!='target':continue
 assert not region_contains(e,[0,0,0]);assert region_contains(e,rules['target_regions'][e['site']]['margin_m'])
 geometry.append(e['case_id'])
result={'passed':True,'reviewed_restore_cases':rows,'target_geometry_cases':geometry,'production_results_written':False}
(B/'benchmark_metrics/validation_reviewed.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({'passed':True,'restore_cases':len(rows),'target_geometry_cases':len(geometry)}))
