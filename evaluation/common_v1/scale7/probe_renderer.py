import argparse,json,os,sys,time
from pathlib import Path
Q=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--egl',type=int,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
os.environ.update(HOME=str(Q/'work/container_home'),NUMBA_CACHE_DIR=str(Q/'work/numba'),CUDA_VISIBLE_DEVICES='0,1,2',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
sys.path.insert(0,str(Q/'actors/B0/code'));from sim_support import configure,build_env
configure(a.out,a.egl);fixture=json.loads((Q/'actors/B0/data/T1/initial_states.json').read_text())[0];env,obs=build_env(Path('/'),fixture,a.out)
(a.out/'READY.json').write_text(json.dumps(dict(egl=a.egl,pid=os.getpid(),initial_scene_verified=True)))
end=time.monotonic()+90
while time.monotonic()<end and not(a.out/'STOP').exists():time.sleep(.2)
env.close()
