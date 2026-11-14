"""Preserve authored scripts/audio, bind all three approved native states."""
import hashlib,json,shutil
from pathlib import Path
B=Path(__file__).resolve().parents[1]
SOURCE=Path('/mnt/disk_4/geyi/audio_switch_benchmark_dev_v1/dev96_20261031/dataset')
OUT=Path('/mnt/disk_4/geyi/audio_switch24_F28d_G22_20261102')
IDS=[f'T{i}_01'for i in range(1,9)]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 OUT.mkdir(parents=True,exist_ok=False);data=OUT/'dataset';data.mkdir();cases=json.loads((SOURCE/'selected.private.json').read_text());selected=[c for c in cases if c['script_id']in IDS];assert len(selected)==24
 states=json.loads((SOURCE/'initial_states.json').read_text());states=[dict(s,assets={k:dict(v,path=str((SOURCE/v['path']).resolve()))for k,v in s['assets'].items()})for s in states]
 for s in states:
  for a in s['assets'].values():assert sha(a['path'])==a['sha256']
 audio=json.loads(Path('/mnt/disk_4/geyi/audio_switch_benchmark_dev_v1/frozen_audio_20261031/manifest.json').read_text());texts={t['text']for c in selected for t in c['turns']};texts.add('Please put the bowl on the stove.')
 for c in selected:texts.update(c.get('clarification_answers',{}).values())
 audio=[a for a in audio if a['text']in texts];assert {a['text']for a in audio}==texts
 for a in audio:assert a['human_audio_review']=='pass'and sha(a['file'])==a['sha256']
 for name,content in [('selected.private.json',selected),('initial_states.json',states),('audio.json',audio)]: (data/name).write_text(json.dumps(content,ensure_ascii=False,indent=2)+'\n')
 protocol=json.loads((SOURCE/'PROTOCOL.json').read_text());protocol.update(version='audio-switch24-f28d-g22-v1',parent_protocol=protocol['version'],status='frozen_development_subset_not_heldout',executor='SmolVLA E3 v4 raw30000',selection=dict(scripts=IDS,states=['LIVE8787_I00','LIVE8787_I01','LIVE8787_I02'],replicates=1,selected_before_results=True),execution=dict(base_commit='f1f6f69',changes='evaluation instrumentation and orchestration only; policy/Agent/YOLO/M1/completion method frozen',input='real-time PCM CLI; no browser/text injection for scored turns',source='unscored accepted TTS predecessor through same voice system; actual policy actions; failure retained',trigger='controlled held-bowl window for pause/switch/reference/waiting; release for QA/backchannels; physics continues unless explicit pause',terminal_hold='40 real physics ticks with current-pose hold; never fake ticks during pause',pause_samples='passive wall-time observations, zero env.step',physical_source='private recorder only; no GT or next subgoal supplied to Agent',standalone_return='independent authored return contract; no replacement of policy by Oracle; evaluator can stop after observed goal plus40 real hold ticks',cloud_fallback=False,jobs=2))
 (data/'PROTOCOL.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n');shutil.copy2(SOURCE/'scene_contract.json',data/'scene_contract.json')
 reference=B/'audio24/reference';reference.mkdir(exist_ok=True)
 prod=Path('/mnt/disk_2/geyi/voice_pi05_harness/scripts/audio_switch_benchmark')
 for name in ['score_dev96.py','score_preflight.py','aggregate.py','dialogue_branches.mjs','t5_dialogue.mjs']:shutil.copy2(prod/name,reference/name)
 rules=Path('/mnt/disk_2/geyi/voice_pi05_harness/docs/evaluation/audio_switch_benchmark_v1/physical_v2.5.0-candidate.frozen.json');shutil.copy2(rules,data/rules.name)
 assert sha(data/rules.name)==protocol['physical']['sha256']
 (OUT/'SELECTION.md').write_text('# 冻结24例\n\n既有T1_01至T8_01，每条I00/I01/I02，首次结果全保留；开发集子集，不是正式泛化成绩。\n\n'+ '\n'.join(f"- {c['case_id']}：{c['title']}"for c in selected)+'\n')
 print(json.dumps(dict(root=str(OUT),cases=len(selected),audio=len(audio)),ensure_ascii=False))
if __name__=='__main__':main()
