"""Canonical sentence endings only; Agent still selects/writes every subgoal."""
import copy
def clean_ending(text):return text.rstrip().rstrip('.').rstrip()
def install(profile,planner):
    if getattr(profile.policy_template,'_sentence_boundary_fixed',False):return
    old=profile.policy_template
    def template(task,operator):
        if not profile.is_smol():return old(task,operator)
        op=copy.deepcopy(operator);op['template']=clean_ending(op['template'])
        return old(clean_ending(task),op)
    template._sentence_boundary_fixed=True
    profile.policy_template=template
    if planner.policy_template is old:planner.policy_template=template

ADDENDUM='The Task and Current subgoal envelope lines each end with exactly ONE period. Existing sentence-final periods are not doubled. Preserve all words and internal clauses.'
