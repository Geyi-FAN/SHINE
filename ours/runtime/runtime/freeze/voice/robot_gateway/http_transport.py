"""Bounded local HTTP transport; diagnostics never become robot-state evidence."""
import faulthandler
import json
import os
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

class GatewayHTTPServer(ThreadingHTTPServer):
    # Frequent browser images/status and speech tools share this local endpoint.
    # The stdlib backlog of5 + short-lived HTTP/1.0 connections is unsuitable
    # for those bursts. Keep connections reusable and leave acceptance headroom.
    request_queue_size=128
    daemon_threads=True

class ResponsiveHandler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def setup(self):
        super().setup()
        self.connection.settimeout(15)
    def parse_request(self):
        self.request_started=time.monotonic()
        if hasattr(self,'_eval_request'):
            del self._eval_request  # HTTP/1.1 reuses the handler, not POST evidence.
        return super().parse_request()

def bounded_snapshot(state,timeout=.75):
    started=time.monotonic()
    if not state.lock.acquire(timeout=timeout):
        return None,time.monotonic()-started
    try:return state.snapshot(),time.monotonic()-started
    finally:state.lock.release()

def deferred_rejection_context(state,request):
    """Never attribute another input/episode's blocked queue to this rejection."""
    if not isinstance(request,dict) or request.get('name') not in ('robot_replace_deferred','robot_cancel_deferred'):
        return None
    args=request.get('args',{})
    if not isinstance(args,dict) or not state.lock.acquire(timeout=.25):return None
    try:
        slot=state.deferred_task
        if (not slot or args.get('episode_id')!=state.episode
                or args.get('deferred_id')!=slot['deferred_id']
                or not slot.get('dispatch_blocked_by_input')
                or args.get('voice_input_id')!=slot['dispatch_blocked_by_input']):return None
        return dict(deferred_id=slot['deferred_id'],blocked=True)
    finally:state.lock.release()

class RequestDiagnostics:
    def __init__(self,directory=None):
        self.directory=Path(directory) if directory else None
        self.lock=threading.Lock();self.last_dump=0
    def record(self,path,status,started,**extra):
        if not self.directory:return
        row=dict(time=time.time(),path=path,http_status=status,elapsed_ms=(time.monotonic()-started)*1000,**extra)
        self.directory.mkdir(parents=True,exist_ok=True)
        with self.lock:
            with (self.directory/'http_requests.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
    def dump_busy_threads(self):
        if not self.directory:return
        with self.lock:
            if time.monotonic()-self.last_dump<10:return
            self.last_dump=time.monotonic();self.directory.mkdir(parents=True,exist_ok=True)
            with (self.directory/'state_lock_busy_threads.log').open('a') as f:
                f.write('UTC unix timestamp '+str(time.time())+'\n');f.flush()
                faulthandler.dump_traceback(file=f,all_threads=True)
