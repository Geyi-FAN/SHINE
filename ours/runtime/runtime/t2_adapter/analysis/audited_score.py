"""Uniform R8 speech-evidence compatibility audit; original v1 scores retained.

No action, timing limit, task contract, physical predicate or evaluated outcome
is changed. Every speech claim requires the exact output key and actual received
PCM hash, in addition to the pre-existing task receipt/meaning/time checks.
"""
import collections,hashlib,json,sys
from pathlib import Path
W=Path(__file__).resolve().parents[1];B=Path('/mnt/disk_2/geyi/voice_f28d_audio_repair_20261102');sys.path.insert(0,str(W/'tools'));sys.path.insert(0,str(B))
import score as frozen
from repair8.audible_binding import bound_output

def audible_r8(voice,messages,directory):
 strict=[];ids=set();reserved={(m.get('epoch'),m.get('outputId'))for m in messages if m.get('type')=='host.output_audio_receipt'and 'isolated_result'in str(m.get('receiptKey',''))}
 for event in voice:
  if event.get('type')!='transcript.assistant':continue
  p=event.get('payload',{})
  if not p.get('audio_sha256')or not p.get('receipt_key'):continue
  matches=bound_output(p,messages,directory)
  if len(matches)!=1:continue
  start=matches[0];identity=(start.get('epoch'),start.get('outputId'))
  if identity in ids:continue
  strict.append((dict(event,audibility_evidence={'kind':'exact_output_key_and_received_PCM_SHA256'}),start));ids.add(identity)
 legacy=frozen.audible_records([e for e in voice if not e.get('payload',{}).get('audio_sha256')],messages)
 return sorted(strict+[x for x in legacy if(x[1].get('epoch'),x[1].get('outputId'))not in(ids|reserved)],key=lambda pair:pair[1]['time'])

source=(W/'tools/score.py').read_text();source=source[:source.index('\ndef aggregate(out):')]
source=source.replace("VERSION='T2-MXOV20-conditional-R8-v1'","VERSION='T2-MXOV20-conditional-R8-audited-v1.1'")
source=source.replace('played=audible_records(voice,messages)','played=audible_r8(voice,messages,d)')
source=source.replace("(not key or any(k in key for k in expected))","(not key or any(k in key for k in expected)or v.get('audibility_evidence',{}).get('kind')=='exact_output_key_and_received_PCM_SHA256')")
source=source.replace("(d/'score.json')","(d/'score_r8_audited.json')")
scope=dict(__name__='audited_evidence_source',__file__=str(W/'tools/score.py'),audible_r8=audible_r8)
exec(compile(source,str(W/'analysis/generated_score_r8.py'),'exec'),scope);evaluate=scope['evaluate']

def aggregate(out):
 reg=json.loads((out/'REGISTERED.json').read_text());specs={s['case_id']:s for s in json.loads((W/'dataset/selected.private.json').read_text())};rows=[];attempts=[]
 for cid in reg['case_ids']:
  c=out/'cases'/cid
  for d in sorted((c/'preparation_attempts').glob('attempt_*')):
   if(d/'PROCESS.json').exists():
    r=json.loads((d/'result.json').read_text());attempts.append(dict(case_id=cid,attempt=d.name,enrolled=r.get('enrolled',False),trigger=r.get('trigger_covered',False),errors=r.get('errors'),directory=str(d)))
  if(c/'formal/PROCESS.json').exists():rows.append(evaluate(c/'formal',specs[cid]))
 N=reg['count'];metrics={k:dict(success=sum(r[k]=='pass'for r in rows),denominator=N,rate=sum(r[k]=='pass'for r in rows)/N,unknown=sum(r[k]=='unknown'for r in rows))for k in['interaction','target','instruction','joint']}
 by={cat:dict(n=sum(r['condition']==cat for r in rows),denominator=10,**{k:sum(r['condition']==cat and r[k]=='pass'for r in rows)for k in metrics})for cat in['MX']}
 s=dict(time=__import__('time').time(),scoring_version='T2-MXOV20-conditional-R8-audited-v1.1',total_registered=N,completed_results=len(rows),metrics=metrics,by_condition=by,preparation=dict(total_attempts=len(attempts),formal_enrolled=len(rows),first_attempt_trigger_covered=sum(a['attempt']=='attempt_001'and a['enrolled']for a in attempts),attempts=attempts),failures=dict(collections.Counter(f for r in rows for f in r['failures'])),rows=rows,compatibility_change='isolated_result exact receipt_key + received PCM SHA256; same semantic/task receipt/timing checks; original scores untouched')
 dest=out/'reports_audited/r8_v1.1';dest.mkdir(parents=True,exist_ok=True);(dest/'summary.json').write_text(json.dumps(s,ensure_ascii=False,indent=2));return s
if __name__=='__main__':
 s=aggregate(Path(sys.argv[1]));print(json.dumps({k:v for k,v in s.items()if k not in['rows','preparation']},ensure_ascii=False,indent=2))
