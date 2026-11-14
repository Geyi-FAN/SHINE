"""Classify provider outages separately from robot/task failures; no billing actions."""
import json,os,time,urllib.request,urllib.error
from pathlib import Path

class ProviderUnavailable(RuntimeError):
    pass

def request_json(request,timeout=90):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request,timeout=timeout) as response:return json.load(response)
        except urllib.error.HTTPError as exc:
            body=exc.read().decode(errors='replace')
            try:error=json.loads(body).get('error',{})
            except ValueError:error={}
            code=error.get('code',error.get('type'))
            if code=='Arrearage':
                record=dict(status='blocked_external_api',provider='configured_dialogue_provider',
                    code=code,http_status=exc.code,message=error.get('message','Provider account unavailable'),
                    observed_unix=time.time(),credentials_logged=False)
                root=os.environ.get('REPAIR_ROOT')
                if root:
                    path=Path(root)/'PROVIDER_BLOCKED.json'
                    path.write_text(json.dumps(record,indent=2))
                raise ProviderUnavailable('Provider Arrearage: account access denied; robot run is incomplete, not a task failure') from None
            if exc.code in (429,500,502,503,504) and attempt<2:
                time.sleep(attempt+1);continue
            raise RuntimeError('Provider HTTP '+str(exc.code)+' '+str(code)+': '+str(error.get('message',body[:200]))) from None
