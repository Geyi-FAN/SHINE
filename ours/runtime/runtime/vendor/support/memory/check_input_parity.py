"""Compare cached training tensors with the real inference transform chain."""
import gzip,json,os
from pathlib import Path
import numpy as np
from openpi import transforms
from openpi.training import checkpoints
from common import ROOT,write_json
from schema import ROOT as DATA
from dataset import PreparedData
from model_config import make_config

def main():
 with gzip.open(DATA/'cache/prompts.jsonl.gz','rt') as f:prompts=[json.loads(x) for x in f]
 count=0;maxerr=0.
 for variant in 'ABCD':
  import common
  common.VARIANT=variant
  cfg=make_config('input_parity');dc=cfg.data.create(cfg.assets_dirs,cfg.model)
  stats=checkpoints.load_norm_stats(Path(os.environ['INITIAL_CHECKPOINT'])/'assets',dc.asset_id)
  transform=transforms.compose([*dc.data_transforms.inputs,transforms.Normalize(stats,use_quantiles=dc.use_quantile_norm),*dc.model_transforms.inputs])
  d=PreparedData(variant)
  for step in [0,500,2808]:
   b=d.batch(step)
   for k in [0,15,16,40,63]:
    idx=d.schedule[step,k];x={'observation/image':b['image']['base_0_rgb'][k],'observation/wrist_image':b['image']['left_wrist_0_rgb'][k],'observation/state':d.anchors['state'][idx], 'prompt':prompts[idx][variant]}
    if variant in 'BD':x['observation/initial_image']=b['image']['right_wrist_0_rgb'][k]
    native=transform(x)
    for name in ['tokenized_prompt','tokenized_prompt_mask']:np.testing.assert_array_equal(native[name],b[name][k])
    np.testing.assert_allclose(native['state'],b['state'][k],atol=1e-6,rtol=1e-6);maxerr=max(maxerr,float(np.max(np.abs(native['state']-b['state'][k]))))
    for name in native['image']:
     np.testing.assert_array_equal(native['image'][name],b['image'][name][k]);assert native['image_mask'][name]==b['image_mask'][name][k]
    count+=1
  corrections=json.loads((ROOT/'configs/token_corrections.json').read_text())['A' if variant in 'AB' else 'C']
  from openpi.models.tokenizer import PaligemmaTokenizer
  tok=PaligemmaTokenizer(200);norm=stats['state'];raw=d.anchors['state']
  z=(raw-norm.q01[:8])/(norm.q99[:8]-norm.q01[:8]+1e-6)*2-1
  for i in map(int,corrections):
   t,m=tok.tokenize(prompts[i][variant],z[i]);ct,cm=d.token_batch([i]);np.testing.assert_array_equal(t,ct[0]);np.testing.assert_array_equal(m,cm[0]);count+=1
 write_json(ROOT/'reports/INPUT_PARITY.json',dict(passed=True,examples=count,max_state_normalization_error=maxerr,tokens_exact=True,image_pixels_exact=True,masks_exact=True));print('INPUT PARITY PASSED',count,maxerr)
if __name__=='__main__':main()
