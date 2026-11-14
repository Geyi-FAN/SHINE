"""One typed E3 point -> one visual arrow, shared by training and inference.

The arrow is a reference cue, never an action direction. No extra target is
introduced. Current/episode-start semantics remain those of sym_geometry.
Rasterization is identical in NumPy (online) and JAX (training).
"""
import re
import numpy as np

VERSION = 'v3_red_arrow_10px_v1'
LEGEND = '; The red arrow points to the referenced location in MAIN'
UNAVAILABLE = '; MAIN marker unavailable'
STYLE = dict(version=VERSION, color_rgb=[255,0,0], outline_rgb=[255,255,255],
             length_px=10, shaft_width_px=2, head_width_px=7, outline_px=1,
             coordinate_order='y,x', image_size=[224,224], camera='MAIN',
             anchor='arrow tip', border='reverse tail horizontally; never move point')


def role_index(plan, stage):
    from sym_contract import ROLES
    if plan['stages'][int(stage)]['kind'] != 'return':return -1
    roles = re.findall(r'\{(\w+)\}', plan['stages'][int(stage)]['grounded'])
    roles = list(dict.fromkeys(roles))
    if len(roles)>1:
        raise ValueError(('V3R expects exactly one active reference', roles))
    return ROLES.index(roles[0]) if roles else -1


def select_points(points, valid, roles):
    """Select one reference for each item; enforce validity BEFORE rounding."""
    points=np.asarray(points);valid=np.asarray(valid);roles=np.asarray(roles)
    p=points[np.arange(len(roles)),np.maximum(roles,0)]
    good=(roles>=0)&valid[np.arange(len(roles)),np.maximum(roles,0)]
    good &= np.isfinite(p).all(-1)&(p>=0).all(-1)&(p<=223).all(-1)
    return np.where(good[:,None],np.rint(p),0).astype(np.int32),good


def marker_info(plan, stage, points, valid):
    from sym_contract import ROLES
    role=role_index(plan,stage)
    p,good=select_points(np.asarray(points)[None],np.asarray(valid)[None],np.array([role]))
    return dict(role_index=role,role=ROLES[role] if role>=0 else None,
                yx=p[0].tolist() if good[0] else None,valid=bool(good[0]),
                style=VERSION,view='MAIN')


# A small hollow chevron and thin shaft. Origin is the exact referenced pixel.
# Seven-pixel head height makes both diagonals symmetric about that pixel.
_RED = {(0,x) for x in range(-9,1)} | {(1,x) for x in range(-9,-3)}
_RED |= {(y,-abs(y)) for y in range(-3,4)}
_RED |= {(y,-abs(y)-1) for y in range(-3,4)}
_WHITE = {(y+dy,x+dx) for y,x in _RED for dy in (-1,0,1) for dx in (-1,0,1)} - _RED


def raster_masks(points, enabled, xp=np):
    """Batched pixel-exact masks; accepts final integer <y,x> coordinates."""
    p=xp.asarray(points);on=xp.asarray(enabled)
    yy=xp.arange(224)[None,:,None];xx=xp.arange(224)[None,None,:]
    dy=yy-p[:,0,None,None];dx=xx-p[:,1,None,None]
    # Keep the tail inside the image at the left border. Direction is cosmetic.
    dx=dx*xp.where(p[:,1]>=10,1,-1)[:,None,None]
    red=xp.zeros((p.shape[0],224,224),dtype=bool)
    white=xp.zeros_like(red)
    for y,x in sorted(_RED):red=red|((dy==y)&(dx==x))
    for y,x in sorted(_WHITE):white=white|((dy==y)&(dx==x))
    return red&on[:,None,None],white&on[:,None,None]


def render_numpy(image, info):
    """Online image is already oriented/resized uint8 RGB, exactly 224 square."""
    image=np.asarray(image)
    if image.dtype!=np.uint8 or image.shape!=(224,224,3):
        raise ValueError(('Unexpected MAIN image',image.shape,image.dtype))
    p=np.asarray([info['yx'] or [0,0]],np.int32)
    red,white=raster_masks(p,np.asarray([info['valid']]))
    out=image.copy();out[white[0]]=[255,255,255];out[red[0]]=[255,0,0]
    return out


def render_jax(images, points, enabled):
    """Draw AFTER native geometric/color augmentation; preserve all other slots."""
    import jax.numpy as jnp
    red,white=raster_masks(points,enabled,jnp)
    main=images['base_0_rgb']
    main=jnp.where(white[...,None],jnp.asarray([1.,1.,1.],main.dtype),main)
    main=jnp.where(red[...,None],jnp.asarray([1.,-1.,-1.],main.dtype),main)
    return {**images,'base_0_rgb':main}
