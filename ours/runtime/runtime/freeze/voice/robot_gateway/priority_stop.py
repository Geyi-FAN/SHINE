"""Execute authenticated pause requests on the simulator's control thread.

This schedules only the existing command implementation. It grants no new
authority and never reads or mutates the simulator from an HTTP thread.
"""
import collections
import dataclasses
import threading
import time


@dataclasses.dataclass
class PendingPause:
    args: dict
    request_id: str
    expires: float
    event: threading.Event = dataclasses.field(default_factory=threading.Event)
    phase: str = "pending"
    result: object = None
    error: object = None


class PriorityStop:
    def __init__(self, capacity=32, lifetime=4.0, clock=time.monotonic):
        self.capacity = capacity
        self.lifetime = lifetime
        self.clock = clock
        self.lock = threading.Lock()
        self.pending = collections.deque()

    def submit(self, args, request_id):
        if not isinstance(args, dict) or not isinstance(request_id, str) or not request_id:
            raise ValueError("invalid_pause_envelope")
        with self.lock:
            if len(self.pending) >= self.capacity:
                raise ValueError("priority_pause_queue_full")
            item = PendingPause(dict(args), request_id, self.clock() + self.lifetime)
            self.pending.append(item)
            return item

    def wait(self, item):
        # No HTTP mutation retry. An expired, unclaimed entry cannot execute
        # later. A claimed entry has the same unknown-result semantics as the
        # ordinary tool transport if its result genuinely becomes unavailable.
        if not item.event.wait(self.lifetime + 0.5):
            with self.lock:
                if item.phase == "pending":
                    item.phase = "cancelled"
                    raise ValueError("priority_pause_expired_without_execution")
                if item.phase == "claimed":
                    return dict(status="unknown", executed=None,
                                code="priority_pause_receipt_unavailable",
                                note="Read status; do not automatically replay this mutation.")
        if item.error is not None:
            raise item.error
        return item.result

    def drain(self, command):
        # Bound work per tick; malformed or repeated traffic cannot starve
        # the controller indefinitely. The same command owns all validation,
        # version fences, receipt deduplication, gripper holding and logging.
        for _ in range(self.capacity):
            with self.lock:
                if not self.pending:
                    return
                item = self.pending.popleft()
                if item.phase != "pending":
                    continue
                if self.clock() >= item.expires:
                    item.phase = "expired"
                    item.error = ValueError("priority_pause_expired_without_execution")
                    item.event.set()
                    continue
                item.phase = "claimed"
            try:
                result = command("robot_pause", item.args, item.request_id)
                error = None
            except Exception as exc:
                result, error = None, exc
            with self.lock:
                item.result, item.error, item.phase = result, error, "finished"
                item.event.set()
