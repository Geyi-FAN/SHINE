"""Agent generates the plan/text; validators only reject, never replace it."""
import json, os, time
from pathlib import Path
import urllib.request
from agent_transport import request_json
from planning_relation_memory import handoff_context,effective_bowl_drawer

ROOT = Path(__file__).resolve().parent
try:
    from .execution_profile import load_catalog, policy_template, is_smol
except ImportError:
    from execution_profile import load_catalog, policy_template, is_smol
CATALOG = load_catalog()
ENVELOPE = '; Coordinates: MAIN, 224x224, <y,x> pixels; Current Subgoal: '
LEGEND = '; The red arrow points to the referenced location in MAIN'

def codex_child_environment(environ):
    """Keep simulator/Cursor native libraries out of the independent CLI."""
    env=dict(environ)
    for name in ('LD_LIBRARY_PATH','LD_PRELOAD','PYTHONPATH','PYTHONHOME','BUNDLE_PATH',
                 'CODEX_THREAD_ID','CODEX_SESSION_ID','CODEX_TOOL_CALL_ID'):
        env.pop(name,None)
    env['CODEX_CI']='1'
    bypass=set(filter(None,(env.get('no_proxy','')+','+env.get('NO_PROXY','')).split(',')))
    bypass.update(('localhost','127.0.0.1','::1'))
    env['no_proxy']=env['NO_PROXY']=','.join(sorted(bypass))
    return env

