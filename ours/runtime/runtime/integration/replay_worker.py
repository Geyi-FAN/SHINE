"""One isolated process, one historical case. Network/actions are denied."""
import base64,copy,gzip,hashlib,io,json,os,sys,time,traceback
from pathlib import Path
B=Path(__file__).resolve().parents[1]
os.environ.update(json.loads((B/'freeze/handoff/ENVIRONMENT_REFERENCE.json').read_text())['values'])
os.environ.update(PYTHONDONTWRITEBYTECODE='1',HYBRID_M2_CURRENT_ONLY='0')
sys.dont_write_bytecode=True
sys.path[:0]=[str(B/'freeze/f28d/source'),str(B/'integration')]
blocked=[]
def audit(event,args):
 if event in ('socket.connect','socket.bind','subprocess.Popen','os.system'):
  blocked.append(event);raise RuntimeError('G1 forbids network/process/actions: '+event)
 if event=='import'and args[0].split('.')[0]in {'mujoco','mujoco_py','libero','robosuite','sim_runtime','openpi_client'}:
  blocked.append('import:'+args[0]);raise RuntimeError('G1 forbids environment/policy import')
sys.addaudithook(audit)
from adapter import F28dExecutionAdapter,Identity,ObservedSceneStateStore,Observation,bind_policy_reference,digest,payload_from_body,deny_private
import text_transport,agent_transport
fake_connection=lambda role:({'model':'Qwen3.8-27B-FP8','chat_url':'http://127.0.0.1:18084/v1/chat/completions'},'REPLAY-NOT-A-REAL-KEY')
text_transport.connection=fake_connection
import local_transport
local_transport.connection=fake_connection
# Install the same role hook BEFORE importing planner/task_language.
# This hook is a deterministic test transport only, never usable for live inference.
agent_transport.request_json=lambda *_a,**_k:(_ for _ in ()).throw(RuntimeError('Replay transport not installed'))
import planner,task_language
from jsonschema import Draft202012Validator
from output_contract import constrain
from observation_validation import errors as tool_errors
from PIL import Image
import ast

def check_original_system(role, body):
 payload=payload_from_body(body)
 if role=='wording':expected=task_language.SYSTEM
 elif role=='planning':expected=planner.Planner().system
 elif role=='verifier':
  stage=payload['selected_subgoal'];required=payload['required_checks']
  kind='drawer' if stage['operation'].startswith(('close_','open_')) else stage['kind'] if stage['kind'] in ('grasp','return','release') else 'placement' if 'release' in required else 'push' if stage['operation']=='push_plate' else 'other'
  rubrics=json.loads((B/'freeze/f28d/source/verifier_rubrics.json').read_text())
  expected=(B/'freeze/f28d/source/verifier_prompt_R11.txt').read_text().replace('<SELECTED_RUBRIC>',rubrics[kind])
 else:
  # Read constant source fragments without importing or constructing an environment.
  tree=ast.parse((B/'freeze/f28d/source/recovery_observer.py').read_text())
  expected=next(ast.literal_eval(n.value)for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='SYSTEM'for t in n.targets))
  suffixes=[n.value.value for n in ast.walk(tree)if isinstance(n,ast.AugAssign)and isinstance(n.target,ast.Name)and n.target.id=='system'and isinstance(n.value,ast.Constant)]
  context=payload.get('observation_request_context')or{}
  if context.get('reason')=='drawer_has_not_completed_after_bounded_execution':expected+=suffixes[0]
  if payload.get('historical_visual_reference'):expected+=suffixes[1]
 return expected==body['messages'][0]['content']

def loadblob(record):
 raw=gzip.decompress((B/record['file']).read_bytes())
 if hashlib.sha256(raw).hexdigest()!=record['sha256']:raise ValueError('Fixture hash mismatch')
 return json.loads(raw)

def frame_set(body):
 return set(local_frame for m in body['messages']if m['role']=='user'and isinstance(m['content'],list)for item in m['content']if item.get('type')=='text'for local_frame in __import__('re').findall(r'frame=(-?\d+)',item['text']))

