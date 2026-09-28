"""Linux process and socket evidence for an owned Gamescope display."""
from __future__ import annotations

import os
import socket
import struct
import time
from pathlib import Path

from .display_backends import ProcessIdentity, process_relationship


def process_ids(proc_root: Path = Path('/proc')) -> list[int]:
    return [int(path.name) for path in proc_root.iterdir() if path.name.isdecimal()]


def process_state(pid: int, proc_root: Path = Path('/proc')) -> str:
    raw = (proc_root / str(pid) / 'stat').read_text()
    return raw[raw.rfind(')') + 1:].split()[0]


def verify_ancestry(pid: int, owner: ProcessIdentity, pgid: int, sid: int, reader) -> list[tuple[int, tuple]]:
    """Read every link twice, including the owner, to reject recycled ancestors."""
    chain = []
    seen = set()
    while pid > 1 and pid not in seen:
        seen.add(pid)
        relation = reader(pid)
        parent, group, session, start = relation
        if group != pgid or session != sid:
            raise RuntimeError('process is outside the owned process group/ancestry')
        chain.append((pid, relation))
        if pid == owner.pid:
            if start != owner.start:
                raise RuntimeError('Gamescope ancestor identity changed')
            break
        pid = parent
    else:
        raise RuntimeError('process is outside the owned process group/ancestry')
    if any(reader(pid) != relation for pid, relation in reversed(chain)):
        raise RuntimeError('Gamescope ancestor identity changed')
    return chain


def _chain_evidence(chain: list[tuple[int, tuple]]) -> list[dict]:
    return [{"pid": pid, "parent_pid": relation[0], "pgid": relation[1],
             "session": relation[2], "start": relation[3]} for pid, relation in chain]


def verify_private_xwayland(display: str, owner: ProcessIdentity, pgid: int, sid: int,
                            *, proc_root: Path = Path('/proc'), socket_factory=socket.socket,
                            monotonic=time.monotonic) -> dict:
    """Verify an owned endpoint with host-local, cookie-free access.

    This establishes ownership of the endpoint, not private authority or an
    access boundary against other local users. Both transports are peer-checked.
    """
    number = display[1:].split('.', 1)[0]
    names = ('/tmp/.X11-unix/X' + number, '@/tmp/.X11-unix/X' + number)
    reader = lambda pid: process_relationship(pid, proc_root=proc_root)

    def listeners_for(path):
        links = {os.readlink(fd) for fd in (path / 'fd').iterdir()}
        listeners = {}
        for line in (proc_root / 'net/unix').read_text().splitlines()[1:]:
            fields = line.split()
            if len(fields) == 8 and fields[7] in names and fields[3:6] == ['00010000', '0001', '01']:
                if 'socket:[' + fields[6] + ']' in links:
                    if fields[7] in listeners:
                        raise RuntimeError('invalid X11 authority: ambiguous socket listener')
                    listeners[fields[7]] = fields[6]
        if not listeners:
            return {}
        if set(listeners) != set(names):
            raise RuntimeError('invalid X11 authority: missing owned Xwayland listener')
        for table in ('tcp', 'tcp6'):
            for line in (proc_root / 'net' / table).read_text().splitlines()[1:]:
                fields = line.split()
                if len(fields) > 9 and fields[3] == '0A' and 'socket:[' + fields[9] + ']' in links:
                    raise RuntimeError('invalid X11 authority: Xwayland has a TCP listener')
        return listeners

    matches = []
    for pid in process_ids(proc_root):
        path = proc_root / str(pid)
        try:
            argv_bytes = (path / 'cmdline').read_bytes()
            argv = argv_bytes.decode().rstrip('\0').split('\0')
            executable = os.readlink(path / 'exe')
            if Path(executable).name != 'Xwayland':
                continue
            # Socket inodes plus ancestry bind displayfd-selected displays; a
            # literal :N argument is not required for this launch mechanism.
            displayfd = any(argv[i] == '-displayfd' and argv[i + 1].isdecimal()
                            for i in range(len(argv) - 1))
            if ':' + number not in argv and not displayfd:
                continue
            listeners = listeners_for(path)
            if not listeners:
                continue
            if '-auth' in argv or '-ac' in argv or any(
                    argv[i:i + 2] == ['-listen', 'tcp'] for i in range(len(argv))):
                raise RuntimeError('invalid X11 authority: unsupported Xwayland access flags')
            chain = verify_ancestry(pid, owner, pgid, sid, reader)
            peers = []
            peer_chains = []
            deadline = monotonic() + 2

            def bound(connection):
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError('Xwayland access handshake deadline expired')
                connection.settimeout(remaining)

            def recheck():
                if (os.readlink(path / 'exe') != executable
                        or (path / 'cmdline').read_bytes() != argv_bytes
                        or any(reader(member) != relation for member, relation in chain)
                        or listeners_for(path) != listeners
                        or any(reader(member) != relation for peer_chain in peer_chains
                               for member, relation in peer_chain)):
                    raise RuntimeError('Xwayland process/socket identity changed during admission')

            for name in names:
                address = '\0' + name[1:] if name.startswith('@') else name
                with socket_factory(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                    bound(connection); connection.connect(address)
                    peer_pid, peer_uid, _ = struct.unpack('3i', connection.getsockopt(
                        socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
                    if peer_uid != os.getuid():
                        raise RuntimeError('Xwayland socket belongs to another user')
                    peer_chain = verify_ancestry(peer_pid, owner, pgid, sid, reader)
                    peer_chains.append(peer_chain)
                    recheck()
                    bound(connection)
                    connection.sendall(struct.pack('<BBHHHHH', ord('l'), 0, 11, 0, 0, 0, 0))
                    reply = b''
                    while len(reply) < 8:
                        bound(connection)
                        block = connection.recv(8 - len(reply))
                        if not block:
                            break
                        reply += block
                    if len(reply) != 8 or reply[0] != 1 or struct.unpack_from('<H', reply, 2)[0] != 11:
                        raise RuntimeError('owned Xwayland rejected credential-free local access')
                    recheck()
                    peers.append({'transport': 'abstract' if name.startswith('@') else 'pathname',
                                  'pid': peer_pid, 'uid': peer_uid, 'start': peer_chain[0][1][3],
                                  'ancestry': _chain_evidence(peer_chain)})
            recheck()
            matches.append({'pid': pid, 'start': chain[0][1][3],
                            'access_model': 'owned-endpoint-host-local-no-cookie',
                            'xauthority_mode': 'no-cookie-sentinel',
                            'tcp': 'no-listeners', 'listeners': listeners,
                            'display_selection': 'displayfd' if displayfd else 'argument',
                            'ancestry': _chain_evidence(chain), 'peers': peers})
        except (OSError, UnicodeError, ValueError):
            continue
    if len(matches) != 1:
        raise RuntimeError('invalid X11 authority: no unique verified owned Xwayland listener')
    return matches[0]
