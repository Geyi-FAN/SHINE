"""Compile final physical verification from the selected public instruction.

This does NOT generate a plan/subgoal, locate points, or read case IDs/labels.
Agent plans remain model-written. Unsupported/ambiguous goals fail closed.
"""
import re
from dataclasses import dataclass

class UnsupportedObjective(ValueError):pass
OBJECTS={'bowl':'akita_black_bowl_1','cheese':'cream_cheese_1','wine_bottle':'wine_bottle_1','plate':'plate_1'}
OBJECT_TASK={'bowl':1,'cheese':6,'wine_bottle':2,'plate':5}
PATTERNS=[
 (3,r'\bopen\s+(?:the\s+)?top\s+drawer'),
 (0,r'\b(?:open|pull open)\s+the\s+middle\s+drawer(?:\s+of the cabinet)?'),
 (1,r'\b(?:put|place|move)\s+(?:the\s+)?bowl\s+(?:on|onto)\s+(?:the\s+)?stove'),
 (2,r'\b(?:put|place|move)\s+(?:the\s+)?(?:wine\s+)?bottle\s+(?:on|onto)\s+(?:the\s+)?(?:top of (?:the )?)?cabinet'),
 (3,r'\b(?:put|place|move)\s+(?:the\s+)?bowl\s+(?:in|inside|into)\s+(?:the\s+)?(?:open\s+)?top\s+drawer'),
 (4,r'\b(?:put|place|move)\s+(?:the\s+)?bowl\s+(?:on|onto)\s+(?:the\s+)?(?:top of (?:the )?)?cabinet'),
 (5,r'\b(?:push|slide)\s+(?:the\s+)?plate\s+(?:to\s+)?(?:the\s+)?front\s+of\s+(?:the\s+)?stove'),
 (6,r'\b(?:put|place|move)\s+(?:the\s+)?(?:cream\s+)?cheese\s+(?:in|inside|into)\s+(?:the\s+)?bowl'),
 (7,r'\b(?:turn|switch)\s+on\s+(?:the\s+)?stove'),
 (8,r'\b(?:put|place|move)\s+(?:the\s+)?bowl\s+(?:on|onto|in|into)\s+(?:the\s+)?plate'),
 (9,r'\b(?:put|place|move)\s+(?:the\s+)?(?:wine\s+)?bottle\s+(?:on|onto)\s+(?:the\s+)?(?:wine\s+)?rack'),
]
RESTORE=re.compile(r'\b(?:return|put)\s+(?:the\s+)?(?P<object>cream cheese|cheese|wine bottle|bottle|bowl|plate)\s+(?:back\s+)?(?:to\s+)?(?P<where>(?:its|the)\s+(?:episode[- ]start|initial|original|starting)\s+(?:position|location|place|spot)|(?:where it was|where it started|its position at the beginning of (?:the source task|this episode|the episode)))',re.I)
CLOSE=re.compile(r'\b(?:close|shut)\s+(?:the\s+)?(?P<joint>middle|top)\s+drawer',re.I)
@dataclass
class Objective:
 target_task:int
 clauses:list
 return_only:bool=False
 restore_object:str|None=None
 close_only:str|None=None
 open_only:str|None=None
 custom_predicate:list|None=None

