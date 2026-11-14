"""Audit every V3R prompt AND marker selection in the actual seeded epoch."""
import json
import jax
import numpy as np
from sym_paths import ROOT
from common import write_json
from dataset import P1Data
from sym_augmentation import points_only
from sym_contract import prompt
from v3_markers import LEGEND,UNAVAILABLE

def main():
    data=P1Data();fn=jax.jit(points_only);root=jax.random.split(jax.random.key(42))[0]
    tok=data.tokenizer._tokenizer;bins=np.digitize(data.token_state,np.linspace(-1,1,257)[:-1])-1
    states=[' '.join(map(str,x)) for x in bins];covered=np.zeros(len(data.points),np.int32)
    n=0;maxlen=0;drawn=0;invalid=0;normal=0
    for step,ids in enumerate(data.schedule):
        pts=np.asarray(fn(jax.random.fold_in(root,step),np.asarray(data.points[ids])))
        coords,good=data.marker_batch(step,pts);np.add.at(covered,ids,1);texts=[]
        for j,i in enumerate(ids):
            if not data.anchors['revision'][i]:assert not good[j];normal+=1;continue
            plan=data.plans[int(data.anchors['episode'][i])];raw=prompt(plan,'V3R',int(data.stages[i]),pts[j],data.point_valid[i])
            base=prompt(plan,'E3',int(data.stages[i]),pts[j],data.point_valid[i])
            assert raw==base+(LEGEND if good[j] else ''),('E3 parity',step,int(i))
            if good[j]:
                y,x=coords[j];assert f'<{y},{x}>' in raw.split('Current Subgoal:')[1] and raw.endswith(LEGEND);drawn+=1
            elif data.marker_roles[i]>=0:assert not raw.endswith(LEGEND);invalid+=1
            texts.append(f"Task: {raw.strip().replace('_',' ').replace(chr(10),' ')}, State: {states[i]};\nAction: ")
        seq=tok.encode(texts,add_bos=True,num_threads=1);longest=max(map(len,seq));assert longest<=200,(step,longest)
        maxlen=max(maxlen,longest);n+=len(seq)
        if step%300==0:print('Audited batch',step,flush=True)
    assert np.all(covered>0)
    out=dict(passed=True,batches=len(data.schedule),global_batch=64,micro_batch=64,seed=42,
        covered_unique_anchors=int(np.count_nonzero(covered)),scheduled_switch_samples=n,
        scheduled_normal_samples=normal,max_tokens=maxlen,overflow=0,drawn_markers=drawn,
        unavailable_markers=invalid,text_marker_coordinate_mismatches=0,
        normal_tokens='All 44944 unique normal anchors checked in dataset_build.json',
        actual_training_retokens_and_rejects_overflow=True)
    write_json(ROOT/'reports/scheduled_prompt_lengths.json',out);print(json.dumps(out,indent=2))

if __name__=='__main__':main()
