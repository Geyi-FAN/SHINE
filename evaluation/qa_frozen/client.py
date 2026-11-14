"""Separate, logged offline vision judge; never imports the execution planner."""
import base64,hashlib,json,time,urllib.request,urllib.error
from pathlib import Path

def credentials():
    root=Path('/mnt/disk_4/geyi/paratera_api')
    cfg=json.loads((root/'agents.json').read_text());env={}
    for line in (root/'.env').read_text().splitlines():
        if '='in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1);env[k.strip()]=v.strip().strip('"').strip("'")
    a=next(x for x in cfg['agents']if x['agent_id']=='agent_04')
    return env[cfg['base_url_env']].rstrip('/'),env[a['api_key_env']]

def image_part(path):
    p=Path(path);mime='image/png'if p.suffix=='.png'else'image/jpeg'
    return dict(type='image_url',image_url=dict(url='data:'+mime+';base64,'+base64.b64encode(p.read_bytes()).decode()))

def call(payload,folder,timeout=150):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
    (folder/'request.json').write_bytes(raw)
    base,key=credentials();began=time.time()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req=urllib.request.Request(base+'/chat/completions',data=raw,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with opener.open(req,timeout=timeout)as f:
            response=f.read();headers={k:f.headers.get(k)for k in ['x-request-id','date','content-type']}
        (folder/'response.json').write_bytes(response)
        d=json.loads(response)
        meta=dict(ok=True,seconds=time.time()-began,requested_model=payload['model'],returned_model=d.get('model'),
                  response_id=d.get('id'),system_fingerprint=d.get('system_fingerprint'),usage=d.get('usage'),headers=headers,
                  request_sha256=hashlib.sha256(raw).hexdigest(),response_sha256=hashlib.sha256(response).hexdigest(),
                  provider='Paratera',credential_alias='agent_04',independent_of_Qwen_answer_model=True)
        (folder/'meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
        return d
    except Exception as e:
        meta=dict(ok=False,seconds=time.time()-began,error_type=type(e).__name__,status=getattr(e,'code',None),
                  request_sha256=hashlib.sha256(raw).hexdigest(),automatic_retry=False)
        (folder/'meta.json').write_text(json.dumps(meta,indent=2)+'\n')
        raise RuntimeError(f'judge_request_failed:{type(e).__name__}:{getattr(e,"code",None)}')from None

def content(d):
    if len(d.get('choices',[]))!=1:raise ValueError('expected_one_completion')
    c=d['choices'][0]
    if c.get('finish_reason')not in ('stop',None):raise ValueError('incomplete_judge_completion')
    return c['message'].get('content','')

def parse_json(s):
    # Permit a single JSON code block, not a second arbitrary object or prose.
    s=s.strip()
    if s.startswith('```json\n')and s.endswith('\n```'):s=s[8:-4].strip()
    d=json.loads(s)
    if not isinstance(d,dict):raise ValueError('judge_object_required')
    return d
