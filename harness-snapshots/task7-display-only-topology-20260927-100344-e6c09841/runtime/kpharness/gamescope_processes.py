"""Linux process and socket evidence for an owned Gamescope display."""
from __future__ import annotations

import os
import ctypes
import sys
import socket
import struct
import time
from pathlib import Path

from .display_backends import ProcessIdentity, process_relationship
from .gamescope_socket import network_namespace


def process_ids(proc_root: Path = Path('/proc')) -> list[int]:
    return [int(path.name) for path in proc_root.iterdir() if path.name.isdecimal()]


def process_state(pid: int, proc_root: Path = Path('/proc')) -> str:
    raw = (proc_root / str(pid) / 'stat').read_text()
    return raw[raw.rfind(')') + 1:].split()[0]


def subreaper_enabled() -> bool:
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Gamescope controller requires Linux child subreaping')
    value = ctypes.c_int()
    if ctypes.CDLL(None, use_errno=True).prctl(37, ctypes.byref(value), 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'PR_GET_CHILD_SUBREAPER failed')
    return value.value == 1


def establish_subreaper() -> dict:
    """Claim this single-launch harness before spawning any child workloads.

    The process must remain dedicated for its lifetime; Linux subreaping is
    process-wide. Never adopt through an ambient external subreaper.
    """
    if subreaper_enabled():
        raise RuntimeError('controller already a subreaper; dedicated fresh process required')
    tasks = list(Path('/proc/self/task').iterdir())
    if len(tasks) != 1 or (tasks[0] / 'children').read_text().strip():
        raise RuntimeError('controller must be single-threaded with no existing children')
    pid = os.getpid()
    relation = process_relationship(pid)
    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'PR_SET_CHILD_SUBREAPER failed')
    if not subreaper_enabled() or process_relationship(pid) != relation:
        raise RuntimeError('controller subreaper verification failed')
    return {'pid': pid, 'start': relation[3], 'subreaper': True,
            'dedicated_single_launch': True, 'relationship': list(relation),
            'network_namespace': network_namespace()}


class AncestryError(RuntimeError):
    def __init__(self, message, evidence):
        super().__init__(message)
        self.evidence = evidence


def verify_ancestry(pid: int, owner: ProcessIdentity, pgid: int, sid: int, reader,
                    *, controller: dict | None = None) -> list[tuple[int, tuple]]:
    """Verify twice to a launch owner or its explicitly recorded subreaper."""
    chain, seen = [], set()
    evidence = {'first': [], 'second': [], 'owner': {'pid': owner.pid, 'start': owner.start},
                'controller': controller, 'candidate_pid': pid}
    try:
        if controller and pid == controller['pid']:
            raise RuntimeError('controller itself is not a Gamescope endpoint')
        while pid > 1 and pid not in seen:
            seen.add(pid)
            relation = reader(pid)
            chain.append((pid, relation))
            evidence['first'] = _chain_evidence(chain)
            parent, group, session, start = relation
            if controller and pid == controller['pid']:
                if (not controller.get('subreaper') or not controller.get('dedicated_single_launch')
                        or start != controller['start']):
                    raise RuntimeError('controller identity changed or subreaper unverified')
                # Adoption is only valid in the launch owner's group/session.
                if any(r[1:3] != (pgid, sid) for _, r in chain[:-1]):
                    raise RuntimeError('adopted process is outside the owned process group/ancestry')
                break
            if pid == owner.pid:
                if start != owner.start:
                    raise RuntimeError('Gamescope ancestor identity changed')
                break
            pid = parent
        else:
            raise RuntimeError('process is outside the owned process group/ancestry')
        for member, relation in reversed(chain):
            pid = member
            second = reader(member)
            evidence['second'].extend(_chain_evidence([(member, second)]))
            if second != relation:
                raise RuntimeError('Gamescope ancestor identity changed')
        return chain
    except (OSError, RuntimeError, KeyError, ValueError) as error:
        evidence.update(status='rejected', failing_pid=pid, reason=type(error).__name__)
        raise AncestryError(str(error), evidence) from error


def signal_identity(identity: ProcessIdentity, sig: int, reader=process_relationship) -> None:
    """Pin the target with a pidfd; never signal a group or a recycled PID."""
    try:
        fd = os.pidfd_open(identity.pid)
    except ProcessLookupError:
        return
    try:
        if reader(identity.pid)[3] != identity.start:
            raise RuntimeError('refusing signal after process identity changed')
        import signal
        signal.pidfd_send_signal(fd, sig)
    except (FileNotFoundError, ProcessLookupError):
        return
    finally:
        os.close(fd)