def validate(inp, out, m2=None):
    if m2 is None:m2=os.environ.get("HYBRID_M2_CURRENT_ONLY","0")=="1"
    e=[]
    if not isinstance(out,dict):return ['Return a JSON object']
    if os.environ.get('CAP_REFERENCE_CONTRACT','0')=='1':
        from reference_contract import errors as reference_errors
        e.extend(reference_errors(inp,out))
    from planning_semantics import errors as semantic_errors
    e.extend(semantic_errors(inp,out))
    if out.get('complete_task') != inp['user_message']:e.append('complete_task must copy raw user_message exactly')
    status=out.get('status');plan=out.get('remaining_plan')
    if status not in ('plan_ready','hold','need_observation','need_clarification'):e.append('invalid status')
    if not isinstance(plan,list):return e+['remaining_plan must be a list']
    if any(not isinstance(s,dict) for s in plan):return e+['Each stage must be a JSON object']
    for s in plan:
        op=CATALOG.get(s.get('operation'))
        if not op:e.append('unknown operator');continue
        if s.get('kind')!=op['kind'] or s.get('object')!=op['object']:e.append('operator kind/object mismatch')
        if not isinstance(s.get('goal'),str) or '{' in s['goal']:e.append('goal must be ungrounded text')
        if 'release it stably' in op['template'] and ('releas' not in s.get('goal','').lower() or 'stabl' not in s.get('goal','').lower()):e.append('goal omits stable release')
    if os.environ.get('PLANNING_RELATION_REPAIR','1')=='1':
        import re
        preservation=re.search(r'\b(?:leave|keep)\s+the\s+bowl\s+(?:inside|in)\s+the\s+top\s+drawer',inp['user_message'],re.I)
        memory=inp['physical_state'].get('relation_state_memory',{}).get('bowl_drawer',{})
        relation=effective_bowl_drawer(inp['physical_state'])
        if preservation and relation is None and status in('plan_ready','hold'):
            e.append('The explicit keep/leave containment requirement is UNKNOWN and has no valid observed relation history. Do not assume it from the user words or a close event. Request observation/clarification, without executing or declaring hold/completion.')
        if preservation and relation is False and(status=='hold'or(status=='plan_ready'and(plan or[{}])[0].get('operation')in('close_top','open_middle'))):
            e.append('Current evidence contradicts the required bowl containment. Do not skip this user clause or declare completion; regenerate a task-consistent correction or ask for clarification.')
        if status=='need_observation'and plan and plan[0].get('operation')in CATALOG:
            chosen=CATALOG[plan[0]['operation']];reference=chosen['reference'];request=str(out.get('request')or'').lower()
            if reference:
                available=any(all(point.get(key)==value for key,value in reference.items())and point.get('available')is True for point in inp['reference_availability'])
                entity=reference['entity'].replace('_',' ')
                named=entity in request or(reference['entity']=='wine_bottle'and'bottle'in request)
                asks_missing=named and any(word in request for word in('provide','missing','unavailable','locate','need'))and('point'in request or reference['keypoint'].lower()in request)
                if available and asks_missing:
                    e.append('The reference for YOUR first chosen operation '+json.dumps(reference)+' is explicitly available:true in this input. Do not claim that point is missing. Re-read the supplied facts and regenerate; a different actual identity/ownership uncertainty may still request its specific evidence. Do not invent coordinates.')
        if preservation and effective_bowl_drawer(inp['physical_state'])is True:
            if any(s.get('operation')in('grasp_bowl','bowl_drawer')for s in plan):
                e.append('A valid observed bowl-in-drawer relation already supports the user preservation clause. Do not re-grasp or re-place that bowl; regenerate your own remaining plan.')
            first=(plan or[{}])[0].get('operation')
            request=str(out.get('request','')).lower()
            if(status=='need_observation'and memory.get('valid_for_planning')is True and
               inp['physical_state'].get('held_object')=='none'and first in('close_top','open_middle')and
               ('bowl'in request or'interior'in request)):
                e.append('You requested the bowl containment observation again although valid planning-only relation_state_memory already provides the last observed containment with provenance and no contrary intervention. Occlusion is not a new failure. Regenerate using that evidence, or identify a DIFFERENT concrete missing prerequisite; do not demand seeing through a closed drawer.')
    from plan_scope import errors as scope_errors
    e.extend(scope_errors(inp['user_message'], plan))
    if status == 'plan_ready':
        from plan_prerequisites import errors as prerequisite_errors
        e.extend(prerequisite_errors(inp['physical_state'], plan, CATALOG))
    if status!='plan_ready':
        if any(out.get(k) is not None for k in ('reference','current_subgoal_template','policy_prompt_template')):e.append('blocked/hold output must not execute')
        if status=='hold' and plan:e.append('hold requires empty plan')
        if status.startswith('need_') and not out.get('request'):e.append('provide request')
        if m2 and status=='need_observation' and plan and plan[0].get('operation') in CATALOG:
            first=CATALOG[plan[0]['operation']]
            if first['reference']:
                # Probe the Agent's OWN first operation, not an Oracle next stage.
                # This local object is validation-only and is never executed/returned.
                probe=dict(out,status='plan_ready',reference=first['reference'],current_subgoal_template=first['template'],policy_prompt_template=policy_template(inp['user_message'],first))
                if not validate(inp,probe,m2=False):
                    e.append('M2: Your own first planned operation has its required reference available and passes current prerequisites. Missing FUTURE references must not block it. Reconsider and regenerate your own executable current subgoal; do not invent coordinates or change task order.')
        return e
    if not plan or plan[0].get('operation') not in CATALOG:return e+['ready needs valid first operation']
    s=plan[0];op=CATALOG[s['operation']];ref=op['reference']
    if op['kind']=='maintain':e.append('use hold, not executable maintain')
    if out.get('reference')!=ref:e.append('reference does not match your chosen operator')
    if out.get('current_subgoal_template')!=op['template']:e.append('write exact training template of your chosen operator')
    expected=policy_template(inp['physical_state'].get('execution_language_task',inp['user_message']),op)
    if out.get('policy_prompt_template')!=expected:e.append('prompt envelope inconsistent; write the required model format exactly: '+repr(expected))
    if ref and not any(all(r.get(k)==v for k,v in ref.items()) and r.get('available') for r in inp['reference_availability']):e.append('current reference unavailable: request observation; never substitute')
    facts=inp['physical_state'];held=facts['held_object']
    tool=out.get('handoff_action','none')
    if tool not in ('none','observe_clear_cabinet','open_observed_empty_gripper'):e.append('invalid handoff_action')
    proof=facts.get('ownership_observation_memory')or{}
    width=facts.get('robot',{}).get('gripper_width_m')
    fresh_empty=(held=='none'and proof.get('planning_ownership_only')is True and
                 0<=inp['frame']-proof.get('revalidated_frame',proof.get('frame',-1000))<=4 and
                 proof.get('visual_evidence_frames')and width is not None and .002<=width<.065)
    needs_empty_open=fresh_empty and(op['kind']=='grasp'or s['operation']in('open_top','open_middle','close_top','close_middle'))
    existing_handoff=handoff_context(inp,s['operation'])['pending_existing_observation_handoff']
    if needs_empty_open and not existing_handoff and tool!='open_observed_empty_gripper':
        e.append('VERIFIED_EMPTY_HAND_PREPARATION: Fresh joint visual/RGB-D/proprio evidence supports an EMPTY hand, but measured fingers are partially closed. Before your chosen grasp/drawer operation, request handoff_action=open_observed_empty_gripper to open in place without Cartesian relocation. Keep authoring your own plan/subgoal. This does not authorize releasing an occupied/uncertain hand or declaring any task complete.')
    if tool=='open_observed_empty_gripper'and(not needs_empty_open or existing_handoff):
        e.append('EMPTY_OPEN_NOT_AUTHORIZED: This bounded tool needs fresh explicitly certified empty-hand evidence, partially closed fingers, and your own selected grasp/drawer operation, without a pending existing cabinet handoff. Do not infer emptiness from closed fingers or user intent.')
    if os.environ.get('PLANNING_HANDOFF_REPAIR','1')=='1':
        context=handoff_context(inp,s['operation'])
        if context['pending_existing_observation_handoff']and tool!='observe_clear_cabinet':
            e.append('Existing post-close handoff condition is met: empty hand, safe gripper, fresh handle distance below12cm, and no prior handoff for this close. Request observe_clear_cabinet before your chosen next operation; its future disengagement instruction is NOT a substitute. If a separate actual safety prerequisite is missing, request that observation instead. Do not invent a Retreat subgoal.')
        if tool=='observe_clear_cabinet':
            if not context['measurements_fresh']:e.append('Post-close handoff requires fresh current robot/distance observations.')
            if context['handle_distance_m']is not None and context['handle_distance_m']>=.12:e.append('The measured hand is already clear of that drawer; do not request redundant handoff.')
            width=context['gripper_width_m']
            if width is not None and .002<=width<.065:e.append('Partially closed gripper is not within the existing handoff controller safe dispatch conditions; request ownership/observation evidence, not an unexecutable handoff.')
    if tool=='observe_clear_cabinet':
        previous=inp['completed_events'][-1] if inp['completed_events'] else {}
        if not previous.get('operation','').startswith('close_'):e.append('cabinet handoff requires your own completed close stage, not a new user goal')
        if held!='none':e.append('cabinet handoff must not release a held object; first resolve ownership')
        if facts.get('robot',{}).get('handoff_for_close_step')==previous.get('confirmed_step'):e.append('This completed close stage already received its handoff tool; do not request it again.')
    import re
    preservation=re.search(r'\b(?:leave|keep)\s+the\s+bowl\s+(?:inside|in)\s+the\s+top\s+drawer',inp['user_message'],re.I)
    if preservation and facts['native_goal_relations'].get('bowl_drawer') is True and any(x.get('operation') in ('grasp_bowl','bowl_drawer') for x in plan):e.append('The user requests preserving an already observed containment, not placing again. Regenerate your plan without disturbing that bowl; keep the explicit drawer order.')
    if op['kind']=='grasp' and held==op['object']:e.append('already holding this object; revise using physical facts')
    if op['kind']=='grasp' and held not in ('none',op['object']):e.append('cannot acquire with another object held or ambiguous holding')
    if s['operation']=='bowl_drawer' and not facts['drawers']['top']['open']:e.append('top drawer not open')
    if op['kind']=='target' and op['object'] in ('bowl','cheese','wine_bottle') and held!=op['object'] and not facts['native_goal_relations'].get(s['operation'],False):e.append('placement prerequisite not met: object neither held nor already at destination')
    if op['kind']=='return' and not any(w in inp['user_message'].lower() for w in ('return','back','start','initial','原位','归位')):e.append('user did not request return')
    if s['operation'].endswith('_clear') and not any(w in inp['user_message'].lower() for w in ('clear','away','withdraw','撤离','移开')):e.append('user did not request clear variant')
    return e

