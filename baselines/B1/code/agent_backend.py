"""One hosted Agent generation, credential01 only, no generation retries/fallback."""
import os,base64,fcntl,hashlib,io,json,time,urllib.error,urllib.request,uuid
from pathlib import Path
from oracle_boundary import assert_clean
R=Path(__file__).resolve().parents[1]
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None

def generate(context,images,root):
 cfg=json.loads((R/'config/MODELS.json').read_text())['agent'];assert_clean(context)
 assert cfg['endpoint']=='https://llmapi.paratera.com/v1/chat/completions'and cfg['credential_no']=='01'
 system=(R/'prompts/agent_system.txt').read_text();content=[dict(type='text',text=json.dumps(context,ensure_ascii=False))]
 from PIL import Image
 for label,array in zip(['CURRENT_MAIN','CURRENT_WRIST'],images):
  out=io.BytesIO();Image.fromarray(array).save(out,format='PNG');content.extend([dict(type='text',text=label),dict(type='image_url',image_url=dict(url='data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()))])
 body=dict(model=cfg['model'],messages=[dict(role='system',content=system),dict(role='user',content=content)],max_tokens=cfg['max_tokens'],temperature=cfg['temperature'],stream=False,response_format=dict(type='json_object'),enable_thinking=False)
 directory=Path(root)/('request_'+str(time.time_ns())+'_'+uuid.uuid4().hex[:8]);directory.mkdir(parents=True)
 (directory/'request.json').write_text(json.dumps(body,ensure_ascii=False,indent=2));start=time.monotonic();record=dict(requested_model=cfg['model'],endpoint=cfg['endpoint'],provider=cfg['provider'],credential_no='01',started=time.time(),retries=0,cached=False,request_sha256=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest(),max_concurrent_in_this_experiment=1)
 key=(R/'private/agent.key').read_text().strip()
 try:
  with Path(os.environ['COMMON_AGENT_LOCK_FILE']).open('a')as lock:
   fcntl.flock(lock,fcntl.LOCK_EX);record['queue_s']=time.monotonic()-start;record['sent_at']=time.time();send=time.monotonic()
   q=urllib.request.Request(cfg['endpoint'],data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
   with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(q,timeout=cfg['request_timeout_s'])as f:
    raw=json.load(f);record.update(actual_model=raw.get('model'),http_status=f.status,request_headers={k:v for k,v in f.headers.items()if 'request-id'in k.lower()or'retry-after'in k.lower()})
   record['upstream_s']=time.monotonic()-send
  (directory/'response.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2));assert raw.get('model')==cfg['model'],'Agent model changed'
  text=raw['choices'][0]['message']['content'];output=json.loads(text);assert isinstance(output,dict),'Agent root must be an object';record.update(status='received',usage=raw.get('usage'),finish_reason=raw['choices'][0].get('finish_reason'));return output,record
 except urllib.error.HTTPError as e:
  detail=e.read().decode(errors='replace').replace(key,'[REDACTED]')[:2000];record.update(status='error',error=type(e).__name__,http_status=e.code,detail=detail,generation_delivery='unknown; no automatic resend');raise RuntimeError('cloud01 HTTP '+str(e.code)+': '+detail)
 except Exception as e:record.update(status='error',error=type(e).__name__,detail=str(e).replace(key,'[REDACTED]')[:500],generation_delivery='unknown; no automatic resend');raise
 finally:record['elapsed_s']=time.monotonic()-start;(directory/'transport.json').write_text(json.dumps(record,indent=2))
