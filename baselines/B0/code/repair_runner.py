"""Registered supplemental trials; no success-based selection or hidden retries."""
import argparse,collections,datetime,hashlib,json,math,os,shutil,subprocess,sys,time,traceback
from pathlib import Path
import run_branches as base
N=Path(__file__).resolve().parents[1]
OLD=Path('/mnt/disk_4/geyi/audio_switch_benchmark/experiments/asr_direct_T2_T8_20261108')
ALIAS={'precondition_wall_s':'setup_wall_s','per_physical_goal_wall_s':'source_wall_s','qa_complete_answer_from_audio_end_s':'qa_complete_audio_s'}
old_prepare=base.prepare_spec
def normalize_budgets(original):
 b=dict(original)
 for dst,src in ALIAS.items():
  value=b.get(dst,b.get(src))
  if isinstance(value,bool)or not isinstance(value,(int,float))or not math.isfinite(value)or value<=0:raise ValueError('Invalid protocol budget: '+src)
  if dst in b and src in b and b[dst]!=b[src]:raise ValueError('Conflicting protocol budgets')
  b[dst]=value
 return b
def prepare(item,case,port):
 spec,client,env=old_prepare(item,case,port)
 if item['branch']=='T8':
  assert not item['case']['private_contract']['require_overlap'],'Pure ASR cannot manufacture its own output speech'
  p=case/'client_spec.private.json';cfg=base.read(p);original=cfg['protocol']['budgets'];cfg['protocol']['budgets']=normalize_budgets(original);base.write(p,cfg)
  spec['common_paused_fixture']=item['case']['initial_mode']=='paused_holding_bowl';base.write(case/'spec.json',spec)
  base.write(case/'PROTOCOL_MAPPING.json',dict(original_budgets=original,actual_client_budgets=cfg['protocol']['budgets'],numeric_thresholds_changed=False,common_pause_is_benchmark_setup_only=spec['common_paused_fixture']))
 return spec,client,env
base.prepare_spec=prepare
def now():return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
def archive(case,run_name):
 root=case.resolve();allowed=Path('/home/geyi/.local/state/audio_asr_repair_20261109/runs').resolve()
 if allowed not in root.parents:raise ValueError('Refuse to remove an unowned live directory')
 target=N/'archived'/run_name/case.name
 if target.exists():raise ValueError('Refuse to overwrite archived case')
 target.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(root,target,symlinks=True)
 manifest={}
 for p in root.rglob('*'):
  if p.is_file()and not p.is_symlink():
   relative=p.relative_to(root);a=hashlib.sha256(p.read_bytes()).hexdigest();b=hashlib.sha256((target/relative).read_bytes()).hexdigest();assert a==b,relative;manifest[str(relative)]=a
 base.write(target/'ARCHIVE_SHA256.json',dict(verified_at=now(),files=manifest,source=str(root),target=str(target)))
 shutil.rmtree(root);root.symlink_to(target,target_is_directory=True)
def refresh(run,items,state,active=None):
 results=[base.read(p)for p in(run/'cases').glob('*/REPAIR_OUTCOME.json')]
 payload=dict(updated_beijing=now(),state=state,registered=len(items),finished=len(results),active=active,by_branch={})
 for branch in ['T2','T3','T4','T5','T7','T8']:
  xs=[x for x in results if x['branch']==branch];payload['by_branch'][branch]=dict(registered=sum(i['branch']==branch for i in items),finished=len(xs),audio_pass=sum(x.get('audio_quality_passed')is True for x in xs),engineering_errors=sum(x.get('engine_error',False)or x.get('status')=='technical_or_setup_failure'or x.get('scoring_returncode',0)!=0 or x.get('v4_scoring_returncode',0)!=0 for x in xs))
 base.write(run/'PROGRESS.json',payload)
 return payload
