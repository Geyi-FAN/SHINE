from pathlib import Path
import json
Q=Path(__file__).resolve().parents[1]
for method in ['B0','B1']:
 p=Q/'actors'/method/'code/raw_gateway.py';s=p.read_text()
 if "conditioning_mode=('symbolic'"not in s:
  s=s.replace('metadata=dict(prompt=text,',"metadata=dict(conditioning_mode=('symbolic'if 'Coordinates:'in text else'complete_task'),prompt=text,");p.write_text(s)
# Shared π0.5 endpoint reports actual conditioning hashes rather than the old
# raw-only endpoint's literal prompt echo. Require the stronger exact check.
for method in ['B0','B1']:
 p=Q/'actors'/method/'code/raw_gateway.py';text=p.read_text()
 text=text.replace(" if v.get('prompt')!=text:raise ValueError('Policy changed literal conditioning')", " if v.get('effective_prompt_sha256')!=hashlib.sha256(text.encode()).hexdigest()or v.get('conditioning_mode')!=metadata['conditioning_mode']:raise ValueError('Policy changed actual conditioning')\n audit=os.environ.get('COMMON_CASE_OUTPUT')\n if audit:\n  with(Path(audit)/'policy_transport.jsonl').open('a')as af:af.write(json.dumps(dict(case_id=episode,call_index=index,seed=metadata.get('evaluation_seed'),requested_prompt_sha256=hashlib.sha256(text.encode()).hexdigest(),effective_prompt_sha256=v['effective_prompt_sha256'],conditioning_mode=v['conditioning_mode']))+'\\n')")
 text=text.replace(" assert metadata['agent']is False and metadata['oracle']is False and metadata['prompt_mode']=='literal_transcript_no_prefix_no_subgoal_no_coordinates'", " assert metadata['complete_task_input_supported']is True and metadata['checkpoint_step']==30000 and metadata['trajectories']==744 and metadata['state_dimension']==8 and metadata['action_horizon']==10\n assert metadata['archive_sha256']=='57315913541eb81f40678a75121e15c55c2622bbbe496a75ead7903f61820588' and metadata['normalization_sha256']=='b3a44bb2810436fb62917decaea58bd4d9110255df527dea21e8fd40c960bd84'")
 p.write_text(text)
# Metadata only: do not attach an Agent or TTS to the raw-ASR baseline.
p=Q/'actors/B0/config/MODELS.json'
if not p.exists():
 c=json.loads((Q/'actors/B1/config/MODELS.json').read_text());p.write_text(json.dumps({k:c[k]for k in ['asr','policy']},indent=2)+'\n')
p=Q/'actors/B1/code/raw_audio_worker.mjs';s=p.read_text()
s=s.replace("expectedSamples:e.samples,text:e.text,replyKind:e.replyKind||'unknown'","expectedSamples:e.samples,receiptKey:'tts_'+e.outputId,text:e.text,replyKind:e.replyKind||'unknown'")
p.write_text(s)
p=Q/'actors/B1/code/agent_gateway.py';s=p.read_text().replace("dict(text=job['text'],responseId=str(sid),audioSuppressed=False)","dict(text=job['text'],responseId=str(sid),receipt_key='tts_'+str(sid),audioSuppressed=False)");p.write_text(s)
# Same deterministic causal client; only replace the underlying audio adapter
# with the historical baseline PCM/Whisper adapter (not Qwen speech input).
transport="const{AudioClient,readWavPcm}=await import('file://"+str(Q)+"/actors/'+process.env.COMMON_METHOD+'/code/raw_audio_client.mjs');"
p=Q/'clients/t3_controlled.mjs';s=p.read_text();lines=s.splitlines();lines=[transport if line.startswith("import{AudioClient,readWavPcm}from")else line for line in lines];p.write_text('\n'.join(lines)+'\n')
p=Q/'clients/T5/client/client.mjs';s=p.read_text();s=s.replace("import {AudioClient as AudioBenchmarkClient,readWavPcm} from './clocked_audio/audio-client.mjs';", "const{AudioClient:AudioBenchmarkClient,readWavPcm}=await import('file://"+str(Q)+"/actors/'+process.env.COMMON_METHOD+'/code/raw_audio_client.mjs');");p.write_text(s)
print('correct per-method PCM route and exact T5 playback binding; no actor decisions changed')
