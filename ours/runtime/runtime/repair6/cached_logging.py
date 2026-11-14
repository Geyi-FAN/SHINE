"""HTTP/Agent threads log only the immutable simulation-owner publication."""
import json,time

def install(bridge):
 def log(kind,**fields):
  sample=bridge.audit.last or{}
  row=dict(time=time.time(),monotonic=time.monotonic(),kind=kind,physics_step=sample.get('step'),control_step=sample.get('policy_actions'),simulation_time=sample.get('simulation_time'),simulation_sample_id=sample.get('sample'),simulation_measurement_source='last_owner_published_snapshot',**fields)
  with bridge.log_lock,(bridge.root/'gateway.jsonl').open('a')as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
 bridge.log=log
