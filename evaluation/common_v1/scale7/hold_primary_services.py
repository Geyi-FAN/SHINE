import sys,time,json,os
from pathlib import Path
Q=Path(__file__).resolve().parents[1];sys.path.insert(0,str(Q/'tools'));from services import start,stop
os.environ['COMMON_CANDIDATE']='r7scale7'
ps=[];fs=[]
try:
 ps,fs=start();(Q/'scale/PRIMARY_READY.json').write_text(json.dumps(dict(ready=True,at=time.time())))
 while not(Q/'scale/STOP_SERVICES').exists():
  assert all(p.poll()is None for p in ps),'A primary service exited';time.sleep(2)
finally:stop(ps,fs)
