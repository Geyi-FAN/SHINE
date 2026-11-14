"""Add a strict10s companion to the published, receipt-reviewed T7 45s score."""
import copy
def add_t7_10s(verdict):
    checks=copy.deepcopy(verdict['checks'])
    for check in checks:
        if check['name']=='handoff_first_action_within_45s':
            value=(check.get('evidence')or{}).get('latency_s')
            if value is not None:check['status']='pass'if value<=10.0 else'fail'
            check['name']='handoff_first_action_within_10s'
    values=[x['status']for x in checks]
    status='fail'if'fail'in values else'unknown'if'unknown'in values else'pass'
    verdict['interaction10']=status
    verdict['joint10']='pass'if status==verdict.get('instruction')=='pass'else'fail'
    verdict['strict10_checks']=checks
    verdict['strict10_note']='Same reviewed cancellation receipts and all checks; only handoff deadline changed to10s; published45s score preserved'
    return verdict
