import sys,json,gzip,time
from pathlib import Path
sys.path.insert(0,'/mnt/disk_4/geyi/smolvla_eval')
from benchmark_metrics import load_rules
from switch_terminal import SwitchTerminal
OLD=Path('/mnt/disk_4/geyi/s1_D0_benchmark_final_20261027');OUT=Path(__file__).resolve().parents[1]/'reports'
cases={x['case_id']:x for x in map(json.loads,(OLD/'data/work/pi05_small722_data_v1/mini/cases.jsonl').read_text().splitlines())}
contracts={x['case_id']:x for x in json.loads((OLD/'data/contracts.json').read_text())}
rows=[]
for p in sorted((OLD/'formal/D0/cases/fresh').iterdir()):
 if not (p/'result.json').exists():continue
 res=json.loads((p/'result.json').read_text())
 with gzip.open(p/'trace.json.gz','rt') as f:tr=json.load(f)
 calls=json.loads((p/'agent_calls.json').read_text());finals=[x for x in calls if x['result']['output'] and len(x['result']['output'].get('remaining_plan',[]))==1]
 gate=SwitchTerminal(cases[p.name],contracts[p.name],load_rules(),tr['metric_initial'])
 passed=None;check=None;start=time.monotonic()
 if finals:
  decision=finals[-1]['result']['output'];first=res['metrics']['instruction_adjusted']['first_step']
  t=max(first or len(tr['measurements']),finals[-1]['input']['frame'],1)
  check=gate.check(tr['measurements'][:t],decision)
  if check['passed']:passed=t
  if first is None:assert not check['passed'],p.name
  # Declining a multi-stage plan cannot leak an Oracle next stage.
  assert not gate.check(tr['measurements'][:t],{'remaining_plan':[{},{}]})['passed']
 rows.append(dict(case_id=p.name,old_actions=res['actions'],old_status=res['status'],old_success=res['metrics']['instruction_adjusted']['success'],causal_prefix_pass_step=passed,check=check,seconds=time.monotonic()-start))
(OUT/'terminal_replay.json').write_text(json.dumps(dict(method='Frozen trajectory prefix checks, not new rollouts',rows=rows),indent=2))
print('cases',len(rows),'prefix accepted',sum(x['causal_prefix_pass_step'] is not None for x in rows))
for x in rows:
 if x['old_success'] and x['old_status'] in ['need_observation','budget_exhausted']:print(x['case_id'],x['causal_prefix_pass_step'],x['old_actions'])
