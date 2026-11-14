"""Existing v2.5 full-task terminal feedback, never intermediate Agent state.

Use the public-instruction compiler's selected target and the existing private
terminal measurement windows. No pose, point, plan or next-stage answer is sent
to the Agent. Thresholds are exactly the independent placement scorer's rules.
"""
OBJECTS={1:'bowl',2:'wine_bottle',3:'bowl',4:'bowl',5:'plate',6:'cheese',8:'bowl',9:'wine_bottle'}
def evidence(bridge):
    from benchmark_metrics.events import restore_window
    obj=OBJECTS.get(bridge.case['target_task'])
    if obj is None or getattr(bridge,'return_only',False) or getattr(bridge,'live_close_only',False) or getattr(bridge,'live_open_only',False):
        return dict(required=False,passed=True,source='existing_full_task_terminal_feedback_v25')
    frames=list(bridge.cache_reader.windows.get(obj,[]))
    if not frames:return dict(required=True,passed=False,source='existing_full_task_terminal_feedback_v25',object=obj,reason='terminal_measurements_unavailable')
    clause=dict(reference_position=frames[-1]['object_position'],stable_required=True,withdraw_required=False)
    result=restore_window(frames,clause,1e6,bridge.rules)
    return dict(required=True,passed=bool(result['complete']),object=obj,
                source='existing_full_task_terminal_feedback_v25',measurements=len(frames),
                phase='full_task_only',position_or_point_disclosed=False)
