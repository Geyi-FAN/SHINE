"""Isolated pi05 inference: accepts raw text, never generates subgoals/coordinates."""
import argparse,dataclasses,io,json,sys,threading,time,hashlib
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import numpy as np

def main(a):
 sys.path[:0]=[str(a.vendor/'src'),str(a.vendor/'packages/openpi-client/src')]
 import jax
 from openpi.models.pi0_config import Pi0Config
 from model_loader import load
 from openpi.models.tokenizer import PaligemmaTokenizer
 print('LOADING_RAW_PROMPT_POLICY',flush=True)
 policy=load(a.checkpoint);tokenizer=PaligemmaTokenizer(4096);contexts={};mutex=threading.Lock()
 norm=a.checkpoint/'assets/physical-intelligence/libero/norm_stats.json'
 meta={'ready':False,'model':'pi05','variant':'E3','checkpoint':str(a.checkpoint),'canonical_checkpoint':'/mnt/disk_4/geyi/e3_v4_744_E3_fulllibero_35k_30000/30000','checkpoint_step':30000,'trajectories':744,'weights':'exported_params','image_size':224,'state_dimension':8,'action_horizon':10,'execute_steps':3,'flow_steps':10,'max_token_len':200,'discrete_state_input':True,'normalization_sha256':hashlib.sha256(norm.read_bytes()).hexdigest(),'prompt_mode':'literal_transcript_no_prefix_no_subgoal_no_coordinates','agent':False,'oracle':False,'yolo':False,'hostname':'240'}
 a.out.mkdir(parents=True,exist_ok=True);audit=(a.out/'inference_audit.jsonl').open('a',buffering=1)
 def infer(req):
  # Private labels/coordinates are neither accepted nor reconstructed.
  allowed={'prompt','evaluation_case_id','evaluation_call_index','evaluation_seed','observation/image','observation/wrist_image','observation/state'}
  if set(req)-allowed:raise ValueError('unknown input keys')
  cid=req.pop('evaluation_case_id');index=int(req.pop('evaluation_call_index'));seed=req.pop('evaluation_seed',None)
  prompt=req['prompt']
  if not isinstance(prompt,str) or not prompt.strip():raise ValueError('empty transcript')
  for key,shape in [('observation/image',(224,224,3)),('observation/wrist_image',(224,224,3)),('observation/state',(8,))]:
   if np.asarray(req[key]).shape!=shape:raise ValueError('invalid sensor shape')
  with mutex:
   if index==0:
    if seed is None or cid in contexts:raise ValueError('duplicate first inference')
    ctx={'rng':jax.random.key(int(seed)),'index':0}
   else:ctx=contexts[cid]
   if index!=ctx['index'] or (index>0 and seed is not None):raise ValueError('inference order mismatch')
   transformed=policy._input_transform(dict(req));_,mask=tokenizer.tokenize(prompt,np.asarray(transformed['state'])[:8]);n=int(mask.sum())
   # Keep the original transcript. The official policy input transform owns
   # the trained 200-token truncation; do not reject ordinary long ASR text.
   truncated=n>200
   policy._rng=ctx['rng'];begin=time.monotonic();answer=policy.infer(req);elapsed=time.monotonic()-begin;ctx.update(rng=policy._rng,index=index+1);contexts[cid]=ctx
   actions=np.asarray(answer['actions']);assert actions.shape==(10,7) and np.isfinite(actions).all()
   audit.write(json.dumps({'episode':cid,'index':index,'prompt':prompt,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'raw_tokens':n,'effective_token_limit':200,'official_truncation':truncated,'seconds':elapsed})+'\n')
   return {'actions':actions.tolist(),'prompt':prompt,'prompt_token_length':min(n,200),'raw_prompt_token_length':n,'official_truncation':truncated,'seconds':elapsed,'evaluation_call_index':index}
 warm={'prompt':'Move the object.','evaluation_case_id':'__generic_warmup__','evaluation_call_index':0,'evaluation_seed':0,'observation/image':np.zeros((224,224,3),np.uint8),'observation/wrist_image':np.zeros((224,224,3),np.uint8),'observation/state':np.zeros(8,np.float32)}
 infer(warm);meta['ready']=True;(a.out/'READY.json').write_text(json.dumps(meta,indent=2));print('POLICY_READY',flush=True)
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def reply(self,code,data):
   body=json.dumps(data).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
  def do_GET(self):self.reply(200,meta)
  def do_POST(self):
   try:
    if self.path!='/infer':raise ValueError('unsupported route')
    size=int(self.headers['Content-Length']);assert 0<size<8*1024**2
    with np.load(io.BytesIO(self.rfile.read(size)),allow_pickle=False) as z:
     req=json.loads(str(z['metadata']));req.update({'observation/image':z['image'],'observation/wrist_image':z['wrist'],'observation/state':z['state']})
    self.reply(200,infer(req))
   except Exception as e:
    import traceback;traceback.print_exc();self.reply(400,{'error':type(e).__name__,'detail':str(e)})
 ThreadingHTTPServer((a.host,a.port),Handler).serve_forever()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--vendor',type=Path,required=True);p.add_argument('--checkpoint',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--port',type=int,default=49441);p.add_argument('--host',default='127.0.0.1');main(p.parse_args())
