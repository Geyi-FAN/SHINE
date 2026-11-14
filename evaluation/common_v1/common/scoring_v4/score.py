"""Read-only attribution amendment: unchanged goals survive metadata task-ID changes.

No physical predicate, timeout, waveform, action or legacy score is changed.
Pause/resume, non-command input and cancelling ONLY a queued task do not replace
an already authorized source goal. Their Interaction checks remain independent.
"""
import argparse,copy,hashlib,importlib.util,json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];D=Path('/mnt/disk_4/geyi/audio_switch_benchmark');sys.path.insert(0,str(R/'scoring_v3'))
_spec=importlib.util.spec_from_file_location('frozen_v3_attribution',R/'scoring_v3/score.py');v3=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(v3)
from attribution import lines
VERSION='audio-logical-goal-attribution-v4-20261109'

def persistent_scope(branch,result,case,ticks):
 turns=result.get('turns',[])
 if not turns or not all(k in turns[0]for k in ['audio_started_wall','audio_ended_wall']):return dict(valid=False,reason='missing_real_source_audio')
 start=turns[0]['audio_started_wall'];deadline=min(result['finished']['time'],turns[0]['audio_ended_wall']+600)
 if branch=='T8':
  main=[t for t in turns if not t.get('prelude')]
  if not main:return dict(valid=False,reason='core_audio_not_delivered; retain_failure_not_infer_robustness')
  start=main[0]['audio_started_wall']
 episode=result.get('episode_id');active=[t for t in ticks if t.get('episode_id')==episode and start<=t.get('time',-1)<=deadline]
 ids=sorted({t['task_id']for t in active if t.get('policy_action')and t.get('task_id')})
 return dict(valid=True,episode_id=episode,ids=ids,window=dict(start=start,deadline=deadline),authorization='real source goal persists; task bookkeeping IDs do not alter the user goal',instruction_string_matching=False)

def grade(case_dir,item,legacy):
 out=v3.grade(case_dir,item,legacy);previous=copy.deepcopy(out);out.update(scoring_version=VERSION,v3_target=out.get('target'),v3_instruction=out.get('instruction'));branch=item['branch'];c=item['case']
 if branch not in ['T2','T8']and not(branch=='T7'and c.get('branch')=='C'):return out
 if out.get('target')=='na':return out
 result=json.loads((case_dir/'result.json').read_text());ticks=lines(case_dir/'recordings'/str(result.get('episode_id'))/'control_ticks.jsonl');proof=persistent_scope(branch,result,c,ticks);out['logical_goal_attribution']=proof
 if not proof['valid']:return out
 ids=set(proof['ids']);w=proof['window'];ticks=[t for t in ticks if t.get('episode_id')==result.get('episode_id')]
 if branch=='T8':
  root=D/'T8/current/judge';sys.path.insert(0,str(root));from target_window import target_evidence
  evidence=[target_evidence(ticks,result.get('episode_id'),i,w['start'],w['deadline'])for i in sorted(ids)];out['target']='pass'if any(x['success']for x in evidence)else'fail';out['logical_target_evidence']=evidence;return out
 goal=c['private_contract'].get('final_target_task_id',c['private_contract'].get('target_task_id'))
 if branch=='T2':
  import types
  root=D/'T2/current';m=v3.load('v4_same_t2_physics',root/'evaluation/scoring.py');judge=m.load_judge(root);physical=types.SimpleNamespace(physical_verdict=judge.__globals__['physical_verdict']);rules=json.loads((root/'dataset/physical_rules.json').read_text())
 else:
  root=D/'T7/current';sys.path[:0]=[str(root/'adapter/judge/reference'),str(root/'adapter/judge')];physical=v3.load('v4_same_t7_physics',root/'adapter/judge/reference/t7_physics.py');rules=json.loads((root/'dataset/physical_rules.json').read_text())
 target,_,checks=physical.physical_verdict(ticks,int(goal),ids,w['start'],w['deadline'],rules);out['target']=target;out['logical_target_checks']=checks
 existing=out.get('physical_checks',[])
 if isinstance(existing,list):
  replacement=next((x for x in checks if x['name'].startswith('target_')),None)
  if replacement:
   for row in existing:
    if row.get('name','').startswith('target_'):row.update(status=replacement['status'],first_step=replacement.get('first_step'),attribution_version=VERSION)
  if existing and'instruction'in out:out['instruction']='fail'if any(x['status']=='fail'for x in existing)else'unknown'if any(x['status']=='unknown'for x in existing)else'pass'
 out['failures']=[x['name']for x in out.get('checks',[])+(existing if isinstance(existing,list)else[])if x.get('status')not in ['pass','na']]
 return out

def main():
 p=argparse.ArgumentParser();p.add_argument('--case',type=Path,required=True);p.add_argument('--item',type=Path,required=True);p.add_argument('--legacy',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();sources=[a.case/'result.json',a.legacy];before={str(x):hashlib.sha256(x.read_bytes()).hexdigest()for x in sources};answer=grade(a.case,json.loads(a.item.read_text()),json.loads(a.legacy.read_text()));assert not a.out.exists();a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(answer,indent=2,ensure_ascii=False));assert before=={str(x):hashlib.sha256(x.read_bytes()).hexdigest()for x in sources};print(json.dumps({k:answer.get(k)for k in ['target','v3_target','instruction','v3_instruction','scoring_version']}))
if __name__=='__main__':main()