def compile_objective(instruction,initial_xyz,current_xyz,articulation,case_id='live',previous_instruction='',source_task_start_xyz=None,current_binary_state=None):
 text=re.sub(r'\s+',' ',instruction.strip()).lower().rstrip('.!')
 if not text:raise UnsupportedObjective('empty_selected_instruction')
 if re.search(r'\b(?:if|unless|perhaps|maybe)\b',text):raise UnsupportedObjective('conditional_goal_requires_explicit_support')
 if re.search(r'\b(?:put|place|move|return|grasp|grab)\s+(?:it|that one|this one)\b',text)and not RESTORE.search(text):raise UnsupportedObjective('unresolved_object_reference')
 hits=[]
 for task,pattern in PATTERNS:
  hits.extend((m.start(),task,m.group())for m in re.finditer(pattern,text,re.I))
 # The canonical task3 explicitly opens and places into the same drawer.
 canonical3=re.search(r'open the top drawer\s*(?:and|then|[,;])\s*put the bowl (?:inside|in it)',text)
 if canonical3:hits.append((canonical3.start(),3,canonical3.group()))
 restore=list(RESTORE.finditer(text));close=list(CLOSE.finditer(text));clauses=[]
 clause=lambda **kw:dict(source='case.instruction.live_selected_public_task',**kw)
 restore_obj=None
 if len(restore)>1:raise UnsupportedObjective('multiple_restore_objects_need_observed_plan_monitor')
 for i,m in enumerate(restore):
  obj={'cream cheese':'cheese','cheese':'cheese','wine bottle':'wine_bottle','bottle':'wine_bottle','bowl':'bowl','plate':'plate'}[m['object']];restore_obj=obj
  source_start='source task'in m['where']
  if source_start and source_task_start_xyz is None:raise UnsupportedObjective('source_task_start_requires_bound_source_reference')
  name=OBJECTS[obj];reference_xyz=source_task_start_xyz if source_start else initial_xyz
  clauses.append(clause(id='restore_'+str(i),kind='restore_episode_start',object=name,reference='bound_source_task_start'if source_start else'episode_start',reference_position=list(reference_xyz[name]),stable_required=True,withdraw_required=bool(re.search(r'move the gripper clear|move the hand clear|withdraw the gripper',text))))
 for i,m in enumerate(close):clauses.append(clause(id='close_'+str(i),kind='close_event',joint=m['joint']))
 custom=re.search(r'(?:put|place|move)\s+(?:the\s+)?(?:cream\s+)?cheese\s+(?:on|onto)\s+(?:the\s+)?stove',text)
 if custom:hits.append((custom.start(),6,custom.group()))
 open_only='top'if any(task==3 for _,task,_ in hits)and not canonical3 and not re.search(r'\b(?:put|place|move)\s+(?:the\s+)?bowl\s+(?:in|inside|into)',text)else None
 if hits:
  hits.sort();target=hits[-1][1];last=hits[-1][0];return_only=False;close_only=None
  # This compiler supports cleanup -> one final goal. Multiple distinct
  # placements need the richer observed plan monitor, not silent last-goal pass.
  if len({t for _,t,_ in hits})>1:raise UnsupportedObjective('multiple_final_operations_not_verified_by_this_adapter')
  if any(m.start()>last for m in restore+close):raise UnsupportedObjective('trailing_cleanup_not_yet_supported')
 elif restore:
  target=OBJECT_TASK[restore_obj];return_only=True;close_only=None;last=restore[-1].start()
  if close:raise UnsupportedObjective('return_then_close_without_final_target_not_yet_supported')
 elif close:
  if len(close)>1:raise UnsupportedObjective('multiple_close_only_goals_need_ordered_monitor')
  target=0;return_only=False;close_only=close[-1]['joint'];last=close[-1].start()
 else:raise UnsupportedObjective('selected_goal_not_in_verified_catalog')
 clauses.append(clause(id='target',kind='native_target',task_id=target,goal_kind='return_released_only'if return_only else'close_only'if close_only else'open_only'if open_only else'explicit_custom_predicate'if custom else'libero_native'))
 if not return_only and not close_only:
  prerequisites=[('restore_'+str(i),m.start())for i,m in enumerate(restore)]+[('close_'+str(i),m.start())for i,m in enumerate(close)]
  prerequisites.sort(key=lambda p:p[1])
  for i,(before,_)in enumerate(prerequisites):
   after=prerequisites[i+1][0]if i+1<len(prerequisites)else'target'
   clauses.append(clause(id='order_'+str(i),kind='completion_order',before=before,after=after))
 for m in re.finditer(r'\b(?:keep(?:ing)?|leav(?:e|ing)|maintain(?:ing)?|preserv(?:e|ing))\s+(?:the\s+)?(?P<object>bowl|plate|cheese|cream cheese|wine bottle)\s+(?P<scope>.+?)(?=[.;]|$)',text):
  obj={'cream cheese':'cheese','wine bottle':'wine_bottle'}.get(m['object'],m['object']);name=OBJECTS[obj];scope=m['scope'];cid='preserve_'+obj
  command_scope=re.sub(r'\bin place\b','',scope)
  if re.search(r'\b(?:put|place|move|open|close|shut|return|turn|push|slide)\b',command_scope):raise UnsupportedObjective('extra_operation_in_keep_clause')
  if 'returned'in scope or ('there'in scope and restore_obj==obj):
   clauses.append(clause(id=cid,kind='preserve_position',object=name,reference_position=list(initial_xyz[name]),activation_after='restore_0'))
  elif any(w in scope for w in ['current position','where it is','on the stove','there','position at the instruction switch','position at instruction switch','instruction-switch position','same position','same place','in place','unchanged','undisturbed'])or re.fullmatch(r'(?:at )?its position(?: until (?:this instruction is complete|you are done|you\x27re done))?',scope):
   clauses.append(clause(id=cid,kind='preserve_position',object=name,reference_position=list(current_xyz[name])))
  elif 'drawer'in scope and any(w in scope for w in ['as it is','unchanged']):
   pass # drawer preservation handled below
  else:raise UnsupportedObjective('unverified_keep_clause:'+scope)
 drawer_keep=re.search(r'(?:keep(?:ing)?|leav(?:e|ing)|maintain(?:ing)?|preserv(?:e|ing))\s+(?:the\s+)?(?:(?P<level>middle|top)\s+)?drawer\s+(?:as it is|unchanged|at (?:its |the )?(?:instruction[- ]switch|current|same) opening(?: until this instruction is complete)?|in (?:its |the )?(?:current|same|instruction[- ]switch) state)',text)
 if drawer_keep:
  level=drawer_keep['level']
  if level is None:
   levels=[x for x in ('middle','top')if x+' drawer'in previous_instruction.lower()]
   if len(levels)!=1:raise UnsupportedObjective('drawer_preservation_level_requires_bound_context')
   level=levels[0]
  clauses.append(clause(id='preserve_'+level,kind='preserve_articulation_state',joint=level,reference_q=articulation[level]))
 binary_words=r'on(?:/|-|\s+(?:or\s+)?)off'
 stove_keep=re.search(r'(?:keep(?:ing)?|leav(?:e|ing)|maintain(?:ing)?|preserv(?:e|ing))\s+(?:the\s+)?stove\s+(?:(?:and (?:its|the) instruction[- ]switch )?(?:in|at) (?:(?:its|their|the) )?(?:(?:current|same)(?: instruction[- ]switch)?|instruction[- ]switch(?: current)?)(?: '+binary_words+r')? state(?: until this instruction is complete)?|and its instruction[- ]switch '+binary_words+r' state(?: until this instruction is complete)?|(?:as it is|unchanged))',text)
 if stove_keep:
  if current_binary_state is None or not isinstance(current_binary_state.get('turn_on_stove'),bool):raise UnsupportedObjective('stove_preservation_requires_bound_current_state')
  clauses.append(clause(id='preserve_stove',kind='preserve_predicate_state',predicate=['turnon','flat_stove_1'],reference_value=current_binary_state['turn_on_stove']))
 if re.search(r'\b(?:keep(?:ing)?|leav(?:e|ing)|maintain(?:ing)?|preserv(?:e|ing))\b',text):
  if not any(c['kind'].startswith('preserve_')for c in clauses):raise UnsupportedObjective('unparsed_persistent_clause')
 # A recognized final goal must not hide an extra unsupported operation.
 residual=text
 spans=[]
 for _,pattern in PATTERNS:
  spans.extend((m.start(),m.end())for m in re.finditer(pattern,text,re.I))
 spans.extend((m.start(),m.end())for m in restore+close)
 if canonical3:spans.append((canonical3.start(),canonical3.end()))
 if custom:spans.append((custom.start(),custom.end()))
 for start,end in sorted(spans,reverse=True):residual=residual[:start]+' '*(end-start)+residual[end:]
 residual=re.sub(r'\b(?:keep(?:ing)?|leav(?:e|ing)|maintain(?:ing)?|preserv(?:e|ing))\b[^.;]*','',residual)
 residual=re.sub(r'\brelease(?:\s+(?:it|them|the object|the bowl|the wine bottle|the cheese))?(?:\s+stably)?\b','',residual)
 residual=re.sub(r'\blet go(?: of (?:it|the object))?\b|\bdisengage(?: from the cabinet)?\b|\bmove the (?:gripper|hand) clear\b|\bwithdraw the gripper\b','',residual)
 if re.search(r'\b(?:put|place|move|open|close|shut|return|turn|switch|push|slide|pick|grasp)\b',residual):raise UnsupportedObjective('unparsed_physical_operation:'+residual.strip())
 return Objective(target_task=target,clauses=clauses,return_only=return_only,restore_object=restore_obj,close_only=close_only,open_only=open_only,custom_predicate=['on','cream_cheese_1','flat_stove_1_cook_region']if custom else None)
