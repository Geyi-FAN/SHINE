"""Continue unattempted cases after a scorer-asset interruption, never replay.

Requires every existing case to have a complete result and valid received PCM.
The same frozen runtime case_run is called, with unchanged fixed ordering.
"""
import json, os, subprocess, sys, time
from pathlib import Path

def main():
    from repair6 import run
    label=sys.argv[1]; root=run.OUT/label
    run.check_freeze()
    cases=json.loads((run.DATA/'selected.private.json').read_text())
    already=[]
    for c in cases:
        d=root/'cases'/c['case_id']
        if not d.exists():continue
        r=json.loads((d/'result.json').read_text());q=json.loads((d/'AUDIO_QUALITY.json').read_text())
        assert q['passed'] and not r.get('errors'), 'Do not replay or silently skip an invalid/failed attempt'
        already.append(c['case_id'])
    (root/'SCORER_ASSET_CONTINUATION.json').write_text(json.dumps(dict(time=time.time(),existing_cases_preserved=already,reason='missing independent physical rule JSON now copied with original hash; no runtime code/threshold/input changed; continue only unattempted IDs'),indent=2))
    for c in cases:
        if c['case_id'] in already:continue
        run.case_run(c,0,label)
        d=root/'cases'/c['case_id'];voice=[p for p in(d/'voice/sessions').glob('*.jsonl')]
        if any('Access denied' in p.read_text()for p in voice):
            (root/'BLOCKED_CLOUD.json').write_text(json.dumps(dict(case_id=c['case_id'],reason='Access denied; stop remaining calls')));return
        if not json.loads((d/'AUDIO_QUALITY.json').read_text())['passed']:
            (root/'INVALID_AUDIO_TIMING.json').write_text(json.dumps(dict(case_id=c['case_id'])));return
        time.sleep(30)
    subprocess.run([run.SIM,str(run.B/'repair6/score.py'),'--final','--label',label],check=True)
    (root/'COMPLETED.json').write_text(json.dumps(dict(time=time.time(),cases=len(cases),results=len(list((root/'cases').glob('*/result.json'))),first_attempts=True,scorer_asset_continuation=True),indent=2))

if __name__=='__main__':main()
