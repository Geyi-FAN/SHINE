import json,time,base64,urllib.request,io,os,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
class VisualVerifier:
 def __init__(self,folder):
  self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True);self.calls=[]
  home=Path(os.environ['HYBRID_HARNESS_HOME']);self.cfg=json.loads((home/'data/harness/config.json').read_text())['providers']['dialogue'];key=Path(self.cfg['apiKeyFile']);self.key=(key if key.is_absolute() else home/key).read_text().strip();self.prompt=Path(__file__).with_name('verifier_prompt.txt').read_text()
 def check(self,stage,entered,rows,sensor,history,diagnostics):
  selected=[r for r in rows if r['frame']>=entered][-4:]
  item=dict(operation=stage['operation'],entered=entered,frame=sensor['frame'],accepted=False,required=['object_identity','goal_relation','temporal_stability']);i=len(self.calls)
  if stage['kind'] in ('return','release') or stage['operation'] in ('cheese_bowl','bowl_drawer','bowl_stove','bowl_plate','bowl_cabinet','bottle_cabinet','bottle_rack'):item['required'].append('release')
  if stage['operation'].endswith('_clear') or stage['operation']=='open_middle':item['required'].append('disengagement')
  catalog=json.loads(Path(__file__).with_name('operators.json').read_text());ref=catalog[stage['operation']]['reference'];entities={stage['object'],ref['entity'] if ref else stage['object']}
  if 'drawer' in stage['object']:entities.update(['top_handle','middle_handle'])
  payload=dict(stage=stage,entered_step=entered,coordinates='MAIN224 y,x',frames=[dict(frame=r['frame'],rgbd_image_keypoints={k:v for k,v in r['geometry'].items() if k.split('.')[0] in entities},proprioception=r.get('sensor')) for r in selected],proprioception=dict(gripper_width_m=sensor['width'],eef_xyz=sensor['eef_xyz'],eef_yx=sensor['eef_yx']),historical_targets=[dict(time_source=t,entity=e,keypoint=k,yx224=p['yx224']) for (t,e,k),p in history.items() if (stage['reference']['entity'] if stage.get('reference') else stage['object'])==e])
  contents=[dict(type='text',text=json.dumps(payload))]
  for r in selected:
   im=Image.fromarray(np.concatenate([r['main'],r['wrist']],axis=1));b=io.BytesIO();im.save(b,format='JPEG',quality=85);path=self.folder/f'{i}_{r["frame"]}.jpg';path.write_bytes(b.getvalue());contents.extend([dict(type='text',text='Observation frame '+str(r['frame'])),dict(type='image_url',image_url=dict(url='data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()))])
  (self.folder/f'{i}_input.json').write_text(json.dumps(payload,indent=2));start=time.monotonic()
  try:
   body=dict(model=os.environ.get('HYBRID_VERIFIER_MODEL','qwen3.8-max'),messages=[dict(role='system',content=self.prompt),dict(role='user',content=contents)],enable_thinking=False,response_format=dict(type='json_object'),temperature=0,max_tokens=1600)
   req=urllib.request.Request(self.cfg['endpoint'].rstrip('/')+'/compatible-mode/v1/chat/completions',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
   with urllib.request.urlopen(req,timeout=90) as f:raw=json.load(f)
   pred=json.loads(raw['choices'][0]['message']['content']);item['response']=pred;item['usage']=raw.get('usage');checks=pred.get('checks',[]);frames={r['frame'] for r in selected}
   valid=all(set(c.get('evidence_frames',[]))<=frames for c in checks)
   passed=all(any(c.get('condition')==name and c.get('verdict')=='pass' and c.get('evidence_frames') for c in checks) for name in item['required'])
   # Common physical guard: no VLM can override a measured closed gripper on placement.
   guard=('release' not in item['required'] or (len(selected)>=2 and all(r.get('sensor',{}).get('width',0)>=.065 for r in selected[-2:])))
   item['accepted']=bool(pred.get('status')=='completed' and valid and passed and guard and len(selected)>=3 and selected[-1]['frame']-selected[0]['frame']>=6)
   item.update(schema_valid=valid,physical_guard=guard)
  except Exception as e:item['infrastructure_error']=type(e).__name__+': '+str(e)
  item['seconds']=time.monotonic()-start;self.calls.append(item)
  with (self.folder/'calls.jsonl').open('a') as f:f.write(json.dumps(item)+'\n')
  return item
