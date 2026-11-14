"""Process-lifetime port claims outside Linux automatic client-port allocation."""
import fcntl
import socket
from pathlib import Path

OFFSETS = (0, 2, 3)


class PortLease:
    def __init__(self, port, locks, ephemeral):
        self.port, self.locks, self.ephemeral = port, locks, ephemeral

    def close(self):
        for handle in self.locks:
            handle.close()
        self.locks = []


def allocate(lane, lock_root, ephemeral_file=Path('/proc/sys/net/ipv4/ip_local_port_range')):
    if lane not in range(4):
        raise ValueError('Invalid lane')
    low, high = map(int, Path(ephemeral_file).read_text().split())
    lock_root = Path(lock_root)
    lock_root.mkdir(parents=True, exist_ok=True)
    for candidate in range(22000 + lane*250, 22250 + lane*250, 5):
        ports = [candidate + offset for offset in OFFSETS]
        if any(low <= port <= high for port in ports):
            continue
        handles, probes = [], []
        claimed = False
        try:
            for port in ports:
                handle = (lock_root/('tcp_'+str(port)+'.lock')).open('ab')
                handles.append(handle)
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                probe = socket.socket()
                probes.append(probe)
                probe.bind(('127.0.0.1', port))
            claimed = True
            return PortLease(candidate, handles, [low, high])
        except OSError:
            pass
        finally:
            for probe in probes:
                probe.close()
            if not claimed:
                for handle in handles:
                    handle.close()
    raise RuntimeError('No free non-ephemeral port triple for lane '+str(lane))
