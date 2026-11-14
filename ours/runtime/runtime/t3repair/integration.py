"""Guarded integration around the R7 physical service and R8 speech package."""
import copy
import functools
import hashlib
import json
import time
from contextvars import ContextVar

_wording_scope = ContextVar('t3_wording_scope', default=None)


def install(cls):
    from t3repair import terminal, stages, memory, scoring
    terminal.install()
    previous_hooks, previous_start, previous_apply = cls.install_hooks, cls.start, cls.apply

    def hooks(b):
        previous_hooks(b)
        import planner, task_language
        import execution_profile
        from entryfix.envelope import install as install_envelope
        install_envelope(execution_profile,planner)
        memory.install()
        memory.install_evidence(b.cache_reader)
        scoring.install_runtime_radius(b)
        stages.install_planner(planner)
        original_factory = b.runner.ObservedCompletion

        def factory(*args, **kwargs):
            existing = b.saved_mon
            subject = tuple(b.token()[:3])
            same_task = existing is not None and getattr(existing, '_t3_stage_subject', None) == subject
            active = copy.deepcopy(existing.active) if same_task else None
            mon = original_factory(*args, **kwargs)
            # Physical observation history can survive a semantic replacement;
            # execution stages cannot. Pause/resume keeps the first3 fields,
            # whereas a new task or semantic revision changes this subject.
            if existing is mon and same_task and active is not None:
                mon.active = active
            elif existing is mon and not same_task:
                mon.active = None
                b.log('previous_task_stage_retired', subject=list(subject),
                      reason='authorized_semantic_task_replacement', creates_completion=False)
            mon._t3_stage_subject = subject
            return stages.install_monitor(mon, b.log)

        b.runner.ObservedCompletion = factory
        original_normalize = task_language.normalize
        b.wording_cache = {}

        def normalize(agent, raw, observed_context=None):
            scope = _wording_scope.get()
            if scope:
                from t3repair.wording import exact_authorized_task, reused_task
                from native_execution import CATALOG
                from entryfix.literal import literal_task
                exact=exact_authorized_task(b.state,raw,CATALOG)
                if exact or literal_task(b.state,raw,b.contract):
                    source='authorized_exact_training_sentence'if exact else'authorized_verified_English_task_verbatim'
                    b.log('wording_reused', identity=list(scope), source=source,
                          semantic_task_unchanged=True, text_rewritten=False)
                    value=reused_task(raw);value['source']=source
                    if not exact:value['output']['rationale']='Preserve the entire authorized verified English Task verbatim; memory IDs remain in the live task record'
                    return value
            cache_key = (scope, raw, json.dumps(observed_context, sort_keys=True), agent.model,
                         hashlib.sha256(task_language.SYSTEM.encode()).hexdigest())
            if scope and cache_key in b.wording_cache:
                value = copy.deepcopy(b.wording_cache[cache_key])
                b.log('wording_reused', identity=list(scope), source='same_task_validated_wording',
                      semantic_task_unchanged=True, saved_previous_seconds=value['seconds'])
                value.update(seconds=0., reused=True)
                return value
            value = original_normalize(agent, raw, observed_context)
            if scope:
                b.wording_cache[cache_key] = copy.deepcopy(value)
                while len(b.wording_cache) > 8:
                    b.wording_cache.pop(next(iter(b.wording_cache)))
            return value

        task_language.normalize = normalize

    def start(b, client, resume=False):
        # Create the same planner that R7 would create, then add execution-log
        # context before generation so its existing bounded validation retries
        # can regenerate errors instead of crashing the physical kernel.
        import planner
        if not hasattr(b, 'planner'):
            b.planner = planner.Planner()
            if __import__('os').environ.get('G21_PROGRESS_GUARD', '1') == '1':
                from g21.observed_goal_guard import ADDENDUM
                b.planner.system += '\n' + ADDENDUM
        if not getattr(b.planner, '_t3_stage_context', False):
            from entryfix.literal import PLANNER_ADDENDUM
            b.planner.system+='\n'+PLANNER_ADDENDUM
            from entryfix.envelope import ADDENDUM as ENVELOPE_ADDENDUM
            b.planner.system+='\n'+ENVELOPE_ADDENDUM
            generate = b.planner.generate

            def with_context(inp):
                scope = tuple(b.token()[:3])
                token = _wording_scope.set(scope)
                started = time.monotonic()
                b.log('planning_cycle_started', identity=list(scope))
                try:
                    stages.reconcile_monitor(b.saved_mon, b.log)
                    return generate(stages.input_with_stage(inp, b.saved_mon))
                finally:
                    _wording_scope.reset(token)
                    b.log('planning_cycle_finished', identity=list(scope), seconds=time.monotonic()-started)

            b.planner.generate = with_context
            b.planner._t3_stage_context = True
        return previous_start(b, client, resume)

    def apply(b, action, phase):
        context = {} if b.ctx is None else b.ctx.f_locals
        engine_phase = context.get('phase') if phase == 'authorized_kernel_control' else None
        origin = ('vla_native' if phase in ('source_policy', 'authorized_native_control') else
                  'vla' if engine_phase == 'policy' else
                  'kernel_' + str(engine_phase) if engine_phase else phase)
        result = previous_apply(b, action, phase)
        if phase != 'async_wait_hold':
            b.log('action_provenance', identity=list(b.token()), origin=origin,
                  engine_phase=engine_phase, actual_vla_action=origin in ('vla','vla_native'),actual_world_step=getattr(b,'physics_steps',None))
        return result

    cls.install_hooks, cls.start, cls.apply = hooks, start, apply
