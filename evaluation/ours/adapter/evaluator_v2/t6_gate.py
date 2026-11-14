"""Independent pre-QA physical gates; never supplies an answer to a model."""
from t1_contract import instruction_goal

HELD={1:'bowl',2:'wine_bottle',3:'bowl',4:'bowl',6:'cheese',8:'bowl',9:'wine_bottle'}


def entry_errors(proof,active_task):
    errors=[]
    if proof.get('state')!='running':errors.append('not_running:'+str(proof.get('state')))
    if not proof.get('task_id'):errors.append('no_current_task')
    if instruction_goal(proof.get('instruction',''))!=active_task:errors.append('wrong_active_goal')
    held=HELD[active_task]
    if proof.get('physical',{}).get('held_object')!=held:errors.append('wrong_or_missing_held_object')
    if held not in proof.get('held_confirmed_5',[]):errors.append('grasp_not_confirmed_for_5_control_ticks')
    if proof.get('last_error') or proof.get('failure_detail'):errors.append('known_execution_error')
    if proof.get('scene_memory',{}).get('state')=='error':errors.append('memory_unavailable')
    return errors


def condition_errors(family,condition,proof):
    p=proof.get('physical',{});goals=p.get('native_goal_relations',{});gaps=proof.get('drawer_gaps',{})
    errors=[]
    def require(flag,name):
        if not flag:errors.append(name)
    if family=='BOWL_CONTENTS':
        require(bool(goals.get('cheese_bowl'))==(condition=='CHEESE_INSIDE'),'bowl_contents_mismatch')
        if condition=='EMPTY_ON_PLATE':require(goals.get('bowl_plate'),'bowl_not_on_plate')
    elif family=='BOWL_PLATE':
        require(bool(goals.get('bowl_plate'))==(condition=='STACKED'),'bowl_plate_relation_mismatch')
        if condition=='BOWL_ON_STOVE':require(goals.get('bowl_stove'),'bowl_not_on_stove')
    elif family=='CHEESE_BOWL':
        if condition=='CHEESE_INSIDE':require(goals.get('cheese_bowl'),'cheese_not_inside')
        elif condition=='CHEESE_OUTSIDE':require(not goals.get('cheese_bowl'),'cheese_not_outside')
        else:require(p.get('held_object')=='cheese','cheese_not_held')
    elif family=='STOVE':
        require(bool(goals.get('turn_on_stove'))==(condition=='ON_EMPTY'),'stove_power_mismatch')
        require(bool(goals.get('bowl_stove'))==(condition=='OFF_WITH_BOWL'),'stove_contents_mismatch')
    elif family=='ABSENT_TENNIS':
        require(not any('tennis' in name.lower() for name in proof.get('scene_inventory_names',[])),'tennis_present')
    elif family=='WINE_LOCATION':
        if condition=='WINE_HELD':require(p.get('held_object')=='wine_bottle','wine_not_held')
        elif condition=='WINE_ON_RACK':require(goals.get('bottle_rack'),'wine_not_on_rack')
        else:require(goals.get('bottle_cabinet'),'wine_not_on_cabinet')
    elif family=='DRAWER_CONTENTS':
        if condition=='CLOSED_UNOBSERVED':require(gaps.get('top',1)<=.01,'top_not_closed')
        else:
            require(p.get('drawers',{}).get('top',{}).get('open'),'top_not_open')
            require(bool(goals.get('bowl_drawer'))==(condition=='OPEN_WITH_BOWL'),'top_drawer_contents_mismatch')
    elif family=='DRAWER_STATE':
        if condition=='CLOSED':require(gaps.get('middle',1)<=.01,'middle_not_closed')
        elif condition=='OPEN':require(p.get('drawers',{}).get('middle',{}).get('open'),'middle_not_open')
        else:require(.025<=gaps.get('middle',-1)<=.09,'middle_not_in_partial_open_band')
    return errors


def gate_errors(card,proof):
    return entry_errors(proof,card['active_task_id'])+condition_errors(card['question_family'],card['condition_id'],proof)


class TrialGate:
    """Only pre-question failures can be retried; begin is a one-way commit."""
    def __init__(self,max_attempts=3):
        self.max_attempts=max_attempts;self.attempts=0;self.qa_started=False
    def attempt(self):
        if self.qa_started:raise RuntimeError('Cannot retry a started QA trial')
        if self.attempts>=self.max_attempts:raise RuntimeError('Pre-QA attempts exhausted')
        self.attempts+=1;return self.attempts
    def begin_question(self,errors):
        if self.qa_started:raise RuntimeError('Duplicate QA start')
        if errors:raise RuntimeError('Question gate failed: '+';'.join(errors))
        self.qa_started=True
