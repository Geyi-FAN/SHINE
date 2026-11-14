"""Additional validation of an Agent-authored small downward approach."""
from recovery_effort import review as effort_review


def review(response,context,diagnosis):
    out=effort_review(response,context,diagnosis)
    if response.get('status')=='program'and out.get('validated_plan_summary'):
        commands=out['validated_plan_summary']['commands']
        descent=any(c['tool']=='move_relative'and c['arguments'].get('dz_m',0)<0 for c in commands)
        if descent and(response.get('approach_path_clear')is not True or context.get('stage_kind')!='grasp'):
            out['errors'].append('A new downward approach needs approach_path_clear=true from CURRENT images and a selected grasp; no route or task change is authorized')
            out['ok']=False
    return out
