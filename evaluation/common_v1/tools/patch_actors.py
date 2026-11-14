"""Apply transport/private-recorder parity; retain each baseline's decision code."""
from pathlib import Path
import hashlib,json,os,shutil
Q=Path(__file__).resolve().parents[1];B=Q.parents[1];N=B/'deployments/ours_full930_readiness_20261114'
for method in ['B0','B1']:
 A=Q/'actors'/method; raw=A/'code/raw_gateway.py';s=raw.read_text();before=hashlib.sha256(s.encode()).hexdigest()
 if "conditioning_mode=('symbolic'"not in s:
  s=s.replace('metadata=dict(prompt=text,',"metadata=dict(conditioning_mode=('symbolic'if 'Coordinates:'in text else'complete_task'),prompt=text,");raw.write_text(s)
 if 'from entryfix.support import augmented'in s:
  print(method,'already patched');continue
 marker="  self.record('initial_observation',False)";assert s.count(marker)==1
 s=s.replace(marker,"  from entryfix.support import augmented\n  mon=self.cache_reader.mon['cheese'];raw_measure=mon.measure;mon.measure=lambda:augmented(mon,raw_measure())\n"+marker)
 marker="  self.publish();write(self.root/'READY.json',self.public)";assert s.count(marker)==1
 s=s.replace(marker,"  self.common_prefix=None\n  if self.family=='T3'and self.spec.get('t3_prepare_mode')=='replay':\n   from prepare_source import SourcePreparer\n   self.common_prefix=SourcePreparer(self)\n"+marker)
 s=s.replace("  if not t['policy_action']or", "  if self.spec.get('t3_prepare_mode')=='replay':return False\n  if not t['policy_action']or")
 # Service the common prefix after commands/Agent generation but before any
 # method actor request. While waiting for real U0, physics remains initial.
 hook="    if self.inflight is not None and self.inflight.done()and not self.buffer:"
 target=A/'code/agent_gateway.py'if method=='B1'else raw
 code=target.read_text()if method=='B1'else s
 assert code.count(hook)==1
 code=code.replace(hook,"    if self.common_prefix is not None and not self.common_prefix.done:\n     self.common_prefix.service();self.publish();time.sleep(.005);continue\n"+hook)
 hook2="    control=active and bool(self.buffer)"
 assert code.count(hook2)==1
 code=code.replace(hook2,"    if self.common_prefix is not None and self.common_prefix.done and self.fixture_hold and self.task_count==1:\n     self.publish();time.sleep(.005);continue\n"+hook2)
 if method=='B1':
  target.write_text(code);raw.write_text(s)
  # Reference source trajectory is private setup, not method subgoal progress.
  text=target.read_text();text=text.replace("  if self.stage and self.stage['status']=='running'and hasattr(self,'stage_monitor'):","  if phase!='T3_private_fixed_preparation_not_method_actions'and self.stage and self.stage['status']=='running'and hasattr(self,'stage_monitor'):")
  target.write_text(text)
 else:raw.write_text(code)
 # Explicit per-lane credentials and request lock; original model and prompt stay.
 if method=='B1':
  p=A/'code/speech_backend.py';s=p.read_text().replace('import base64,','import os,base64,').replace("(R/'private/tts.key').read_text().strip()","Path(os.environ['COMMON_TTS_KEY_FILE']).read_text().strip()");p.write_text(s)
  p=A/'code/agent_backend.py';s=p.read_text().replace('import base64,','import os,base64,').replace("(R/'private/cloud01_generation.lock').open('a')","Path(os.environ['COMMON_AGENT_LOCK_FILE']).open('a')");p.write_text(s)
 (A/'cache/tmp').mkdir(parents=True,exist_ok=True)
print('two actors patched; raw ASR/Agent prompts and model configs preserved')
