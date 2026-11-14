"""Agent-written execution wording, using original user text only."""
import json, time, urllib.request
from agent_transport import request_json
SYSTEM='''Rewrite the user's robot request into concise English compatible with manipulation training.
Preserve EVERY requested object, destination, temporal source, operation order and keep/leave condition.
Do not add an initial-position return, a drawer closure, a new destination, or a keep condition absent from the user.
"Leave X inside Y" means preserve existing containment; never turn it into pick-and-place.
Clarify an open/close drawer operation with "using its handle". Placement wording may explicitly
include "release it stably" as the normal physical meaning of placing; do not add a separate retreat.
Use the full task, not only the current phase. The Task line describes requested goals,
not a primitive action list: NEVER insert pick up, grasp, acquire or lift unless the original
user explicitly asked for that action. Acquiring an object belongs to the current subgoal,
not an unconditional full-task instruction. Use "place" for the user's "put"; preserve
"return" as return to the SAME historical starting position and stable release, never
rewrite it into a new pick-up instruction. Do not remove an explicit stable release.
 Do not invent observed state, completion or coordinates.
If a current_image_observation is provided, you may identify the destination bowl
with its CURRENT observed support, e.g. "the bowl currently on top of the cabinet"
or "the bowl currently on the stove". This is perceptual grounding of the SAME bowl,
not a command to move the bowl. Use it for cheese-into-bowl only when the user's full
task does not itself move/return the bowl first; otherwise the current support may
become outdated. Never convert that descriptor into a bowl transport operation.
Return JSON {execution_task: string, semantic_changes: [], rationale: string}.
execution_task must have no trailing full stop. semantic_changes must be empty: only wording clarification is permitted.'''
def wording_errors(raw,text):
    import re
    errors=[];lower=text.lower();original=raw.lower()
    if re.search(r'\b(?:pick\s+up|grasp|acquire|lift)\b',lower) and not re.search(r'\b(?:pick\s+up|grasp|acquire|lift)\b',original):
        errors.append('Do not insert a grasp/pick-up/lift prerequisite into the complete Task. Keep those in current subgoals only.')
    if re.search(r'\breturn\b',original) and not re.search(r'\breturn\b',lower):errors.append('Preserve return and its historical temporal source explicitly.')
    if 'stabl' in original and 'stabl' not in lower:errors.append('Preserve the explicit stable release/stability requirement.')
    if re.search(r'\b(?:leave|leaving|keep|keeping)\b',original) and not re.search(r'\b(?:leave|leaving|keep|keeping)\b',lower):errors.append('Preserve the keep/leave condition.')
    if re.search(r'\breturn\b',lower) and not re.search(r'\b(?:return|back)\b',original):errors.append('Do not add an unrequested return.')
    if re.search(r'\bclose\b',lower) and not re.search(r'\bclose\b',original):errors.append('Do not add an unrequested close operation.')
    if re.search(r'\b(?:keep|keeping|leave|leaving)\b',lower) and not re.search(r'\b(?:keep|keeping|leave|leaving)\b',original):errors.append('Do not add a keep/leave requirement absent from the user.')
    if any(x in text for x in '{}<>'):errors.append('No numeric position/placeholder in normalized task.')
    return errors

def normalize(planner,raw,observed_context=None):
    start=time.monotonic();attempts=[]
    messages=[dict(role='system',content=SYSTEM),dict(role='user',content=json.dumps(dict(original_user_message=raw,current_image_observation=observed_context))) ]
    for _ in range(3):
        body=dict(model=planner.model,messages=messages,
            enable_thinking=False,response_format=dict(type='json_object'),temperature=0,max_tokens=1100)
        request=urllib.request.Request(planner.url,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+planner.key,'Content-Type':'application/json'})
        out=request_json(request,timeout=90)
        content=out['choices'][0]['message']['content'];pred=json.loads(content)
        assert isinstance(pred.get('execution_task'),str) and pred['execution_task'].strip()
        errors=wording_errors(raw,pred['execution_task'])
        if pred.get('semantic_changes')!=[]:errors.append('Only wording clarification is allowed, with no reported task changes.')
        attempts.append(dict(output=pred,errors=errors,usage=out.get('usage')))
        if not errors:return dict(raw_user_message=raw,output=pred,attempts=attempts,seconds=time.monotonic()-start,usage=out.get('usage'))
        messages += [dict(role='assistant',content=content),dict(role='user',content='Regenerate from the original request. Validation: '+json.dumps(errors))]
    raise ValueError('Agent task wording failed validation: '+json.dumps(attempts))
