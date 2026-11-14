"""D0 final gate. A scoped native-success BIT + original S1 observations.
No environment, simulator, metric contract, or private Oracle monitor is accepted.
"""
from observed_completion import DESTINATIONS,distance
TARGET_OPERATORS={0:'open_middle',1:'bowl_stove',2:'bottle_cabinet',3:'bowl_drawer',4:'bowl_cabinet',5:'push_plate',6:'cheese_bowl',7:'turn_on_stove',8:'bowl_plate',9:'bottle_rack'}
class TerminalGate:
 def __init__(self,target_task,user_message):
  self.target_task=int(target_task);self.expected=TARGET_OPERATORS[self.target_task]
  self.user_message=user_message;self.prefix=None;self.initial_plan=None
 def register_plan(self,plan):
  if self.initial_plan is None:
   self.initial_plan=[dict(s) for s in plan]
   self.prefix=[s['operation'] for s in plan[:-1]]
 def check(self,mon,decision,native_success,frame,feedback_task):
  if type(native_success) is not bool:raise TypeError('Native feedback must be one boolean')
  if int(feedback_task)!=self.target_task:raise ValueError('Feedback target task mismatch')
  if mon.last!=frame:raise ValueError('Final gate requires current observed sensor frame')
  plan=decision.get('remaining_plan',[]) if decision else []
  checks={'final_agent_stage':len(plan)==1 and plan[0]['operation']==self.expected,
          'native_success':native_success,'prefix_complete':False,
          'user_return_represented':True,'release_constraints':False}
  have=[e for e in mon.events if e.get('source')=='s1_rgb_proprio_v1' and e.get('outcome')=='completed' and e['confirmed_step']<=frame]
  seq=iter(have)
  checks['prefix_complete']=self.prefix is not None and all(any(e['operation']==op for e in seq) for op in self.prefix)
  if any(w in self.user_message.lower() for w in ('return','归位','放回')):
   checks['user_return_represented']=any(op.startswith('return_') for op in (self.prefix or []))
  # This experiment supports the existing six no-drawer placement operators.
  # The benchmark supplies the final spatial relation; do not re-test the 14px
  # current-object/target point match that original S1 used for this relation.
  if checks['final_agent_stage']:
   stage=plan[0];obj=stage['object']
   if stage['operation'] not in DESTINATIONS:raise ValueError('D0-v1 final operator not validated: '+stage['operation'])
   release=mon._released(mon.samples[-1],obj)
   checks['release_constraints']=bool(release)
   sample=mon.samples[-1];settings=mon.settings
   release_evidence=dict(open_gripper=sample['width']>=settings.open_width_m,fresh_K1=mon.point(sample,obj,'K1') is not None,fresh_K2=mon.point(sample,obj,'K2') is not None,stable=mon.stable(obj),separation=distance(mon.point(sample,obj,'K1'),sample['eef_yx'])>=settings.clear_px and sample['eef_yx'] is not None and mon.point(sample,obj,'K1') is not None)
  return dict(frame=frame,feedback_task=self.target_task,checks=checks,release_evidence=release_evidence if checks['final_agent_stage'] else {},
              passed=all(v is True for v in checks.values()),
              blocked=[k for k,v in checks.items() if v is not True],
              source='native_task_success_bit_plus_original_s1_release_guards',
              required_prefix=list(self.prefix or []))
