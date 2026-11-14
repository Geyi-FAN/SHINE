"""One immutable task/physics cohort. Never mix live successor fields into it."""
import time

def inspect(sample,now=None):
    now=time.monotonic()if now is None else now
    return dict(sample=sample,physics_step=sample['step'],control_step=sample['policy_actions'],
                task_elapsed_s=max(0,now-sample['task_started'])if sample['task_started']else 0,
                simulation_time=sample['simulation_time'],physical_state_sha256=sample['state_hash'],
                mode=sample['mode'],task_id=sample['task_id'],task_count=sample['task_count'],
                fixture_hold=sample['fixture_hold'],source_phase_reached=sample['source_phase_reached'],
                hold_remaining=sample['hold_remaining'],route=sample['route'],kernel_error=sample['kernel_error'])
