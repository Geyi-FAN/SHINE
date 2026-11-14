from pathlib import Path
import json
R=Path('/mnt/disk_4/geyi/audio_switch_benchmark/deployments/common_scoring_oracle_baselines_20261114/actors/B1');D=Path('/mnt/disk_4/geyi/audio_switch_benchmark')
NODE='/mnt/disk_2/geyi/voice_pi05_harness/runtime/node-v22.23.3-linux-x64/bin/node'
def read(p):return json.loads(Path(p).read_text())
def write(p,v):Path(p).write_text(json.dumps(v,indent=2))
def state_fixture(branch,state_id):
 if branch=='T1':rows=read(R/'data/T1/initial_states.json')
 elif branch=='T4':rows=read(R/'data/T4/data/initial_states.json')
 elif branch=='T5':rows=read(R/'data/T5/initial_states.json')
 elif branch=='T7':rows=read(R/'data/T7/initial_states.json')
 elif branch=='T8':rows=read(R/'data/T8/data/initial_states.json')
 else:raise ValueError(branch)
 return next(s for s in rows if s['state_id']==state_id)
def config_for(item,ports,case):
 b=item['branch'];cid=item['public_case_id'];c=item['case'];gp,wp,vp=ports
 proto=None;audio=None;client=None;env={};spec=dict(case_id=cid,source_task=0,target_task=999,context_turns=[],serve_live=False,task_control_budget=1200,reset_count=1,initial_version=0,service_lifetime_s=3600,evaluation_family=b,policy_seed=item.get('policy_seed',7))
 if b=='T1':
  spec['fixture']=state_fixture(b,item['state_id']);proto=R/'data/T1/protocol.json';env=dict(AUDIO_BENCH_DATA=str(R/'data/T1'),T1_BROWSER_TOKEN_FILE=str(R/'private/browser.token'),T1_COMMON_AUDIO_CLIENT=str(R/'adapter/shared/t8_adapter/audio-client.mjs'));client=[NODE,str(R/'adapter/T1/client.mjs')]
 elif b=='T2':
  c=next(x for x in read(R/'data/T2_ALL.json') if x['case_id']==cid);c.update(robot_port=gp,gateway_port=gp,web_port=wp);spec['fixture']=c['fixture'];spec['source_task']=c['source_task'];proto=D/'T2/current/dataset/PROTOCOL.json';env={'T2_BROWSER_TOKEN_FILE':str(R/'private/browser.token'),'T2_ROBOT_TOKEN_FILE':str(R/'private/robot.token')};p=case/'client_spec.private.json';write(p,c);client=[NODE,str(R/'adapter/T2/client/t2_client.mjs'),str(case),f'http://127.0.0.1:{wp}',str(p)]
 elif b=='T3':
  c=read(R/'data/T3/specs'/(cid+'.json'));spec.update(c);spec.update(case_id=cid,evaluation_family=b,gateway_port=gp,web_port=wp);proto=None;p=case/'client_spec.private.json';write(p,dict(c,gateway_port=gp,web_port=wp));client=[NODE,str(R/'adapter/T3/client.mjs'),str(p),str(case)]
 elif b=='T4':
  data=R/'data/T4/data';c=next(x for x in read(data/'selected.private.json')if x['case_id']==cid);contract=c['private_contract'];spec.update(fixture=state_fixture(b,item['state_id']),source_task=contract['source_task_id'],phase=contract['source_stage'],context_turns=[t['text']for t in c['context_turns']]);proto=data/'PROTOCOL.json';p=case/'client_spec.private.json';write(p,dict(case=c,budgets=read(proto)['budgets'],audio=read(data/'audio_manifest.json'),web_port=wp,robot_port=gp,delivery_stage='full'));env={'T4_ROBOT_TOKEN_FILE':str(R/'private/robot.token'),'T4_BROWSER_TOKEN_FILE':str(R/'private/browser.token')};client=[NODE,str(R/'adapter/T4/client.mjs'),str(p),str(case)]
 elif b=='T5':
  spec['fixture']=state_fixture(b,item['state_id']);proto=R/'data/T5/PROTOCOL.json';audio=R/'data/T5/audio_manifest.json';env={'AUDIO_BENCH_DATA':str(R/'data/T5'),'AUDIO_BENCH_AUDIO':str(audio),'T5_BROWSER_TOKEN_FILE':str(R/'private/browser.token'),'T5_ALLOW_UNREVIEWED_AUDIO':'1'};client=[NODE,str(R/'adapter/T5/client/client.mjs')]
 elif b=='T6':
  cards=read(D/'T6/current/dataset/scene_cards.private.json');card=next(x for x in cards if x['scene_card_id']==c['scene_card_id']);spec.update(fixture=read(R/'data/T6/fixture.private.json'),source_task=c['preparation'][0]if c['preparation']and isinstance(c['preparation'][0],int)else c['active_task_id'],target_task=c['active_task_id'],t6_card=card,context_turns=['reference preparation']if c['preparation']else[]);client=None
 elif b=='T7':
  spec['fixture']=state_fixture(b,item['state_id']);mapping=next(x for x in read(D/'T7/current/dataset/CASE_ID_MAP.json')if x['case_id']==cid);folder=R/'data/T7'/mapping['condition'];c=next(x for x in read(folder/'cases.private.json')if x['case_id']==mapping['runtime_case_id']);p=case/'client_spec.private.json';write(p,dict(authored=c,protocol=read(folder/'PROTOCOL.json'),audio_manifest=str(folder/'audio.json'),dataset_dir=str(folder),gateway_url=f'http://127.0.0.1:{gp}',robot_token_file=str(R/'private/robot.token'),discovery_file=str(case/'voice/run/daemon.json'),probe_policy=False));client=[NODE,str(R/'adapter/T7/client/client.mjs'),str(p),str(case)]
 elif b=='T8':
  data=R/'data/T8/data';c=next(x for x in read(data/'selected.private.json')if x['case_id']==cid);spec['fixture']=state_fixture(b,item['state_id']);proto=data/'PROTOCOL.json';p=case/'client_spec.private.json';write(p,dict(authored=c,protocol=read(proto),audio_manifest=str(data/'audio_manifest.json'),web_port=wp,gateway_port=gp));client=[NODE,str(R/'adapter/shared/t8_adapter/client.mjs'),str(p),str(case)]
 else:raise ValueError(b)
 env.update(AUDIO_BENCH_OUT=str(case),AUDIO_BENCH_BASE=f'http://127.0.0.1:{wp}',AUDIO_BENCH_CASE=cid)
 if proto:env['AUDIO_BENCH_PROTOCOL']=str(proto)
 return spec,client,env
