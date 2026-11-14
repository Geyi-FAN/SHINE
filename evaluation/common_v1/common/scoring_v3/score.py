"""Three-method shared regrade. Preserve legacy scores, change attribution only."""
import argparse,copy,hashlib,importlib.util,json,sqlite3,sys
from pathlib import Path
from attribution import VERSION,causal_ids,lines
D=Path('/mnt/disk_4/geyi/audio_switch_benchmark');R=Path(__file__).resolve().parents[1]
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def grade(directory,item,legacy):
 result=json.loads((directory/'result.json').read_text());ticks=lines(directory/'recordings'/str(result.get('episode_id'))/'control_ticks.jsonl');events=lines(directory/'task_events.jsonl')
 if not ticks:ticks=lines(directory/'control_ticks.jsonl')
 if not events:events=result.get('timeline',{}).get('events',[])
 if not events and(directory/'gateway/episodes.sqlite').exists():
  with sqlite3.connect((directory/'gateway/episodes.sqlite').resolve().as_uri()+'?mode=ro',uri=True)as db:events=[dict(json.loads(p),time=t,kind=k)for t,k,p in db.execute('SELECT time,kind,payload FROM events WHERE episode=?',(result.get('episode_id'),))]
 branch=item['branch'];c=item['case'];old=legacy['rows'][0]if'rows'in legacy else legacy;answer=copy.deepcopy(old);proof=causal_ids(branch,result,c,events,ticks);answer['scoring_version']=VERSION;answer['legacy_scoring_version']=old.get('scoring_version');answer['attribution']=proof;answer['legacy_target']=old.get('target');answer['legacy_instruction']=old.get('instruction')
 if branch=='T8'or old.get('target')=='na':return answer
 if not proof['valid']:
  answer['target']='fail'
  if answer.get('instruction')not in [None,'na']:answer['instruction']='fail'
  return answer
 ids=set(proof['ids']);w=proof['window'];ticks=[dict(t,policy_action=False)if t.get('policy_action')and t.get('time',-1)<proof.get('authorized_after',{}).get(t.get('task_id'),-1)else t for t in ticks];p=c.get('private_contract',c.get('private_judge',{}));goal=p.get('final_target_task',p.get('final_target_task_id',p.get('target_task_id',c.get('target_task'))))
 if branch=='T7':
  anchor=result['turns'][0]['audio_ended_wall']if c.get('branch')=='C'else old.get('source_ready_time')or result['turns'][-1]['audio_ended_wall']
  w['deadline']=min(result['finished']['time'],anchor+600)
 if goal is None:return answer
 root=D/branch/'current'
 if branch=='T1':
  sys.path.insert(0,str(root/'adapter/judge'));from score_t1_native import target_verdict
  target,physical=target_verdict(ticks,goal,ids,w['start'],w['deadline'],1200);answer['target']=target;answer['physical_checks']=physical
 else:
  # Use exact frozen per-category physical function; no new radius/hold rule.
  if branch=='T2':
   import types
   sys.path.insert(0,str(root));bootstrap=load('portable_attribution_t2',root/'evaluation/scoring.py');judge=bootstrap.load_judge(root);mod=types.SimpleNamespace(physical_verdict=judge.__globals__['physical_verdict']);rules=json.loads((root/'dataset/physical_rules.json').read_text())
  elif branch=='T7':
   sys.path[:0]=[str(root/'adapter/judge/reference'),str(root/'adapter/judge')];mod=load('physical_attribution_t7',root/'adapter/judge/reference/t7_physics.py');rules=json.loads((root/'dataset/physical_rules.json').read_text())
  else:
   common=D/'T4/current/scoring/legacy/t4/scoring';sys.path[:0]=[str(common),str(D/'T4/current/scoring/legacy/freeze/authority_src')];mod=load('physical_attribution_common',common/'score_t1.py')
   rules_path=root/'dataset/physical_rules.json'
   if not rules_path.exists():rules_path=D/'regressions/c3r_pi05_70_serial_20261108/data/T3/data/physical_rules.json'
   rules=c['rules']if branch=='T3'else json.loads(rules_path.read_text())
  target,_,updated=mod.physical_verdict([t for t in ticks if t.get('episode_id')==result.get('episode_id')],int(goal),ids,w['start'],w['deadline'],rules);answer['target']=target
  physical=answer.get('physical_checks',[])
  if isinstance(physical,list):
   for row in physical:
    if row.get('name','').startswith('target_'):
     replacement=next((x for x in updated if x['name'].startswith('target_')),None)
     if replacement:row.update(status=replacement['status'],first_step=replacement.get('first_step'),attribution_version=VERSION)
   if physical and'instruction'in answer:answer['instruction']='fail'if any(x['status']=='fail'for x in physical)else'unknown'if any(x['status']=='unknown'for x in physical)else'pass'
  answer['physical_target_attribution_checks']=updated
 answer['failures']=[x['name']for x in answer.get('checks',[])+ (answer.get('physical_checks',[])if isinstance(answer.get('physical_checks'),list)else[])if x.get('status')not in ['pass','na']]
 return answer
def main():
 p=argparse.ArgumentParser();p.add_argument('--case',type=Path,required=True);p.add_argument('--item',type=Path,required=True);p.add_argument('--legacy',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();sources=[a.case/'result.json',a.legacy];before={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in sources};v=grade(a.case,json.loads(a.item.read_text()),json.loads(a.legacy.read_text()));assert not a.out.exists();a.out.write_text(json.dumps(v,indent=2,ensure_ascii=False));assert before=={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in sources};print(json.dumps({k:v.get(k)for k in ['target','legacy_target','instruction','legacy_instruction','scoring_version']}))
if __name__=='__main__':main()
