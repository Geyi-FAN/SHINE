"""EMA server, identical paired per-case seeds and immutable reference."""
import argparse,dataclasses,hashlib,logging,json,os
from response_memo import ResponseMemo,fingerprint
from pathlib import Path
from common import VARIANT,sha256
from model_config import make_config
class Isolated:
 def __init__(self,policy,key_factory,model):
  import numpy as np
  from openpi.models.tokenizer import PaligemmaTokenizer
  self.policy=policy;self.key_factory=key_factory;self.model=model;self.contexts={};self.last_tokens=None;self.memo=ResponseMemo()
  long_tokenizer=PaligemmaTokenizer(4096);original=policy._input_transform
  def checked_transform(x):
   raw=x['prompt'];result=original(x)
   tokens,mask=long_tokenizer.tokenize(raw,result['state'][:8]);length=int(mask.sum())
   if length>200:raise ValueError(f'Inference prompt would be truncated: {length}>200')
   assert np.array_equal(tokens[:length],result['tokenized_prompt'][:length]),'State/tokenizer parity mismatch'
   assert length==int(result['tokenized_prompt_mask'].sum())
   self.last_tokens=length
   return result
  policy._input_transform=checked_transform
 def infer(self,observation):
  import numpy as np
  x=dict(observation);cid=x.pop('evaluation_case_id');i=int(x.pop('evaluation_call_index'));seed=x.pop('evaluation_seed',None)
  reference=x.get('observation/initial_image')
  if i==0:
   if seed is None:raise ValueError('Missing first seed')
   ctx=dict(rng=self.key_factory(int(seed)),index=0)
   if self.model in 'BD':ctx['reference']=np.asarray(reference).copy()
  else:
   if seed is not None:raise ValueError('No mid-trial RNG reset')
   ctx=self.contexts[cid]
  assert i==ctx['index']
  if self.model in 'BD':assert np.array_equal(reference,ctx['reference']),'Reference changed'
  if self.model in 'AC':x.pop('observation/initial_image',None)
  import jax
  request_key=fingerprint(dict(observation=x,rng=np.asarray(jax.random.key_data(ctx['rng']))))
  saved=self.memo.get(request_key);hit=saved is not None
  if hit:
   out=saved['output'];ctx['rng']=saved['rng'];self.last_tokens=saved['tokens']
  else:
   self.policy._rng=ctx['rng'];out=self.policy.infer(x);ctx['rng']=self.policy._rng
   self.memo.put(request_key,dict(output=out,rng=ctx['rng'],tokens=self.last_tokens))
  ctx['index']+=1;self.contexts[cid]=ctx
  action_sha=hashlib.sha256(np.ascontiguousarray(out['actions']).tobytes()).hexdigest()
  out.update(paired_request_sha256=request_key,paired_response_memo_hit=hit,paired_action_sha256=action_sha)
  audit=os.environ.get('PAIRED_POLICY_AUDIT')
  if audit:
   with open(audit,'a') as f:f.write(json.dumps(dict(case_context=cid,call=i,input_sha256=request_key,action_sha256=action_sha,memo_hit=hit))+'\n')
  out['evaluation_call_index']=i
  out['prompt_token_length']=self.last_tokens
  if self.model in 'BD':out['provided_initial_reference_sha256']=hashlib.sha256(ctx['reference'].tobytes()).hexdigest()
  return out

def main():
 p=argparse.ArgumentParser();p.add_argument('--checkpoint',type=Path,required=True);p.add_argument('--port',type=int,required=True);p.add_argument('--protocol-id',required=True);a=p.parse_args()
 identity=json.loads((a.checkpoint.parent/'identity.json').read_text());assert identity['variant']==VARIANT,'Checkpoint variant mismatch'
 import jax
 from openpi.policies import policy_config
 from openpi.serving.websocket_policy_server import WebsocketPolicyServer
 from v3_markers import VERSION
 metadata=dict(paired_exact_response_reuse=True,model=VARIANT,checkpoint=str(a.checkpoint.resolve()),weights='EMA',protocol_id=a.protocol_id,current_state=True,state_dimension=8,GT=False,history=False,oracle_subgoal=False,stage_completion='per-client S0 Oracle or S1 RGB/proprio; final controller stop',position_source='YOLO image-only',subgoal_source='Agent',visual_marker=True,marker_version=VERSION,training_identity_sha256=sha256(a.checkpoint.parent/'identity.json'))
 cfg=dataclasses.replace(make_config(a.checkpoint.parent.name),policy_metadata=metadata)
 logging.basicConfig(level=logging.INFO,force=True)
 policy=policy_config.create_trained_policy(cfg,a.checkpoint)
 WebsocketPolicyServer(Isolated(policy,jax.random.key,VARIANT),host='127.0.0.1',port=a.port,metadata=metadata).serve_forever()
if __name__=='__main__':main()
