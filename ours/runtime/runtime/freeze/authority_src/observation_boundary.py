"""The same camera transform is used for review artifacts and actual policy requests."""
import hashlib
import numpy as np
from PIL import Image
from sim_state import observation_state
VERSION='switch-observation-v4.1-explicit-training-profile'
# Audit guard for replay rasterization only; never used as a scoring threshold.
def negligible_raster_difference(d):
 return d['max_channel_error']<=2 and d['changed_pixel_fraction']<=.001 and d['mean_channel_error']<=.001
PROFILES={
 'smolvla_e3_training_256':{'rotation':'180 degrees','resize':'PIL bilinear 256->224->256, exact reviewed training path','marker':'none'},
 'pi05_libero_224':{'rotation':'180 degrees','resize':'openpi resize_with_pad 224x224','marker':'none'},
 'smolvla_switch_256':{'rotation':'180 degrees','resize':'none; require original 256x256 RGB','marker':'none in canonical base view; method overlays must be logged separately'},
}
def digest(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def pixel_difference(actual,reference):
 a=np.asarray(actual);b=np.asarray(reference);assert a.shape==b.shape
 d=np.abs(a.astype(np.int16)-b.astype(np.int16))
 return dict(exact=bool(np.array_equal(a,b)),max_channel_error=int(d.max()),mean_channel_error=float(d.mean()),changed_pixel_fraction=float(np.any(d>0,axis=-1).mean()),pixels_over_2_fraction=float(np.any(d>2,axis=-1).mean()))
def camera(raw,profile):
 a=np.ascontiguousarray(np.asarray(raw,np.uint8)[::-1,::-1])
 if profile=='pi05_libero_224':
  from openpi_client import image_tools
  return image_tools.convert_to_uint8(image_tools.resize_with_pad(a,224,224))
 if profile=='smolvla_e3_training_256':
  if a.shape!=(256,256,3):raise ValueError(a.shape)
  return np.asarray(Image.fromarray(a).resize((224,224),Image.Resampling.BILINEAR).resize((256,256),Image.Resampling.BILINEAR))
 if profile=='smolvla_switch_256':
  if a.shape!=(256,256,3):raise ValueError(('SmolVLA requires raw 256x256 RGB',a.shape))
  return a
 raise ValueError(profile)
def request(obs,instruction,profile):
 return {'observation/image':camera(obs['agentview_image'],profile),'observation/wrist_image':camera(obs['robot0_eye_in_hand_image'],profile),'observation/state':observation_state(obs),'prompt':instruction}
def save_views(obs,directory,extra=None):
 from pathlib import Path
 directory=Path(directory);directory.mkdir(parents=True,exist_ok=True);report={'version':VERSION,'profiles':{},'extra':extra or {}}
 for name,key in [('main','agentview_image'),('wrist','robot0_eye_in_hand_image')]:
  a=np.asarray(obs[key],np.uint8);Image.fromarray(a).save(directory/f'raw_{name}.png')
  report['raw_'+name]={'shape':list(a.shape),'sha256_pixels':digest(a)}
 for profile in PROFILES:
  req=request(obs,'',profile);report['profiles'][profile]={}
  for name,key in [('main','observation/image'),('wrist','observation/wrist_image')]:
   Image.fromarray(req[key]).save(directory/f'{profile}_{name}.png');report['profiles'][profile][name]={'shape':list(req[key].shape),'sha256_pixels':digest(req[key])}
 report['state_sha256']=digest(observation_state(obs));return report