class Planner:
    def __init__(self, model=None):
        from text_transport import connection
        cfg, key = connection('planning')
        self.model = cfg['model']
        self.normalized_task = None
        from temporal_plan_memory import TemporalPlanMemory
        self.progress_memory=TemporalPlanMemory()
        self.key = key
        self.url = cfg['chat_url']
        self.system=(ROOT/('prompt_smolvla_e3.txt' if is_smol() else 'prompt.txt')).read_text()+'\nGENERIC OPERATORS:\n'+json.dumps(CATALOG)
        if os.environ.get('PLANNING_HANDOFF_REPAIR','1')=='1':
            self.system+='\nPOST-CLOSE HANDOFF: physical_state.planning_handoff_context summarizes the ALREADY EXISTING12cm/empty-hand rule from current measurements. If pending_existing_observation_handoff is true and you execute a different next operation, write handoff_action="observe_clear_cabinet". Do not omit it because the next VLA instruction mentions disengagement. It is the existing bounded observation tool, not a new task or subgoal. Already-performed, held/uncertain payload, stale measurements or unsafe grip do not authorize it.'
        if os.environ.get('PLANNING_RELATION_REPAIR','1')=='1':
            self.system+='\nOBSERVED RELATION HISTORY: relation_state_memory is last-observed, planning-only evidence, NEVER simulator truth or new completion proof. latest_relation_observations retains the raw current proxy; a closed drawer makes that proxy unassessable. If valid_for_planning is true, use the labeled past containment to maintain an explicit keep/leave clause across occlusion; do not repeatedly demand to see through a closed drawer. Fresh contrary evidence or object/top-drawer intervention invalidates memory. Absent or invalid memory remains unknown; never infer containment from the user words. This does not fill missing current placement points or declare new task completion.'
            self.system+='\nFACT CONSISTENCY: Read reference_availability literally; available:true is not a missing point. A completed grasp in history is not current ownership; use the fresh held_object/support observations for reacquisition. With no valid containment memory and a currently unknown keep/leave relationship, request its evidence rather than assuming it or claiming all goals are satisfied.'
        from plan_scope import ADDENDUM
        self.system += ADDENDUM
        from plan_prerequisites import ADDENDUM as PREREQUISITES
        self.system += PREREQUISITES
        from planning_semantics import ADDENDUM as SEMANTICS
        self.system += SEMANTICS
        self.system+='\nVERIFIED EMPTY-HAND TOOL: handoff_action may also be "open_observed_empty_gripper". Request it before your selected grasp or drawer operation when fresh physical_state.ownership_observation_memory certifies EMPTY ownership from two visual opinions plus independent current RGB-D clearance and the measured hand is partially closed (.002m to .065m). It opens fingers at the SAME Cartesian pose for16 steps; no translation, no release of an occupied/uncertain hand, no new goal or completion. A closed empty hand can retain contact with a previous button/handle even though no movable object is held. An already-open hand does not need this tool. Existing post-close observe_clear_cabinet takes precedence when its own context is pending. The runtime independently rechecks the evidence before acting.'
        if os.environ.get('CAP_REFERENCE_CONTRACT','0')=='1':
            from reference_contract import ADDENDUM
            self.system+='\n'+ADDENDUM
    def generate(self, inp):
        # Strict allowlist: evaluator plans/contracts/next-stage answers cannot cross this boundary.
        assert set(inp)=={'user_message','physical_state','completed_events','reference_availability','episode_id','task_version','frame','mode'}
        if self.progress_memory.begin(inp):self.normalized_task=None
        from planning_semantics import explain
        inp=explain(inp)
        if os.environ.get('PLANNING_HANDOFF_REPAIR','1')=='1':
            import copy
            inp=copy.deepcopy(inp)
            inp['physical_state']['planning_handoff_context']=handoff_context(inp)
        if os.environ.get('REPAIR_TASK_LANGUAGE','0')=='1':
            from task_language import normalize
            import copy
            if self.normalized_task is None:self.normalized_task=normalize(self,inp['user_message'],inp['physical_state'].get('observed_scene_context'))
            inp=copy.deepcopy(inp)
            inp['physical_state']['execution_language_task']=self.normalized_task['output']['execution_task']
        if os.environ.get('CAP_REFERENCE_CONTRACT','0')=='1':
            from reference_contract import explain as explain_references
            inp=explain_references(inp)
        messages=[dict(role='system',content=self.system),dict(role='user',content=json.dumps(inp))]
        attempts=[];start=time.monotonic()
        for _ in range(3):
            body=dict(model=self.model,messages=messages,enable_thinking=False,response_format={'type':'json_object'},temperature=0,max_tokens=2600)
            request=urllib.request.Request(self.url,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
            response=request_json(request,timeout=float(os.environ.get('HYBRID_PLANNER_REQUEST_TIMEOUT','90')));content=response['choices'][0]['message']['content']
            try:out=json.loads(content)
            except ValueError:out=None
            errors=validate(inp,out)+self.progress_memory.errors(inp,out);attempts.append(dict(output=out,errors=errors))
            if not errors:
                self.progress_memory.record(inp,out)
                return dict(output=out,attempts=attempts,seconds=time.monotonic()-start,model=self.model,task_language=self.normalized_task)
            messages += [dict(role='assistant',content=content),dict(role='user',content='Regenerate your JSON; input-only validation errors: '+json.dumps(errors))]
        return dict(output=None,attempts=attempts,seconds=time.monotonic()-start,model=self.model,error='validation_exhausted')


class CodexPlanner:
    """Same contract/validator as Qwen; isolated ACP session via existing login."""
    def __init__(self):
        self.model = 'codex-configured-backend'
        self.system = (ROOT/('prompt_smolvla_e3.txt' if is_smol() else 'prompt.txt')).read_text()+'\nGENERIC OPERATORS:\n'+json.dumps(CATALOG)

    def generate(self, inp):
        import subprocess, signal
        assert set(inp)=={'user_message','physical_state','completed_events','reference_availability','episode_id','task_version','frame','mode'}
        start=time.monotonic();attempts=[];feedback=[]
        child_env=codex_child_environment(os.environ)
        local=ROOT.parent/'configs/unified_execution.local.json'
        proxy=os.environ.get('HYBRID_CODEX_PROXY')
        if not proxy and local.exists():proxy=json.loads(local.read_text()).get('codex_proxy')
        if proxy:
            child_env.update(http_proxy=proxy,https_proxy=proxy,HTTP_PROXY=proxy,HTTPS_PROXY=proxy)
        for _ in range(3):
            request=dict(system=self.system,input=inp,feedback=feedback,fast=os.environ.get('HYBRID_CODEX_FAST','0')=='1')
            proc=subprocess.Popen([str(ROOT.parent/'runtime/node/bin/node'),str(ROOT.parent/'scripts/codex_planner_request.mjs')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True,env=child_env)
            try:
                stdout,stderr=proc.communicate(json.dumps(request),timeout=120)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.communicate()
                return dict(output=None,attempts=attempts,seconds=time.monotonic()-start,model=self.model,error='codex_timeout')
            if proc.returncode:
                return dict(output=None,attempts=attempts,seconds=time.monotonic()-start,model=self.model,error='codex_timeout' if proc.returncode==2 else 'codex_backend_failed',exitcode=proc.returncode)
            response=json.loads(stdout);self.model=response['model']
            try:out=json.loads(response['text'])
            except ValueError:out=None
            errors=validate(inp,out,m2=False);attempts.append(dict(output=out,errors=errors))
            if not errors:return dict(output=out,attempts=attempts,seconds=time.monotonic()-start,model=self.model,backend='codex',config=response.get('config'),fast_requested=response.get('fast_requested'))
            feedback=errors
        return dict(output=None,attempts=attempts,seconds=time.monotonic()-start,model=self.model,error='validation_exhausted')


def make_planner(backend=None):
    backend=backend or os.environ.get('HYBRID_PLANNER_BACKEND','qwen')
    if backend=='qwen':return Planner(model='qwen3.8-max')
    if backend=='codex':return CodexPlanner()
    raise ValueError('planner backend must be qwen or codex')
