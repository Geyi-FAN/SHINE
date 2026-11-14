"""Read-only formal admission; wrong model/key lane/circuit cannot silently run."""
def validate_policy(p,revision,gpu):
 expected=dict(model='pi05',variant='E3',checkpoint_step=30000,trajectories=744,state_dimension=8,image_size=224,visual_marker=False,flow_steps=10,execute_steps=3,runtime_revision=revision,gpu=gpu,warmup_passed=True)
 for key,value in expected.items():
  if p.get(key)!=value:raise RuntimeError('Policy identity mismatch: '+key)
def validate_provider(p):
 for key,value in dict(provider='paratera',model='Qwen3.8-27B',credential_no='04',local_model_fallback=False,automatic_generation_retry=False).items():
  if p.get(key)!=value:raise RuntimeError('Cloud04 identity mismatch: '+key)
 if p.get('circuit',{}).get('blocked',True):raise RuntimeError('Cloud04 circuit blocked; no further cases dispatched')
 if p.get('storage',{}).get('unsynced_receipts'):raise RuntimeError('Cloud04 receipts not synchronized')
