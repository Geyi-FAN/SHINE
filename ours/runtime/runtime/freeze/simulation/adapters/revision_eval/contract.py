from .tasks import TASKS

def contract(c, initial, at):
    """Compile explicit requirements; no broad 'necessary operation' exemption."""
    source,target,branch=c['source'],c['target'],c['branch']
    name=TASKS[source][1];same=name is not None and name==TASKS[target][1]
    terminal=c['phase'] in ('M4','C6','D2','P2','K2')
    held_now=name is not None and at['target_contact'] and not at['support_contact']
    restore=branch in ('RESTORE','FULL_RESTORE') and name is not None
    close=None
    preserve={}
    if source in (0,7):
        key='middle' if source==0 else 'stove'
        if branch=='RESTORE':close=key
        else:preserve[key]=at['articulation'][key]
    if source==3:
        if branch in ('CLOSE','FULL_RESTORE','CLOSE_INPLACE'):close='top'
        else:preserve['top']=at['articulation']['top']
        if branch=='CLOSE' and (held_now or c['phase']=='C6'):restore=True
    if branch=='BASE' and held_now and not same:restore=True
    if source==8 and terminal and target==5 and branch=='BASE':restore=True
    # A held object leaves the only arm unavailable to open a closed drawer.
    if target==3 and held_now and at['articulation']['top']>-.14:restore=True
    # The instruction remains binding when a placement has just regained
    # support. BASE includes explicit "put it back, then ..." revisions;
    # routing only by airborne contact silently skipped their required undo.
    # Conditional drawer set-down clauses are intentionally not unconditional
    # restore requests: their actual holding/opening condition is handled above.
    if c.get('contract_version')==3 and name is not None:
        explicit_restore=bool(c.get('intent_axes',{}).get('old_result_policy',{}).get('restore_object'))
        explicit_restore=explicit_restore or any(
            event.get('predicate')=='source_object_restored_supported_released'
            for event in c.get('acceptance_v2',{}).get('events',[]))
        restore=restore or explicit_restore
    preserve_object=bool(name and not same and not restore and branch not in ('CONTINUE','PAUSE'))
    payload=None
    if source==6 and terminal and target in (1,3,4,8) and branch=='BASE':
        preserve_object=False;payload=['on','cream_cheese_1','akita_black_bowl_1']
    if branch=='KEEP_PAYLOAD':preserve_object=False;payload=['on','akita_black_bowl_1','plate_1']
    return dict(restore=restore,close=close,preserve_joints=preserve,
        preserve_object=preserve_object,source_object=name,payload=payload,
        source_reference=initial['all_object_poses'].get(name),
        preserve_reference=at['all_object_poses'].get(name),
        closed_with_bowl=branch=='CLOSE_INPLACE')
