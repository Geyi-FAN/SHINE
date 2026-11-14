"""Language-only extension of the selected-task verifier; no plan or answer.

Keep the actual public instruction and all physical thresholds unchanged.
Normalize only equivalent conjunction boundaries and binary stove prohibitions.
"""
import re

PERSIST_PREFIX=re.compile(r'^(?P<keep>(?:keep(?:ing)?|leave|leaving|maintain(?:ing)?|preserv(?:e|ing))\s+(?:the\s+)?(?:stove|bowl|plate|cream cheese|cheese|wine bottle)\s+[^.;]*?)(?:,?\s+)(?:and\s+then|and|then)\s+(?=(?:please\s+)?(?:put|place|move|push|slide|open|close|shut|return|turn|switch)\b)',re.I)
EXPLICIT_STOVE=re.compile(r'\b(?:keep(?:ing)?|leave|leaving|maintain(?:ing)?|preserv(?:e|ing))\s+(?:the\s+)?stove\s+(?P<value>off|on)\b',re.I)
STOVE_PROHIBITION=re.compile(r"\b(?:do not|don't|never)\s+(?:turn|switch)\s+(?:on\s+(?:the\s+)?stove|(?:the\s+)?stove\s+on)\b",re.I)

def normalize_selected_task(text,current_binary_state):
    # A prohibition on switching ON is a persistent OFF requirement, never a
    # command to actuate the switch. Unknown/currently ON cannot masquerade OFF.
    text=STOVE_PROHIBITION.sub('keep the stove off',text)
    literals=list(EXPLICIT_STOVE.finditer(text))
    desired={m['value'].lower()=='on'for m in literals}
    from continuation.live.objectives import UnsupportedObjective
    if len(desired)>1:raise UnsupportedObjective('conflicting_explicit_stove_states')
    if desired:
        if current_binary_state is None or type(current_binary_state.get('turn_on_stove'))is not bool:
            raise UnsupportedObjective('explicit_stove_preservation_requires_observed_current_state')
        expected=next(iter(desired))
        if current_binary_state['turn_on_stove']!=expected:
            raise UnsupportedObjective('explicit_stove_state_not_satisfied_at_activation')
        if not expected and re.search(r'\b(?:turn|switch)\s+(?:on\s+(?:the\s+)?stove|(?:the\s+)?stove\s+on)\b',EXPLICIT_STOVE.sub('',text),re.I):
            raise UnsupportedObjective('conflicting_stove_preservation_and_action')
        text=EXPLICIT_STOVE.sub('keep the stove in its current state',text)
    # Semicolon delimits an already explicit maintenance clause from the next
    # command. It does not add/delete operations, roles, destinations or order.
    return PERSIST_PREFIX.sub(lambda m:m['keep']+'; ',text,count=1)

def install():
    from continuation.live import objectives
    from t3_adapter.runtime_repairs import _rebind
    old=objectives.compile_objective
    if getattr(old,'t4_persistent_verifier',False):return
    def compile_objective(instruction,initial_xyz,current_xyz,articulation,case_id='live',previous_instruction='',source_task_start_xyz=None,current_binary_state=None):
        normalized=normalize_selected_task(instruction,current_binary_state)
        return old(normalized,initial_xyz,current_xyz,articulation,case_id,previous_instruction,source_task_start_xyz,current_binary_state)
    compile_objective.t4_persistent_verifier=True
    _rebind(old,compile_objective)
