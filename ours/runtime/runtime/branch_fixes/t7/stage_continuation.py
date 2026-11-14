"""Candidate only: same unfinished grasp continuation is not a new re-grasp.
Does not select a stage, retire one, reset a clock, or assert ownership/goal.
"""
ADDENDUM='''
UNFINISHED OPERATION CONTINUATION: physical_state.active_execution_stage is the
actual currently selected operation. If completed:false, it has not been
retired. held_object alone is a fallible ownership cue, not proof of the full
grasp-and-LIFT-CLEAR goal. You may author a plan continuing that SAME unfinished
grasp, even if the ownership estimate names its object; continuing the existing
operation is not a fresh duplicate grasp. Its original start/clock is kept.
Do not select a later placement just because holding is estimated. If evidence
is genuinely missing, name the specific remaining goal fact; repeating the
same already-answered ownership question supplies no new evidence. A NEW grasp
after an accepted completed grasp remains redundant. You still choose the plan,
write the training template, and need original completion evidence to advance.
PRECEDENCE: The generic "already holding, skip grasp" rule applies to a NEW
operation, not continuing a selected unfinished grasp. A fallible held_object
label MUST NOT override active_execution_stage.completed:false. Until an
accepted completion retires the active stage, your first executable operation
MUST have its same operation/kind/object. If its current reference is available,
a continuation of that existing grasp is admissible and still aims to complete
its original lift-clear goal. Do not jump to placement, do not invent a completed
event, and do not ask merely to reconfirm the already supplied completion flag.
Request observation only for a specifically missing prerequisite; not as a way
to evade continuing an executable, unfinished operation.
'''
ERROR='already holding this object; revise using physical facts'

def continues_unfinished_grasp(inp,out):
    if not isinstance(out,dict)or out.get('status')!='plan_ready':return False
    facts=inp.get('physical_state')or{};active=facts.get('active_execution_stage')or{}
    first=(out.get('remaining_plan')or[{}])[0]
    entered=active.get('entered_step')
    if not isinstance(entered,(int,float)):return False
    for event in inp.get('completed_events',[]):
        if event.get('outcome')=='completed' and event.get('operation')==active.get('operation') and event.get('object',active.get('object'))==active.get('object'):
            if event.get('entered_step')==entered:return False
            if event.get('entered_step')is None:
                confirmed=event.get('confirmed_step')
                if not isinstance(confirmed,(int,float))or confirmed>=entered:return False
    return (active.get('completed')is False and active.get('kind')=='grasp'
        and facts.get('observed_step')==inp.get('frame')==active.get('observation_frame')
        and all(active.get(k)==first.get(k)for k in ['operation','kind','object'])
        and facts.get('held_object')==active.get('object'))

def validate_with(base,inp,out,*args,**kwargs):
    errors=base(inp,out,*args,**kwargs)
    if continues_unfinished_grasp(inp,out):return [e for e in errors if e!=ERROR]
    return errors


def install(module):
    if getattr(module.validate,'_t7_same_grasp_continuation',False):return
    previous=module.validate
    def validate(inp,out,*args,**kwargs):return validate_with(previous,inp,out,*args,**kwargs)
    validate._t7_same_grasp_continuation=True
    module.validate=validate
    init=module.Planner.__init__
    def initialize(planner,*args,**kwargs):
        init(planner,*args,**kwargs)
        planner.system+='\n'+ADDENDUM
    module.Planner.__init__=initialize
