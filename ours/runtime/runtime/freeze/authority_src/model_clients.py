"""Optional network clients. No simulator objects or future source actions are sent."""
import io,json,os,urllib.request
import numpy as np
class SmolVLAHTTP:
 label='pi05_e3_v4_616_http'
 def __init__(self):
  self.url='http://'+os.environ.get('SWITCH_POLICY_HOST','127.0.0.1')+':'+os.environ.get('SWITCH_POLICY_PORT','19840')
 def metadata(self):
  with urllib.request.urlopen(self.url,timeout=15) as response:metadata=json.load(response)
  metadata.pop('requests',None);metadata.pop('uptime_seconds',None);return metadata
 def infer(self,req):
  assert req['observation/image'].shape==(224,224,3) and req['observation/wrist_image'].shape==(224,224,3)
  metadata={k:v for k,v in req.items() if not isinstance(v,np.ndarray)};buf=io.BytesIO()
  np.savez(buf,image=req['observation/image'],wrist=req['observation/wrist_image'],state=req['observation/state'],metadata=json.dumps(metadata))
  if req['evaluation_call_index']==0:
   from pathlib import Path
   root=Path(__file__).resolve().parents[3];folder=root/'first_requests';folder.mkdir(exist_ok=True)
   cid=req['evaluation_case_id'];assert Path(cid).name==cid
   (folder/(cid+'.npz')).write_bytes(buf.getvalue())
  request=urllib.request.Request(self.url,data=buf.getvalue(),headers={'Content-Type':'application/octet-stream'})
  with urllib.request.urlopen(request,timeout=600) as response:out=json.load(response)
  assert out['evaluation_call_index']==req['evaluation_call_index'];return out
def smolvla_http():return SmolVLAHTTP()
def pi05_websocket():
 # Standard OpenPI accepts canonical observations, but its default server does
 # not guarantee the requested evaluation_seed is honored. Record/verify that
 # capability on the actual server before a paired stochastic experiment.
 from openpi_client.websocket_client_policy import WebsocketClientPolicy
 from functools import partial
 from unittest.mock import patch
 import websockets.sync.client
 connect=websockets.sync.client.connect
 with patch('websockets.sync.client.connect',partial(connect,ping_interval=None,ping_timeout=None)):
  return WebsocketClientPolicy(os.environ.get('SWITCH_POLICY_HOST','127.0.0.1'),int(os.environ.get('SWITCH_POLICY_PORT','8000')))
