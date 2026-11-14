"""Check the exact cached four-arm inputs without allocating CUDA."""
import json,os
from pathlib import Path
import numpy as np
from common import ROOT,read_config,sha256,write_json
from schema import ROOT as DATA,WORK
from dataset import PreparedData

def main():
 report=json.loads((DATA/'reports/VALIDATION.json').read_text());assert report['passed']
 hashes=json.loads((DATA/'reports/ARTIFACT_HASHES.json').read_text());checked=0
 # Verify immutable numeric/token/reference artifacts and case definitions.
 for k,v in hashes.items():
  if k.startswith('cache/') or k in ('train/episodes.json','train/normal_samples.json','mini/cases.jsonl','mini/protocol.json'):
   assert sha256(DATA/k)==v,k;checked+=1
 ds={v:PreparedData(v) for v in 'ABCD'}
 for step in [0,1,500,1404,2808]:
  bs={v:d.batch(step) for v,d in ds.items()}
  for v in 'BCD':
   for k in ['state','actions','valid','revision']:np.testing.assert_array_equal(bs['A'][k],bs[v][k])
   for k in ['base_0_rgb','left_wrist_0_rgb']:np.testing.assert_array_equal(bs['A']['image'][k],bs[v]['image'][k])
  for a,b in [('A','B'),('C','D')]:np.testing.assert_array_equal(bs[a]['tokenized_prompt'],bs[b]['tokenized_prompt'])
  np.testing.assert_array_equal(bs['B']['image']['right_wrist_0_rgb'],bs['D']['image']['right_wrist_0_rgb'])
  assert bs['B']['image_mask']['right_wrist_0_rgb'].all() and not bs['A']['image_mask']['right_wrist_0_rgb'].any()
 cases=[json.loads(l) for l in (DATA/'mini/cases.jsonl').read_text().splitlines()];assert len(cases)==200
 for c in cases:
  for k in ['context_file','snapshot_file','initial_state_file','reference_image','bddl_file']:
   if k in c:assert Path(c[k].replace('/mnt/disk_2/geyi',str(WORK),1)).is_file(),(c['case_id'],k)
 result=dict(passed=True,checked_artifact_hashes=checked,training_episodes=712,new_episodes=72,mini_cases=200,steps=2809,
   paired_batches_verified=[0,1,500,1404,2808],original_validation=report,GT_schema=json.loads((DATA/'reports/GT_SCHEMA.json').read_text()),
   normal_GT='unavailable',privileged_GT_variants=['C','D'],reference_variants=['B','D'],source_files_modified=False)
 write_json(ROOT/'reports/DATA_PREFLIGHT.json',result);print(json.dumps({k:v for k,v in result.items() if k!='original_validation'},ensure_ascii=False))
if __name__=='__main__':main()
