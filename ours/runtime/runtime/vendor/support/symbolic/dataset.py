"""Thin, immutable adapter over A-D tensors plus symbolic annotation sidecars."""
import importlib.util
import json
import os
import numpy as np
from sym_paths import BASE_CODE,BASE_DATA,DATA
from sym_contract import prompt
from common import VARIANT

spec=importlib.util.spec_from_file_location('original_ad_dataset',BASE_CODE/'src/dataset.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class P1Data(module.PreparedData):
    def __init__(self):
        super().__init__('A')
        self.schedule=np.concatenate([self.schedule,self.schedule],axis=0)
        self.arm=VARIANT
        self.symbolic=json.loads((DATA/'manifest.json').read_text())
        if not self.symbolic.get('complete'):raise RuntimeError('Symbolic labels incomplete')
        self.plans=json.loads((DATA/'plans.json').read_text())
        self.points=np.load(DATA/'points.npy',mmap_mode='r');self.point_valid=np.load(DATA/'point_valid.npy',mmap_mode='r')
        self.stages=np.load(DATA/'stages.npy',mmap_mode='r')
        self.marker_roles=np.load(DATA/'marker_roles.npy',mmap_mode='r')
        from openpi.models.tokenizer import PaligemmaTokenizer
        self.tokenizer=PaligemmaTokenizer(200)
        from pathlib import Path
        norm=json.loads((Path(os.environ['INITIAL_CHECKPOINT'])/'assets/physical-intelligence/libero/norm_stats.json').read_text())['norm_stats']['state']
        lo=np.asarray(norm['q01'][:8],np.float64);hi=np.asarray(norm['q99'][:8],np.float64)
        self.token_state=(self.anchors['state']-lo)/(hi-lo+1e-6)*2-1

    def symbolic_tokens(self,step,updated_points):
        ids=self.schedule[step];tokens,masks=self.token_batch(ids);texts=[]
        for j,idx in enumerate(ids):
            if not self.anchors['revision'][idx]:
                texts.append(None);continue
            plan=self.plans[int(self.anchors['episode'][idx])]
            raw=prompt(plan,self.arm,int(self.stages[idx]),updated_points[j],self.point_valid[idx])
            # The native tokenizer itself truncates; reject overflow beforehand.
            bins=np.digitize(self.token_state[idx],np.linspace(-1,1,257)[:-1])-1
            full=f"Task: {raw.strip().replace('_',' ').replace(chr(10),' ')}, State: {' '.join(map(str,bins))};\nAction: "
            count=len(self.tokenizer._tokenizer.encode(full,add_bos=True))
            if count>200:raise ValueError(('Prompt overflow after augmentation',self.arm,int(idx),count))
            tokens[j],masks[j]=self.tokenizer.tokenize(raw,self.token_state[idx]);texts.append(raw)
        return tokens,masks,texts

    def marker_batch(self,step,updated_points):
        from v3_markers import select_points
        ids=self.schedule[step]
        return select_points(updated_points,self.point_valid[ids],self.marker_roles[ids])
