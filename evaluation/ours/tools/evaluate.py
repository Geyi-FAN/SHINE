"""All branches share one frozen C3r runtime; only private setup/adapters vary."""
import argparse,fcntl,importlib.util,json,os,sys,hashlib
from pathlib import Path
N=Path(__file__).resolve().parents[1];B=N.parents[1];RUNTIME=os.environ.get('READINESS_RUNTIME_NAME','runtime');assert RUNTIME in('runtime','runtime_v2','runtime_v3','runtime_v4','runtime_v5','runtime_v6','runtime_v7','runtime_v8');W=N/'code'/RUNTIME;P=B/'T6/releases/t6-prefix-v2-20261108';T3=B/'deployments/our_t3_prepared_judge_20261109'
def read(p):return json.loads(Path(p).read_text())
def main():
 p=argparse.ArgumentParser();p.add_argument('--case-id',required=True);p.add_argument('--lane',type=int,choices=range(4),required=True);p.add_argument('--index',type=int,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--repetition',type=int,default=1);p.add_argument('--formal',action='store_true');p.add_argument('--lease-fd',type=int,required=True);a=p.parse_args()
 assert 0<=a.index<1600
 # Parent owns the account lease throughout preflight + formal and passes its descriptor.
 fd=a.lease_fd;os.fstat(fd);assert Path(os.readlink(f'/proc/self/fd/{fd}')).resolve()==(N/'locks'/f'lane{a.lane}.lock').resolve()
 sys.path[:0]=[str(N/'tools'),str(W/'tools'),str(P/'adapter'),str(P/'adapter/support'),str(P/'tools')]
 from verify_freeze import verify
 check=verify(W);assert check['passed'],check['failures'][:5]
 from catalog import item_for
 item=item_for(a.case_id);item.update(repetition_index=a.repetition,trial_uid=item['case_uid']+f':R{a.repetition:02d}')
 a.out.mkdir(parents=True,exist_ok=False)
 sp=importlib.util.spec_from_file_location('frozen_common_runner',N/'tools/runner.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
 r.W=W;r.ROUND=a.out;r.IS_FORMAL_TRIAL=a.formal;r.LANE=a.lane;r.POLICY_PORT=28010+a.lane;r.VOICE_CONFIG=N/f'private/voice_lane{a.lane}.json';r.refresh=lambda:None;r.PREFIX_GATEWAY=N/'tools/eval_gateway_replay_v2.py'
 gpu=read(N/'reports/GPU_MAP.json');r.RENDER_GPU=gpu['renderer_egl_by_lane'][a.lane];os.environ['CUDA_VISIBLE_DEVICES']=gpu['gpu_uuids'][a.lane]
 os.environ['C3R_EVAL_RUN_ID']='ours-full930-readiness-20261114:'+a.out.parent.name+':'+a.out.name
 os.environ['VOICE_T6_QA_AUDIT']=str(a.out/'cases'/a.case_id/'qa_audit.jsonl')
 original=r.config_for
 def config(*args,**kw):
  spec,client,env=original(*args,**kw)
  if item['branch']=='T4':client[1]=str(N/'adapter/T4/client.mjs')
  if item['branch']=='T5':client[1]=str(N/'adapter/T5/client/client.mjs')
  if item['branch']=='T8':client[1]=str(N/'tools/t8_client_v2.mjs')
  env['PYTHONPATH']=str(N/'tools')+os.pathsep+env.get('PYTHONPATH','')
  if item['branch']=='T3':
   spec.update(t3_prepare_mode='replay',t3_bank_root=str(T3/'data/T3-controlled-source-prefix-v2-20261109'));client[1]=str(N/'tools/t3_controlled_client.mjs')
  if item['branch']=='T6':
   from run_prepared_case import resolve_case
   _,prefix,_=resolve_case(a.case_id,P);spec['t6_frozen_prefix']=str(prefix)
   for asset in spec['fixture']['assets'].values():
    f=P/asset['relative_path'];assert hashlib.sha256(f.read_bytes()).hexdigest()==asset['sha256'];asset['path']=str(f)
  return spec,client,env
 r.config_for=config
 spawn=r.subprocess.Popen
 def replace_gateway(cmd,*args,**kw):
  cmd=[str(x)for x in cmd]
  if item['branch']=='T3'and str(r.R/'adapter/eval_gateway70.py')in cmd:cmd[cmd.index(str(r.R/'adapter/eval_gateway70.py'))]=str(N/'tools/eval_gateway_T3_controlled.py')
  if item['branch']=='T8'and str(r.R/'adapter/eval_gateway70.py')in cmd:cmd[cmd.index(str(r.R/'adapter/eval_gateway70.py'))]=str(N/'tools/eval_gateway_T8_idle_v3.py')
  original_gateway=str(r.R/'adapter/eval_gateway70.py')
  if original_gateway in cmd:cmd[cmd.index(original_gateway)]=str(N/'adapter/eval_gateway70.py')
  return spawn(cmd,*args,**kw)
 r.subprocess.Popen=replace_gateway
 result=r.run_case(300+a.index,item);case=a.out/'cases'/a.case_id
 (case/'UNIFIED_PROVENANCE.json').write_text(json.dumps(dict(runtime=check,branch=item['branch'],formal=a.formal,trial_uid=item['trial_uid'],common_runtime_root=str(W),T3_track='controlled-source-v2'if item['branch']=='T3'else None,voice_profile_sha256=hashlib.sha256((W/'config/voice_profile.json').read_bytes()).hexdigest(),provider='Paratera04/Qwen3.8-27B',policy_port=r.POLICY_PORT,private_GT_passed_to_online_agent=False),indent=2)+'\n')
 print(json.dumps({k:result.get(k)for k in ['case_id','status','elapsed_seconds','error','audio_played']},ensure_ascii=False))
 if result['status']!=('preparation_preflight_passed'if os.environ.get('REPAIR_PREP_ONLY')=='1'else'finished'):raise SystemExit(2)
if __name__=='__main__':main()
