"""Read existing first attempts only; no model calls, raw edits or rescoring."""
import json,collections,hashlib
from pathlib import Path
Q=Path('/mnt/disk_4/geyi/audio_switch_benchmark/deployments/common_scoring_oracle_baselines_20261114')
RUN=Q/'runs/formal1770_v1';OUT=Q/'audits/target_unknown_T2_20261115'
OUT.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def lines(p):return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []
vals=[read(p) for p in (RUN/'outcomes').glob('B1:*.json')]
u=[];t2=[]
for v in vals:
 s=v.get('score',{});uid=v['trial_uid'];d=RUN/'cases'/uid
 if s.get('target')=='unknown':
  r=read(d/'result.json');ep=r.get('episode_id');ticks=lines(d/'recordings'/str(ep)/'control_ticks.jsonl')
  proof=s.get('attribution',{});w=proof.get('window',{});ids=proof.get('ids',[])
  active=[t for t in ticks if t.get('episode_id')==ep and t.get('task_id') in ids and w.get('start',0)<=t.get('time',0)<=w.get('deadline',float('inf')) and t.get('policy_action')]
  events=lines(d/'task_events.jsonl');trans=[read(p) for p in (d/'agent_calls').glob('*/transport.json')]
  u.append(dict(trial_uid=uid,branch=v['branch'],case_id=v['case_id'],engine_error=v.get('engine_error'),audio_quality=v.get('audio_quality_passed'),
    attribution_valid=proof.get('valid'),ids=ids,total_ticks=len(ticks),authorized_policy_ticks=len(active),
    failed_checks=[c['name'] for c in s.get('checks',[]) if c.get('status')=='fail'],
    physical_checks=s.get('physical_target_attribution_checks'),legacy_target=s.get('legacy_target'),
    client_errors=v.get('client_errors',[]),agent_errors=v.get('agent_errors',[]),
    final_phase=v.get('final_status',{}).get('agent_execution',{}).get('phase'),
    transport=[{k:x.get(k) for k in ['status','error','detail','elapsed_s','elapsed_seconds']} for x in trans],
    event_kinds=dict(collections.Counter(x.get('kind') for x in events)),directory=str(d)))
 if v['branch']=='T2':
  r=read(d/'result.json');samples=lines(d/'pause_observations.jsonl');events=lines(d/'task_events.jsonl')
  messages=r.get('messages',[]);voice=[x for p in (d/'voice/sessions').glob('*.jsonl') for x in lines(p)]
  t2.append(dict(trial_uid=uid,case_id=v['case_id'],interaction=s.get('interaction'),target=s.get('target'),instruction=s.get('instruction'),
   checks=s.get('checks',[]),prep_checks=s.get('preparation_checks',[]),physical=s.get('physical_checks',[]),
   sample_count=len(samples),sample_modes=dict(collections.Counter(x.get('mode') for x in samples)),
   sample_physical_sha_available=sum(bool(x.get('physical_state_sha256')) for x in samples),
   message_types=dict(collections.Counter(x.get('type') for x in messages)),
   voice_types=dict(collections.Counter(x.get('type') for x in voice)),
   client_errors=v.get('client_errors'),event_kinds=dict(collections.Counter(x.get('kind') for x in events)),directory=str(d)))
summary=dict(unknown_count=len(u),unknown_by_branch=dict(collections.Counter(x['branch'] for x in u)),unknown_zero_ids=sum(not x['ids'] for x in u),unknown_zero_authorized_policy=sum(not x['authorized_policy_ticks'] for x in u),
  t2_count=len(t2),t2_interaction=dict(collections.Counter(x['interaction'] for x in t2)),
  t2_check_failures=dict(collections.Counter(c['name'] for x in t2 for c in x['checks'] if c['status']=='fail')),
  t2_checks_pass=dict(collections.Counter(c['name'] for x in t2 for c in x['checks'] if c['status']=='pass')),
  t2_empty_samples=sum(not x['sample_count'] for x in t2))
for n,x in [('unknown47.json',u),('t2_120.json',t2),('SUMMARY.json',summary)]:
 (OUT/n).write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(summary))
