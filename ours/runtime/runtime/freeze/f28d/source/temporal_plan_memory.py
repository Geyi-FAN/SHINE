"""Keep the Agent's own accepted plan history; reject unmotivated prefix resets.

Never creates a next operation, event, coordinate or physical measurement.
"""
import copy,re


class TemporalPlanMemory:
    def __init__(self):self.key=None;self.initial=None;self.initial_frame=None
    def begin(self,inp):
        key=(inp['episode_id'],inp['task_version'],inp['user_message'])
        changed=key!=self.key
        if changed:self.key=key;self.initial=None;self.initial_frame=None
        return changed
    def record(self,inp,out):
        if self.initial is None and out.get('status')=='plan_ready':
            self.initial=copy.deepcopy(out['remaining_plan']);self.initial_frame=inp['frame']
    def errors(self,inp,out):
        if not self.initial or not isinstance(out,dict)or out.get('status')!='plan_ready':return[]
        plan=out.get('remaining_plan')or[]
        if not plan:return[]
        obj=plan[0]['object'];held=inp['physical_state'].get('held_object')
        history=sorted((e for e in inp.get('completed_events',[])if e.get('outcome')=='completed'),key=lambda e:e['confirmed_step'])
        prefix=[];cursor=self.initial_frame-1
        for stage in self.initial:
            accepted=next((e for e in history if e['confirmed_step']>cursor and e['operation']==stage['operation']and e.get('object')==stage.get('object')),None)
            if accepted is None:break
            prefix.append(accepted);cursor=accepted['confirmed_step']
        ledger=[dict(operation=e['operation'],object=e['object'],confirmed_step=e['confirmed_step'])for e in prefix]
        latest_drawer={}
        for e in prefix:
            if e['operation'].startswith(('close_','open_')):latest_drawer['top'if e['operation'].endswith('top')else'middle']=e
        for level,e in latest_drawer.items():
            state=inp['physical_state'].get('drawers',{}).get(level,{})
            contrary=state.get('closed_current')is False if e['operation'].startswith('close_')else state.get('open')is False
            # A real prerequisite reversal may require unloading/replanning.
            # Missing evidence is not a measured reversal; old events are not
            # allowed to overrule a clearly supplied new contrary observation.
            if contrary:return[]
        suffix=' ORDERED ACCEPTED PREFIX (your own plan aligned to its EARLIEST matching accepted events, NOT the latest accidental loop): '+str(ledger)+'. A later unrequested repeat does not erase this already satisfied prefix. Re-read the user order, present evidence and your remaining goal; you still author every next operation.'
        current=plan[0]['operation']
        if current.startswith(('close_','open_'))and sum(s['operation']==current for s in self.initial)==1 and any(e['operation']==current for e in prefix):
            level='top'if current.endswith('top')else'middle';state=inp['physical_state'].get('drawers',{}).get(level,{})
            satisfied=state.get('closed_confirmed')is True if current.startswith('close_')else state.get('open')is True
            if satisfied:return['TEMPORAL_PLAN_MEMORY_CONFLICT: This drawer goal already has an accepted completion in your ordered plan AND current observation still confirms its goal state. Do not re-enact the completed operation or ask to free an occupied hand solely for that redundant action.'+suffix]
        if plan[0].get('kind')!='return'or held!=obj:return[]
        returns=[(i,s)for i,s in enumerate(self.initial)if s.get('kind')=='return'and s.get('object')==obj]
        if len(returns)!=1:return[]
        i=returns[0][0]
        transports=[s for s in self.initial[i+1:]if s.get('kind')=='target'and s.get('object')==obj]
        if not transports:return[]
        user=inp['user_message'].lower()
        # Repeated requests/persistent constraints may legitimately require repair.
        if re.search(r'\b(?:again|once more|keep|leave|maintain|remain)\b|再次|再归位|保持',user):return[]
        prior=[e for e in prefix if e.get('object')==obj and e.get('operation','').startswith('return_')]
        grasps=[e for e in history if e.get('operation')=='grasp_'+obj]
        if not prior or not grasps or grasps[-1]['confirmed_step']<=prior[-1]['confirmed_step']:return[]
        return ['TEMPORAL_PLAN_MEMORY_CONFLICT: Your OWN accepted plan at frame '+str(self.initial_frame)+
            ' contains exactly one earlier return of '+obj+' followed by a later requested transport of that SAME object. '+
            'Accepted observed events confirm that return at '+str(prior[-1]['confirmed_step'])+
            ' and a subsequent grasp at '+str(grasps[-1]['confirmed_step'])+'. The current hand holds '+obj+
            '. During that later transport its departure from the start is expected; current returned_and_released=false does not by itself cancel the earlier event. '+
            'Re-read the original user order and regenerate only the remaining plan. Do not restart the completed prefix solely to make an earlier temporary goal true again. '+
            'These are observed estimates, not simulator truth: if you have a concrete evidence conflict, request its observation. No next-stage answer or new completion is supplied.'+suffix]
