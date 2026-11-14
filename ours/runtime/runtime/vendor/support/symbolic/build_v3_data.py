"""Derive visual-marker labels without changing E3 causal stages/actions/data order."""
import collections,gzip,json,shutil,os
from pathlib import Path
import numpy as np
from sym_paths import ROOT,DATA,BASE_DATA
from common import sha256,write_json
from sym_contract import ROLES,Oracle,prompt
from v3_markers import role_index,select_points,marker_info,STYLE,LEGEND,UNAVAILABLE

SOURCE=Path(os.environ.get('SYMBOLIC_PARENT_DATA','/mnt/disk_4/geyi/pi05_symbolic_E1_E3_20261015/data'))

def main():
    original=json.loads((SOURCE/'manifest.json').read_text())
    assert original['complete'] and original['all_causal_prefix_invariance_checked']
    DATA.mkdir(parents=True,exist_ok=True)
    for name in list(original['derived_hashes'])+['manifest.json']:
        if not (DATA/name).exists():shutil.copy2(SOURCE/name,DATA/name)
    for name,digest in original['derived_hashes'].items():
        assert sha256(SOURCE/name)==digest,(name,'E3 labels changed')
        assert sha256(DATA/name)==digest,(name,'V3R must reuse identical labels')
    for name,digest in original['source_hashes'].items():assert sha256(BASE_DATA/name)==digest
    plans=json.loads((DATA/'plans.json').read_text());anchors=dict(np.load(BASE_DATA/'cache/anchors.npz'))
    stages=np.load(DATA/'stages.npy');points=np.load(DATA/'points.npy');valid=np.load(DATA/'point_valid.npy')
    n=len(stages);roles=np.full(n,-1,np.int16);stage_counts=collections.Counter();role_counts=collections.Counter()
    for i in np.flatnonzero(anchors['revision']):
        plan=plans[int(anchors['episode'][i])];stage=int(stages[i]);roles[i]=role_index(plan,stage)
        stage_counts[plan['stages'][stage]['kind']]+=1
        role_counts[ROLES[roles[i]] if roles[i]>=0 else 'none']+=1
    selected,enabled=select_points(points,valid,roles)
    for name,value in [('marker_roles',roles),('marker_yx',selected),('marker_valid',enabled)]:np.save(DATA/(name+'.npy'),value)
    causal_frames=0
    for ei in range(len(plans)):
        ep=np.load(SOURCE/'episodes'/f'{ei:04d}.npz');oracle=Oracle(plans[ei])
        labels=[oracle.observe(g,int(t)) for g,t in zip(ep['guards'],ep['all_frames'])]
        np.testing.assert_array_equal(labels,ep['all_stages'])
        cut=len(labels)//2;other=Oracle(plans[ei]);changed=ep['guards'].copy();changed[cut:]=~changed[cut:]
        changed_labels=[other.observe(g,int(t)) for g,t in zip(changed,ep['all_frames'])]
        assert labels[:cut]==changed_labels[:cut]
        causal_frames+=len(labels)
    from dataset import P1Data
    data=P1Data();tok=data.tokenizer._tokenizer
    tokens=np.lib.format.open_memmap(DATA/'tokens_V3R.npy',mode='w+',dtype=np.int32,shape=(n,200))
    masks=np.lib.format.open_memmap(DATA/'token_masks_V3R.npy',mode='w+',dtype=bool,shape=(n,200))
    tokens[:]=0;masks[:]=False;lengths=np.zeros(n,np.int16)
    normalized=data.token_state;bins=np.digitize(normalized,np.linspace(-1,1,257)[:-1])-1
    normal_ok=0;examples=[]
    with gzip.open(SOURCE/'prompts_unaugmented.jsonl.gz','rt') as inp,gzip.open(DATA/'prompts_unaugmented.jsonl.gz','wt') as out:
        batch=[];indices=[];raws=[]
        def flush():
            nonlocal normal_ok
            if not batch:return
            seq=tok.encode(batch,add_bos=True,num_threads=8)
            for i,raw,full,ss in zip(indices,raws,batch,seq):
                assert len(ss)<=200,(i,len(ss));tokens[i,:len(ss)]=ss;masks[i,:len(ss)]=True;lengths[i]=len(ss)
                out.write(json.dumps(dict(anchor=i,V3R=raw,marker_role=int(roles[i]),marker_yx=selected[i].tolist() if enabled[i] else None))+'\n')
                if not anchors['revision'][i]:
                    t,m=data.token_batch(np.array([i]));np.testing.assert_array_equal(tokens[i],t[0]);np.testing.assert_array_equal(masks[i],m[0]);normal_ok+=1
                elif len(examples)<12 and (i%9000==0 or not examples):examples.append(dict(anchor=i,prompt=full,token_count=len(ss)))
            batch.clear();indices.clear();raws.clear()
        for i,line in enumerate(inp):
            row=json.loads(line);assert row['anchor']==i
            if anchors['revision'][i]:
                plan=plans[int(anchors['episode'][i])];raw=prompt(plan,'V3R',int(stages[i]),points[i],valid[i])
                base=prompt(plan,'E3',int(stages[i]),points[i],valid[i]);assert base==row['E3']
                assert raw==base+(LEGEND if enabled[i] else '')
            else:raw=row['E3']
            state=' '.join(map(str,bins[i]));full=f"Task: {raw.strip().replace('_',' ').replace(chr(10),' ')}, State: {state};\nAction: "
            batch.append(full);indices.append(i);raws.append(raw)
            if len(batch)>=2048:flush()
        flush();assert i+1==n
    tokens.flush();masks.flush();np.save(DATA/'prompt_lengths.npy',lengths)
    assert normal_ok==original['normal_anchors']
    mini=json.loads((DATA/'mini_plans.json').read_text())
    role_plans={cid:[dict(stage=s,kind=p['stages'][s]['kind'],role_index=role_index(p,s)) for s in range(len(p['stages']))] for cid,p in mini.items()}
    write_json(DATA/'mini_marker_plans.json',role_plans)
    write_json(DATA/'marker_style.json',STYLE)
    manifest={**original,'schema':'visual_marker_dataset.V3R.v1','variant':'V3R','complete':True,
        'parent_symbolic_dataset':str(SOURCE),'parent_manifest_sha256':sha256(SOURCE/'manifest.json'),
        'all_causal_prefix_invariance_checked':True,'causal_replay_frames':causal_frames,
        'marker_style':STYLE,'normal_marker_count':int(enabled[~anchors['revision']].sum()),
        'switch_marker_count':int(enabled.sum()),'switch_no_marker_count':int(anchors['revision'].sum()-enabled.sum()),
        'active_role_counts':dict(role_counts),'stage_anchor_counts':dict(stage_counts),
        'token_audit':{'V3R':dict(anchors=n,max_tokens=int(lengths.max()),overflows=0)},
        'normal_token_parity':True,'shared_labels_equal_E3':True,'original_actions_and_schedule_unchanged':True,
        'point_labels_augmented_at_runtime':True,'raw_images_modified':False,'formal_training_started':False,
        'augmentation_validation_report':str(ROOT/'reports/augmentation_integration.json')}
    manifest['derived_hashes']={name:sha256(DATA/name) for name in list(original['derived_hashes'])+['marker_roles.npy','marker_yx.npy','marker_valid.npy','marker_style.json','tokens_V3R.npy','token_masks_V3R.npy','mini_marker_plans.json']}
    write_json(DATA/'manifest.json',manifest);write_json(ROOT/'reports/dataset_build.json',manifest)
    write_json(ROOT/'reports/actual_prompt_examples.json',examples)
    print(json.dumps({k:manifest[k] for k in ['complete','total_anchors','switch_marker_count','switch_no_marker_count','token_audit','stage_anchor_counts','active_role_counts']},indent=2))

if __name__=='__main__':main()
