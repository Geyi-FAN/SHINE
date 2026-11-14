"""Exact-input paired response reuse; never reuse outputs for different evidence."""
import copy,hashlib,pickle
import numpy as np

def canonical(value):
    if isinstance(value,(np.ndarray,np.generic)):
        a=np.asarray(value);return ('array',a.dtype.str,a.shape,np.ascontiguousarray(a).tobytes())
    if isinstance(value,dict):return ('dict',tuple((k,canonical(v)) for k,v in sorted(value.items())))
    if isinstance(value,(tuple,list)):return (type(value).__name__,tuple(canonical(v) for v in value))
    if isinstance(value,(str,int,float,bool,bytes,type(None))):return (type(value).__name__,value)
    raise TypeError('Unfingerprinted input type: '+str(type(value)))

def fingerprint(value):return hashlib.sha256(pickle.dumps(canonical(value),protocol=5)).hexdigest()

class ResponseMemo:
    def __init__(self):self.values={};self.hits=0;self.misses=0
    def get(self,key):
        if key in self.values:self.hits+=1;return copy.deepcopy(self.values[key])
        self.misses+=1;return None
    def put(self,key,value):self.values[key]=copy.deepcopy(value)
