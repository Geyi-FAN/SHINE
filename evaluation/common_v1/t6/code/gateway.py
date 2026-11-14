"""T6 preparation/evidence adapter around the frozen single-Agent actor.

No reference answer/condition/GT enters Agent context. One original action owner.
"""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
ACTOR=ROOT.parent/'actors/B1'
sys.path[:0]=[str(ACTOR/'code'),str(ACTOR/'adapter/evaluator_v2'),str(ACTOR/'adapter/T1/reference')]
source=(ACTOR/'code/agent_gateway.py').read_text()
old="    else:raise ValueError('unsupported_endpoint')"
assert source.count(old)==1
source=source.replace(old,"    elif op=='t6_query':v=self.t6_query(body['body'])\n"+old)
old="   elif path=='/input_activity':command=dict(op='input_activity',body=body)"
assert source.count(old)==1
source=source.replace(old,"   elif path=='/eval/t6':command=dict(op='t6_query',body=body)\n"+old)
actor=type(sys)('t6_frozen_actor')
actor.__file__=str(ACTOR/'code/agent_gateway.py')
sys.modules[actor.__name__]=actor
exec(compile(source,str(ROOT/'code/generated_actor_adapter.py'),'exec'),actor.__dict__)
base=actor.base
original_generate=actor.generate
active_engine=None

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):base.write(p,v)

def public_panel(current,history):
    # History contains real replayed MAIN/WRIST, never GT points or reference answers.
    panel=Image.new('RGB',(256,416),'white');draw=ImageDraw.Draw(panel)
    draw.text((4,1),'CURRENT OBSERVATION',fill='black')
    panel.paste(Image.fromarray(current),(0,16))
    for i,(step,old)in enumerate(history[-2:]):
        x=i*128;draw.text((x+2,274),'HISTORY step '+str(step),fill='black')
        panel.paste(Image.fromarray(old).resize((128,128)),(x,288))
    return np.asarray(panel)

def audited_generate(context,images,folder):
    b=active_engine
    request_time=time.time()
    capture=b.captures.pop(id(context))
    rendered=[public_panel(img,[(step,frames[k])for step,frames in b.prefix_visual[-2:]])for k,img in enumerate(images)]
    d=b.root/'qa_inputs';d.mkdir(exist_ok=True)
    name=str(time.time_ns());paths=[]
    for label,array in zip(('MAIN','WRIST'),rendered):
        p=d/(name+'_'+label+'.png');Image.fromarray(array).save(p);paths.append(str(p))
    combined=d/(name+'_both.png');Image.fromarray(np.concatenate(rendered,axis=1)).save(combined)
    row=dict(request_time=request_time,snapshot_time=capture['time'],image_time=capture['time'],reason=context.get('reason'),
        user_revision=b.pending_agent_revision,context=context,images=paths,
        image=str(combined),sha256=sha(combined),facts=capture['facts'],
        input_geometry='CURRENT upper 256x256 per view; two labeled actually observed prefix history frames below')
    row['facts']['requested_at']=capture['time']
    row['facts']['offset_seconds']=capture['facts']['time']-capture['time']
    with (b.root/'QA_INPUTS.private.jsonl').open('a')as f:f.write(json.dumps(row,default=base.jsonable)+'\n')
    return original_generate(context,rendered,folder)

