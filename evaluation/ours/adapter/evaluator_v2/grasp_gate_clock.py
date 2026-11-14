"""Five distinct real control cycles; retain legacy policy-update audit."""
from collections import deque

class GraspClock:
    def __init__(self, names, length=5):
        self.names = tuple(names)
        self.length = length
        self.identity = None
        self.physics = self.policy = None
        self.real_windows = {n: deque(maxlen=length) for n in self.names}
        self.legacy_windows = {n: deque(maxlen=length) for n in self.names}

    def update(self, identity, physics_step, policy_step, rows):
        if identity != self.identity:
            self.identity = identity
            self.physics = self.policy = None
            self.real_windows = {n: deque(maxlen=self.length) for n in self.names}
            self.legacy_windows = {n: deque(maxlen=self.length) for n in self.names}
        flags = {n: bool(rows.get(n, {}).get('bilateral_finger_contact')
                         and rows.get(n, {}).get('target_contact')
                         and not rows.get(n, {}).get('support_contact'))
                 for n in self.names}
        if physics_step != self.physics:
            for name in self.names:
                self.real_windows[name].append(flags[name])
            self.physics = physics_step
        if policy_step != self.policy:
            for name in self.names:
                self.legacy_windows[name].append(flags[name])
            self.policy = policy_step

    def confirmed(self, legacy=False):
        windows = self.legacy_windows if legacy else self.real_windows
        return [name for name, values in windows.items()
                if len(values) == self.length and all(values)]
