"""Candidate evidence normalization diagnostic only; immutable original scores."""
import collections,hashlib,importlib.util,json,sys,time
from pathlib import Path
from receipt_enrichment import enrich
Q=Path('/mnt/disk_4/geyi/audio_switch_benchmark/deployments/common_scoring_oracle_baselines_20261114');A=Q/'audits/target_unknown_T2_20261115';ROOT=Q.parents[1]/'T2/current';RUN=Q/'runs/formal1770_v1'
spec=importlib.util.spec_from_file_location('t2_portable_audit',ROOT/'evaluation/scoring.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
fn=m.load_judge(ROOT);base=fn.__globals__['audible_r8'];statistics=[]
def wrapped(voice,messages,directory):
    normalized,stats=enrich(voice,messages,directory);statistics.append(stats)
    return base(normalized,messages,directory)
fn.__globals__['audible_r8']=wrapped
# evaluate_readonly obtains a fresh namespace, so use a temporary symlink view here.
import tempfile
registered=json.loads((RUN/'REGISTERED.json').read_text());results=[]
for item in registered:
 if item['branch']!='T2':continue
 uid=item['trial_uid'];d=RUN/'cases'/uid;old=json.loads((RUN/'outcomes'/(uid+'.json')).read_text())['score']
 evidence=[d/'result.json',d/'pause_observations.jsonl',d/'task_events.jsonl',RUN/'outcomes'/(uid+'.json'),d/'common_score/SCORE.json']
 evidence += list((d/'voice/sessions').glob('*.jsonl'));before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence if p.exists()}
 statistics.clear()
 with tempfile.TemporaryDirectory(prefix='t2-identity-audit-') as tmp:
  view=Path(tmp)
  for p in d.iterdir():
   if p.name.startswith('score'):continue
   (view/p.name).symlink_to(p,target_is_directory=p.is_dir())
  new=fn(view,item['case'])
 assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in before.items())
 # Retain existing common v4 physical attribution; only receiver evidence differs.
 old_checks={x['name']:x for x in old.get('checks',[])};new_checks={x['name']:x for x in new.get('checks',[])}
 changed=[dict(name=n,before=old_checks[n]['status'],after=x['status'],evidence=x.get('evidence')) for n,x in new_checks.items() if n in old_checks and old_checks[n]['status']!=x['status']]
 assert all(x['name'].startswith('valid_pcm_reply_') for x in changed),changed
 results.append(dict(trial_uid=uid,method=item['method'],old_interaction=old['interaction'],candidate_interaction=new['interaction'],old_target=old['target'],old_instruction=old['instruction'],changed_checks=changed,checks=new['checks'],stats=list(statistics),raw_unchanged=True))
(A/'T2_EVIDENCE_CANDIDATE.json').write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n')
summary={}
for method in ['B0','B1']:
 xs=[x for x in results if x['method']==method];summary[method]=dict(n=len(xs),old_pass=sum(x['old_interaction']=='pass' for x in xs),candidate_pass=sum(x['candidate_interaction']=='pass' for x in xs),changed_cases=sum(bool(x['changed_checks']) for x in xs),remaining_failures=dict(collections.Counter(c['name'].rsplit('_',1)[-1] if c['name'].startswith('valid_pcm_reply_') else c['name'] for x in xs for c in x['checks'] if c['status']=='fail')))
(A/'T2_EVIDENCE_CANDIDATE_SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
