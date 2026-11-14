"""Batch adapter for the prepared A-D inputs. It does not run a trainer."""
import numpy as np
from schema import ROOT, WORK, read

class PreparedData:
    def __init__(self,variant='A'):
        assert variant in 'ABCD';self.variant=variant
        self.cfg=read(ROOT/'train'/f'config_{variant}.json')
        self.preparation=read(ROOT/'train/preparation.json')
        assert self.preparation['image_cache_status']=='complete'
        self.anchors=dict(np.load(ROOT/'cache/anchors.npz'))
        self.schedule=np.load(ROOT/'cache/batches.npy',mmap_mode='r')
        self.tokens=np.load(ROOT/'cache'/f'tokens_{variant}.npy',mmap_mode='r')
        self.masks=np.load(ROOT/'cache'/f'token_masks_{variant}.npy',mmap_mode='r')
        self.refs=np.load(WORK/'pi05_revision_mix13_state_init_4420/data/reference/initial_images.npy',mmap_mode='r')
        self.newrefs=np.load(ROOT/'cache/new_initial_images.npy',mmap_mode='r')
        self.refidx=np.load(ROOT/'cache/reference_index.npy',mmap_mode='r')
        assert self.refidx.shape==(len(self.anchors['episode']),)
        self.images={}
        for key in ['image','wrist_image']:
            self.images[key]=[
                np.load(WORK/'pi05_revision_p1/data/images'/f'{key}.npy',mmap_mode='r'),
                np.load(ROOT/'cache'/f'new_{key}.npy',mmap_mode='r'),
                np.load(WORK/'pi05_revision_mix13_2210/data/images'/f'{key}.npy',mmap_mode='r'),
                np.load(WORK/'pi05_revision_mix13_4420/data/images'/f'{key}.npy',mmap_mode='r')]
        norm=read(__import__('pathlib').Path(__import__('os').environ.get('INITIAL_CHECKPOINT',self.cfg['initial_checkpoint']))/'assets/physical-intelligence/libero/norm_stats.json')['norm_stats']
        self.normalized={}
        for key in ['state','actions']:
            a=self.anchors[key];dim=a.shape[-1]
            low=np.asarray(norm[key]['q01'][:dim],np.float64);high=np.asarray(norm[key]['q99'][:dim],np.float64)
            z=(a-low)/(high-low+1e-6)*2-1
            self.normalized[key]=np.pad(z.astype(np.float32),[(0,0)]*(z.ndim-1)+[(0,32-dim)])

        from pathlib import Path
        corrections=read(Path(__file__).resolve().parents[1]/'configs/token_corrections.json')
        self.token_corrections=corrections['A' if variant in 'AB' else 'C']

    def token_batch(self,ids):
        tokens=np.array(self.tokens[ids],copy=True);masks=np.array(self.masks[ids],copy=True)
        for j,i in enumerate(ids):
            if str(i) in self.token_corrections:
                fix=self.token_corrections[str(i)];tokens[j]=fix['tokens'];masks[j]=fix['mask']
        return tokens,masks

    def batch(self,step):
        ids=self.schedule[step];old=self.preparation['old_switch_anchors'];rev=self.preparation['revision_anchors']
        m_old=ids<old;m_new=(ids>=old)&(ids<rev);m_norm=ids>=rev
        cams={}
        for key,sets in self.images.items():
            out=np.empty((len(ids),224,224,3),np.uint8)
            out[m_old]=sets[0][ids[m_old]];out[m_new]=sets[1][ids[m_new]-old]
            ni=ids[m_norm]-rev;split=len(sets[2]);nr=np.empty((len(ni),224,224,3),np.uint8)
            take=ni<split;nr[take]=sets[2][ni[take]];nr[~take]=sets[3][ni[~take]-split]
            out[m_norm]=nr;cams[key]=out
        reference=np.zeros_like(cams['image'])
        if self.variant in 'BD':
            reference[m_new]=self.newrefs[self.refidx[ids[m_new]]]
            reference[~m_new]=self.refs[self.refidx[ids[~m_new]]]
        tokens,masks=self.token_batch(ids)
        return dict(image={'base_0_rgb':cams['image'],'left_wrist_0_rgb':cams['wrist_image'],'right_wrist_0_rgb':reference},
                    image_mask={'base_0_rgb':np.ones(len(ids),bool),'left_wrist_0_rgb':np.ones(len(ids),bool),
                                'right_wrist_0_rgb':np.full(len(ids),self.variant in 'BD')},
                    state=self.normalized['state'][ids],actions=self.normalized['actions'][ids],
                    valid=self.anchors['valid'][ids],revision=self.anchors['revision'][ids],
                    tokenized_prompt=tokens,tokenized_prompt_mask=masks)

    def batches(self,start=0,stop=None):
        for step in range(start,len(self.schedule) if stop is None else stop):yield step,self.batch(step)


class P1Data(PreparedData):
    def __init__(self):
        from common import VARIANT
        super().__init__(VARIANT)
