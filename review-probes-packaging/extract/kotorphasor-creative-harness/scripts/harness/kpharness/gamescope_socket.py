"""Exact stale-node cleanup for an admitted, owned Xwayland pathname.

unlinkat has no inode predicate. A held canonical flock and immediate rechecks
bound cooperating harness races; uncooperative replacement after the final
stat is an irreducible kernel-interface limitation, recorded in every receipt.
"""
from __future__ import annotations

import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path


def _identity(value):
    return {name: getattr(value, 'st_' + name) for name in
            ('dev', 'ino', 'mode', 'uid', 'gid', 'size', 'mtime_ns', 'ctime_ns')}


def _parent_identity(value):
    return {name: getattr(value, 'st_' + name) for name in ('dev', 'ino', 'mode', 'uid', 'gid')}


def capture_socket_node(path, *, parent_uid=0):
    path = Path(path)
    if not re.fullmatch(r'X(?:0|[1-9][0-9]*)', path.name):
        raise RuntimeError('invalid X11 socket basename')
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parent = _parent_identity(os.fstat(fd))
        if parent['uid'] != parent_uid or stat.S_IMODE(parent['mode']) != 0o1777:
            raise RuntimeError('unexpected X11 socket parent ownership/mode')
        node = _identity(os.stat(path.name, dir_fd=fd, follow_symlinks=False))
        if not stat.S_ISSOCK(node['mode']) or node['uid'] != os.getuid():
            raise RuntimeError('unexpected X11 socket type/uid')
        return {'path': str(path), 'parent': str(path.parent), 'basename': path.name,
                'parent_identity': parent, 'node': node, 'type': 'socket'}
    finally:
        os.close(fd)


def canonical_lock_guard():
    """Require a held lock capability in this process, including inherited FDs."""
    root = Path(os.environ.get('KP_GAMESCOPE_REPO_ROOT', Path(__file__).resolve().parents[3]))
    git = root / '.git'
    if git.is_file():
        text = git.read_text().strip()
        if not text.startswith('gitdir: '): raise RuntimeError('cannot resolve canonical repository lock')
        worktree_git = (root / text[8:]).resolve()
        common = (worktree_git / (worktree_git / 'commondir').read_text().strip()).resolve()
        root = common.parent
    path = root / 'tmp/harness-locks/live-game.lock'
    expected = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(expected.st_mode): raise RuntimeError('canonical lock is not a regular file')
    for link in Path('/proc/self/fd').iterdir():
        try:
            descriptor = int(link.name)
            actual = os.fstat(descriptor)
            if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino): continue
            key = f'{os.major(actual.st_dev):02x}:{os.minor(actual.st_dev):02x}:{actual.st_ino}'
            for line in Path('/proc/self/fdinfo', link.name).read_text().splitlines():
                fields = line.split()
                if ('FLOCK' in fields and 'WRITE' in fields and key in fields
                        and fields[-2:] == ['0', 'EOF']):
                    again = os.stat(path, follow_symlinks=False)
                    if (again.st_dev, again.st_ino) != (actual.st_dev, actual.st_ino):
                        raise RuntimeError('canonical lock identity changed')
                    return {'path': str(path), 'fd': descriptor, 'dev': actual.st_dev, 'ino': actual.st_ino,
                            'exclusive': True}
        except FileNotFoundError:
            continue
        except OSError as error:
            if error.errno == 9: continue  # /proc enumeration's own closed fd
            raise
    raise RuntimeError('canonical live lock is not held by this controller')


def network_namespace(pid='self', proc_root=Path('/proc')):
    """Kernel namespace identity; scoped evidence, not global socket absence."""
    value = (proc_root / str(pid) / 'ns/net').stat()
    return {'dev': value.st_dev, 'ino': value.st_ino}


def socket_rows(path, proc_root=Path('/proc')):
    names = {path, '@' + path}
    lines = (proc_root / 'net/unix').read_text().splitlines()
    if not lines or lines[0].split() != ['Num', 'RefCount', 'Protocol', 'Flags', 'Type', 'St', 'Inode', 'Path']:
        raise RuntimeError('invalid UNIX socket table header is incomplete evidence')
    matches = []
    for line in lines[1:]:
        fields = line.split()
        if len(fields) < 7:
            raise RuntimeError('malformed UNIX socket table is incomplete evidence')
        if len(fields) >= 8 and fields[7] in names:
            matches.append(line)
    return matches


