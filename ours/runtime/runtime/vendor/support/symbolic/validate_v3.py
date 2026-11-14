"""Production train/online marker parity, augmentation alignment and fallback gates."""
import re,json
import numpy as np
import jax
import jax.numpy as jnp
from sym_paths import ROOT
from common import write_json
from dataset import P1Data
from sym_augmentation import augment
from sym_contract import prompt
from v3_markers import render_numpy,render_jax,select_points,marker_info,raster_masks,LEGEND,UNAVAILABLE

def main():
    rng=np.random.default_rng(42)
    # Edge/corner + invalid + no-active-subgoal behavior, and online/training parity.
    points=np.array([[0,0],[0,223],[223,0],[223,223],[146,72],[1,1],[222,222],[30,6]],np.int32)
    enabled=np.array([1,1,1,1,1,0,0,1],bool)
    raw=rng.integers(0,256,(8,224,224,3),dtype=np.uint8)
    images={name:raw.astype(np.float32)/255*2-1 for name in ['base_0_rgb','left_wrist_0_rgb','right_wrist_0_rgb']}
    out=jax.jit(render_jax)(images,points,enabled)
    cpu=np.stack([render_numpy(raw[i],dict(yx=points[i].tolist(),valid=bool(enabled[i]))) for i in range(8)])
    np.testing.assert_array_equal(np.rint((np.asarray(out['base_0_rgb'])+1)*127.5).astype(np.uint8),cpu)
    for name in ['left_wrist_0_rgb','right_wrist_0_rgb']:np.testing.assert_array_equal(out[name],images[name])
    for i in range(8):
        if enabled[i]:np.testing.assert_array_equal(cpu[i,points[i,0],points[i,1]],[255,0,0])
        else:np.testing.assert_array_equal(cpu[i],raw[i])
    pp=np.array([[[146.5,72.5]],[[223.01,10]],[[np.nan,3]],[[2,3]],[[2,3]]]);vv=np.array([[1],[1],[1],[0],[1]],bool)
    chosen,good=select_points(pp,vv,np.array([0,0,0,0,-1]));assert good.tolist()==[True,False,False,False,False]
    np.testing.assert_array_equal(chosen[0],[146,72])
    data=P1Data();aug=jax.jit(augment);mark=jax.jit(render_jax);root=jax.random.split(jax.random.key(42))[0]
    samples=0;marked=0;normal=0
    for step in [0,1,1404,2808,2809,5617]:
        batch=data.batch(step);ids=data.schedule[step]
        images,pts=aug(jax.random.fold_in(root,step),batch['image'],np.asarray(data.points[ids]));pts=np.asarray(pts)
        coords,valid=data.marker_batch(step,pts);out=mark(images,coords,valid)
        tokens,masks,texts=data.symbolic_tokens(step,pts)
        red,white=raster_masks(coords,valid);pixels=red|white
        before=np.asarray(images['base_0_rgb']);after=np.asarray(out['base_0_rgb'])
        np.testing.assert_array_equal(after[~pixels],before[~pixels])
        for key in ['left_wrist_0_rgb','right_wrist_0_rgb']:np.testing.assert_array_equal(out[key],images[key])
        for j,i in enumerate(ids):
            if not data.anchors['revision'][i]:
                assert not valid[j] and texts[j] is None;np.testing.assert_array_equal(after[j],before[j]);normal+=1
            else:
                info=marker_info(data.plans[int(data.anchors['episode'][i])],int(data.stages[i]),pts[j],data.point_valid[i])
                assert info['valid']==bool(valid[j])
                if valid[j]:
                    y,x=coords[j];assert info['yx']==[int(y),int(x)]
                    assert f'<{y},{x}>' in texts[j].split('Current Subgoal:')[1]
                    assert texts[j].endswith(LEGEND)
                    np.testing.assert_array_equal(after[j,y,x],[1.,-1.,-1.]);marked+=1
                elif info['role_index']>=0:assert not texts[j].endswith(LEGEND)
            assert masks[j].sum()<=200;samples+=1
    # Invalid/out-of-view references are suppressed in text AND image, not clipped.
    i=next(i for i,r in enumerate(data.marker_roles) if r>=0)
    plan=data.plans[int(data.anchors['episode'][i])];s=int(data.stages[i]);p=np.array(data.points[i]);v=np.array(data.point_valid[i])
    p[int(data.marker_roles[i])]=[-.01,120]
    raw=prompt(plan,'V3R',s,p,v);assert 'at unavailable' in raw and not raw.endswith(LEGEND)
    info=marker_info(plan,s,p,v);assert not info['valid']
    report=dict(passed=True,train_online_pixel_exact=True,edge_and_invalid_cases=13,
        production_augmented_samples=samples,drawn_markers=marked,normal_images_unchanged=normal,
        wrists_and_third_slot_unchanged=True,outside_marker_pixels_unchanged=True,
        text_marker_integer_coordinate_parity=True,no_marker_for_out_of_frame=True,
        actual_native_augmentation_separately_checked='augmentation_integration.json')
    write_json(ROOT/'reports/marker_validation.json',report);print(json.dumps(report,indent=2))

if __name__=='__main__':main()
