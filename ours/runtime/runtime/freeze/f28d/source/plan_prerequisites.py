"""Conservative single-gripper plan consistency. Reject only; Agent replans."""
OBJECTS={'bowl','cheese','wine_bottle'}
DRAWERS={'open_top','close_top','open_middle','close_middle'}
def errors(facts,plan,catalog):
 held=facts.get('held_object')
 if held not in OBJECTS|{'none'}:return []
 opened=facts.get('drawers',{}).get('top',{}).get('open')
 relation=facts.get('native_goal_relations',{})
 for i,stage in enumerate(plan):
  name=stage.get('operation');op=catalog.get(name)
  if not op:continue
  obj=op['object'];kind=op['kind']
  if name in DRAWERS:
   if held!='none':
    return ['SINGLE_GRIPPER_CONFLICT: At remaining operation '+str(i)+' ('+name+'), your own preceding steps/current ownership leave '+held+' in the only gripper. Drawer-handle manipulation requires an empty gripper. Regenerate a physically executable order from the public task, or request the genuinely unresolved evidence/clarification. Do not invent a return, closure or automatic release. Already satisfied goals need not be performed again.']
   if name=='open_top':opened=True
   if name=='close_top':opened=False
  elif kind=='grasp':
   if held not in ('none',obj):return ['SINGLE_GRIPPER_CONFLICT: A planned grasp cannot acquire '+obj+' while '+held+' remains held. Regenerate without adding an unrequested destination.']
   held=obj
  elif name=='bowl_drawer' and opened is False and relation.get(name)is not True:
   return ['CONTAINER_PREREQUISITE: Your remaining placement requires the top drawer open, but the observed state and preceding steps do not establish it. Regenerate your own task-consistent plan; a future location point cannot replace this physical prerequisite.']
  elif kind in ('return','release') or (kind=='target' and obj in OBJECTS):
   if held not in ('none',obj):return ['SINGLE_GRIPPER_CONFLICT: Your plan asks '+name+' while another object '+held+' remains held. Resolve actual ownership through observation/clarification or an authorized earlier stage.']
   held='none'
 return []
ADDENDUM="\nPLAN FEASIBILITY: This robot has one gripper. Check the WHOLE remaining plan against observed ownership. Grasping a bowl and then manipulating a drawer handle while still holding it conflicts with this embodiment. Necessary opening may need to precede acquiring the object. A requested placement/return includes release; it frees the gripper afterward. Do not invent return, closing, or release destinations to repair your own plan. If actual ownership or the user's requested order is unresolved, request its evidence/clarification. You still author the plan and exact training-compatible subgoal.\n"
