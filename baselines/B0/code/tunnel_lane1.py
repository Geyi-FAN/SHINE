"""Private SSH forward; authentication stays in private/ssh240.json."""
import socketserver,select
from remote_ops import connect
ssh=connect()
class Handler(socketserver.BaseRequestHandler):
 def handle(self):
  ch=ssh.get_transport().open_channel('direct-tcpip',('127.0.0.1',49541),self.request.getpeername())
  try:
   while True:
    read,_,_=select.select([self.request,ch],[],[],30)
    if self.request in read:
     data=self.request.recv(65536)
     if not data:break
     ch.sendall(data)
    if ch in read:
     data=ch.recv(65536)
     if not data:break
     self.request.sendall(data)
  finally:ch.close()
class Server(socketserver.ThreadingTCPServer):allow_reuse_address=True;daemon_threads=True
print('FORWARD_READY',flush=True)
Server(('127.0.0.1',49541),Handler).serve_forever()