def run_one(item,run,lane):
 outcome=base.run_case(item,run,base.SETTINGS['port']);case=Path(outcome['directory'])
 if(case/'SCORE.json').exists():
  private=case/'V4_ITEM.private.json';base.write(private,item)
  with(case/'v4_scoring.log').open('w')as f:q=subprocess.run([base.SIM,'-B',str(N/'scoring_v4/score.py'),'--case',str(case),'--item',str(private),'--legacy',str(case/'SCORE.json'),'--out',str(case/'SCORE_V4.json')],stdout=f,stderr=subprocess.STDOUT)
  outcome['v4_scoring_returncode']=q.returncode
  if q.returncode==0:outcome['score_v4']=base.read(case/'SCORE_V4.json')
 outcome.update(repair_revision='transport-scoring-r2-20261109',repair_reasons=item.get('repair_reasons',[]),original_case_directory=item.get('original_case_directory'),lane=lane)
 base.write(case/'REPAIR_OUTCOME.json',outcome);return outcome
def main():
 p=argparse.ArgumentParser();p.add_argument('--lane',type=int,choices=[0,1],required=True);p.add_argument('--preflight',action='store_true');p.add_argument('--run-name');a=p.parse_args();lane=a.lane
 base.SETTINGS.update(gpu=6 if lane==0 else 1,asr=f'ws://127.0.0.1:{49940 if lane==0 else 49950}',policy=f'http://127.0.0.1:{49941 if lane==0 else 49942}',port=54401 if lane==0 else 54411)
 os.environ['RAW_ASR_EVIDENCE_ROOT']=str(N/f'asr_lane{lane}')
 source=N/'config'/('PREFLIGHT4.json'if a.preflight else'REPAIR_REGISTERED.json');registered=base.read(source)
 if not a.preflight:
  groups={b:[x for x in registered if x['branch']==b]for b in ['T8','T2','T4','T3','T7','T5']}
  registered=[groups[b][i]for i in range(max(map(len,groups.values())))for b in groups if i<len(groups[b])]
 items=registered[lane::2]
 if not a.preflight:
  assert base.read(N/'reports/PREFLIGHT_ACCEPTANCE.json')['ready']is True
  for rel,sha in base.read(N/'config/SOURCE_SHA256.json').items():
   if hashlib.sha256((N/rel).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen repair source changed: '+rel)
 run_name=a.run_name or('preflight_v1_lane'+str(lane)if a.preflight else'supplement193_lane'+str(lane));run=N/'runs'/run_name;run.mkdir(parents=True,exist_ok=True);(run/'cases').mkdir(exist_ok=True)
 base.write(run/'REGISTERED.json',items);base.write(run/'COORDINATOR.json',dict(pid=os.getpid(),started_beijing=now(),preflight=a.preflight,lane=lane,source=str(source)))
 state='running'
 try:
  for item in items:
   uid=item['trial_uid'];case=run/'cases'/uid
   if case.exists():raise ValueError('Refuse duplicate or unfinished supplemental trial: '+uid)
   if shutil.disk_usage('/home/geyi').free<10*1024**3:raise RuntimeError('SSD live I/O workspace below 10GiB free')
   refresh(run,items,state,dict(branch=item['branch'],trial_uid=uid));print('START',item['branch'],uid,flush=True)
   outcome=run_one(item,run,lane);print('END',uid,outcome['status'],'pcm',outcome.get('audio_quality_passed'),'target',outcome.get('score_v4',{}).get('target'),flush=True)
   archive(case,run_name);refresh(run,items,state)
   if not a.preflight and(outcome.get('audio_quality_passed')is not True or outcome.get('engine_error')or outcome['status']=='technical_or_setup_failure'or outcome.get('scoring_returncode',0)!=0 or outcome.get('v4_scoring_returncode',0)!=0):raise RuntimeError('Supplemental engineering/admission failure; stop dispatch, retain first result')
  state='completed'
 except BaseException as e:state='stopped_with_error';base.write(run/'COORDINATOR_ERROR.json',dict(error=repr(e),traceback=traceback.format_exc()));raise
 finally:refresh(run,items,state)
if __name__=='__main__':main()
