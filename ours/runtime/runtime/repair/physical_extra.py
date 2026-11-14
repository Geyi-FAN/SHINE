"""Private evaluator/setup evidence; never exported to a planning tool."""
import math

def evidence(env,obs):
    sim=env.sim;names=sim.model.geom_names;cabinet=[i for i,n in enumerate(names)if n and str(n).startswith('wooden_cabinet_1')]
    contact=False
    for i in range(sim.data.ncon):
        c=sim.data.contact[i];a,b=int(c.geom1),int(c.geom2)
        if a in cabinet or b in cabinet:
            other=b if a in cabinet else a;name=str(names[other]or'')
            contact|=name.startswith(('robot0_','gripper0_'))
    xyz=obs['robot0_eef_pos'];distance=min((math.dist(xyz,sim.data.geom_xpos[i])for i in cabinet),default=None)
    out=dict(cabinet_robot_contact=contact if cabinet else None,hand_to_cabinet_geom_center_m=distance)
    try:out['cheese_stove']=bool(env.env._eval_predicate(['on','cream_cheese_1','flat_stove_1_cook_region']))
    except (KeyError,ValueError,AttributeError):out['cheese_stove']=None
    return out
