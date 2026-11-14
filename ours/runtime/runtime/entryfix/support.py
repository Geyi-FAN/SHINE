"""Private physical evidence: loaded bowl-side contacts include friction forces.

Never used as a point, planning instruction or permission. Legacy contact and
all numeric windows remain logged. The supplement is only for native bowl
containment, with upward non-robot load below COM exceeding the existing
minimum support force. Release and stability are still separate requirements.
"""
import copy
import numpy as np

def container_support(mon):
    m,d=mon.model,mon.live;contacts=[]
    for i,c in enumerate(d.contact[:d.ncon]):
        a,b=int(c.geom1),int(c.geom2)
        if(a in mon.target_geoms)==(b in mon.target_geoms):continue
        other=a if b in mon.target_geoms else b
        if other in mon.robot_geoms or mon.object_geom_owner.get(other)!='akita_black_bowl_1':continue
        force=np.zeros(6);mon.mj.mj_contactForce(m,d,i,force)
        world=c.frame.reshape(3,3).T@force[:3];world*=1 if b in mon.target_geoms else-1
        if c.pos[2]>=d.xipos[mon.target_body,2]-.001:continue
        contacts.append(dict(geom1=a,geom2=b,normal_z=float(abs(c.frame.reshape(3,3)[0,2])),normal_force=float(force[0]),upward_force=float(world[2]),contact_z=float(c.pos[2])))
    # LIBERO's official task6 BDDL uses On(cheese,bowl), not In(region).
    native=bool(mon.env.env._eval_predicate(['on','cream_cheese_1','akita_black_bowl_1']))
    up=sum(c['upward_force']for c in contacts);threshold=mon.config.minimum_support_force
    return dict(native_containment=native,loaded=bool(native and up>=threshold),upward_contact_force_newton=up,minimum_support_force_newton=threshold,contacts=contacts,source='current_private_simulator_normal_plus_friction_force')

def augmented(mon,measurement):
    out=copy.deepcopy(measurement);ev=container_support(mon)
    out['geometric_support_contact']=out.get('geometric_support_contact',out['support_contact']);out['container_support_evidence']=ev
    out['support_contact']=bool(out['support_contact']or ev['loaded']);return out

def install(cls):
    # The final acceptance used augmented target measurements, but private
    # recorders read a DIFFERENT monitor via cache_reader. Both must measure
    # the same existing loaded-contact predicate. This private reader never
    # supplies positions or intermediate completions to the online Agent.
    original_init=cls.__init__
    def initialize(b,*args,**kwargs):
        original_init(b,*args,**kwargs)
        mon=b.cache_reader.mon['cheese'];raw=mon.measure
        mon.measure=lambda:augmented(mon,raw())
    cls.__init__=initialize
    original=cls.measure
    def measure(b,phase):
        mon=b.target
        if mon.target_name!='cream_cheese_1':return original(b,phase)
        old=mon.measure;mon.measure=lambda:augmented(mon,old())
        try:return original(b,phase)
        finally:mon.measure=old
    cls.measure=measure
    # The historical gate had a containment exception which did not check
    # actual load. Keep its release/stability/40-step checks, require load too.
    from t3repair.terminal import CompletionGate
    observe=CompletionGate.observe
    def guarded(self,row,subject,target_task,return_only=False,full_contract=False):
        if target_task==6 and not return_only:
            row=copy.deepcopy(row)
            row['adjusted_goal']=bool(row['adjusted_goal']and row['target']['support_contact'])
        return observe(self,row,subject,target_task,return_only,full_contract)
    CompletionGate.observe=guarded
