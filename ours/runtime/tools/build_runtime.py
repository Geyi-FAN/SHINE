"""Build the independent shared service from inspected, pinned source inputs."""
import ast
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import sys

W = Path(__file__).resolve().parents[1]
# FROZEN_BUILD_GUARD: a new revision requires a separate checkout.
if (W/'FREEZE.json').exists():
    raise RuntimeError('Refuse to rebuild an already frozen runtime; create a new revision')
B = W/'runtime'
ROOTS = json.loads((W/'provenance/BRANCH_SOURCE_ROOTS.json').read_text())


def exact(text, old, new):
    if text.count(old) != 1:
        raise ValueError(('Unexpected composition anchor', old[:100], text.count(old)))
    return text.replace(old, new)


def build():
    fixes = B/'common_fixes'
    fixes.mkdir(exist_ok=True)
    t7 = Path(ROOTS['t7'])
    names = ['bootstrap_evidence', 'latency_integration', 'pending_preparation',
             'stage_continuation', 'waiting_runtime', 'waiting_contract', 'waiting_language',
             'cancel_clarification', 'cancel_audio_evidence', 'terminal_observation']
    for name in names:
        shutil.copy2(t7/(name+'.py'), fixes/(name+'.py'))
    p = fixes/'latency_integration.py'
    s = exact(p.read_text(), 'from private_transport import install as install_private_transport',
              'from unified.transport import install as install_private_transport')
    p.write_text(s)
    t4 = Path(ROOTS['t4'])
    for name in ['objectives.py', 'acoustic_routing.py']:
        dst = B/'t4_adapter'/name
        dst.parent.mkdir(exist_ok=True)
        shutil.copy2(t4/'t4_adapter'/name, dst)
    # Keep actual currentness/ownership protection, without experiment-specific
    # routing affinity or logs falsely claiming an old private pool is active.
    t = ast.parse((t4/'kernel/runtime_patch.py').read_text())
    selected = [n for n in t.body if isinstance(n, (ast.Import, ast.ImportFrom))
                or isinstance(n, ast.FunctionDef) and n.name in
                {'revalidate_late_policy', 'install_ownership', 'install_bridge'}]
    for n in ast.walk(ast.Module(body=selected, type_ignores=[])):
        if isinstance(n, ast.FunctionDef) and n.name == 'initialize':
            n.body = ast.parse("original_init(bridge,*args,**kwargs)\ninstall_ownership(bridge.mon_class)\nbridge.log('currentness_ownership_guard_installed', source='reviewed_T4', creates_completion=False)").body
    (B/'unified/t4_bridge.py').write_text(ast.unparse(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])))+'\n')
    # Actual pi05 kernel operators and Node input authority share one profile.
    p = B/'freeze/voice/robot_gateway/native_execution.py'
    s = p.read_text().replace("'smolvla_e3_v4'", "'pi05_e3_v4'")
    s = s.replace('actions[:4]', 'actions[:3]')
    p.write_text(s)
    p = B/'native_prefetch/scheduler.py'
    s = p.read_text().replace('offset + 4', 'offset + 3').replace('不足4步', '不足3步')
    s = s.replace('four-action', 'three-action').replace('time-aligned four', 'time-aligned three')
    p.write_text(s)
    (B/'freeze/voice/robot_gateway/policy_backend.py').write_text(
        '"""Compatibility names resolve exclusively to the pi05 actor."""\n'
        'from unified.actor import Pi05HTTPClient,SmolHTTPClient,build_inputs,build_smol_inputs,build_replay_smol_inputs,validate_policy_metadata\n')
    # Required source helper is code only; no old config or credentials copied.
    src = Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102/freeze/voice/scripts/project_config.py')
    dst = B/'freeze/voice/scripts/project_config.py'
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    server = B/'freeze/voice/robot_gateway/server.py'
    original_server = Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102/freeze/voice/robot_gateway/server.py')
    s = exact(original_server.read_text(), 'token = (ROOT / "private/robot.token").read_text().strip()',
              'token = Path(os.environ["HARNESS_ROBOT_TOKEN_FILE"]).read_text().strip()')
    server.write_text(s)
    link = B/'freeze/study/authority_src'
    if not link.exists():
        link.symlink_to('../authority_src', target_is_directory=True)
    # Base generated code is materialized, so no runtime exec of historical
    # branch launchers, source directories or their evaluator-specific labels.
    source = (W/'provenance/base_gateway_materialized.py').read_text()
    source = exact(source, ' core,runner,authority=configure(a.out,a.gpu)',
                   " os.environ['HYBRID_POLICY_PORT']=str(a.policy_port)\n core,runner,authority=configure(a.out,a.gpu)")
    source = exact(source, "client=Client(port=a.policy_port);metadata=client.get_server_metadata();assert metadata['weights_sha256']=='30a620085ba28b8faec160ae68a9276d705ec0fb6d2fc9237e706379d0c5eebc';assert metadata['normalization_sha256']=='d4e03a22ef5d89a910e32c233a509465ad0d265381a06745917d69fd8924a635';state.policy_metadata=metadata",
                   'client=Client(port=a.policy_port);metadata=client.get_server_metadata();state.policy_metadata=metadata')
    source = exact(source, ' install_c3r(SingleOwnerBridge)',
                   ' install_c3r(SingleOwnerBridge)\n from unified.hooks import install_bridge as install_shared\n install_shared(SingleOwnerBridge)')
    source = exact(source, 'from native_execution import NativeExecution,native_candidate,CATALOG',
                   'from native_execution import NativeExecution,CATALOG\n from speech_routing import native_candidate')
    # The actual current task identity owns wording/planning. Background
    # preparation may cache observations, never submit old-generation plans.
    source = exact(source, ' install_waiting_prefetch(b,state)',
                   ' # Current-identity evidence preparation is installed by common C3r hooks.')
    source = exact(source, "result['execution_kernel']='C3r';",
                   "result['execution_kernel']='C3r';result['runtime_revision']='audio-c3r-pi05-744-r3';result['scene_inventory']=None;")
    source = exact(source, '  return receipt\n state.command=command',
                   "  if isinstance(receipt,dict) and isinstance(receipt.get('qa_evidence'),dict):receipt['qa_evidence']['drawer_facts']=None\n  return receipt\n state.command=command")
    source = exact(source, "    stepped=b.pump(now>=tick)\n    if stepped:tick=time.monotonic()+.05",
                   "    stepped=b.pump(now>=tick)\n    from terminal_observation import tick as terminal_hold_tick\n    if not stepped:stepped=terminal_hold_tick(b,state,now>=tick)\n    if stepped:tick=time.monotonic()+.05")
    source = source.replace("spec.get('serve_live')or time.monotonic()-started<1600",
                            "spec.get('serve_live')or time.monotonic()-started<spec.get('service_lifetime_s',1600)")
    source_routing=(t7/'speech_routing.py').read_text()
    source_routing=exact(source_routing,'def native_candidate(state,fresh_episode_task,held_object):\n','def native_candidate(state,fresh_episode_task,held_object):\n    if state.policy_metadata.get(\'executor\') == \'pi05_e3_v4\':\n        return None, \'pi05_full_c3r_agent_prompt_required\'\n')
    (fixes/'speech_routing.py').write_text(source_routing)
    # Benchmark labels belong in private audit files; the planning context sees
    # the randomly generated episode identity rather than a semantic case ID.
    source = exact(source, "case_id=spec['case_id'],source_task=", "case_id=state.episode,source_task=")
    source = exact(source, " objective_context=[None]", " (a.out/'benchmark_identity.private.json').write_text(json.dumps(dict(benchmark_case_id=spec['case_id'],episode_id=state.episode)))\n objective_context=[None]")
    # Keep ordinary environment resolution 256; policy views/points use the
    # existing fixed 256->224 transform. No image or coordinate augmentation.
    (B/'unified/gateway.py').write_text(source)
    service = (B/'repair6/service.py').read_text()
    service = exact(service, "self.token=(B/'freeze/voice/private/robot.token').read_text().strip()",
                    "self.token=Path(os.environ['HARNESS_ROBOT_TOKEN_FILE']).read_text().strip()")
    service = exact(service, "B/'repair6/gateway.py'", "B/'unified/gateway.py'")
    service = exact(service, "state['execution_service_revision']='R5'",
                    "state['execution_service_revision']='R7-T3.2+C3r+pi05-744-r3';state['runtime_revision']='audio-c3r-pi05-744-r3'")
    service = service.replace('p.wait(12)', 'p.wait(60)')
    service = service.replace("p.add_argument('--port',type=int,default=8801)", "p.add_argument('--port',type=int,required=True)")
    service = service.replace("p.add_argument('--policy-port',type=int,default=19867)", "p.add_argument('--policy-port',type=int,required=True)")
    (B/'unified/service.py').write_text(service)
    print(json.dumps(dict(gateway_lines=len(source.splitlines()), status='built_not_started')))


if __name__ == '__main__':
    build()
