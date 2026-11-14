"""Reject hidden simulator facts before a planner request is sent."""
import json,time
FORBIDDEN={'oracle_for_scoring_only','oracle_next_stage','oracle_event',
           'object_position','object_quaternion_wxyz','simulator_object_pose',
           'cache_validity_private','cache_reusable','initial_xyz'}
def validate(value):
    if isinstance(value,dict):
        bad=FORBIDDEN.intersection(value)
        if bad:raise RuntimeError('Private facts reached planner boundary: '+','.join(sorted(bad)))
        if value.get('source')=='simulator_physical_facts_v2.5':
            raise RuntimeError('Simulator physical snapshot reached planner')
        for item in value.values():validate(item)
    elif isinstance(value,(list,tuple)):
        for item in value:validate(item)
def audit_planner(inp,bridge):
    validate(inp)
    for event in inp.get('completed_events',[]):
        if any(x in event.get('source','').lower()for x in ['oracle','simulator']):
            raise RuntimeError('Private stage event reached planner')
    with(bridge.root/'nonoracle_boundary.jsonl').open('a')as f:
        f.write(json.dumps(dict(time=time.time(),episode=bridge.state.episode,
            task=bridge.state.task_id,version=bridge.state.version,
            planner_input_private_fields_absent=True,
            subgoal_source='cloud_agent',point_source='YOLO',
            memory_validity_source='visual_consensus_and_robot_proprioception',
            intermediate_completion='observed_RGBD_proprio_and_cloud_verifier',
            final_metric_source='independent_simulator_evaluator'))+'\n')
