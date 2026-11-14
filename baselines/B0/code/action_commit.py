"""Same frame alignment and action scaling as frozen NativePrefetchMixin.
No task interpretation, target checks or subgoal generation.
"""
import numpy as np
def select_actions(actions,bootstrap,elapsed):
 a=np.asarray(actions,float)
 if a.shape!=(10,7) or not np.isfinite(a).all():raise ValueError('invalid action chunk')
 a=np.clip(a,-1,1);a[:,6]=np.where(a[:,6]>0,1.,-1.)
 offset=0 if bootstrap else elapsed
 if offset<0 or offset+3>len(a):raise ValueError('prediction_horizon_expired')
 return list(a[offset:offset+3]),offset
