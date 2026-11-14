"""Reuse 32 approved scripts and all3 approved live8787 states; no new audio."""
import hashlib,json,shutil
from pathlib import Path
SOURCE=Path('/mnt/disk_4/geyi/audio_switch_benchmark_dev_v1/dev96_20261031/dataset')
AUDIO=Path('/mnt/disk_4/geyi/audio_switch_benchmark_dev_v1/frozen_audio_20261031/manifest.json')
BASE=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102')
TARGET_MAP={'bowl_on_stove':1,'bowl_on_plate':8,'cheese_in_bowl':6,'wine_on_cabinet':2,'bowl_at_episode_start_released':1,'cheese_on_stove':6}
def execution_spec(c):
 sid=c['script_id'];pre=c['precondition'];source=pre.startswith(('running bowl_to_stove','paused bowl_to_stove'))
 plan=dict(source_task=1,target_task=TARGET_MAP.get(c['private_contract']['target'],0),context_turns=['put the bowl on the stove']if source else[],phase='M2'if source else None,start_paused=pre.startswith('paused'),restore='bowl'if sid in('T4_01','T3_02')else None,return_only=sid=='T4_01',preserve_bowl=sid in('T4_02','T7_01'),prelude_qa=None)
 if sid=='T4_02':plan.update(source_task=1,context_turns=['put the bowl on the stove'],source_completion_required=True)
 if sid=='T6_02':plan.update(source_task=6,context_turns=['put the cream cheese in the bowl','put the wine bottle on top of the cabinet'],source_completion_required=True,second_source_held='wine_bottle',phase='M2')
 if sid=='T3_04':plan.update(source_task=0,context_turns=['open the middle drawer of the cabinet and disengage from the cabinet'],source_completion_required=True)
 if sid=='T4_04':plan.update(prelude_qa='Where is the bowl right now?',custom_goal_predicate=['on','cream_cheese_1','flat_stove_1_cook_region'],unsupported_native_task='cheese_on_stove; language handling tested, not in ten trained complete tasks')
 plan.update(setup_mode='unscored_public_text_policy_execution',held_source_entity='wine_bottle'if sid=='T6_02'else'bowl'if source else None,source_window_task_count=2 if sid=='T6_02'else 1)
 return plan
def main():
 out=BASE/'expanded96/dataset';out.mkdir(parents=True,exist_ok=True)
 for name in ('selected.private.json','initial_states.json','PROTOCOL.json','scene_contract.json','physical_v2.5.0-candidate.frozen.json'):
  if(SOURCE/name).exists():shutil.copyfile(SOURCE/name,out/name)
 protocol=json.loads((out/'PROTOCOL.json').read_text());parent=json.loads((BASE/'dataset/PROTOCOL.json').read_text());protocol['evidence_implementation']=parent.get('evidence_implementation',{});protocol['repair_round']=parent.get('repair_round',{});protocol['setup']['method']='unscored public text authorization + same-policy actual execution; all scored turns real reviewed PCM; no pose write/reset';(out/'PROTOCOL.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2))
 audio=json.loads(AUDIO.read_text());cases=json.loads((out/'selected.private.json').read_text());clips={a['text']:a for a in audio}
 missing=[]
 for c in cases:
  plan=execution_spec(c)
  texts=[t['text']for t in c['turns']]+plan['context_turns']+list(c.get('clarification_answers',{}).values())
  if plan['prelude_qa']:texts.append(plan['prelude_qa'])
  # Predecessor preparation is unscored public typed authorization, not a
  # waveform, pose injection or reset. Only scored turns/QA need audio.
  texts=[t['text']for t in c['turns']]+list(c.get('clarification_answers',{}).values())+([plan['prelude_qa']]if plan['prelude_qa']else[])
  missing.extend((c['case_id'],t)for t in texts if t not in clips)
 for a in audio:assert hashlib.sha256(Path(a['file']).read_bytes()).hexdigest()==a['sha256']
 (out/'audio.json').write_text(json.dumps(audio,ensure_ascii=False,indent=2));(out/'execution_specs.json').write_text(json.dumps({c['case_id']:execution_spec(c)for c in cases},indent=2))
 review=dict(cases=len(cases),scripts=len({c['script_id']for c in cases}),states=len({c['scene_binding']['state_id']for c in cases}),audios=len(audio),missing_reviewed_audio=missing,physical_eligible=sum(c['private_contract']['physical_eligible']for c in cases),tts_newly_generated=0,formally_run=0)
 (out/'READINESS.json').write_text(json.dumps(review,indent=2));print(json.dumps(review))
if __name__=='__main__':main()
