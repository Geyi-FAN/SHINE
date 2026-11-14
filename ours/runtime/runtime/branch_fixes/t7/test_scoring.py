"""Independent score transport regression against prior untouched saved cases."""
import importlib.util,json,sys,tempfile
from pathlib import Path
A=Path(__file__).parent;sys.path.insert(0,str(A));import score
old=Path('/mnt/disk_4/geyi/t7_goal10_v3_20261102/recovered30');cases=json.loads((old/'dataset/selected.private.json').read_text());protocol=json.loads((old/'dataset/PROTOCOL.json').read_text());judge,derive=score.load_judge(old);rows=[]
selected=[next(c for c in cases if c['branch']==b)for b in ['N','C','R']]
for c in selected:
 d=old/'cases'/c['case_id'];expected=json.loads((d/'verdict.json').read_text());_,v=score.evaluate_one(judge,derive,d,c,protocol)
 for m in score.METRICS:assert v[m]==expected[m],(c['case_id'],m,v[m],expected[m])
 rows.append(dict(case_id=c['case_id'],metrics_unchanged=True))
for seconds,expected10,expected45 in [(20,'fail','pass'),(50,'fail','fail')]:
 c=[dict(name='handoff_first_action_within_10s',status='fail',evidence={'latency_s':seconds})];assert score.grade(c,10)==expected10 and score.grade(c,45)==expected45
assert score.grade([dict(name='handoff_first_action_within_10s',status='fail',evidence=None)],45)=='fail'
import runpy
s=runpy.run_path(str(A/'gateway.py'))['source'];assert 'install_waiting_prefetch(b,state)'not in s and 'NativePrefetchMixin'in s
compile(s,str(A/'gateway.py'),'exec')
report=dict(saved_cases=rows,time_limits_negative_tests=3,unsafe_wording_prefetch_removed=True,native_action_prefetch_preserved=True)
Path('/mnt/disk_2/geyi/t7_handoff_latency_20261103/SCORING_TESTS.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
