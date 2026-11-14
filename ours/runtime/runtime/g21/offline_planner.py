"""One real local Agent regeneration on the recorded public observation.

No simulator, reference next stage, answer cache or robot actions are used.
"""
import argparse,json,os,sys,time
from pathlib import Path

B=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    os.environ.update(json.loads((B/'freeze/handoff/ENVIRONMENT_REFERENCE.json').read_text())['values'])
    os.environ.update(R34_LOCAL_REQUEST_LOG=str(args.out/'local_requests'),HYBRID_EXECUTOR='smolvla_e3_v4')
    sys.path[:0]=[str(B),str(B/'freeze/f28d/source')]
    import text_transport,agent_transport
    agent_transport.request_json=text_transport.request_json
    import planner
    from g21.observed_goal_guard import install,ADDENDUM,errors
    install(planner)
    source=Path('/mnt/disk_4/geyi/voice_f28d_G2_20261101/G2_natural8_v2/SW4_T02_M2_T08_SWITCH_T02_M2_S04/local_requests/planning')
    folder=next(iter(sorted(source.iterdir())))
    request=json.loads((folder/'request_original.json').read_text())
    inp=json.loads(request['messages'][1]['content'])
    old=json.loads(json.loads((folder/'response.json').read_text())['choices'][0]['message']['content'])
    (args.out/'input.json').write_text(json.dumps(inp,indent=2))
    model=planner.Planner();model.system+='\n'+ADDENDUM
    (args.out/'system_prompt.txt').write_text(model.system)
    start=time.monotonic();result=model.generate(inp);out=result.get('output')
    summary=dict(source=str(folder),model=result.get('model'),seconds=time.monotonic()-start,
                 old_operations=[s['operation']for s in old['remaining_plan']],
                 old_rejected_by_new_guard=bool(errors(inp,old)),
                 new_operations=[s['operation']for s in(out or{}).get('remaining_plan',[])],
                 validated_output=out is not None,attempts=len(result['attempts']),
                 no_oracle_next_stage=True,no_robot_actions=True)
    (args.out/'result.json').write_text(json.dumps(dict(summary=summary,agent=result),indent=2))
    print(json.dumps(summary),flush=True)
    return 0 if out is not None and not errors(inp,out) else 1

if __name__=='__main__':raise SystemExit(main())
