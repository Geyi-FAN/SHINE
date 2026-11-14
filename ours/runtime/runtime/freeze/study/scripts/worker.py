"""Frozen F1 algorithms on the byte-identical published308 cases/protocol."""
import argparse
import fcntl
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
F1=Path('/mnt/disk_4/geyi/F1_switch308_20261031/evolution/versions/F28d_fp8_transport_20261031')


def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=['agent'],required=True);p.add_argument('--index',type=int,required=True);a=p.parse_args()
    for name,sha in json.loads((F1/'FROZEN.json').read_text()).items():assert hashlib.sha256((F1/name).read_bytes()).hexdigest()==sha,name
    seal=json.loads((ROOT/'STUDY_FROZEN.json').read_text())
    for name,sha in seal['sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha,name
    case=json.loads((ROOT/'data/jobs.json').read_text())[a.index]['case']
    assert case['instruction']==case['instruction_original']==case['public_user_instruction']
    out=ROOT/'runs/agent'/case['case_id'];(ROOT/'logs/locks').mkdir(exist_ok=True)
    with(ROOT/'logs/locks'/('agent_'+case['case_id'])).open('a')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if out.exists():raise SystemExit('Preserving first attempt; no implicit rerun')
        port=int(os.environ['SCALE_POLICY_PORT']);physical_gpu=int(os.environ['SCALE_RENDER_DEVICE']);yolo=int(os.environ['SCALE_YOLO_DEVICE'])
        mapping=json.loads(Path('/workspace/runtime/egl_device_map.json').read_text())
        egl=mapping[str(physical_gpu)]
        assert port in [29865,29866,29867,29868,39865,39866,39867,39868] and physical_gpu in [1,4,6,7] and yolo in [1,4,6,7]
        os.environ.update(MUJOCO_EGL_DEVICE_ID=str(egl),HYBRID_YOLO_DEVICE=str(yolo),HYBRID_HARNESS_HOME='/workspace/runtime/harness',
            R34_LOCAL_ROLES=str(F1/'local_roles.json'),R34_LOCAL_REQUEST_LOG=str(out/'local_requests'),P012_ROOT=str(ROOT),P012_ARM='P2',
            P2_REFINE_VARIANT='R11',HYBRID_CONTRACT_FILE=str(ROOT/'data/contracts_private.json'),HYBRID_PLANS_FILE=str(ROOT/'plans.json'),
            HYBRID_ORACLE_REVIEW='1',HYBRID_EXECUTOR='smolvla_e3_v4',HYBRID_AGENT_MODEL='Qwen3.8-27B-FP8',HYBRID_COMPLETION='S1',
            HYBRID_FINAL_PROTOCOL='D1',S1_OBSERVE_ARM='B',HYBRID_POLICY_NAMESPACE='F28d_fp8_stable308_20261031_agent',
            REPAIR_TASK_LANGUAGE='1',REPAIR_DRAWER_GUARD='1',REPAIR_ROI_YOLO='1',REPAIR_STAGNATION_OBSERVATION='1',
            REPAIR_CONTAINER_GUARD='1',REPAIR_GRASP_GUARD='1',REPAIR_STRONG_GRASP_JOINT='1',REPAIR_CLOSE_CANDIDATE_HOLD='1',
            REPAIR_LOST_OWNERSHIP='1',PLANNING_HANDOFF_REPAIR='1',PLANNING_RELATION_REPAIR='1')
        runtime_environment=json.loads((F1/'VERSION.json').read_text()).get('runtime_environment',{})
        assert set(runtime_environment)<=set(['HYBRID_KNOWN_CLOSED_EPISODE_START'])
        os.environ.update(runtime_environment)
        os.environ['NUMBA_CACHE_DIR']='/workspace/runtime/f1_numba_cache'
        Path(os.environ['NUMBA_CACHE_DIR']).mkdir(parents=True,exist_ok=True)
        sys.path[:0]=[str(ROOT/'compat_source'),str(F1/'source'),str(ROOT/'scripts'),str(ROOT)]
        import benchmark_metrics
        from benchmark_metrics.config import fingerprint as rules_fingerprint
        assert rules_fingerprint(benchmark_metrics.load_rules())=='d64038f1ccd17ebc6c9327de21c0711a98c07542d5b817f057ff165e1cde59e6'
        import text_transport
        text_transport.install_network_guard()
        import agent_transport
        agent_transport.request_json=text_transport.request_json
        import local_transport
        original_settings=local_transport.settings
        def settings():
            cfg=original_settings()
            assert cfg.get('preserve_role_api_urls') is True
            assert all(e['api_base_url']=='http://127.0.0.1:18084/v1'for e in cfg['roles'].values())
            return cfg
        local_transport.settings=settings
        from policy_backend import SmolHTTPClient
        from response_memo import fingerprint
        class RoutedClient(SmolHTTPClient):
            def __init__(self):self.port=port
            def exchange(self,method,path,body=None):
                assert path in ['/metadata','/infer']
                conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=120 if method=='POST'else 10)
                try:
                    conn.request(method,path,body=body,headers={'Content-Type':'application/octet-stream'}if body is not None else{})
                    response=conn.getresponse();data=json.loads(response.read())
                    if response.status!=200:raise RuntimeError('Policy service HTTP '+str(response.status))
                    return data
                finally:conn.close()
            def get_server_metadata(self):return self.exchange('GET','/metadata')
            def infer(self,request):
                meta={k:request[k]for k in ['prompt','evaluation_case_id','evaluation_call_index']}
                if 'evaluation_seed'in request:meta['evaluation_seed']=request['evaluation_seed']
                data=io.BytesIO();np.savez(data,image=request['observation/image'],wrist=request['observation/wrist_image'],state=request['observation/state'],metadata=json.dumps(meta))
                answer=self.exchange('POST','/infer',data.getvalue())
                answer.update(paired_request_sha256=fingerprint(request),paired_response_memo_hit=False,paired_action_sha256=fingerprint(np.asarray(answer['actions'],np.float32)))
                return answer
        client=RoutedClient();metadata=client.get_server_metadata()
        assert metadata['weights_sha256']=='30a620085ba28b8faec160ae68a9276d705ec0fb6d2fc9237e706379d0c5eebc'
        assert metadata['normalization_sha256']=='d4e03a22ef5d89a910e32c233a509465ad0d265381a06745917d69fd8924a635'
        import run
        import oracle_review
        from compat import install
        install(oracle_review)
        from authority_bridge import install as install_published
        install_published(run,case,out,oracle=False)
        result=run.run(case,run.Planner(model='Qwen3.8-27B'),client,out,1200)
        result.update(server_metadata=metadata,study='F28d_fp8_stable308_20261031',comparison_arm='agent',method='F28d_fp8_transport_20261031',
            task_configuration_id=case['config'],raw_legacy_short_instruction=case['legacy_short_instruction_original'],
            public_full_instruction=case['public_user_instruction'],input_mode=case['input_mode'],source_snapshot_sha256=case['snapshot_sha256'],
            policy_seed=case['policy_seed'],authoritative_benchmark='switch-v4.1-train-aligned-20261028',score_variant='original_v25',
            published_stop_policy=case['stop_policy'],observation_profile='smolvla_switch_256',metric_extension='switch-explicit-invariants-v1',
            all_four_agents_local=True,cloud_API_calls=0,paid_fallback=False,no_best_of_retry=True,execution_host='10.103.14.171',
            policy_service_port=port,render_gpu=physical_gpu,render_egl_device=egl,yolo_gpu=yolo,physical_bundle_root='/mnt/disk_1/geyi/F1_switch308_20261031/evolution/studies/F28d_fp8_stable308_20261031',
            F1_frozen_sha256=hashlib.sha256((F1/'FROZEN.json').read_bytes()).hexdigest(),study_frozen_sha256=hashlib.sha256((ROOT/'STUDY_FROZEN.json').read_bytes()).hexdigest())
        result['runtime_code_files']={}
        for name in ['run','planner','scene_memory','observed_completion','extended_completion','observed_state_memory','points','policy_backend','sim_runtime','eval_inputs','benchmark_metrics','benchmark_metrics.config','sym_geometry','plan_prerequisites','authority_bridge','text_transport','local_transport']:
            m=sys.modules.get(name)
            if m is not None and getattr(m,'__file__',None):
                f=Path(m.__file__);result['runtime_code_files'][name]=dict(file=str(f),sha256=hashlib.sha256(f.read_bytes()).hexdigest())
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        if result.get('status')in['runtime_error','blocked_external_api']or result.get('valid_for_performance')is False:raise SystemExit(78)
        files={}
        for f in sorted(out.rglob('*')):
            if f.is_file()and f.name not in ['TRANSFER_READY.json','TRANSFER_ACK.json']:
                h=hashlib.sha256()
                with f.open('rb')as stream:
                    for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
                files[str(f.relative_to(out))]=dict(sha256=h.hexdigest(),bytes=f.stat().st_size)
        ready=dict(case_id=case['case_id'],arm='agent',index=a.index,files=files,performance_valid=True,execution_host='171')
        (out/'TRANSFER_READY.json').write_text(json.dumps(ready,indent=2))
        print(json.dumps(dict(case_id=case['case_id'],status=result['status'],success=result.get('metrics',{}).get('instruction_adjusted',{}).get('success'))),flush=True)


if __name__=='__main__':main()
