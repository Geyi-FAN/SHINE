"""Forward real planner observation requests and dispatch the existing bounded tool.

No task IDs, private contract, object truth, coordinate fallback or subgoal
generation. All motion still passes the existing owner/token/pause guards.
"""
import ast,copy,hashlib,math
from functools import wraps

VERSION='planner-observation-context-and-empty-view-v1'
ADDENDUM='''
PLANNER OBSERVATION REQUEST CONTEXT: When reason=planner_requested_observation,
planner_request is the actual planning Agent's unresolved observation request,
not a completion answer. Answer THAT request, not a generic scene description.
Current selected_stage is still unfinished; a past grasp is not current ownership.
If a needed YOLO point is absent, recognizing an object is not a numeric point:
never invent coordinates and do not say none means that request is resolved.
If selected_stage is cheese_bowl, the hand is CURRENTLY empty with measured OPEN
fingers, and MAIN/WRIST clearly show a free short upward path, observe_above is
also available to raise the empty camera/hand WORLD+z3cm for a fresh view.
It is an observation tool only; never grasp, release, complete or change tasks.
Do not request it under a roof, with uncertain clearance/ownership or with a
carried object. When unsure, observe_only. The controller checks fresh evidence,
open/empty state, current task ownership and at most2 raises per selected stage.
'''

def request_context(recovery,mon):
    if recovery.pending!='agent_requested':return None
    event=next((e for e in reversed(recovery.events)if e.get('event')=='agent_requested_observation'),None)
    if not event or not isinstance(event.get('request'),str)or not event['request'].strip():return None
    age=mon.last-event.get('frame',-1000)
    if not 0<=age<=64:return None
    if event.get('stage_entered')!=mon.entered or event.get('selected_stage')!=mon.active:return None
    return dict(reason='planner_requested_observation',planner_request=event['request'],
        request_frame=event['frame'],selected_stage=copy.deepcopy(mon.active),
        completion_created=False,request_source='actual_planning_agent_output')

def install_context(cls=None):
    if cls is None:
        from recovery_runtime import RecoveryRuntime as cls
    old=cls.inspect
    if getattr(old,'_t06l_context_handoff',False):return
    @wraps(old)
    def inspect(recovery,mon):
        context=request_context(recovery,mon)
        if context:
            original=mon.diagnostics.get('observation_request_context')
            # Explicit current-target or tool contexts remain stronger.
            if not original or original.get('reason')=='planner_requested_observation':
                mon.diagnostics=dict(mon.diagnostics,observation_request_context=context)
                recovery.events.append(dict(event='planner_observation_context_forwarded',frame=mon.last,
                    request_frame=context['request_frame'],request=context['planner_request'],creates_completion=False))
        return old(recovery,mon)
    inspect._t06l_context_handoff=True;cls.inspect=inspect
    import recovery_observer
    if ADDENDUM not in recovery_observer.SYSTEM:recovery_observer.SYSTEM+='\n'+ADDENDUM
    recovery_observer.RecoveryObserver.check.__globals__['SYSTEM']=recovery_observer.SYSTEM

def raise_proof(mon,recovery,prediction,attempts,step):
    if not isinstance(prediction,dict)or prediction.get('recovery_request')!='observe_above':return None
    active=mon.active or{}
    if active.get('operation')!='cheese_bowl'or active.get('kind')!='target':return None
    context=request_context(recovery,mon)
    if not context or not mon.samples:return None
    width=mon.samples[-1]['width']
    if not isinstance(width,(int,float))or not math.isfinite(width)or width<.065:return None
    if mon.held!='none' or prediction.get('held_object')!='none':return None
    facts=recovery.visual_facts or{}
    if facts.get('frame')!=mon.last or facts.get('recovery_request')!='observe_above':return None
    if mon.last not in prediction.get('evidence_frames',[]):return None
    if recovery.grip_release_until is not None:return None
    key=(active['operation'],mon.entered)
    if attempts.get(key,0)>=2:return None
    return dict(request=context['planner_request'],source_frame=mon.last,
        request_frame=context['request_frame'],operation=active['operation'],
        stage_entered=mon.entered,attempt=attempts.get(key,0)+1,world_z_m=.03,
        gripper='measured_open_and_empty; retain',creates_completion=False)

def transform(tree):
    count=0;event_count=0
    class Dispatch(ast.NodeTransformer):
        def visit_Call(self,node):
            nonlocal event_count
            self.generic_visit(node)
            if isinstance(node.func,ast.Name)and node.func.id=='dict'and any(k.arg=='event'and isinstance(k.value,ast.Constant)and k.value.value=='agent_requested_observation'for k in node.keywords):
                node.keywords.extend([ast.keyword(arg='selected_stage',value=ast.parse('dict(mon.active) if mon.active is not None else None',mode='eval').body),ast.keyword(arg='stage_entered',value=ast.parse('mon.entered',mode='eval').body)])
                event_count+=1
            return node
        def visit_If(self,node):
            nonlocal count
            self.generic_visit(node)
            if ast.unparse(node.test)=='step >= recovery_wait_until':
                first=node.body[0]
                if not(isinstance(first,ast.Expr)and ast.unparse(first.value)=='recovery.inspect(mon)'):raise ValueError('Unexpected pending inspection')
                prefix=ast.parse('''prediction = recovery.inspect(mon)
view_proof = _t06l_raise_proof(mon, recovery, prediction, stage_observation_attempts, step)
if view_proof is not None:
    recovery_pose = PoseHold(obs, env.env.robots[0].controller)
    recovery_pose.xyz[2] += .03
    target_observation_until = step + 12
    observation_wait = True
    stage_observation_attempts[(mon.active['operation'], mon.entered)] = view_proof['attempt']
    recovery.events.append(dict(frame=step, event='agent_requested_empty_hand_camera_raise', **view_proof))
''').body
                node.body=prefix+node.body[1:];count+=1
            return node
    tree=Dispatch().visit(tree)
    if count!=1 or event_count!=1:raise ValueError('Expected one observation dispatcher/event, got '+str((count,event_count)))
    ast.fix_missing_locations(tree);return tree

def install(cls):
    install_context()
    original=cls.build_run_function
    if getattr(original,'_t06l_observation_dispatch',False):return
    def build(bridge):
        original(bridge)
        path=bridge.root/'generated_kernel.py';tree=transform(ast.parse(path.read_text()))
        namespace=dict(bridge.run_function.__globals__,_t06l_raise_proof=raise_proof)
        exec(compile(tree,str(path),'exec'),namespace)
        code=ast.unparse(tree)+'\n';path.write_text(code);bridge.run_function=namespace['run']
        bridge.log('t06l_observation_dispatch_compiled',version=VERSION,
            actual_kernel_guarded=True,generated_kernel_sha256=hashlib.sha256(code.encode()).hexdigest(),
            no_coordinate_or_completion_created=True,owner_and_pause_guards_preserved=True,
            max_per_stage=2,raise_m=.03,control_ticks=12)
    build._t06l_observation_dispatch=True;cls.build_run_function=build

def identity(cls):
    from recovery_runtime import RecoveryRuntime
    return dict(version=VERSION,actual_context_guarded=bool(getattr(RecoveryRuntime.inspect,'_t06l_context_handoff',False)),
        actual_dispatch_guarded=bool(getattr(cls.build_run_function,'_t06l_observation_dispatch',False)),
        agent_request_not_reference_answer=True,independent_score_changed=False)
