"""Keep complete v6; install presentation fix only AFTER it finishes; new block."""
import hashlib,json,shutil,subprocess,time
from pathlib import Path
B=Path(__file__).resolve().parents[1];PY='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python';D=B/'run_data';O=B/'reports'
def emit(s):print(s,flush=True)
while 'FORMAL10_ALL_FINISHED'not in(D/'driver_v6_restored.console.log').read_text():time.sleep(10)
manifest=json.loads((D/'FREEZE.json').read_text());archive=O/'source_archive_formal10_v6';archive.mkdir(exist_ok=False);mapping=[]
for p,h in manifest['files'].items():
 src=Path(p);assert hashlib.sha256(src.read_bytes()).hexdigest()==h,('v6_runtime_drift',p)
 try:rel=src.relative_to(B)
 except ValueError:rel=Path('external')/h/src.name
 dst=archive/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst);mapping.append(dict(original=p,archived=str(dst),sha256=h))
(archive/'SOURCE_ARCHIVE.json').write_text(json.dumps(dict(time=time.time(),scope='exact source/data during complete first v6 formal10; before any formatter modification',files=mapping),indent=2));shutil.copy2(D/'FREEZE.json',D/'FREEZE.formal10_v6.json')
for name in('summary.json','RESULTS.md','cases.csv'):
 if(O/name).exists():shutil.copy2(O/name,O/(Path(name).stem+'.formal10_v6'+Path(name).suffix))
emit('v6 fully preserved; installing sentence-boundary-only fix')
p=B/'t3repair/integration.py';s=p.read_text();old='        import planner, task_language';assert s.count(old)==1
s=s.replace(old,chr(10).join([old,'        import execution_profile','        from entryfix.envelope import install as install_envelope','        install_envelope(execution_profile,planner)']))
old="            b.planner.system+="+repr(chr(10))+"+PLANNER_ADDENDUM";assert s.count(old)==1
s=s.replace(old,chr(10).join([old,"            from entryfix.envelope import ADDENDUM as ENVELOPE_ADDENDUM","            b.planner.system+="+repr(chr(10))+"+ENVELOPE_ADDENDUM"]))
p.write_text(s)
f=B/'entryfix/freeze.py';fs=f.read_text();fs=fs.replace("version='T3-entryfix-v1.5'","version='T3-entryfix-v1.7'").replace('native bowl containment plus measured current','native task6 On(cheese,bowl), not In; measured current').replace('R7-T3.2 entry guards; authorized English verbatim; release goal validation guidance','R7-T3.2 entry guards; scoped task lifecycle; authorized English verbatim; release goal guidance; canonical sentence ending; actual new-task VLA timing')
f.write_text(fs)
subprocess.run([PY,'-m','unittest','entryfix.test_entry','entryfix.test_support','entryfix.test_lifecycle','entryfix.test_envelope','selected_eval.test_adapters'],cwd=B,check=True)
subprocess.run([PY,str(B/'entryfix/freeze.py')],cwd=B,check=True)
subprocess.run([PY,'-u',str(B/'selected_eval/run.py'),'--ids','T3R2_S06_V0_I00','--label','probe07_v7'],cwd=B,check=True)
probe=B/'runs/probe07_v7/T3R2_S06_V0_I00/verdict.json'
if not probe.exists():raise SystemExit('probe07 incomplete; no new formal block')
v=json.loads(probe.read_text());(O/'PROBE07_V7.json').write_text(json.dumps(v,ensure_ascii=False,indent=2))
if v['interaction']!='pass':raise SystemExit('probe07 interaction failed; preserve and inspect')
subprocess.run([PY,'-u',str(B/'selected_eval/run.py'),'--label','formal10_v7'],cwd=B,check=True)
cases=json.loads((D/'cases.private.json').read_text());missing=[c['case_id']for c in cases if not(B/'runs/formal10_v7'/c['case_id']/'verdict.json').exists()]
if missing:raise SystemExit('formal10_v7 incomplete: '+str(missing))
emit('FORMAL10_V7_ALL_FINISHED')
