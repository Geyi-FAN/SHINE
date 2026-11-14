"""Materialize a portable prepared-data workspace, never copies live checkpoints."""
import argparse,json,os,shutil,subprocess
from pathlib import Path
from common import ROOT,write_json,sha256
from schema import ROOT as DATA,WORK

def main():
 p=argparse.ArgumentParser();p.add_argument('--destination',type=Path,required=True);a=p.parse_args();dest=a.destination.resolve();dest.mkdir(parents=True,exist_ok=True)
 def copy(src,rel=None):
  src=Path(src);rel=rel or src.relative_to(WORK);target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True)
  if src.is_dir():
   target.mkdir(parents=True,exist_ok=True)
   subprocess.run(['rsync','-aL','--exclude=.venv','--exclude=.git','--exclude=__pycache__','--exclude=.jax_cache','--exclude=checkpoints','--exclude=logs','--exclude=smoke_eval','--exclude=evaluations','--exclude=mini/runtime',str(src)+'/',str(target)+'/'],check=True)
  else:
   if not target.exists() or target.stat().st_size!=src.stat().st_size:shutil.copy2(src,target)
 copy(ROOT);copy(DATA)
 for rel in ['pi05_revision_p1/data/images','pi05_revision_mix13_2210/data/images','pi05_revision_mix13_4420/data/images']:
  for key in ['image.npy','wrist_image.npy']:copy(WORK/rel/key)
 copy(WORK/'pi05_revision_mix13_state_init_4420/data/reference/initial_images.npy')
 for rel in ['openpi','memory_dataset_v5_fast60_20261013/pipeline','pi05_layout_memory_20261012/runtime/TurboVLA','pi05_layout_memory_20261012/runtime/LIBERO']:
  copy(WORK/rel)
 copy(WORK/'pi05_revision_p1/goal_new_state_test_p0_3750_v2_stratified/src/sim_state.py')
 cases=[json.loads(l) for l in (DATA/'mini/cases.jsonl').read_text().splitlines()]
 for c in cases:
  for k in ('context_file','snapshot_file','initial_state_file','reference_image','bddl_file'):
   if k in c:
    f=Path(c[k]);copy(f)
    if k=='snapshot_file':copy(f.with_suffix('.json'))
 ck=Path(os.environ['INITIAL_CHECKPOINT']);target=dest/'.cache/openpi/openpi-assets/checkpoints/pi05_libero';target.mkdir(parents=True,exist_ok=True)
 subprocess.run(['rsync','-aL',str(ck)+'/',str(target)+'/'],check=True)
 copy(WORK/'.cache/openpi/big_vision/paligemma_tokenizer.model')
 # The run-time script substitutes the deployed root; retain immutable source
 # cases/configs/protocol hashes and map only lookup paths at runtime.
 write_json(dest/'BUNDLE_INFO.json',dict(schema='memory_ad_portable.v1',source_root=str(WORK),data='pi05_memory_ad_data_20261013',code=ROOT.name,
  initial_checkpoint='.cache/openpi/openpi-assets/checkpoints/pi05_libero',raw_training_hdf_included=False,
  contains_prepared_training_inputs=True,contains_complete_mini_runtime=True,source_reports_included=True))
 print('Bundle materialized:',dest,flush=True)
if __name__=='__main__':main()
