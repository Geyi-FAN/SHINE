"""Preserve already-authorized, verified English Task; Agent still writes plans."""
import re
def literal_task(state,raw,contract):
    if raw!=getattr(state,'instruction',None)or not re.fullmatch(r'[\x20-\x7e\n]+',raw):return False
    record=getattr(state,'task_record',None)or{};candidate=record.get('candidate_contract')or{}
    if any(record.get(k)or candidate.get(k)for k in('preconditions','persistent_constraints')):return False
    if record.get('reference_memory_ids')or candidate.get('reference_memory_ids'):
        # IDs are retained in the live task record and planner context. They
        # are not extra instructions. Reuse only its exact, checked full text.
        if not(record.get('complete_instruction')==raw and candidate.get('instruction')==raw and not candidate.get('unresolved')and candidate.get('semantic_check',{}).get('decision')=='checked'):return False
    clauses=(contract or{}).get('clauses',[])
    return bool(clauses)and all(c.get('source')=='case.instruction.live_selected_public_task'for c in clauses)

PLANNER_ADDENDUM='''
PHYSICAL GOAL WORDING: Every target/place/return step goal must explicitly state
that the object is released stably ("released stably"). "placed stably" alone
omits release. Apply this to FUTURE placement steps too, even while the current
step is drawer closing. Grasp goals should say held, not released. Keep the user
task unchanged. Never add a return or drawer closing that the user did not request.
The remaining_plan[].goal fields are UNGROUNDED physical-state text. Never put
coordinates or brace placeholders into goal. Symbolic position references belong
ONLY in current_subgoal_template and policy_prompt_template. A goal can say
"the bowl is on the plate, released stably"; it cannot contain {current.plate.K3}.
'''