def main(case_id):
 data=json.loads((B/'dataset/cases'/(case_id+'.json')).read_text());adapter=F28dExecutionAdapter();out=dict(case_id=case_id,group=data['group'],errors=[],calls=[],planner_generations=[],network_attempts=blocked,new_model_calls=0,robot_actions=0,role_counts={r:0 for r in ['wording','planning','verifier','recovery']})
 originals=[];records={};transport_failures=[]
 for row in data['calls']:
  try:
   role=row['role'];files=row['files'];body=loadblob(files['request_original.json']);wire=loadblob(files['request_wire.json']);adapted=adapter.role_body(role,body)
   assert adapted==body,'Adapter changed original role request'
   if role=='planning':
    p=payload_from_body(body);i=Identity(str(p['episode_id']),'replay-task',p['task_version'],0,'recorded',p['frame']);assert adapter.planner_input(p,i)==p
    ObservedSceneStateStore().publish(p['physical_state'],Observation(p['frame'],0),fresh_detector_points=[],resolved_action_references=[])
   if role in ('wording','planning'):
    rebuilt=copy.deepcopy(adapted);rebuilt['chat_template_kwargs']={'enable_thinking':rebuilt.pop('enable_thinking',False)};atlas=[]
   else:rebuilt,atlas=local_transport.wire_body(adapted,role)
   request_equal=rebuilt==wire
   system_equal=check_original_system(role,body)
   entry=dict(role=role,record_id=row['record_id'],original_sha256=files['request_original.json']['sha256'],wire_equal=request_equal,body_unchanged=True,source_system_equal=system_equal)
   if not system_equal:out['errors'].append(dict(role=role,record_id=row['record_id'],kind='source_system_prompt_mismatch'))
   if not request_equal:
    entry['changed_top_keys']=[k for k in set(wire)|set(rebuilt)if wire.get(k)!=rebuilt.get(k)];out['errors'].append(dict(role=role,record_id=row['record_id'],kind='wire_body_mismatch',keys=entry['changed_top_keys']))
   if role in ('verifier','recovery'):
    expected=loadblob(files['atlas.json']);entry['atlas_equal']=atlas==expected
    if atlas!=expected:out['errors'].append(dict(role=role,record_id=row['record_id'],kind='atlas_mapping_mismatch'))
    # Verify original embedded observations decode, and retain their sizes/pixel hashes.
    images=[]
    for m in body['messages']:
     if isinstance(m['content'],list):
      for item in m['content']:
       if item.get('type')=='image_url':
        raw=local_transport.image_bytes(item);im=Image.open(io.BytesIO(raw)).convert('RGB');images.append(dict(size=list(im.size),pixel_sha256=hashlib.sha256(im.tobytes()).hexdigest()))
    entry['original_images']=images
   if 'response.json'in files:
    response=loadblob(files['response.json']);records[row['record_id']]=(body,response,row)
    try:pred=json.loads(response['choices'][0]['message']['content'])
    except Exception:pred=None
    if role in('verifier','recovery'):
     schema=wire['response_format']['json_schema']['schema'];schema_errors=[e.message for e in Draft202012Validator(schema).iter_errors(pred)];entry['schema_errors']=schema_errors
     # Historical invalid responses are preserved, not promoted into accepted actions.
     if role=='recovery'and isinstance(pred,dict):entry['tool_validation_errors']=tool_errors(pred,payload_from_body(body))
    entry['response_json_valid']=pred is not None
   else:
    entry['historical_transport_failure']=loadblob(files['transport.json']).get('status');transport_failures.append(row['record_id'])
   out['calls'].append(entry);out['role_counts'][role]+=1
  except Exception as exc:out['errors'].append(dict(role=row['role'],record_id=row['record_id'],kind='role_replay_exception',error=type(exc).__name__+': '+str(exc)))
 # Execute the actual frozen Planner.generate + normalize validation and ordered memory
 # against every recorded pre-generation input, consuming historical responses in order.
 queue=[r for r in data['calls']if r['role']in('wording','planning')];cursor=0
 def replay(request,timeout=90):
  nonlocal cursor
  if cursor>=len(queue):raise AssertionError('Generated extra model request')
  row=queue[cursor];cursor+=1
  expected,response,_=records[row['record_id']]
  body=json.loads(request.data)
  assert body==expected,'Actual frozen generator request differs from recorded '+row['role']+' '+row['record_id']
  return copy.deepcopy(response)
 planner.request_json=replay;task_language.request_json=replay
 try:
  p=planner.Planner();agent_calls=loadblob(data['supporting']['agent_calls.json'])
  for n,item in enumerate(agent_calls):
   inp=copy.deepcopy(item['input']);identity=Identity(str(inp['episode_id']),'replay-task',inp['task_version'],0,'recorded',inp['frame']);inp=adapter.planner_input(inp,identity)
   expected=item['result'];result=p.generate(inp)
   equal=result.get('output')==expected.get('output')and result.get('attempts')==expected.get('attempts')
   out['planner_generations'].append(dict(index=n,frame=inp['frame'],output_equal=equal,status=(result.get('output')or{}).get('status'),attempts=len(result.get('attempts',[])),recorded_output=expected.get('output'),replayed_output=result.get('output')))
   if not equal:out['errors'].append(dict(kind='planner_generation_mismatch',index=n))
  if cursor!=len(queue):out['errors'].append(dict(kind='unconsumed_text_requests',consumed=cursor,expected=len(queue)))
 except Exception as exc:out['errors'].append(dict(kind='planner_generate_exception',index=len(out['planner_generations']),error=type(exc).__name__+': '+str(exc)))
 out['text_requests_consumed']=cursor;out['historical_transport_failures']=transport_failures
 # Coordinate tests use genuine saved YOLO points, not GT positions or rounded text.
 coordinate_checks=0
 try:
  raws=gzip.decompress((B/data['supporting']['points/detections.jsonl']['file']).read_bytes());assert hashlib.sha256(raws).hexdigest()==data['supporting']['points/detections.jsonl']['sha256']
  import numpy as np
  for line in raws.decode().splitlines():
   row=json.loads(line)
   for point in row['points']:
    yx=point['yx224']
    if all(0<=v<=223 for v in yx):
     expected=np.rint((np.asarray(yx)+.5)*(256/224)-.5).astype(int).tolist()
     ref=dict(time_source=row['time_source'],entity=point['entity'],keypoint=point['keypoint']);token='{'+'.'.join(ref[k]for k in ['time_source','entity','keypoint'])+'}'
     decision=dict(status='plan_ready',reference=ref,policy_prompt_template='reference '+token)
     _,meta=bind_policy_reference(decision,dict(point,time_source=row['time_source'],frame=row['frame']),camera_transform_id='main256-to224-fixed-v1',expected_episode_id=case_id)
     assert meta['yx']==expected
     coordinate_checks+=1
 except Exception as exc:out['errors'].append(dict(kind='coordinate_parity_exception',error=str(exc)))
 out['coordinate_checks']=coordinate_checks;out['pass']=not out['errors']
 dest=B/'reports/G1/cases'/(case_id+'.json');dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:out[k]for k in ['case_id','pass','role_counts','coordinate_checks','errors']}),flush=True)
 return 0 if out['pass']else 1
if __name__=='__main__':sys.exit(main(sys.argv[1]))
