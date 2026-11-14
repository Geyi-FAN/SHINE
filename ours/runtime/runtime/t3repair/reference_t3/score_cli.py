"""Reuse frozen T3 physical/semantic rules; only declare CLI audio boundaries."""
import json
from pathlib import Path
from score_t3 import evaluate as legacy
VERSION='t3-cli-F28d-candidate-v1'
def evaluate(directory,spec,rules):
    directory=Path(directory);p=directory/'result.json';r=json.loads(p.read_text()) if p.exists() else {}
    u=next((x for x in r.get('turns',[]) if x['turn_id']=='U1'),None)
    if not u or any(k not in u for k in ('audio_started_wall','audio_ended_wall')):
        return dict(case_id=spec['case_id'],interaction='fail',target='fail',instruction='fail',failures=['source_or_complete_switch_audio_not_reached'],errors=r.get('errors',[]),scoring_version=VERSION)
    out=legacy(directory,spec,rules);end=u['audio_ended_wall'];events=r.get('messages',[])
    first=next((x for x in events if x['type']=='client.output_first_pcm' and end<=x['time']<=end+10),None)
    done={(x['epoch'],x['outputId']) for x in events if x['type']=='client.output_clocked_complete'}
    for x in out['checks']:
        if x['name']=='actual_reply_audio_within_10s':x.update(name='reply_pcm_received_within_10s',status='pass' if first else 'fail',sink='clocked_pcm_receiver_not_physical_speaker')
    out['checks'].append(dict(name='reply_pcm_fully_consumed',status='pass' if first and (first['epoch'],first['outputId']) in done else 'fail'))
    out['checks'].append(dict(name='no_typed_benchmark_task_injection',status='pass' if r.get('typed_benchmark_task_injection') is False else 'fail'))
    out['interaction']='pass' if all(x['status']=='pass' for x in out['checks']) else 'fail'
    out['failures']=[x['name'] for x in out['checks']+out.get('physical_checks',[]) if x['status']!='pass'];out['scoring_version']=VERSION;out['track']='unified_F28d_candidate_development_not_admitted'
    return out
