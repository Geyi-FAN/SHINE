import ast,json
from pathlib import Path
import numpy as np
from sym_paths import ROOT,DATA,BASE_DATA
from common import write_json,sha256
from dataset import P1Data

def main():
 parent=Path('/mnt/disk_2/geyi/pi05_symbolic_V3_20261015');e3=Path('/mnt/disk_4/geyi/pi05_symbolic_E1_E3_20261015/data');v3=Path('/mnt/disk_4/geyi/pi05_symbolic_V3_20261015/data')
 for name in ['sym_geometry.py','sym_augmentation.py']:assert sha256(ROOT/'src'/name)==sha256(parent/'src'/name)
 def nodes(p):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(p.read_text()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name!='prompt'}
 assert nodes(ROOT/'src/sym_contract.py')==nodes(parent/'src/sym_contract.py')
 d=P1Data();orig=np.load(BASE_DATA/'cache/batches.npy');np.testing.assert_array_equal(d.schedule,np.concatenate([orig,orig]));assert d.schedule.shape==(5618,64)
 assert np.all(d.anchors['revision'][d.schedule].sum(1)==48)
 roles=np.load(DATA/'marker_roles.npy');on=roles>=0;assert on.sum()==23238 and set(roles[on])=={7}
 for name in ['tokens','token_masks']:
  ours=np.load(DATA/f'{name}_V3R.npy',mmap_mode='r');old=np.load(e3/f'{name}_E3.npy',mmap_mode='r');visual=np.load(v3/f'{name}_V3.npy',mmap_mode='r')
  np.testing.assert_array_equal(ours[~on],old[~on]);np.testing.assert_array_equal(ours[on],visual[on])
 c=json.loads((ROOT/'configs/V3R.json').read_text());old=json.loads((parent/'configs/V3.json').read_text());keys=['batch_size','revision_per_batch','seed','action_horizon','action_dim','max_token_len','peak_lr','end_lr','warmup_steps','ema_decay','gradient_clip','weight_decay','lr_schedule_steps']
 for k in keys:assert c[k]==old[k],k
 write_json(ROOT/'reports/E3_alignment.json',dict(passed=True,non_return_token_parity_E3=int((~on).sum()),return_token_parity_V3=int(on.sum()),causal_compiler_and_oracle_unchanged=True,geometry_and_augmentation_unchanged=True,schedule_shape=list(d.schedule.shape),both_epochs_original_schedule=True,recipe_unchanged_except_epochs=True))
 print('Alignment checks passed',flush=True)
if __name__=='__main__':main()
