import argparse,hashlib,json,os,sys,time
from pathlib import Path
Q=Path(__file__).resolve().parents[1];N=Q.parent/'ours_full930_readiness_20261114';B=Q.parents[1]
def read(p):return json.loads(Path(p).read_text())
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--item',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--lane',type=int,required=True);a=p.parse_args()
 item=read(a.item);lane=a.lane;gpu=read(N/'reports/GPU_MAP.json');method=item['method']
 cache=Q/'work/numba';cache.mkdir(parents=True,exist_ok=True)
 os.environ.update(HOME=str(Q/'work/container_home'),NUMBA_CACHE_DIR=str(cache),COMMON_CASE_OUTPUT=str(a.run/'cases'/item['trial_uid']),COMMON_METHOD=method,COMMON_LANE=str(lane),COMMON_TTS_KEY_FILE=str(Q/'private'/('tts_lane%d.key'%lane)),COMMON_AGENT_LOCK_FILE=str(Q/'private'/('agent_lane%d.lock'%lane)),COMMON_RENDER_GPU=str(gpu['renderer_egl_by_lane'][lane]),COMMON_GATEWAY_PORT=str(28310+lane),COMMON_POLICY_URL='http://127.0.0.1:%d'%(28110+lane),RAW_ASR_URL='ws://127.0.0.1:%d'%(28210+lane),CUDA_VISIBLE_DEVICES='0,1,2,3')
 os.environ['PYTHONPATH']=str(Q/'common')+':'+str(N/'code/runtime_v8/runtime')+':'+os.environ.get('PYTHONPATH','')
 sys.path[:0]=[str(Q/'common'),str(N/'code/runtime_v8/runtime')]
 if item['branch']=='T6':
  sys.path.insert(0,str(Q/'t6/code'));import attempt
  value=attempt.one(dict(item['case'],trial_uid=item['trial_uid']),a.run,item['registration_index']+1)
  value.update(audio_played=value.get('audit',{}).get('audio_admitted',False),score={'qa_pending_fixed_judge':True})
 else:
  sys.path.insert(0,str(Q/'tools'));import attempt
  attempt.SETTINGS.update(gpu=gpu['renderer_egl_by_lane'][lane],asr=os.environ['RAW_ASR_URL'],policy=os.environ['COMMON_POLICY_URL'],port=28310+lane)
  value=attempt.run_attempt(item,a.run,28310+lane)
 value.update(method=method,trial_uid=item['trial_uid'],branch=item['branch'],case_id=item['public_case_id'],registration_index=item['registration_index'],paired_trial_uid=item.get('paired_trial_uid'),lane=lane)
 target=a.run/'outcomes'/(item['trial_uid']+'.json');target.parent.mkdir(exist_ok=True);target.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n')
 print(json.dumps({k:value.get(k)for k in ['trial_uid','status','audio_played','score']}),flush=True)
