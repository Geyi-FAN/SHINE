"""Read-only, method-neutral benchmark scoring; no policy tools or actor imports."""
import argparse,copy,hashlib,importlib.util,json,os,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent; B=Path('/mnt/disk_4/geyi/audio_switch_benchmark')
sys.path[:0]=[str(HERE),str(HERE/'scoring_v3')]
VERSION='three-method-common-oracle-v1-20261114'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(name,p):
 spec=importlib.util.spec_from_file_location(name,p);mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod

def canonical_score(score,branch):
 if score.get('schema')=='t2_portable_judge_output_v1':
  assert len(score['rows'])==1;score=score['rows'][0]
 out=copy.deepcopy(score)
 if branch=='T7':
  assert 'interaction45'in out,'Missing prespecified T7 45s metric'
  out['interaction']=out['interaction45']
 for key in ['interaction','target','instruction']:
  if key in out:
   assert out[key]in ['pass','fail','unknown','na',True,False,None],(key,out[key])
   if type(out[key])is bool:out[key]='pass'if out[key]else'fail'
 out['physical_instruction_independent_of_interaction']=True
 out['joint_interaction_and_instruction']='pass'if out.get('interaction')=='pass'and out.get('instruction')=='pass'else'unknown'if'unknown'in(out.get('interaction'),out.get('instruction'))else'fail'
 return out

def grade(case,item,out):
 case=Path(case);out=Path(out);out.mkdir(parents=True,exist_ok=False)
 assert item['branch']!='T6','QA uses the separate frozen GLM-4.6V v4/r3 pipeline with fixed90 denominator'
 allowed_ids={item['public_case_id']}
 if item['branch']=='T7':
  mapping=next(x for x in read(B/'T7/current/dataset/CASE_ID_MAP.json')if x['case_id']==item['public_case_id'])
  allowed_ids.add(mapping['runtime_case_id'])
 assert read(case/'result.json')['case_id']in allowed_ids,'Scoring case identity mismatch'
 # Read-only core evidence checks; output lives outside the rollout directory.
 evidence=[case/'result.json',case/'spec.json']
 evidence+=[p for p in [case/'task_events.jsonl',case/'physical.jsonl']if p.is_file()]
 evidence+=list((case/'recordings').glob('*/control_ticks.jsonl'))
 before={str(p):sha(p)for p in evidence}
 legacy=out/'LEGACY.json'
 proc=subprocess.run([sys.executable,'-B',str(HERE/'legacy.py'),item['public_case_id'],str(case),str(legacy)],capture_output=True,text=True)
 (out/'legacy.log').write_text(proc.stdout+'\n'+proc.stderr)
 if proc.returncode:raise RuntimeError('independent legacy judge failed; retained logs at '+str(out))
 original=canonical_score(read(legacy),item['branch'])
 v4=load('common_v4',HERE/'scoring_v4/score.py');answer=v4.grade(case,item,original)
 if item['branch']=='T3'and read(case/'spec.json').get('t3_prepare_mode')=='replay':
  from controlled import source_check,adapt_source_check
  spec=read(case/'spec.json');res=read(case/'result.json');key=str(spec['source_task'])+'_'+spec['phase']
  bank=B/'deployments/our_t3_prepared_judge_20261109/data/T3-controlled-source-prefix-v2-20261109'/key
  ticks=[json.loads(x)for x in next((case/'recordings').glob('*/control_ticks.jsonl')).read_text().splitlines()if x.strip()]
  try:check=source_check(res,read(case/'SOURCE_PREPARATION.json'),ticks,spec,read(bank/'PREFIX.json'),sha(bank/'actions.jsonl'))
  except (OSError,ValueError,KeyError,TypeError)as e:check=dict(name='controlled_source_reference_actions_and_original_physical_trigger',status='fail',reason=type(e).__name__)
  answer=adapt_source_check(answer,check,res)
 answer=canonical_score(answer,item['branch'])
 answer.update(common_scoring_version=VERSION,paired_trial_uid=item.get('paired_trial_uid',item.get('trial_uid')),method=item.get('method'),branch=item['branch'])
 assert before=={str(p):sha(p)for p in evidence},'Scorer modified raw evidence'
 (out/'SCORE.json').write_text(json.dumps(answer,indent=2,ensure_ascii=False)+'\n')
 (out/'EVIDENCE_READONLY.json').write_text(json.dumps(dict(verified=True,sha256=before,common_scoring_version=VERSION),indent=2)+'\n')
 return answer
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--case',type=Path,required=True);p.add_argument('--item',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();x=grade(a.case,read(a.item),a.out);print(json.dumps({k:x.get(k)for k in ['interaction','target','instruction','common_scoring_version']}))
