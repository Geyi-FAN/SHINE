"""Deploy validated candidate only into a disconnected, empty main episode."""
import hashlib,json,os,subprocess,sys,time,urllib.request
from pathlib import Path
B=Path(__file__).resolve().parents[1];MAIN=Path('/mnt/disk_2/geyi/voice_pi05_harness');OUT=B/'reports/deployment';PY='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python';sys.path.insert(0,str(MAIN/'scripts/live_tests'))
from deploy_interaction_when_idle import safe_to_reload
def get(port,path,auth=False):
 h={'Authorization':'Bearer '+(MAIN/'private/robot.token').read_text().strip()}if auth else{}
 with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}{path}',headers=h),timeout=5)as r:return json.load(r)
def write(state,**kw):
 OUT.mkdir(parents=True,exist_ok=True);v=dict(time=time.time(),state=state,action_model_restarted=False,web_restarted=False,**kw);(OUT/'DEPLOYMENT.json').write_text(json.dumps(v,ensure_ascii=False,indent=2));print(json.dumps(v,ensure_ascii=False),flush=True)
def main():
 summary=json.loads((B/'reports/FINAL_SUMMARY.json').read_text());assert summary['completed']==10 and not summary['audit']['freeze_drift']
 assert all(r['interaction']=='pass'for r in summary['cases']if r['number']in(3,4,8)),'03/04/08 formal interaction must pass'
 assert 'OK'in(B/'reports/python_tests.log').read_text()and'FAILED'not in(B/'reports/python_tests.log').read_text()
 assert '90 passed'in(B/'reports/voice_tests_v3.log').read_text()
 conf=MAIN/'configs/unified_execution.local.json';before=conf.read_bytes();old=json.loads(before)
 assert old['f28d_bundle']=='/mnt/disk_2/geyi/voice_t3_harness_repair_20261102','parallel backend changed; preserve it'
 assert old['voice_bundle_path']=='/mnt/disk_2/geyi/voice_f28d_audio_repair_20261102/artifacts/repair8_audio_daemon/dist/index.js','parallel voice changed; preserve it'
 signature=None;stable=0
 for _ in range(6):
  s=get(8801,'/status',True);v=get(8787,'/api/session');key=(s.get('episode_id'),s.get('task_version'),s.get('reset_count'))
  stable=stable+1 if safe_to_reload(s,v)and key==signature else 1 if safe_to_reload(s,v)else 0;signature=key if stable else None
  if stable>=3:break
  time.sleep(2)
 if stable<3:write('pending_main_active_preserved');return
 OUT.mkdir(exist_ok=True);(OUT/'original_unified_execution.local.json').write_bytes(before)
 spec=json.loads(Path(old['live_spec']).read_text());(OUT/'live_spec.json').write_text(json.dumps(spec,indent=2))
 new=dict(old,f28d_bundle=str(B),gateway_entry=str(B/'entryfix/live_service.py'),live_spec=str(OUT/'live_spec.json'),live_output='/mnt/disk_4/geyi/audio_t3_entry_repair_20261102/main_service',voice_bundle_path=str(B/'artifacts/repair8_audio_daemon/dist/index.js'),freeze_manifest=str(B/'run_data/FREEZE.json'))
 (OUT/'candidate_unified_execution.local.json').write_text(json.dumps(new,indent=2));assert conf.read_bytes()==before,'parallel configuration update'
 s=get(8801,'/status',True);v=get(8787,'/api/session');assert safe_to_reload(s,v)and signature==(s['episode_id'],s['task_version'],s['reset_count'])
 temp=conf.with_suffix('.entryfix.new');temp.write_text(json.dumps(new,indent=2));os.chmod(temp,0o600);temp.replace(conf)
 write('reloading_voice_and_robot',old_episode=s['episode_id'])
 for component in('voice','robot'):
  if component=='robot'and not safe_to_reload(get(8801,'/status',True),get(8787,'/api/session')):
   write('partial_voice_only_user_became_active');return
  subprocess.run([PY,str(MAIN/'scripts/services.py'),'restart','--component',component],cwd=MAIN,check=True)
 deadline=time.monotonic()+180
 while time.monotonic()<deadline:
  try:
   now=get(8801,'/status',True);voice=get(8787,'/api/session')
   if now.get('ready')and now.get('execution_service_revision')=='R7-T3.2':
    assert now['state']=='idle'and now['task_id']is None and now['policy_action_steps']==0
    assert now['policy_metadata']==s['policy_metadata'];assert voice['voice_connected']is False
    (OUT/'POST_DEPLOY_STATUS.json').write_text(json.dumps(now,ensure_ascii=False,indent=2));write('deployed',new_episode=now['episode_id'],revision=now['execution_service_revision'],weights_sha256=now['policy_metadata']['weights_sha256'],policy_actions=0);return
  except(OSError,ValueError):pass
  time.sleep(1)
 write('verification_failed_no_automatic_second_reload');raise RuntimeError('new main service not verified')
if __name__=='__main__':main()