class Engine(actor.Engine):
    def __init__(self,args):
        global active_engine
        self.observer=None;self.prefix_visual=[];self.captures={};self.setup_requested=False
        super().__init__(args);active_engine=self
        # Same independent gate implementation, with unused atlas rendering removed.
        path=ACTOR/'adapter/evaluator_v2/t6_eval.py'
        text=path.read_text()
        text=text.replace('   from qa_image import qa_image\n','')
        text='\n'.join("   image=images[0]"if '   image=qa_image('in line else line for line in text.splitlines())
        ns=dict(__file__=str(path),__name__='private_t6_observer')
        exec(compile(text,str(ROOT/'code/private_gate_adapter.py'),'exec'),ns)
        self.observer=ns['Evaluator'](self,self.state,self.spec,self.root)
        self.replay_prefix()
        # This is the common, public current-task setup API, not an ASR question.
        self.current_task=self.spec['public_current_task']
        self.history.append(dict(role='user',text=self.current_task,source='benchmark_authorized_current_task_setup_NOT_ASR',time=time.time()))
        self.history.append(dict(role='tool',event='actual_visual_preparation_history_available',
            frames=[x[0]for x in self.prefix_visual],note='History images contain only earlier observations; use CURRENT for current-state claims.'))
        self.request_agent('authorized_current_task_setup')
        self.setup_requested=True;self.publish()
        save(self.root/'T6_ADAPTER_READY.json',dict(time=time.time(),prefix_verified=True,model='Qwen3.8-27B',question_not_injected=True))

    def replay_prefix(self):
        from sim_state import capture,identity
        folder=Path(self.spec['prefix']);meta=json.loads((folder/'PREFIX.json').read_text())
        assert meta['construction_gate_passed'] is True
        assert meta['fixture']['state_id']==self.spec['fixture']['state_id']
        assert {k:v['sha256']for k,v in meta['fixture']['assets'].items()}=={k:v['sha256']for k,v in self.spec['fixture']['assets'].items()}
        assert sha(folder/'actions.jsonl')==meta['actions_sha256']
        assert sha(folder/'endpoint.npz')==meta['endpoint_sha256']
        rows=[json.loads(x)for x in (folder/'actions.jsonl').read_text().splitlines()]
        assert len(rows)==meta['steps'] and [x['step']for x in rows]==list(range(1,len(rows)+1))
        self.prefix_visual.append((0,[np.ascontiguousarray(self.obs[k][::-1,::-1])for k in ['agentview_image','robot0_eye_in_hand_image']]))
        frames=self.root/'prefix_history';frames.mkdir(exist_ok=True)
        for row in rows:
            action=np.asarray(row['action'],float)
            assert action.shape==(7,)and np.isfinite(action).all()
            self.apply(action,'T6_common_prefix_not_scored_QA')
            if row['step'] in (len(rows)//2,len(rows)):
                images=[np.ascontiguousarray(self.obs[k][::-1,::-1])for k in ['agentview_image','robot0_eye_in_hand_image']]
                self.prefix_visual.append((row['step'],images))
                for k,array in zip(('MAIN','WRIST'),images):Image.fromarray(array).save(frames/(str(row['step'])+'_'+k+'.png'))
        actual=identity(capture(self.env))
        from t6_gate import condition_errors,HELD
        errors=condition_errors(self.spec['t6_card']['question_family'],self.spec['t6_card']['condition_id'],self.observer.latest)
        if actual!=meta['state_identity']:errors.append('prefix_endpoint_physical_state_drift')
        if self.observer.latest['physical']['held_object']!=HELD[self.spec['t6_card']['active_task_id']]:errors.append('prefix_end_wrong_held_object')
        save(self.root/'PREFIX_REPLAY.json',dict(passed=not errors,errors=errors,steps=len(rows),
            actual_state_identity=actual,expected_state_identity=meta['state_identity'],
            actions_sha256=meta['actions_sha256'],time=time.time(),no_endpoint_restore=True,
            memory_rebuilt_from_actual_observations=True))
        assert not errors,'prefix replay rejected: '+repr(errors)
        self.pose=base.PoseHold(self.obs,self.env.env.robots[0].controller)

    def snapshot_for_agent(self):
        self.record('causal_QA_snapshot_no_environment_step',False)
        context=super().snapshot_for_agent()
        self.captures[id(context)]=dict(time=self.last['time'],facts=self.private_facts())
        return context

    def private_facts(self):
        t=self.last;p=t['physical'];rows=t['measurements']
        return dict(time=t['time'],simulation_time=t['simulation_time'],step=t['step'],
            mode=self.state.mode,held=p.get('held_object'),objects=p.get('objects'),
            drawers=p.get('drawers'),relations=p.get('native_goal_relations'),
            articulation=rows.get('bowl',{}).get('articulation'),extra=t.get('evaluator_extra'),
            task_id=self.state.task_id,episode_id=self.state.episode,version=self.state.version,
            control_steps=self.control_steps,source='private_benchmark_ONLY_never_in_agent_context')

    def t6_query(self,body):
        op=body.get('op')
        if op=='gate':
            proof=self.observer.query(body)
            proof['identity']['task_version']=self.state.version
            return proof
        if op=='inspect':return self.observer.query(body)
        if op=='facts':return self.private_facts()
        raise ValueError('unsupported_T6_private_query')

actor.generate=audited_generate
actor.Engine=Engine
if __name__=='__main__':actor.main()
