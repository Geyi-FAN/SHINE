"""Publish completion speech only after measured, current holding observations.

Does not plan, act, alter acceptance, or read benchmark expected answers.
Repeated status polling is not an additional observation.
"""
class CompletionReceiptWindow:
    def __init__(self, required=40):
        self.required = required
        self.subject = None
        self.last_frame = None
        self.count = 0

    def observe(self, subject, frame, verified):
        subject = tuple(subject)
        if subject != self.subject:
            self.subject, self.last_frame, self.count = subject, None, 0
        if not verified:
            self.count, self.last_frame = 0, frame
        elif frame != self.last_frame:
            self.count = self.count + 1 if self.last_frame is not None and frame == self.last_frame + 1 else 1
            self.last_frame = frame
        return dict(ready=self.count >= self.required,
                    consecutive_verified_physics_frames=self.count,
                    required_physics_frames=self.required,
                    last_observed_physics_frame=self.last_frame,
                    source='current_supervisor_verification_each_real_physics_frame')
