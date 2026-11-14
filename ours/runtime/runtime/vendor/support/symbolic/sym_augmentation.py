"""Native A image augmentation, joint points, and unchanged loss RNG semantics.

All image preprocessing happens BEFORE text tokenization. compute_loss must be
called with train=False afterwards while the nnx model stays in train mode.
The original A implementation used main-style augmentation on its masked third
slot too; retain that detail for exact RGB parity.
"""
import augmax
import jax
import jax.numpy as jnp


def chain(main,types=None):
    transforms=[]
    if main:transforms.extend([augmax.RandomCrop(212,212),augmax.Resize(224,224),augmax.Rotate((-5,5))])
    transforms.append(augmax.ColorJitter(brightness=.3,contrast=.4,saturation=.5))
    return augmax.Chain(*transforms,input_types=types)


def per_micro(key,images,points):
    pre_key=jax.random.split(key,3)[0]
    keys=jax.random.split(pre_key,points.shape[0])
    result={};updated=None
    for name,image in images.items():
        x=image.astype(jnp.float32)/255.*2.-1. if image.dtype==jnp.uint8 else image
        x=x/2.+.5
        if name=='base_0_rgb':
            x,updated=jax.vmap(chain(True,(augmax.InputType.IMAGE,augmax.InputType.KEYPOINTS)))(keys,(x,points))
        else:x=jax.vmap(chain(name=='right_wrist_0_rgb'))(keys,x)
        result[name]=x*2.-1.
    return result,updated


def augment(key,images,points,micro_batch=64):
    n=points.shape[0]//micro_batch
    if n==1:return per_micro(key,images,points)
    keys=jax.random.split(key,n)
    shaped=jax.tree.map(lambda x:x.reshape(n,micro_batch,*x.shape[1:]),images)
    imgs,p=jax.vmap(per_micro)(keys,shaped,points.reshape(n,micro_batch,*points.shape[1:]))
    return jax.tree.map(lambda x:x.reshape(points.shape[0],*x.shape[2:]),imgs),p.reshape(points.shape)


def points_only(key,points):
    keys=jax.random.split(jax.random.split(key,3)[0],points.shape[0])
    joint=chain(True,(augmax.InputType.IMAGE,augmax.InputType.KEYPOINTS))
    return jax.vmap(lambda k,p:joint(k,(jnp.zeros((224,224,3),jnp.float32),p))[1])(keys,points)