def _chain_evidence(chain: list[tuple[int, tuple]]) -> list[dict]:
    return [{"pid": pid, "parent_pid": relation[0], "pgid": relation[1],
             "session": relation[2], "start": relation[3]} for pid, relation in chain]


def verify_private_xwayland(display: str, owner: ProcessIdentity, pgid: int, sid: int,
                            *, proc_root: Path = Path('/proc'), socket_factory=socket.socket,
                            monotonic=time.monotonic, controller=None, evidence_callback=None,
                            node_capture=None) -> dict:
    """Verify an owned endpoint with host-local, cookie-free access.

    This establishes ownership of the endpoint, not private authority or an
    access boundary against other local users. Both transports are peer-checked.
    """
    from .gamescope_socket import capture_socket_node
    node_capture = node_capture or capture_socket_node
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
    candidates = []
    for pid in process_ids(proc_root):
        path = proc_root / str(pid)
        candidate = None
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
            candidate = {'display': display, 'pid': pid, 'executable': executable,
                         'cmdline': ['<redacted-authority>' if i and argv[i - 1] == '-auth' else arg
                                     for i, arg in enumerate(argv)], 'phase': 'socket_binding'}
            candidates.append(candidate)
            relation = reader(pid)
            candidate.update(_chain_evidence([(pid, relation)])[0])
            candidate['state'] = process_state(pid, proc_root)
            candidate['socket_fds'] = {fd.name: os.readlink(fd) for fd in (path / 'fd').iterdir()
                                      if os.readlink(fd).startswith('socket:[')}
            candidate['socket_rows'] = [line for line in (proc_root / 'net/unix').read_text().splitlines()[1:]
                                        if line.split()[-1:] and line.split()[-1] in names]
            if evidence_callback: evidence_callback(candidates)
            listeners = listeners_for(path)
            if not listeners:
                continue
            if '-auth' in argv or '-ac' in argv or any(
                    argv[i:i + 2] == ['-listen', 'tcp'] for i in range(len(argv))):
                raise RuntimeError('invalid X11 authority: unsupported Xwayland access flags')
            candidate.update(listeners=listeners, phase='ancestry')
            chain = verify_ancestry(pid, owner, pgid, sid, reader, controller=controller)
            candidate['ancestry'] = _chain_evidence(chain)
            if chain[0][1] != relation:
                raise RuntimeError('Xwayland candidate identity changed before admission')
            launch_relation = reader(owner.pid)
            if (launch_relation[3] != owner.start or launch_relation[1:3] != (pgid, sid)
                    or (controller and launch_relation[0] != controller['pid'])):
                raise RuntimeError('Gamescope launch owner identity changed')
            candidate['launch_owner'] = _chain_evidence([(owner.pid, launch_relation)])[0]
            controller_namespace = network_namespace('self', proc_root)
            xwayland_namespace = network_namespace(pid, proc_root)
            candidate['network_namespace'] = {'controller': controller_namespace,
                                              'xwayland': xwayland_namespace}
            if (controller_namespace != xwayland_namespace or
                    (controller and controller.get('network_namespace', controller_namespace) != controller_namespace)):
                raise RuntimeError('Xwayland/controller network namespace differs from admission scope')
            node = dict(node_capture(names[0]))
            node['network_namespace'] = candidate['network_namespace']
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
                        or reader(owner.pid) != launch_relation
                        or any(reader(member) != relation for member, relation in chain)
                        or listeners_for(path) != listeners
                        or dict(node_capture(names[0]), network_namespace=candidate['network_namespace']) != node
                        or network_namespace('self', proc_root) != controller_namespace
                        or network_namespace(pid, proc_root) != xwayland_namespace
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
                    peer_chain = verify_ancestry(peer_pid, owner, pgid, sid, reader, controller=controller)
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
                            'ancestry': _chain_evidence(chain), 'peers': peers,
                            'pathname_node': node, 'candidate': candidate})
            candidate['phase'] = 'admitted'
            if evidence_callback: evidence_callback(candidates)
        except (OSError, UnicodeError, ValueError, RuntimeError) as error:
            if candidate is not None:
                candidate.update(status='rejected', error_category=type(error).__name__)
                if isinstance(error, AncestryError): candidate['failed_chain'] = error.evidence
                if evidence_callback: evidence_callback(candidates)
            if isinstance(error, RuntimeError): raise
            continue
    if len(matches) != 1:
        raise RuntimeError('invalid X11 authority: no unique verified owned Xwayland listener')
    return matches[0]
