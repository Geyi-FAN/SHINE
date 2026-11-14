"""Wall-clock forecast from observed publications, including failures and pauses."""
from datetime import datetime, timedelta, timezone
from statistics import median

BEIJING = timezone(timedelta(hours=8))

def stamp(t):
    return datetime.fromtimestamp(t, BEIJING).strftime('%Y-%m-%d %H:%M:%S')

def remaining_minutes(n0, n1, rate0, rate1):
    if n1 == 0:
        return n0 / rate0 if rate0 > 0 else (0 if n0 == 0 else None)
    if rate1 <= 0 or (n0 > 0 and rate0 <= 0):
        return None
    first = n1 / rate1
    # Four primary lanes prefer B1; the three extra lanes cannot use speech accounts.
    # Once B1 is done, all seven lanes can finish B0's remaining queue.
    tail = max(0, n0 - rate0 * first)
    return first + (tail / (rate0 * 7 / 3) if tail else 0)

def forecast(registered, observed, now, session_start, phase):
    plan = {m: sum(x['method'] == m for x in registered) for m in ['B0', 'B1']}
    done = {m: sum(x['method'] == m for _, x in observed) for m in plan}
    left = {m: plan[m] - done[m] for m in plan}
    windows, estimates = [], []
    for requested in [15, 30]:
        minutes = min(requested, max(0, (now - session_start) / 60))
        if minutes < 5:
            continue
        recent = [x for t, x in observed if now - minutes * 60 <= t <= now]
        counts = {m: sum(x['method'] == m for x in recent) for m in plan}
        rates = {m: counts[m] / minutes for m in plan}
        estimate = remaining_minutes(left['B0'], left['B1'], rates['B0'], rates['B1'])
        windows.append(dict(minutes=minutes, counts=counts, cases_per_minute=rates,
                            remaining_minutes=estimate))
        if estimate is not None and all(left[m] == 0 or counts[m] >= 3 for m in plan):
            estimates.append(estimate)
    value = dict(observed=len(observed), planned=len(registered), done_by_method=done,
                 remaining_by_method=left, windows=windows, phase=phase,
                 estimate_is_conditional=True, statistical_confidence_interval=False,
                 caveat='Recent throughput-window spread; long outages or unknown bugs can delay completion.')
    if not any(left.values()):
        value.update(state='collection_complete', collection_complete=True)
    elif phase == 'stopped' or phase == 'stopped_by_request':
        value.update(state='blocked_no_committed_finish_time')
    elif estimates:
        low, high = min(estimates) * 60, max(estimates) * 60
        value.update(state='estimated', remaining_seconds=median(estimates) * 60,
                     collection_finish_earliest=stamp(now + low), collection_finish_latest=stamp(now + high),
                     report_finish_earliest=stamp(now + low + 1800),
                     report_finish_latest=stamp(now + high + 3600),
                     offline_judge_allowance_minutes=[30, 60])
    else:
        value['state'] = 'insufficient_recent_observations'
    return value
