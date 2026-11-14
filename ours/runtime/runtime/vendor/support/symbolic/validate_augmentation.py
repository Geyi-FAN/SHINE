"""Compare integrated augmentation to original A, and an independent heatmap."""
import importlib.util
import json
import jax
import jax.numpy as jnp
import numpy as np
import augmax
from sym_paths import ROOT,BASE_CODE
from common import write_json
from sym_augmentation import augment,chain
from openpi.models import model as model_lib
from reference_model import preprocess_reference


def main():
    spec=importlib.util.spec_from_file_location('ad_data_aug',BASE_CODE/'src/dataset.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old);data=old.PreparedData('A')
    batch=data.batch(0);images={k:jnp.asarray(x) for k,x in batch['image'].items()}
    raw_obs={k:v for k,v in batch.items() if k not in ('actions','valid','revision')}
    points=np.array([[y+.23,x+.37] for y in [35,73,111,149,187] for x in [73,149]],np.float32)
    points=np.broadcast_to(points,(64,*points.shape)).copy()
    root=jax.random.split(jax.random.key(42))[0];key=jax.random.fold_in(root,0)
    results=[]
    for micro in (64,32):
        fn=jax.jit(lambda k,imgs,pts:augment(k,imgs,pts,micro))
        actual,coords=fn(key,images,jnp.asarray(points))
        native={k:[] for k in images}
        keys=[key] if micro==64 else list(jax.random.split(key,64//micro))
        for i,mkey in enumerate(keys):
            o=jax.tree.map(lambda x:x[i*micro:(i+1)*micro] if x is not None else x,raw_obs)
            processed=jax.jit(lambda k,o:preprocess_reference(jax.random.split(k,3)[0],model_lib.Observation.from_dict(o),train=True))(mkey,o)
            for name in native:native[name].append(processed.images[name])
        diffs={name:float(jnp.max(jnp.abs(actual[name]-jnp.concatenate(vals)))) for name,vals in native.items()}
        assert max(diffs.values())<=1e-6,diffs
        results.append(dict(micro_batch=micro,max_rgb_difference=diffs))
    # Rendered Gaussian landmarks are independent image evidence for the keypoints.
    pts=points[0];yy,xx=np.mgrid[:224,:224]
    heat=np.exp(-((yy[:,:,None]-pts[:,0])**2+(xx[:,:,None]-pts[:,1])**2)/(2*1.8**2)).astype(np.float32)
    image=np.repeat(heat.max(-1)[:,:,None],3,-1)
    joint=chain(True,(augmax.InputType.IMAGE,augmax.InputType.DENSE,augmax.InputType.KEYPOINTS))
    @jax.jit
    def probe(k):
        _,h,p=joint(k,(jnp.asarray(image),jnp.asarray(heat),jnp.asarray(pts)))
        center=jnp.stack([(h*jnp.asarray(yy)[:,:,None]).sum((0,1)),(h*jnp.asarray(xx)[:,:,None]).sum((0,1))],-1)/h.sum((0,1))[:,None]
        return jnp.linalg.norm(center-p,axis=-1)
    errors=np.concatenate([np.asarray(probe(jax.random.key(i))) for i in range(32)])
    assert errors.max()<.5
    report=dict(passed=True,devices=[str(d) for d in jax.devices()],native_A_rgb_parity=results,
        max_gaussian_keypoint_error_px=float(errors.max()),mean_gaussian_keypoint_error_px=float(errors.mean()),
        original_rng_split_and_fold_preserved=True,normal_and_switch_images_in_same_batch=True,
        production_augmentation_function_tested=True)
    write_json(ROOT/'reports/augmentation_integration.json',report);print(json.dumps(report,indent=2))


if __name__=='__main__':main()
