"""Match official float64 norm-stat arithmetic before native state tokenization.
Frozen prepared artifacts remain unchanged; corrected tokens live in runtime config.
"""
import gzip,json,os
from pathlib import Path
import numpy as np
from common import ROOT,write_json
from schema import ROOT as DATA
from openpi.models.tokenizer import PaligemmaTokenizer

def main():
 a=np.load(DATA/'cache/anchors.npz')['state'];norm=json.loads((Path(os.environ['INITIAL_CHECKPOINT'])/'assets/physical-intelligence/libero/norm_stats.json').read_text())['norm_stats']['state']
 low=np.array(norm['q01'][:8]);high=np.array(norm['q99'][:8]);native=(a-low)/(high-low+1e-6)*2-1
 old=(a-low.astype(np.float32))/(high.astype(np.float32)-low.astype(np.float32)+1e-6)*2-1
 bins=np.linspace(-1,1,257)[:-1];ids=set(np.flatnonzero(np.any(np.digitize(native,bins)!=np.digitize(old,bins),axis=1)).tolist())
 tokenizer=PaligemmaTokenizer(200);result={'schema':'official_norm_precision_correction.v1','count':len(ids),'A':{},'C':{}}
 with gzip.open(DATA/'cache/prompts.jsonl.gz','rt') as f:
  for i,line in enumerate(f):
   if i in ids:
    p=json.loads(line)
    for v in ['A','C']:
     t,m=tokenizer.tokenize(p[v],native[i]);result[v][str(i)]={'tokens':t.tolist(),'mask':m.tolist()}
 write_json(ROOT/'configs/token_corrections.json',result);print('Corrected native state token precision for',len(ids),'anchors; frozen cache unchanged')
if __name__=='__main__':main()
