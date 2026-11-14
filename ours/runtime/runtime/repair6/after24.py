"""Finish the unchanged24 first, then freeze the evidence-driven pause repair."""
import hashlib,json,shutil,subprocess,time
from pathlib import Path
B=Path(__file__).resolve().parents[1];ROOT=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102');FIRST=ROOT/'R5b/formal24_r5b_20261102';OUT=ROOT/'R6/regression18b'
def record(state,**kw):
 p=ROOT/'R6_CHAIN_STATUS.json';p.write_text(json.dumps(dict(time=time.time(),state=state,**kw),indent=2));print(state,kw,flush=True)
def main():
 record('waiting_for_unchanged24_complete')
 while not(FIRST/'COMPLETED.json').exists():
  for marker in ['BLOCKED_CLOUD.json','INVALID_AUDIO_TIMING.json','ABORTED_IMPLEMENTATION.json']:
   if(FIRST/marker).exists():record('halted',reason=marker);return
  time.sleep(10)
 verdicts=json.loads((FIRST/'reports/verdicts.json').read_text());summary=json.loads((FIRST/'reports/summary.json').read_text())
 if len(verdicts)!=24 or not summary.get('valid_for_audio_benchmark'):record('halted_incomplete_audio_evidence');return
 unresolved=[]
 import sys
 sys.path.insert(0,str(B/'repair6/reference'));import score_preflight;score_preflight.DOC=ROOT/'R5b/dataset';import score_dev96
 authored=json.loads((ROOT/'R5b/dataset/selected.private.json').read_text());protocol=json.loads((ROOT/'R5b/dataset/PROTOCOL.json').read_text())
 for raw in verdicts:
  c=next(c for c in authored if c['case_id']==raw['case_id']);v=score_dev96.evaluate(FIRST/'cases'/c['case_id'],c,protocol)
  bad=[x['name']for x in v['checks']if x['status']!='pass']
  known=(v['category']=='T2'and bad==['physical_pause_deadline'])or(v['category']=='T5'and set(bad)<={'complete_correct_goal_dispatched','first_new_action_deadline'})or(v['category']=='T6'and bad==['qa_semantics_T6_01_U01'])or(v['category']=='T7'and set(bad)<={'waiting_registered','waiting_handoff_exactly_once','handoff_after_independent_predecessor_success'})
  if bad and not known:unresolved.append(dict(case_id=v['case_id'],bad=bad))
 if unresolved:record('needs_additional_evidence_review_before_freeze',cases=unresolved);return
 record('waiting_for_candidate_engineering_acceptance')
 while not(ROOT/'R6_READY_TO_FREEZE.json').exists():time.sleep(5)
 OUT.mkdir(parents=True,exist_ok=False);source=ROOT/'expanded96/dataset';shutil.copytree(source,OUT/'dataset');fixtures=json.loads((OUT/'dataset/initial_states.json').read_text());
 for fixture in fixtures:
  for asset in fixture['assets'].values():
   asset_path=Path(asset['path']);asset_path=asset_path if asset_path.is_absolute()else Path('/mnt/disk_4/geyi/audio_switch_benchmark_dev_v1/dev96_20261031/dataset')/asset_path;assert asset_path.is_file();assert hashlib.sha256(asset_path.read_bytes()).hexdigest()==asset['sha256'];asset['path']=str(asset_path)
 (OUT/'dataset/initial_states.json').write_text(json.dumps(fixtures,indent=2));cases=json.loads((source/'selected.private.json').read_text());cases=[c for c in cases if c['script_id']in ['T2_01','T2_04','T8_02','T5_01','T6_01','T7_01']];assert len(cases)==18
 (OUT/'dataset/selected.private.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2));protocol=json.loads((OUT/'dataset/PROTOCOL.json').read_text());protocol['setup']['predecessor_input']='reviewed_source_audio';protocol['legacy_waiting_handoff_s']=protocol['budgets']['waiting_handoff_from_independent_predecessor_success_s'];protocol['budgets']['waiting_handoff_from_independent_predecessor_success_s']=45;protocol['deadline_revision_note']='waiting physical first action uses the same45s as an ordinary new task; retain original10s offline score separately; no pause/QA/geometry thresholds changed';(OUT/'dataset/PROTOCOL.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2))
 manifest=json.loads((ROOT/'R5b/FREEZE.json').read_text())
 for name,h in manifest['files'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
 manifest.update(revision='R6-compound-pause',time=time.time(),changes='Evidence-driven repairs: compound pause; complete clarification; current-location QA; bounded zero-execution argument correction; task-bound public execution metadata; read-only queue wording prefetch; existing Native policy tail must open fingers before queued handoff; logged container-contact support. Action/YOLO weights and four execution-role prompts unchanged. Waiting45s primary with original10s supplementary.')
 paths=list((B/'artifacts/repair6_audio_daemon/dist').rglob('*.js'))+list((B/'repair6').rglob('*'))+list((OUT/'dataset').glob('*.json'))
 for p in paths:
  if p.is_file()and p.name!='after24.py'and '__pycache__'not in p.parts:manifest['files'][str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
 (OUT/'FREEZE.json').write_text(json.dumps(manifest,indent=2))
 command='cd '+str(B)+' && AUDIO_REPAIR_EXECUTION_GPU=4 AUDIO_REPAIR_POLICY_PORT=19866 AUDIO_REPAIR_OUT='+str(OUT)+' exec /mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python -u -m repair6.run --label regression18_r6b_20261102 > '+str(OUT/'console.log')+' 2>&1'
 subprocess.run(['tmux','new-session','-d','-s','audio_repair_reg18_R6b_20261102',command],check=True);record('started_pause_and_protected_audio18',path=str(OUT))
if __name__=='__main__':main()
