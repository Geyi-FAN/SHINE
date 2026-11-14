"""Contract evaluator: physical predicates -> events -> explicit temporal clauses.

Public results use True/False/None (unknown). No simulator, model, policy prompts,
Oracle transitions or historical strict/SGS flags are modified here.
"""
import math
from .config import load_rules, fingerprint
from .reasons import REASONS
from .contracts import validate_contract
from .adapters import policy_measurements, restore_frames, region_for_frame, containment
from .predicates import distance, drawer_gap, region_contains
from .events import restore_radius, restore_window, high_releases, close_event, preservation_states


def conjunction(values):
    if any(v is False for v in values): return False
    return None if any(v is None for v in values) else True


def ever(values):
    if any(v is True for v in values): return True
    return None if not values or any(v is None for v in values) else False


def result(states):
    value = ever(states)
    return {'success':value,'first_step':next((i+1 for i,v in enumerate(states) if v is True),None),
            'status':'unknown' if value is None else 'pass' if value else 'fail'}


def evaluate_episode(trace, case, contract, rules=None):
    rules = rules or load_rules(); validate_contract(contract)
    if case['case_id'] != contract['case_id']: raise ValueError('Case/contract mismatch')
    ms = policy_measurements(trace); n = len(ms); native = [m['goal_frame']['goal'] for m in ms]
    if any(type(v) is not bool for v in native): raise ValueError('Native goal must be boolean')
    diagnostics = {'hold_frames_excluded':len(trace['measurements'])-n,
                   'initial_state_evidence_available':bool(trace.get('metric_initial')),
                   'native_target_lost_steps':[i+1 for i in range(1,n) if native[i-1] and not native[i]],
                   'limits':['Support contact is a logged proxy, not exact net support force.',
                             'Release between snapshot and first measurement is not observable without initial evidence.']}
    adjusted = list(native); site = {5:'main_table_stove_front_region',9:'wine_rack_1_top_region'}.get(case.get('target_task')) if case.get('kind')!='normal' else None
    if site:
        for i,m in enumerate(ms):
            if native[i]: continue  # expanded set includes every original success
            evidence = region_for_frame(m,site)
            if evidence is None: adjusted[i] = None
            else:
                # Original task5/9 each has one On goal. Other predicates cannot be overridden.
                adjusted[i] = region_contains(evidence,rules['target_regions'][site]['margin_m'])
    states = {}; events = {}; reasons = {}; target_id = None
    for c in contract['clauses']:
        cid,kind = c['id'],c['kind']
        if kind=='completion_order': continue
        try:
            if kind=='native_target':
                target_id = cid; states[cid] = native; events[cid] = result(native)['first_step']
            elif kind=='restore_episode_start':
                frames = restore_frames(ms,c['object'],rules['evidence']['source_identity_tolerance_m']); rad = restore_radius(case,c,rules)
                w = max(rules['restore'][k] for k in ['position_steps','support_steps','release_steps','stable_steps','withdraw_steps'])
                flags = [restore_window(frames[max(0,i-w+1):i+1],c,rad,rules) for i in range(n)]
                first = next((i+1 for i,f in enumerate(flags) if f['complete']),None)
                drops = [e for e in high_releases(frames,c['reference_position'],rules) if first is None or e['onset']<=first]
                if drops: first = None; reasons[cid] = '归位前发生高处无支撑释放，落地稳定不清除该失败'
                events[cid] = first; states[cid] = [first is not None and i+1>=first for i in range(n)]
                diagnostics[cid] = {'radius_m':rad,'high_release_events':drops,
                                    'first_position_step':next((i+1 for i,f in enumerate(flags) if f['position']),None)}
            elif kind=='close_event':
                qs = [m['source']['articulation'][c['joint']] for m in ms]
                first = close_event(qs,rules)
                initial_q = trace.get('metric_initial',{}).get('articulation',{}).get(c['joint'])
                if initial_q is not None and drawer_gap(initial_q)<=rules['close']['gap_m']: first=0
                events[cid] = first; states[cid] = [first is not None and i+1>=first for i in range(n)]
                if initial_q is None and qs and drawer_gap(qs[0])<=rules['close']['gap_m']:
                    states[cid] = [True if first is not None and i+1>=first else None for i in range(n)]
                if c.get('continuous_preservation'):
                    states[cid] = [None]*n; reasons[cid]='显式持续关闭条款需要单独契约，不能仅使用关闭事件'
                if first is not None:
                    spec=rules['reopen_diagnostic']; values=[drawer_gap(q) for q in qs[first:]]
                    _,onset=preservation_states(values,spec['gap_m'],spec['severe_gap_m'],spec['confirmation_steps'])
                    diagnostics[cid]={'reopen_onset':first+onset if onset is not None else None}
            elif kind in {'preserve_position','preserve_articulation_state'}:
                values=[]
                for m in ms:
                    try:
                        value = distance(m['source']['all_object_poses'][c['object']]['position'],c['reference_position']) if kind=='preserve_position' else abs(m['source']['articulation'][c['joint']]-c['reference_q'])
                        if not math.isfinite(value): raise ValueError('Non-finite preservation measurement')
                        values.append(value)
                    except KeyError: values.append(None)
                spec=rules['preserve_position' if kind=='preserve_position' else 'preserve_joint']
                states[cid],onset=preservation_states(values,spec['tolerance_m'],spec['severe_m'],spec['confirmation_steps'])
                diagnostics[cid]={'violation_onset':onset}
            elif kind=='preserve_containment':
                history=True; states[cid]=[]
                for m in ms:
                    value=containment(m,cid)
                    if value is not None and type(value) is not bool: raise ValueError('Containment must be boolean')
                    history=conjunction([history,value]); states[cid].append(history)
            else:
                states[cid]=[None]*n; reasons[cid]='不支持的契约条款：'+kind
        except KeyError as error:
            states[cid]=[None]*n; reasons[cid]='轨迹缺少证据：'+str(error)
            if kind in {'restore_episode_start','close_event'}: events[cid]=None
    def instruction(target_flags):
        local=dict(states);local[target_id]=target_flags
        first_events=dict(events);first_events[target_id]=next((i+1 for i,v in enumerate(target_flags) if v is True),None)
        for c in contract['clauses']:
            if c['kind']!='completion_order':continue
            a,b=first_events.get(c['before']),first_events.get(c['after'])
            if a is None or b is None:
                order=None if any(v is None for v in local[c['before']]+local[c['after']]) else False
            else:
                order=a<b
                # Missing switch-state evidence may make an already-closed prerequisite
                # appear late solely due to its confirmation window. Do not invent failure.
                before=next(x for x in contract['clauses'] if x['id']==c['before'])
                if not order and before['kind']=='close_event' and not trace.get('metric_initial') and n:
                    try:
                        if drawer_gap(ms[0]['source']['articulation'][before['joint']])<=rules['close']['gap_m']:order=None
                    except KeyError:order=None
                # Missing expanded geometry before the first true target means its first onset is unknown.
                if c['after']==target_id and any(v is None for v in target_flags[:b]):order=None
            local[c['id']]=[order]*n
        out=result([conjunction([v[i] for v in local.values()]) for i in range(n)])
        evaluation_step=out['first_step'] or next((i+1 for i in range(n-1,-1,-1) if target_flags[i] is True),n or None)
        out['evaluation_step']=evaluation_step
        out['clauses_at_evaluation_step']={}
        if evaluation_step is not None:
            for c in contract['clauses']:
                value=local[c['id']][evaluation_step-1]
                entry={'value':value}
                if value is False:
                    entry['reason_code'],entry['reason_zh']=REASONS.get(c['kind'],('UNKNOWN_CLAUSE','未知条款'))
                elif value is None:
                    entry.update(reason_code='INSUFFICIENT_OR_PENDING_EVIDENCE',reason_zh='证据缺失、初态歧义或连续窗口尚待确认')
                out['clauses_at_evaluation_step'][c['id']]=entry
        return out
    components={}
    for c in contract['clauses']:
        if c['id'] not in states: continue
        entry=result(states[c['id']]);entry['last_state']=states[c['id']][-1] if n else None
        if entry['last_state'] is False:
            entry['failure_code'],entry['failure_reason_zh']=REASONS.get(c['kind'],('UNKNOWN_CLAUSE','未知条款'))
        if entry['last_state'] is None: entry['evidence_status']='insufficient_or_pending'
        components[c['id']]=entry
    return {'schema_version':1,'case_id':case['case_id'],'rules_version':rules['version'],
            'rules_sha256':fingerprint(rules),'contract_sha256':fingerprint(contract),
            'policy_steps':n,'target_native':result(native),'target_adjusted':result(adjusted),
            'instruction_native':instruction(native),'instruction_adjusted':instruction(adjusted),
            'components':components,'completion_events':events,
            'evidence_issues':reasons,'diagnostics':diagnostics}
