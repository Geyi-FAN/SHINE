"""Count actual, new simulation frames in the existing physical acceptance gate."""
from repair6.completion import CompletionGate as PreviousGate


class CompletionGate(PreviousGate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_world_step = None
        self.last_simulation_time = None
        self.frame_rejection = None

    def observe(self, row, subject, *args, **kwargs):
        if tuple(subject) != self.subject:
            self.frame_rejection = 'different_task_subject'
            return False
        world, stamp = row.get('world_physics_step'), row.get('simulation_time')
        if world is None or stamp is None:
            self.frame_rejection = 'missing_real_physics_clock'
            return False
        if self.last_world_step is not None:
            if world <= self.last_world_step or stamp <= self.last_simulation_time:
                self.frame_rejection = 'duplicate_or_noncausal_physics_frame'
                return False
        self.last_world_step, self.last_simulation_time = world, stamp
        self.frame_rejection = None
        return super().observe(row, subject, *args, **kwargs)


def install():
    import repair6.completion
    repair6.completion.CompletionGate = CompletionGate