def cleanup_socket_node(record, *, owned_absent, lock_guard=canonical_lock_guard,
                        rows_reader=socket_rows, namespace_reader=network_namespace, before_final=None,
                        evidence=None):
    result = evidence if evidence is not None else {}
    result.update(status='unknown', path=record['path'], recorded=record,
                  utc=datetime.now(timezone.utc).isoformat(),
                  race_limit='unlinkat cannot exclude uncooperative replacement after final stat')
    fd = None
    try:
        result['lock'] = lock_guard()
        namespaces = record['network_namespace']
        result['endpoint_absence_scope'] = 'admitted-controller-network-namespace'
        result['network_namespace'] = namespaces
        def check_namespace():
            current = namespace_reader()
            result['observed_network_namespace'] = current
            if current != namespaces['controller'] or current != namespaces['xwayland']:
                raise RuntimeError('controller or admitted Xwayland network namespace changed')
        check_namespace()
        fd = os.open(record['parent'], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        if _parent_identity(os.fstat(fd)) != record['parent_identity']:
            raise RuntimeError('socket parent identity changed')
        # Snapshot every other display node; no sibling is ever mutated.
        def siblings():
            return {name: _identity(os.stat(name, dir_fd=fd, follow_symlinks=False))
                    for name in os.listdir(fd) if re.fullmatch(r'X[0-9]+', name)
                    and name != record['basename']}
        result['siblings_before'] = siblings()
        result['sibling_listeners_before'] = {name: rows_reader(str(Path(record['parent']) / name))
                                             for name in result['siblings_before']}
        def check():
            lock_guard()
            if _parent_identity(os.fstat(fd)) != record['parent_identity']:
                raise RuntimeError('socket parent identity changed')
            named_parent = os.stat(record['parent'], follow_symlinks=False)
            if _parent_identity(named_parent) != record['parent_identity']:
                raise RuntimeError('socket parent pathname changed')
            owned_absent()
            check_namespace()
            rows = rows_reader(record['path'])
            check_namespace()
            result['socket_rows'] = rows
            if rows: raise RuntimeError('pathname or abstract socket is still active')
            try:
                value = _identity(os.stat(record['basename'], dir_fd=fd, follow_symlinks=False))
            except FileNotFoundError:
                return None
            result['observed_node'] = value
            if value != record['node'] or not stat.S_ISSOCK(value['mode']) or value['uid'] != os.getuid():
                raise RuntimeError('socket node identity/type/uid changed')
            return value
        first = check()
        if before_final: before_final()
        last = check()
        if first != last: raise RuntimeError('socket node changed during final check')
        if siblings() != result['siblings_before']: raise RuntimeError('protected sibling changed')
        if check() != last: raise RuntimeError('socket node changed immediately before unlink')
        if last is not None:
            os.unlink(record['basename'], dir_fd=fd)
            result['action'] = 'unlink'
        # Repeat scoped process/socket-table checks and exact absence proof.
        if check() is not None: raise RuntimeError('socket reappeared after unlink')
        result['siblings_after'] = siblings()
        if result['siblings_after'] != result['siblings_before']:
            raise RuntimeError('protected sibling changed')
        result['sibling_listeners_after'] = {name: rows_reader(str(Path(record['parent']) / name))
                                            for name in result['siblings_before']}
        if result['sibling_listeners_after'] != result['sibling_listeners_before']:
            raise RuntimeError('protected sibling listener changed')
        check_namespace()
        result['status'] = 'removed' if last is not None else 'already_absent'
        return result
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        result.update(status='unknown', error=f'{type(error).__name__}: {error}')
        if fd is not None:
            try: result['siblings_after'] = siblings()
            except (OSError, UnboundLocalError): result['siblings_after'] = 'unavailable'
        raise RuntimeError('stale X11 node cleanup incomplete: ' + str(error)) from error
    finally:
        if fd is not None: os.close(fd)
