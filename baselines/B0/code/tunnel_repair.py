"""Isolated SSH forwarding for the two repaired literal-transcript policies."""
import argparse,select,socketserver,sys
sys.path.insert(0,'/mnt/disk_4/geyi/audio_switch_benchmark/experiments/asr_direct_pi05_20261108/code')
from remote_ops import connect
p=argparse.ArgumentParser();p.add_argument('--port',type=int,required=True);a=p.parse_args();ssh=connect()
class Handler(socketserver.BaseRequestHandler):
 def handle(self):
  ch=ssh.get_transport().open_channel('direct-tcpip',('127.0.0.1',a.port),self.request.getpeername())
  try:
   while True:
    ready,_,_=select.select([self.request,ch],[],[],30)
    if self.request in ready:
     data=self.request.recv(65536)
     if not data:break
     ch.sendall(data)
    if ch in ready:
     data=ch.recv(65536)
     if not data:break
     self.request.sendall(data)
  finally:ch.close()
class Server(socketserver.ThreadingTCPServer):allow_reuse_address=True;daemon_threads=True
print('FORWARD_READY',a.port,flush=True);Server(('127.0.0.1',a.port),Handler).serve_forever()
