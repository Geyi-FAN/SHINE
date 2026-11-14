"""Audit actual evidence, not benchmark reference answers."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parents[1]
def rows(path):return[json.loads(x)for x in path.read_text().splitlines()if x.strip()]if path.exists()else[]
def audit(case):
 events=rows(case/'gateway.jsonl');transcripts=[e['prompt']for e in events if e['kind']=='literal_conditioning_updated'and e.get('asr')is not None];setup=[e['prompt']for e in events if e['kind']=='literal_conditioning_updated'and e.get('asr')is None]
 calls=[e for e in events if e['kind']=='executor_input'];bad=[x['prompt']for x in calls if x['prompt']not in transcripts+setup]
 shape_bad=[];npzs=list((case/'policy_inputs').glob('*.npz'))
 for p in npzs:
  with np.load(p,allow_pickle=False)as z:
   if set(z.files)!={'image','wrist','state','prompt'}or z['image'].shape!=(224,224,3)or z['wrist'].shape!=(224,224,3)or z['state'].shape!=(8,):shape_bad.append(str(p))
   if str(z['prompt'])not in transcripts+setup:bad.append(str(p))
 outputs=list((case/'client').glob('output*.wav'))
 return dict(directory=str(case),inferences=len(calls),saved_policy_inputs=len(npzs),asr_transcripts=transcripts,typed_setup_instructions=setup,nonliteral_requests=bad,sensor_schema_errors=shape_bad,output_wav_count=len(outputs),passed=not bad and not shape_bad and not outputs)
def main():
 p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();out=[audit(c)for c in sorted((a.run/'cases').iterdir())if(c/'ENGINE_FINISHED.json').exists()]
 payload=dict(cases=out,total=len(out),passed=all(x['passed']for x in out),input_contract='actual_ASR_text_or_declared_T6_controlled_setup_only; MAIN224_WRIST224_state8; no GT coordinates or planned subgoals')
 (a.run/'INPUT_AUDIT.json').write_text(json.dumps(payload,indent=2));print(json.dumps({k:v for k,v in payload.items()if k!='cases'}));assert payload['passed']
if __name__=='__main__':main()
