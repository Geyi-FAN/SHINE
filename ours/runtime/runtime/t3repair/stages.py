"""Idempotent continuation of an active operation, never fabricated completion."""
import copy


def key(stage):
    return tuple(stage.get(k) for k in ('operation', 'kind', 'object'))


def reconcile_monitor(mon, log):
    """Retire a stale active pointer only by an ALREADY accepted exact event."""
    if mon is None or not mon.active:
        return False
    event = next((e for e in reversed(mon.events)
                  if e.get('outcome') == 'completed'
                  and e.get('operation') == mon.active.get('operation')
                  and e.get('object') == mon.active.get('object')
                  and e.get('entered_step') == mon.entered
                  and isinstance(e.get('confirmed_step'), (int, float))
                  and mon.entered <= e['confirmed_step'] <= mon.last), None)
    if event is None:
        return False
    log('stage_pointer_reconciled', operation=mon.active['operation'],
        entered_step=mon.entered, confirmed_step=event['confirmed_step'],
        source='existing_accepted_observation_event', creates_completion=False)
    mon.active = None
    return True


def errors(inp, out):
    active = inp.get('physical_state', {}).get('active_execution_stage')
    if not active or not isinstance(out, dict) or out.get('status') != 'plan_ready':
        return []
    plan = out.get('remaining_plan') or []
    if plan and key(active) != key(plan[0]):
        return ['ACTIVE_STAGE_NOT_RETIRED: Your current selected operation is still '
                'in progress and has no accepted completion or authorized retirement. '
                'Continue that SAME operation, or request the concrete missing '
                'observation/recovery. Do not replace it or invent a completion. '
                'Generate your own plan and subgoal from current evidence.']
    return []


def install_monitor(mon, log):
    if getattr(mon, '_t3_idempotent_select', False):
        return mon
    previous = mon.select

    def select(stage):
        reconcile_monitor(mon, log)
        if mon.active:
            if key(mon.active) != key(stage):
                raise ValueError('Unfinished operation requires accepted completion or explicit retirement')
            log('stage_continued', operation=stage['operation'], entered_step=mon.entered,
                current_frame=mon.last, preserves_completion_window=True, creates_completion=False)
            return
        previous(stage)
        log('stage_selected', operation=stage['operation'], entered_step=mon.entered)

    mon.select = select
    mon._t3_idempotent_select = True
    return mon


def install_planner(module):
    if getattr(module.validate, '_t3_stage_guard', False):
        return
    previous = module.validate

    def validate(inp, out, *args, **kwargs):
        return previous(inp, out, *args, **kwargs) + errors(inp, out)

    validate._t3_stage_guard = True
    module.validate = validate


def input_with_stage(inp, mon):
    inp = copy.deepcopy(inp)
    if mon is not None and mon.active:
        inp['physical_state']['active_execution_stage'] = dict(
            **copy.deepcopy(mon.active), entered_step=mon.entered,
            observation_frame=mon.last, source='selected_stage_execution_log',
            completed=False)
    return inp
