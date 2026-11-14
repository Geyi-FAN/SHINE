"""Derive container contact from logged raw geometry; no live GT/model calls.

The old source monitor's table-support list excludes a bowl. Preserve its raw
boolean and add only actual cheese/bowl contacts at the same world physics step.
No absent contact is guessed and no thresholds/windows are changed.
"""
import copy,gzip,json
PAIR=['akita_black_bowl_1','cream_cheese_1']
def contact_in(measurement):
 pairs=measurement.get('object_object_contacts')
 if pairs is None:return None
 return any(p.get('objects')==PAIR and p.get('penetration',0)>0 for p in pairs)
def derive(ticks,directory):
 logged={};files=[]
 for path in sorted((directory/'tasks').glob('*/trace.json.gz')):
  trace=json.load(gzip.open(path,'rt'));files.append(str(path))
  for row in trace.get('measurements',[]):
   step=row.get('world_physics_step');measurement=row.get('target',{})
   value=contact_in(measurement)
   if value is None:value=contact_in(row.get('source',{}))
   if step is not None and value is not None:logged[(path.parent.name,step)]=value
 result=[];changed=0
 for original in ticks:
  t=copy.deepcopy(original);m=t.get('measurements',{}).get('cheese')
  if m is not None:
   direct=contact_in(m);contact=direct if direct is not None else logged.get((t.get('task_id'),t.get('step')))
   if (not m.get('support_contact') and t.get('physical',{}).get('native_goal_relations',{}).get('cheese_bowl') is True and contact is True):
    m['support_contact_raw']=m.get('support_contact');m['support_contact']=True;m['support_derivation']='logged cheese/bowl contact at matching task+world-step with native containment';changed+=1
  result.append(t)
 return result,dict(version='v1.5-logged-container-contact',derived_frames=changed,raw_trace_files=files,threshold_changes=False)
