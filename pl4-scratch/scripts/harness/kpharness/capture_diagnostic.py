"""One bounded animated-pattern capture diagnostic on a private Gamescope display.

This module is checked in but never run by tests or other tooling. When a
single run is authorized, the operator starts it on the host with
``--authorized-single-run``. It then:

1. takes the canonical live-game lock and keeps the descriptor for every child;
2. refuses if any wineserver, swkotor, gamescope, ffmpeg, or ffprobe process
   already exists, and retains the ``/proc`` evidence;
3. snapshots the harness closure (plus this driver) and verifies it is
   source-equal, then runs the child from that snapshot;
4. prints the route, FFprobe, and launch cleanup-ledger commitments before any
   child starts;
5. plays ``PATTERN_GRAPH`` (lavfi ``testsrc2`` at 60 FPS with a per-frame
   full-frame luma step) in ``mpv`` on a private Gamescope Xwayland lease and
   records the verified window for a 30 s marker interval;
6. cleans up recorder, client, then display, and evaluates every criterion.

The verdict is PASS, FAIL, or ``calibration_ambiguous``. The last means the
per-frame differences did not separate cleanly around the calibrated noise
floor, so the content result cannot be attributed to capture; it is used only
when the level sequence and every non-content criterion passed. Otherwise any
failed criterion gives FAIL, and ``failing_criteria`` lists each one. There is no
automatic retry. Any failed criterion exits nonzero and keeps all
evidence in the run directory.
"""
from __future__ import annotations

import argparse
import datetime
import fcntl
import hashlib
import json
import os
import re
import secrets
import signal
import stat
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import display_backends as D
from .creative_accept import (append_commitment_line, cleanup_state_clear, initialize_cleanup_ledger,
                              validate_commitment_log)
from .display_backends import CADENCE_POLICY, CONTENT_POLICIES
from .gamescope_snapshot import DEFAULT_ENTRIES, MANIFEST, create_snapshot, verify_snapshot
from .recording import FORBIDDEN_X11_STARTUP, probe_deadline_seconds, probe_tool_identity

WIDTH, HEIGHT, FPS = 1024, 768, 60
LEAD_SECONDS, ACCEPTANCE_SECONDS, TAIL_SECONDS = 3.0, 30.0, 1.0
WINDOW_DISCOVERY_SECONDS = 10.0
CLIENT = '/usr/bin/mpv'
CLIENT_TITLE = 'kp-diag-testsrc2'
# The diagnostic pattern. testsrc2 alone changes little per frame when it moves
# slowly (R11-C1: a quarter-speed testsrc2 had fresh frames at 0.84 DIF). The eq
# step compresses testsrc2 to 40% contrast and adds a full-frame brightness
# level that changes on every output frame: level(n) = (3n mod 7) - 3, seven
# levels 0.11 apart. Any two frames 1 to 6 frames apart differ by at least one
# level across the whole frame; adjacent frames by at least three. Only a skip of
# exactly 7 frames (117 ms) repeats a level, and the cadence gate's 50 ms maximum
# gap (3 frame intervals) rejects such a capture. The expression has no comma,
# so it needs no filtergraph escaping inside mpv's ``av://lavfi:`` URL. mpv and
# FFmpeg link the same libavfilter on the host.
PATTERN_PERIOD_FRAMES = 7
PATTERN_LEVEL_STEP = 0.11
PATTERN_STEP = ('eq=contrast=0.4:brightness=(3*n-7*floor(3*n/7)-3)*%s:eval=frame' % PATTERN_LEVEL_STEP)
PATTERN_GRAPH = f'testsrc2=size={WIDTH}x{HEIGHT}:rate={FPS},{PATTERN_STEP}'
DEFAULT_FFMPEG = '/usr/bin/ffmpeg'
# FFprobe has no default: the operator passes ``--ffprobe``, a native ELF recorded by path and SHA-256.
CONTENT_POLICY = 'animated-diagnostic-v2'
MARKERS = {'pattern_start': r'\[kp-diag\] pattern_start', 'pattern_end': r'\[kp-diag\] pattern_end'}
MARKER_LINES = {'pattern_start': '[kp-diag] pattern_start', 'pattern_end': '[kp-diag] pattern_end'}
FORBIDDEN_NAMES = ('wineserver', 'swkotor', 'gamescope', 'ffmpeg', 'ffprobe')
# A wrapped target (``bash ~/.local/bin/ffmpeg``) shows its real name only in
# the first script argument after one of these launchers.
WRAPPER_NAMES = ('sh', 'bash', 'dash', 'zsh', 'env', 'nice', 'ionice', 'nohup', 'setsid',
                 'exec', 'python', 'python3', 'perl')
# The dynamic loader run as a program (``/lib64/ld-linux-x86-64.so.2 /usr/bin/ffmpeg``):
# comm, exe, and argv[0] name the loader, and the loaded program is its first
# non-option argument. comm is cut to 15 characters (``ld-linux-x86-64``).
LOADER_NAME = re.compile(r'ld-linux[\w.-]*|ld\.so(\.[0-9]+)*|ld-[0-9.]+\.so')
# glibc ld.so options that take a value; every other ``--`` option is a flag.
LOADER_OPTIONS_WITH_VALUE = ('--library-path', '--inhibit-rpath', '--audit', '--preload', '--argv0',
                             '--glibc-hwcaps-prepend', '--glibc-hwcaps-mask')
PROTECTED_DISPLAYS = (0, 94, 100)
CLEANUP_ORDER = ('recorder', 'source_process', 'display')
SNAPSHOT_ENTRIES = tuple(DEFAULT_ENTRIES) + ('kpharness.capture_diagnostic',)
COMMITMENT_KIND = 'kpharness.capture-diagnostic-commitments.v1'
RESULT_KIND = 'kpharness.capture-diagnostic-result.v1'
OWNED_FILE = 'diagnostic-owned.json'
INTERRUPT_SIGNALS = (signal.SIGINT, signal.SIGHUP, signal.SIGTERM)
# Ordered-cleanup budget after an interrupt, from the components' own bounds.
_DIAGNOSTIC_FRAMES = int((WINDOW_DISCOVERY_SECONDS + LEAD_SECONDS + ACCEPTANCE_SECONDS + TAIL_SECONDS + 10) * FPS)
CLEANUP_BUDGET_COMPONENTS = {
    # thread join 2 + four xwininfo queries x 5 + FFmpeg SIGINT 15 + SIGKILL 5 + PTS and content probes
    'recorder': 2 + 4 * 5 + 15 + 5 + 2 * probe_deadline_seconds(_DIAGNOSTIC_FRAMES),
    'source_process': 2 + 2,
    # Gamescope group SIGTERM 5 + SIGKILL 5 + leader reap 5 + socket cleanup margin 10
    'display': 5 + 5 + 5 + 10,
    'evidence_margin': 15,
}
CLEANUP_BUDGET_SECONDS = float(sum(CLEANUP_BUDGET_COMPONENTS.values()))
# Everything the child legitimately runs before its cleanup starts.
CHILD_PRE_CLEANUP_COMPONENTS = {
    # Gamescope readiness deadline 20 + its xwininfo/xprop queries 5 + 10
    'lease_start': 20 + 5 + 10,
    'window_discovery': WINDOW_DISCOVERY_SECONDS,
    # recorder startup admission 5 + two geometry reads (two xwininfo queries x 5 each)
    'recorder_start': 5 + 4 * 5,
    'lead': LEAD_SECONDS, 'acceptance': ACCEPTANCE_SECONDS, 'tail': TAIL_SECONDS,
    'margin': 30,
}
# An uninterrupted run ends with the same ordered cleanup, including both
# frame-scaled FFprobe probes, so its bound includes the full cleanup budget.
CHILD_RUN_SECONDS = float(sum(CHILD_PRE_CLEANUP_COMPONENTS.values())) + CLEANUP_BUDGET_SECONDS
CRITERIA = ('no_shm_fallback', 'first_frame_admission', 'exact_geometry', 'content_gate',
            'canonical_pts_binding', 'rate_at_least_99_percent',
            'missing_or_dropped_at_most_half_percent', 'maximum_gap_50ms', 'zero_ffmpeg_duplicates',
            'cadence_evidence_recomputed', 'acceptance_interval_matches_route', 'cleanup_complete',
            'no_owned_survivors', 'ledger_clear', 'protected_displays_unchanged',
            'media_sha256_recorded', 'snapshot_unchanged', 'no_driver_error')
# Criteria that fail with the content result itself. cadence_evidence_recomputed
# also fails then (the recorder folds content failures into the cadence status),
# so the verdict judges it with content aside (``_cadence_recomputed_apart_from_content``).
CONTENT_CRITERIA = ('content_gate', 'cadence_evidence_recomputed')


class DiagnosticRefused(RuntimeError):
    """A precondition failed before the single launch; evidence is retained."""


class DiagnosticInterrupted(BaseException):
    """SIGINT, SIGHUP, or SIGTERM arrived; ordered cleanup runs before exit."""


def _utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + '\n')


def client_command() -> list[str]:
    # mpv sets _NET_WM_PID (glxgears and vkcube do not) and keeps a fixed title.
    return [CLIENT, '--no-config', '--really-quiet', '--terminal=no', '--vo=gpu', '--ao=null',
            '--osc=no', '--osd-level=0', '--input-default-bindings=no', '--border=no',
            f'--geometry={WIDTH}x{HEIGHT}+0+0', '--keepaspect-window=no', f'--title={CLIENT_TITLE}',
            '--force-window=immediate', '--loop-file=inf',
            'av://lavfi:' + PATTERN_GRAPH]


def route_document(ffmpeg: str) -> dict:
    return {'schema': 1, 'kind': 'kpharness.capture-diagnostic-route.v1',
            'pattern': {'source': 'lavfi testsrc2 with a per-frame full-frame luma step',
                        'graph': PATTERN_GRAPH, 'size': [WIDTH, HEIGHT], 'rate': FPS,
                        'step': {'filter': PATTERN_STEP, 'period_frames': PATTERN_PERIOD_FRAMES,
                                 'level_step_brightness': PATTERN_LEVEL_STEP},
                        'changes_every_frame': True},
            'client': client_command(), 'markers': dict(MARKERS), 'marker_lines': dict(MARKER_LINES),
            'acceptance_pair': ['pattern_start', 'pattern_end'],
            'durations': {'lead_seconds': LEAD_SECONDS, 'acceptance_seconds': ACCEPTANCE_SECONDS,
                          'tail_seconds': TAIL_SECONDS},
            'geometry': [WIDTH, HEIGHT], 'capture': {'target': 'window', 'ffmpeg': ffmpeg},
            'content_policy': dict(CONTENT_POLICIES[CONTENT_POLICY]),
            'cadence_policy': dict(CADENCE_POLICY)}


# -- process preflight --------------------------------------------------------

def _exe_sha256(descriptor: int) -> str:
    digest = hashlib.sha256()
    while block := os.read(descriptor, 1024 * 1024):
        digest.update(block)
    return digest.hexdigest()


def _tool_index(tools) -> list[dict]:
    """(role, sha256, size, dev, ino) of each configured tool ELF, in the configured order."""
    index = []
    for tool in tools or ():
        info = os.stat(tool['resolved_path'])
        index.append({'role': tool.get('role', Path(tool['resolved_path']).name), 'sha256': tool['sha256'],
                      'size': info.st_size, 'dev': info.st_dev, 'ino': info.st_ino})
    return index


def _match_exe(entry: Path, index: list[dict], cache: dict, *, path: Path | None = None,
               prefix: str = 'exe') -> dict:
    """Compare one process's executable (or ``path``) with the configured tools by inode, then size and SHA-256."""
    unreadable = 'exe_identity_unreadable' if prefix == 'exe' else f'{prefix}_program_unreadable'
    try:
        descriptor = os.open(entry / 'exe' if path is None else path, os.O_RDONLY)
    except OSError as error:
        return {unreadable: f'{type(error).__name__}: {error}'}
    try:
        info = os.fstat(descriptor)
        for tool in index:
            if (info.st_dev, info.st_ino) == (tool['dev'], tool['ino']):
                return {f'{prefix}_tool_match': tool['role'], f'{prefix}_match_by': 'inode'}
        candidates = [tool for tool in index if tool['size'] == info.st_size]
        if not candidates or not stat.S_ISREG(info.st_mode):
            return {}
        key = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if key not in cache:
            cache[key] = _exe_sha256(descriptor)
        for tool in candidates:
            if cache[key] == tool['sha256']:
                return {f'{prefix}_tool_match': tool['role'], f'{prefix}_match_by': 'sha256',
                        f'{prefix}_sha256': cache[key]}
        return {}
    except OSError as error:
        return {unreadable: f'{type(error).__name__}: {error}'}
    finally:
        os.close(descriptor)


def _is_loader(name: object) -> bool:
    return isinstance(name, str) and LOADER_NAME.fullmatch(Path(name).name.lower()) is not None


def loader_program(row: dict) -> str | None:
    """The program a dynamic-loader launch runs, or None when the row is not a loader launch."""
    argv = row.get('argv') or []
    if not (_is_loader(row.get('comm')) or _is_loader(row.get('exe')) or (argv and _is_loader(argv[0]))):
        return None
    position = 1
    while position < len(argv):
        item = argv[position]
        if item in LOADER_OPTIONS_WITH_VALUE:
            position += 2
        elif item.startswith('--'):
            position += 1
        else:
            return item or None
    return None


def process_inventory(proc_root: Path = Path('/proc'), *, uid: int | None = None, tools=None) -> list[dict]:
    """Inventory every /proc row. A row whose comm, stat, or cmdline cannot be read is kept as unreadable.

    With ``tools`` (configured FFmpeg/FFprobe identities), each readable
    executable of this uid is also compared with them by inode, then by size and
    SHA-256, so a renamed copy is found by content, not only by name. A
    dynamic-loader launch records its program argument (``loader_program``), and
    that file (relative paths resolve against ``/proc/PID/cwd``) is compared the
    same way.
    """
    uid = os.getuid() if uid is None else uid
    index = _tool_index(tools)
    cache: dict = {}
    rows = []
    for entry in Path(proc_root).iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            owner = os.stat(entry).st_uid
        except (FileNotFoundError, ProcessLookupError):
            continue  # exited during the scan
        except OSError as error:
            rows.append({'pid': int(entry.name), 'uid': None, 'unreadable': f'{type(error).__name__}: {error}'})
            continue
        row = {'pid': int(entry.name), 'uid': owner}
        try:
            row['comm'] = (entry / 'comm').read_text().strip()
            raw = (entry / 'stat').read_text()
            row['start'] = raw[raw.rindex(')') + 1:].split()[19]
            argv = (entry / 'cmdline').read_bytes().decode(errors='replace').rstrip('\0').split('\0')
        except (FileNotFoundError, ProcessLookupError):
            if not entry.exists():
                continue  # exited during the scan
            row['unreadable'] = 'FileNotFoundError: /proc entry file missing'
            rows.append(row)
            continue
        except (OSError, ValueError, IndexError) as error:
            row['unreadable'] = f'{type(error).__name__}: {error}'
            rows.append(row)
            continue
        try:
            exe = os.readlink(entry / 'exe')
            row['exe'] = exe[:-len(' (deleted)')] if exe.endswith(' (deleted)') else exe
        except (FileNotFoundError, ProcessLookupError):
            row['exe'] = None  # zombie, kernel thread, or exited
        except OSError as error:
            # The kernel hides exe of non-dumpable processes (kwin_wayland, ssh-agent)
            # even from their own user. comm and argv still classify the row.
            row['exe'] = None
            row['exe_unreadable'] = f'{type(error).__name__}: {error}'
        # Never retain an authority path.
        row['argv'] = ['<authority-path-redacted>' if position and argv[position - 1] == '-auth' else item
                       for position, item in enumerate(argv)]
        program = loader_program(row)
        if program is not None:
            row['loader_program'] = program
        if index and owner == uid:
            row.update(_match_exe(entry, index, cache))
            if program is not None:
                path = Path(program) if Path(program).is_absolute() else entry / 'cwd' / program
                row.update(_match_exe(entry, index, cache, path=path, prefix='loader'))
        rows.append(row)
    return sorted(rows, key=lambda row: row['pid'])


def _target_names(row: dict) -> set[str]:
    argv = row.get('argv') or []
    names = {str(row.get('comm', '')).lower()}
    if row.get('exe'):
        names.add(Path(row['exe']).name.lower())
    if row.get('loader_program'):
        names.add(Path(row['loader_program']).name.lower())
    if argv:
        names.add(Path(argv[0]).name.lower())
        launcher = Path(argv[0]).name.lower()
        if launcher in WRAPPER_NAMES or re.fullmatch(r'python3(\.[0-9]+)?', launcher):
            script = next((item for item in argv[1:] if item and not item.startswith('-') and '=' not in item),
                          None)
            if script is not None:
                names.add(Path(script).name.lower())
    return names


def _launch_chain(proc_root: Path, pid: int) -> set[int]:
    """This process and its ancestors: the operator's own launch, never a target."""
    chain = set()
    while pid > 1 and pid not in chain:
        chain.add(pid)
        try:
            raw = (Path(proc_root) / str(pid) / 'stat').read_text()
            pid = int(raw[raw.rindex(')') + 1:].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return chain


def forbidden_processes(rows: list[dict], owned: frozenset | set = frozenset(), *,
                        exclude: frozenset | set = frozenset()) -> list[dict]:
    blocked = []
    for row in rows:
        if row['pid'] in exclude or 'unreadable' in row:
            continue
        if ((row.get('exe_tool_match') or row.get('loader_tool_match')
             or any(name.startswith(prefix) for name in _target_names(row) for prefix in FORBIDDEN_NAMES))
                and (row['pid'], row['start']) not in owned):
            blocked.append(row)
    return blocked


def unreadable_processes(rows: list[dict], *, uid: int | None = None,
                         exclude: frozenset | set = frozenset()) -> list[dict]:
    uid = os.getuid() if uid is None else uid
    return [row for row in rows if 'unreadable' in row and row['pid'] not in exclude
            and row.get('uid') in (uid, None)]


def preflight(proc_root: Path, run_dir: Path, *, self_pid: int | None = None, tools=None) -> dict:
    """Refuse on any target process or any unreadable row of this uid. Nothing is ever signalled."""
    rows = process_inventory(proc_root, tools=tools)
    exclude = _launch_chain(proc_root, os.getpid() if self_pid is None else self_pid)
    forbidden = forbidden_processes(rows, exclude=exclude)
    unreadable = unreadable_processes(rows, exclude=exclude)
    evidence = {'utc': _utc(), 'forbidden_names': list(FORBIDDEN_NAMES),
                'tool_identities': [{'role': tool.get('role'), 'resolved_path': tool.get('resolved_path'),
                                     'sha256': tool.get('sha256')} for tool in tools or ()],
                'forbidden': forbidden,
                'unreadable': unreadable, 'launch_chain_excluded': sorted(exclude),
                'refused': bool(forbidden or unreadable)}
    _write(Path(run_dir) / 'preflight.json', evidence)
    if forbidden:
        raise DiagnosticRefused('preflight found existing Wine, game, Gamescope, or FFmpeg processes')
    if unreadable:
        raise DiagnosticRefused('preflight could not read every /proc entry of this user')
    return evidence


def protected_displays(root: Path = Path('/tmp')) -> dict:
    result = {}
    for number in PROTECTED_DISPLAYS:
        entry = {}
        for name, path in (('socket', root / '.X11-unix' / f'X{number}'), ('lock', root / f'.X{number}-lock')):
            try:
                info = os.lstat(path)
                entry[name] = {'exists': True, 'dev': info.st_dev, 'ino': info.st_ino,
                               'mode': info.st_mode, 'uid': info.st_uid, 'mtime_ns': info.st_mtime_ns}
            except FileNotFoundError:
                entry[name] = {'exists': False}
        result[str(number)] = entry
    return result


def process_alive(pid: int, start: str) -> bool:
    try:
        raw = Path(f'/proc/{pid}/stat').read_text()
        fields = raw[raw.rindex(')') + 1:].split()
        # A zombie is exited; only its parent's reap remains.
        return fields[19] == start and fields[0] != 'Z'
    except (OSError, ValueError, IndexError):
        return False


def kill_owned_identity(identity: dict) -> bool:
    """SIGKILL one recorded owned process through a pidfd, only if its start still matches."""
    pid, start = identity.get('pid'), identity.get('start')
    if type(pid) is not int or pid <= 1 or not isinstance(start, str) or not start:
        return False
    open_pidfd = getattr(os, 'pidfd_open', None)
    send = getattr(signal, 'pidfd_send_signal', None)
    if open_pidfd is None or send is None:
        return False
    try:
        descriptor = open_pidfd(pid, 0)
    except (ProcessLookupError, FileNotFoundError):
        return True
    except OSError:
        return False
    try:
        if not process_alive(pid, start):
            return True  # PID reused or exited: never signal a process we do not own
        send(descriptor, signal.SIGKILL, None, 0)
        return True
    except ProcessLookupError:
        return True
    except OSError:
        return False
    finally:
        os.close(descriptor)


# -- lock and tools ------------------------------------------------------------

def canonical_lock_path() -> Path:
    from .creative import shared_lock_path
    return shared_lock_path(Path(__file__).resolve().parents[3])


def acquire_lock(path: Path) -> int:
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise DiagnosticRefused('canonical lock is not a regular file')
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        os.close(descriptor)
        raise DiagnosticRefused('another live harness holds the canonical lock') from error
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def native_elf_identity(command: str) -> dict:
    """Refuse wrappers: the configured tool must resolve to one native ELF file."""
    path = Path(command)
    if not path.is_absolute():
        raise DiagnosticRefused('capture tools must be configured by absolute path')
    try:
        resolved = path.resolve(strict=True)
        descriptor = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise DiagnosticRefused(f'capture tool is missing: {command}') from error
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o111
                or os.pread(descriptor, 4, 0) != b'\x7fELF'):
            raise DiagnosticRefused(f'capture tool is not a native executable ELF file: {command}')
        digest = hashlib.sha256()
        while block := os.read(descriptor, 1024 * 1024):
            digest.update(block)
    finally:
        os.close(descriptor)
    return {'command': command, 'resolved_path': str(resolved), 'sha256': digest.hexdigest()}


def with_inherited_descriptor(popen: Callable, descriptor: int) -> Callable:
    """Every child keeps the lock descriptor, so the lock outlives no owned process."""
    def launch(command, **kwargs):
        kwargs['pass_fds'] = tuple(sorted(set(kwargs.get('pass_fds', ())) | {descriptor}))
        return popen(command, **kwargs)
    return launch


# -- cleanup --------------------------------------------------------------------

def ordered_cleanup(steps) -> dict:
    """Attempt every component in order; one failure never skips a later component."""
    result = {'order': [], 'errors': {}}
    for name, operation in steps:
        result['order'].append(name)
        if operation is None:
            result[name] = 'not_started'
            continue
        try:
            operation()
            result[name] = 'passed'
        except BaseException as error:
            result[name] = 'failed'
            result['errors'][name] = f'{type(error).__name__}: {error}'
    result['status'] = ('passed' if result['order'] == list(CLEANUP_ORDER)
                        and all(result[name] == 'passed' for name in CLEANUP_ORDER) else 'failed')
    return result


def stop_client(process) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError('diagnostic client survived SIGKILL wait') from error


# -- child ----------------------------------------------------------------------

def child_config(run_dir: Path, *, ffmpeg: str, ffprobe: str, lock_fd: int,
                 token_fd: int | None = None, token_sha256: str | None = None) -> dict:
    run_dir = Path(run_dir)
    return {'run_dir': str(run_dir), 'ffmpeg': ffmpeg, 'ffprobe': ffprobe, 'lock_fd': lock_fd,
            'token_fd': token_fd, 'token_sha256': token_sha256,
            'native_log': str(run_dir / 'diagnostic-native.log'), 'geometry': [WIDTH, HEIGHT]}


def create_child_token() -> tuple[int, str]:
    """A nonce only the supervisor holds, delivered to the child on an inherited pipe."""
    token = secrets.token_hex(32)
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, token.encode())
    finally:
        os.close(write_fd)
    return read_fd, hashlib.sha256(token.encode()).hexdigest()


def trusted_lock_path(repository_root: Path | None = None) -> Path:
    """The canonical lock of the repository this code belongs to; never from the environment."""
    from .gamescope_socket import canonical_lock_path_for, trusted_repository_root
    root = trusted_repository_root(__file__) if repository_root is None else Path(repository_root)
    return canonical_lock_path_for(root)


def verify_child_authority(config: dict, *, lock_guard=None, repository_root: Path | None = None) -> dict:
    """Refuse a ``--child`` start that did not come from the supervisor holding the lock.

    The lock check uses the descriptor the supervisor passed (``lock_fd``): it
    must be the file at the trusted canonical lock path (same device and inode)
    and hold its exclusive flock. The path comes from this code's own location
    (a verified snapshot manifest's ``repository_root``, or the checkout),
    never from ``KP_GAMESCOPE_REPO_ROOT``. A same-uid process that really holds
    the canonical lock is inside the trust boundary.
    """
    token_fd, expected = config.get('token_fd'), config.get('token_sha256')
    if type(token_fd) is not int or token_fd < 3 or not isinstance(expected, str) \
            or re.fullmatch(r'[0-9a-f]{64}', expected) is None:
        raise DiagnosticRefused('child start lacks the supervisor token descriptor')
    try:
        if not stat.S_ISFIFO(os.fstat(token_fd).st_mode):
            raise DiagnosticRefused('child token descriptor is not the supervisor pipe')
        token = b''
        while len(token) <= 64 and (block := os.read(token_fd, 65 - len(token))):
            token += block
    except OSError as error:
        raise DiagnosticRefused('child token descriptor is unreadable') from error
    finally:
        try:
            os.close(token_fd)
        except OSError:
            pass
    run_dir = Path(config['run_dir'])
    try:
        committed = json.loads((run_dir / 'commitments.json').read_text()).get('child_token_sha256')
    except (OSError, ValueError, AttributeError) as error:
        raise DiagnosticRefused('child start has no supervisor commitments') from error
    digest = hashlib.sha256(token).hexdigest()
    if len(token) != 64 or digest != expected or digest != committed:
        raise DiagnosticRefused('child token does not match the supervisor commitment')
    if lock_guard is None:
        from .gamescope_socket import held_lock_descriptor
        lock_fd = config.get('lock_fd')
        if type(lock_fd) is not int or lock_fd < 0:
            raise DiagnosticRefused('child config has no canonical lock descriptor')
        def lock_guard():
            return held_lock_descriptor(lock_fd, trusted_lock_path(repository_root))
    try:
        held = lock_guard()
    except (OSError, RuntimeError, ValueError) as error:
        raise DiagnosticRefused(f'child does not hold the canonical lock: {error}') from error
    if not isinstance(held, dict) or held.get('fd') != config.get('lock_fd'):
        raise DiagnosticRefused('child lock descriptor is not the held canonical lock')
    return held


def record_owned(run_dir: Path, role: str, pid: object, start: object) -> None:
    """Keep the owned-process list current on disk, so a killed child still names its processes."""
    if type(pid) is not int or not isinstance(start, str) or not start:
        return
    path = Path(run_dir) / OWNED_FILE
    try:
        owned = json.loads(path.read_text()) if path.exists() else []
    except (OSError, ValueError):
        owned = []
    owned.append({'role': role, 'pid': pid, 'start': start})
    temporary = path.with_name('.' + path.name + '.tmp')
    temporary.write_text(json.dumps(owned, sort_keys=True) + '\n')
    os.replace(temporary, path)


def _record_lease_owned(run_dir: Path, lease) -> None:
    try:
        receipt = lease.receipt()
    except Exception:  # evidence only; cleanup never depends on it
        return
    for identity in _owned_identities({'lease': receipt}):
        record_owned(run_dir, identity.get('role', 'display'), identity.get('pid'), identity.get('start'))


class _ChildSignals:
    """First interrupt aborts the run; later ones never abort the ordered cleanup."""
    def __init__(self):
        self.received: list[str] = []
        self.cleaning = False
        self.previous = {}

    def handler(self, signum, frame):
        self.received.append(signal.Signals(signum).name)
        if not self.cleaning and len(self.received) == 1:
            raise DiagnosticInterrupted(signal.Signals(signum).name)

    def install(self):
        for number in INTERRUPT_SIGNALS:
            self.previous[number] = signal.signal(number, self.handler)

    @staticmethod
    def unblock():
        """The supervisor spawns this child with the interrupt set blocked; a held signal arrives here."""
        signal.pthread_sigmask(signal.SIG_UNBLOCK, INTERRUPT_SIGNALS)

    def restore(self):
        for number, previous in self.previous.items():
            signal.signal(number, previous)


def _append_marker(path: Path, name: str) -> None:
    with path.open('a') as stream:
        stream.write(MARKER_LINES[name] + '\n'); stream.flush(); os.fsync(stream.fileno())


def _wait_for_window(lease, pid: int, discover, run, monotonic, sleep):
    deadline = monotonic() + WINDOW_DISCOVERY_SECONDS
    while True:
        try:
            return discover(lease, [pid], run=run, monotonic=monotonic)
        except RuntimeError:
            if monotonic() >= deadline:
                raise
            sleep(.25)


def run_child(config: dict, *, lease_factory, popen, discover, verifier_factory, recorder_factory,
              sleep, monotonic, start_reader, run=subprocess.run) -> dict:
    run_dir = Path(config['run_dir'])
    # Every child of this process inherits the lock: lease, client, FFmpeg,
    # both FFprobe probes, and every xwininfo query.
    locked = with_inherited_descriptor(popen, config['lock_fd'])
    locked_run = with_inherited_descriptor(run, config['lock_fd'])
    native_log = Path(config['native_log'])
    native_log.write_text('')
    evidence = {'utc_started': _utc(), 'config': dict(config), 'error': None, 'client': None,
                'window': None, 'lease': None, 'recorder': None, 'cleanup': None, 'interrupts': []}
    lease = recorder = client = client_log = None
    signals = _ChildSignals()
    signals.install()
    try:
        try:
            # Handlers first, then unblock: a signal held since the spawn raises
            # here, inside the ordered-cleanup scope, and nothing started yet
            # (lease, client, FFmpeg) inherits a blocked interrupt set.
            signals.unblock()
            lease = lease_factory(run_dir, WIDTH, HEIGHT, popen=locked)
            lease.start()
            _record_lease_owned(run_dir, lease)
            client_log = (run_dir / 'client.log').open('xb')
            client = locked(client_command(), env=dict(lease.game_environment({'PATH': '/usr/bin:/bin'})),
                            stdout=client_log, stderr=subprocess.STDOUT, start_new_session=True)
            evidence['client'] = {'pid': client.pid, 'start': start_reader(client.pid)}
            record_owned(run_dir, 'client', client.pid, evidence['client']['start'])
            window = _wait_for_window(lease, client.pid, discover, locked_run, monotonic, sleep)
            evidence['window'] = window.receipt()
            verifier = verifier_factory(lease, run=locked_run)
            recorder = recorder_factory(run_dir, verifier=verifier, lease=lease, ffmpeg=config['ffmpeg'],
                ffprobe=config['ffprobe'], named_markers=dict(MARKERS),
                cadence_start_marker='pattern_start', cadence_end_marker='pattern_end',
                content_policy=CONTENT_POLICY, popen=locked, run=locked_run,
                inherited_fds=(config['lock_fd'],))
            recorder.start(window, native_log)
            process = getattr(recorder, 'process', None)
            if process is not None and type(getattr(process, 'pid', None)) is int:
                record_owned(run_dir, 'recorder', process.pid, start_reader(process.pid))
            sleep(LEAD_SECONDS)
            _append_marker(native_log, 'pattern_start')
            sleep(ACCEPTANCE_SECONDS)
            _append_marker(native_log, 'pattern_end')
            sleep(TAIL_SECONDS)
            recorder.check()
        except BaseException as error:
            evidence['error'] = f'{type(error).__name__}: {error}'
        finally:
            # Later interrupts are recorded but never abort the ordered cleanup.
            signals.cleaning = True
            evidence['cleanup'] = ordered_cleanup([
                ('recorder', None if recorder is None else recorder.stop),
                ('source_process', None if client is None else (lambda: stop_client(client))),
                ('display', None if lease is None else lease.close)])
            if client_log is not None:
                client_log.close()
            try:
                evidence['recorder'] = None if recorder is None else recorder.receipt()
                evidence['lease'] = None if lease is None else lease.receipt()
            except BaseException as error:
                evidence['error'] = evidence['error'] or f'evidence: {type(error).__name__}: {error}'
            evidence['interrupts'] = list(signals.received)
            evidence['utc_finished'] = _utc()
            _write(run_dir / 'diagnostic-run.json', evidence)
    finally:
        signals.restore()
    return evidence


def _child_main(config_path: str) -> int:
    """Supervisor-started child only; refuses without the token pipe and the held lock."""
    from .display_backends import OwnedWindowVerifier, discover_owned_x11_window, process_start
    from .gamescope_xwayland import GamescopeXwaylandLease
    from .recording import X11WindowRecorder
    config = json.loads(Path(config_path).read_text())
    verify_child_authority(config)
    # Every later lock check in this child (socket cleanup, discovery) uses the
    # trusted root, whatever the inherited environment said.
    from .gamescope_socket import trusted_repository_root
    os.environ['KP_GAMESCOPE_REPO_ROOT'] = str(trusted_repository_root(__file__))
    evidence = run_child(config, lease_factory=GamescopeXwaylandLease, popen=subprocess.Popen,
                         discover=discover_owned_x11_window, verifier_factory=OwnedWindowVerifier,
                         recorder_factory=X11WindowRecorder, sleep=time.sleep,
                         monotonic=time.monotonic, start_reader=process_start)
    return 0 if evidence['error'] is None and evidence['cleanup']['status'] == 'passed' else 1


# -- evaluation -----------------------------------------------------------------

def _acceptance_interval(cadence: dict) -> dict:
    pair = cadence['acceptance_interval']
    matching = [item for item in cadence['intervals']
                if item.get('start_marker') == pair['start_marker'] and item.get('end_marker') == pair['end_marker']]
    if len(matching) != 1:
        raise ValueError('acceptance interval is not unique')
    return matching[0]


def evaluate(observation: dict) -> dict:
    """Evaluate each pass criterion from the recorded evidence, independently."""
    recorder = observation.get('recorder') or {}
    capture = recorder.get('capture') or {}
    cadence = recorder.get('cadence') or {}
    media = (recorder.get('media') or {}).get('continuous') or {}
    window = observation.get('window') or {}
    lease = observation.get('lease') or {}
    log = observation.get('ffmpeg_log') or ''

    def check(predicate) -> bool:
        try:
            return bool(predicate())
        except (KeyError, TypeError, ValueError, AttributeError, IndexError, ZeroDivisionError):
            return False

    canonical = D._canonical_pts(cadence.get('pts_artifact'), media, cadence.get('probe_tool')) \
        if cadence and media else None
    interval = check(lambda: _acceptance_interval(cadence)) and _acceptance_interval(cadence)
    policy = dict(CONTENT_POLICIES[CONTENT_POLICY])
    criteria = {
        'no_shm_fallback': check(lambda: not any(token.decode() in log for token in FORBIDDEN_X11_STARTUP)
            and capture['startup']['shm']['status'] == 'no_fallback_observed'
            and not capture['startup']['shm']['forbidden_matches']),
        'first_frame_admission': check(lambda: capture['startup']['status'] == 'passed'
            and type(capture['startup']['first_frame']) is int and capture['startup']['first_frame'] >= 1
            and capture['status'] == 'passed' and recorder.get('failure') is None),
        'exact_geometry': check(lambda: D._geometry_evidence_matches(capture['geometry_precondition'],
                window_id=window['id'], width=WIDTH, height=HEIGHT)
            and capture['command'][capture['command'].index('-window_id') + 1] == window['id']
            and [lease['width'], lease['height']] == [WIDTH, HEIGHT]),
        'content_gate': check(lambda: cadence['content']['policy'] == policy
            and cadence['content']['status'] == 'passed'
            and cadence['content']['acceptance']['distinct_ratio'] >= policy['minimum_distinct_ratio']
            and canonical is not None
            and D._content_evidence_passed(cadence, media, canonical, interval)),
        'canonical_pts_binding': check(lambda: canonical is not None
            and cadence['pts_artifact']['master_sha256'] == media['sha256'] == observation['media_sha256']),
        'rate_at_least_99_percent': check(lambda: float(interval['effective_fps'])
            >= FPS * CADENCE_POLICY['minimum_rate_ratio']),
        'missing_or_dropped_at_most_half_percent': check(lambda: float(interval['missing_or_dropped_ratio'])
            <= CADENCE_POLICY['maximum_drop_ratio']),
        'maximum_gap_50ms': check(lambda: float(interval['maximum_gap_seconds'])
            <= CADENCE_POLICY['maximum_gap_seconds']),
        'zero_ffmpeg_duplicates': check(lambda: capture['diagnostics']['terminal']['dup_frames'] == 0
            and cadence['terminal_progress']['dup_frames'] == 0 and interval['ffmpeg']['dup_frames'] == 0),
        'cadence_evidence_recomputed': check(lambda: D._cadence_evidence_passed(cadence, capture, media, {})
            and D._window_capture_matches(capture, lease_id=lease['lease_id'], xdisplay=lease['display'],
                                          width=WIDTH, height=HEIGHT, window=window)),
        'acceptance_interval_matches_route': check(lambda: [interval['start_marker'], interval['end_marker']]
            == observation['route']['acceptance_pair']
            and float(interval['span_seconds']) >= .9 * float(observation['route']['acceptance_seconds'])),
        'cleanup_complete': check(lambda: observation['cleanup']['status'] == 'passed'
            and observation['cleanup']['order'] == list(CLEANUP_ORDER)
            and all(observation['cleanup'][name] == 'passed' for name in CLEANUP_ORDER)),
        'no_owned_survivors': check(lambda: observation['owned_survivors'] == []),
        'ledger_clear': observation.get('ledger_clear') is True,
        'protected_displays_unchanged': check(lambda: observation['protected_before'] is not None
            and observation['protected_before'] == observation['protected_after']),
        'media_sha256_recorded': check(lambda: re.fullmatch(r'[0-9a-f]{64}', observation['media_sha256'])
            is not None and observation['media_sha256'] == media['sha256']),
        'snapshot_unchanged': observation.get('snapshot_unchanged') is True,
        'no_driver_error': 'error' in observation and observation['error'] is None,
    }
    failing = [name for name in CRITERIA if not criteria[name]]
    content = content_recomputation(cadence, media, canonical, interval)
    separation = content.get('separation') if content else None
    sequence = content.get('level_sequence') if content else None
    cadence_apart = check(lambda: _cadence_recomputed_apart_from_content(cadence, capture, media, lease, window))
    non_content = [name for name in failing if name not in CONTENT_CRITERIA]
    if 'cadence_evidence_recomputed' in failing and not cadence_apart:
        non_content.append('cadence_evidence_recomputed')
    # The per-frame differences do not separate around the calibrated floor, and
    # that is the only problem: the content failures are all calibration_ambiguous
    # (the level sequence passed) and every non-content criterion passed.
    only_ambiguous = bool(content and isinstance(separation, dict) and separation.get('status') == 'ambiguous'
                          and content.get('failures')
                          and all(str(item).startswith('calibration_ambiguous') for item in content['failures']))
    if not failing:
        verdict = 'PASS'
    elif only_ambiguous and not non_content:
        verdict = 'calibration_ambiguous'
    else:
        verdict = 'FAIL'
    return {'criteria': criteria, 'verdict': verdict, 'failing_criteria': failing,
            'content_separation': separation, 'content_level_sequence': sequence,
            'cadence_recomputed_apart_from_content': cadence_apart}


def _cadence_recomputed_apart_from_content(cadence, capture, media, lease, window) -> bool:
    """The cadence recomputation as if the content gate had passed: the cadence status
    counts only the recorded failures that are not content failures."""
    content_failures = set(cadence['content']['failures'])
    others = [item for item in cadence['failures'] if item not in content_failures]
    if others:
        return False
    aside = {**cadence, 'status': 'passed', 'failures': []}
    return bool(D._cadence_evidence_passed(aside, capture, media, {}, content_aside=True)
                and D._window_capture_matches(capture, lease_id=lease['lease_id'], xdisplay=lease['display'],
                                              width=WIDTH, height=HEIGHT, window=window))


def content_recomputation(cadence, media, canonical, interval) -> dict | None:
    """The content block recomputed from the hashed artifact under the diagnostic policy, never taken
    from the receipt; None when the artifact cannot be recomputed."""
    try:
        if not cadence or not media or canonical is None or not interval:
            return None
        recomputed = D.content_recomputed(cadence, media, canonical, interval)
        if recomputed is None or recomputed.get('policy') != dict(CONTENT_POLICIES[CONTENT_POLICY]):
            return None
        return recomputed
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def content_separation_status(cadence, media, canonical, interval) -> dict | None:
    """Separation (status, counts, histogram) recomputed from the hashed artifact; None when unavailable."""
    recomputed = content_recomputation(cadence, media, canonical, interval)
    separation = recomputed.get('separation') if recomputed else None
    return separation if isinstance(separation, dict) else None


def supervisor_thread_count(task_dir: Path = Path('/proc/self/task')) -> int:
    """OS threads of this process, native ``_thread`` threads included (threading counts only its own)."""
    return len(os.listdir(task_dir))


# -- supervisor -----------------------------------------------------------------

@dataclass
class Dependencies:
    proc_root: Path
    lock_path: Callable[[], Path]
    create_snapshot: Callable
    verify_snapshot: Callable
    manifest_sha256: Callable[[Path], str]
    spawn_child: Callable
    protected_displays: Callable[[], dict]
    alive: Callable[[int, str], bool]
    cleanup_budget: float = CLEANUP_BUDGET_SECONDS
    kill_owned: Callable[[dict], bool] = kill_owned_identity
    child_run_seconds: float = CHILD_RUN_SECONDS

    @classmethod
    def host(cls) -> 'Dependencies':
        from .gamescope_snapshot import _sha256
        return cls(proc_root=Path('/proc'), lock_path=canonical_lock_path,
                   create_snapshot=lambda source, snapshot, entries: create_snapshot(source, snapshot, entries=entries),
                   verify_snapshot=lambda snapshot, source_root, entries: verify_snapshot(
                       snapshot, source_root=source_root, entries=entries),
                   manifest_sha256=lambda snapshot: _sha256(Path(snapshot) / MANIFEST),
                   spawn_child=subprocess.Popen, protected_displays=protected_displays, alive=process_alive)


def _owned_identities(run_evidence: dict) -> list[dict]:
    owned = []
    if isinstance(run_evidence.get('client'), dict):
        owned.append({'role': 'client', **run_evidence['client']})
    lease = run_evidence.get('lease') or {}
    for name in ('gamescope', 'ready_child'):
        identity = (lease.get('owner') or {}).get(name)
        if isinstance(identity, dict):
            owned.append({'role': f'display:{name}', **identity})
    access = (lease.get('x11') or {}).get('access') or {}
    if 'pid' in access and 'start' in access:
        owned.append({'role': 'display:xwayland', 'pid': access['pid'], 'start': access['start']})
    return owned


def _all_owned(run_dir: Path, run_evidence: dict, child: dict | None) -> list[dict]:
    """Every identity the run recorded, deduplicated by (pid, start)."""
    candidates = [] if child is None else [child]
    try:
        recorded = json.loads((Path(run_dir) / OWNED_FILE).read_text())
        candidates += [item for item in recorded if isinstance(item, dict)]
    except (OSError, ValueError):
        pass
    candidates += _owned_identities(run_evidence)
    owned, seen = [], set()
    for identity in candidates:
        key = (identity.get('pid'), identity.get('start'))
        if type(key[0]) is int and isinstance(key[1], str) and key[1] and key not in seen:
            seen.add(key); owned.append(identity)
    return owned


class _SupervisorSignals:
    """Forward the first SIGINT/SIGHUP/SIGTERM to the child's session; never abort its cleanup."""
    def __init__(self):
        self.received: list[str] = []
        self.child = None
        self.forwarded = False
        self.previous = {}

    def handler(self, signum, frame):
        self.received.append(signal.Signals(signum).name)
        if self.child is None:
            raise DiagnosticInterrupted(signal.Signals(signum).name)
        self.forward()

    def forward(self):
        if not self.forwarded and self.child.poll() is None:
            self.forwarded = True
            try:
                self.child.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass

    def install(self):
        for number in INTERRUPT_SIGNALS:
            self.previous[number] = signal.signal(number, self.handler)

    def restore(self):
        for number, previous in self.previous.items():
            signal.signal(number, previous)


def _wait_for_child(process, signals: _SupervisorSignals, deps: 'Dependencies', monotonic=time.monotonic,
                    sleep=time.sleep) -> dict:
    """Wait for the child; after an interrupt or overrun, allow the full cleanup budget."""
    run_deadline = monotonic() + deps.child_run_seconds
    cleanup_deadline = None
    while True:
        code = process.poll()
        if code is not None:
            return {'returncode': code, 'budget_exhausted': False}
        now = monotonic()
        if not signals.forwarded and now >= run_deadline:
            signals.received.append('run_deadline')
            signals.forward()
        if signals.forwarded and cleanup_deadline is None:
            cleanup_deadline = now + deps.cleanup_budget
        if cleanup_deadline is not None and now >= cleanup_deadline:
            return {'returncode': None, 'budget_exhausted': True}
        sleep(.1)


def _kill_owned_after_budget(process, owned: list[dict], deps: 'Dependencies') -> dict:
    """Only after the cleanup budget: kill the child's own session group and each recorded identity."""
    evidence = {'child_group_killed': False, 'identities_signalled': [], 'kill_failures': []}
    try:
        os.killpg(process.pid, signal.SIGKILL)  # the child leads its own session
        evidence['child_group_killed'] = True
    except ProcessLookupError:
        pass
    except OSError as error:
        evidence['kill_failures'].append({'role': 'child_group', 'error': f'{type(error).__name__}: {error}'})
    for identity in owned:
        if deps.alive(identity['pid'], identity['start']):
            if deps.kill_owned(identity):
                evidence['identities_signalled'].append(identity)
            else:
                evidence['kill_failures'].append({**identity, 'error': 'kill refused or failed'})
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        evidence['kill_failures'].append({'role': 'child', 'error': 'child not reaped after SIGKILL'})
    time.sleep(.2)
    return evidence


def _proc_start(proc_root: Path, pid: int) -> str:
    raw = (Path(proc_root) / str(pid) / 'stat').read_text()
    return raw[raw.rindex(')') + 1:].split()[19]


def supervise(options, deps: Dependencies) -> int:
    run_root = Path(options.run_root).resolve()
    run_dir = run_root / (datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-')
                          + uuid.uuid4().hex[:8])
    # Refuse before claiming a run directory if the launch head cannot leave it.
    validate_commitment_log(options.commitment_log, run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    result = {'kind': RESULT_KIND, 'run_dir': str(run_dir), 'started_utc': _utc(), 'launches': 0,
              'errors': [], 'commitments': None, 'criteria': None, 'verdict': 'FAIL', 'media_sha256': None}
    lock_fd = token_fd = None
    head = None
    protected_before = None
    process = None
    child_identity = None
    tools = None
    wait = None
    signals = _SupervisorSignals()
    signals.install()
    try:
        lock_fd = acquire_lock(deps.lock_path())
        # Tool identities first: preflight also finds renamed copies of them by content.
        ffmpeg = native_elf_identity(options.ffmpeg)
        ffprobe = native_elf_identity(options.ffprobe)
        tools = [{'role': 'ffmpeg', **ffmpeg}, {'role': 'ffprobe', **ffprobe}]
        preflight(deps.proc_root, run_dir, tools=tools)
        protected_before = deps.protected_displays()
        snapshot = Path(options.snapshot).resolve()
        source_root = Path(options.source_root).resolve()
        deps.create_snapshot(source_root, snapshot, SNAPSHOT_ENTRIES)
        deps.verify_snapshot(snapshot, source_root, SNAPSHOT_ENTRIES)
        manifest_sha = deps.manifest_sha256(snapshot)
        recorded_probe = probe_tool_identity(options.ffprobe)
        if (recorded_probe['resolved_path'], recorded_probe['sha256']) != (ffprobe['resolved_path'], ffprobe['sha256']):
            raise DiagnosticRefused('configured FFprobe identity differs from the recorder identity')
        route = _canonical(route_document(options.ffmpeg))
        route_path = run_dir / 'diagnostic-route.json'
        with route_path.open('xb') as stream:
            stream.write(route)
        head = initialize_cleanup_ledger(run_dir, commitment_log=options.commitment_log)
        token_fd, token_sha = create_child_token()
        commitments = {'kind': COMMITMENT_KIND, 'run_dir': str(run_dir),
                       'route_sha256': hashlib.sha256(route).hexdigest(),
                       'ffprobe_sha256': ffprobe['sha256'], 'ffprobe_resolved_path': ffprobe['resolved_path'],
                       'ffmpeg': ffmpeg, 'cleanup_ledger_sha256': head,
                       'snapshot_manifest_sha256': manifest_sha, 'child_token_sha256': token_sha,
                       'cleanup_budget_seconds': deps.cleanup_budget, 'utc': _utc()}
        result['commitments'] = commitments
        _write(run_dir / 'commitments.json', commitments)
        line = json.dumps(commitments, sort_keys=True, separators=(',', ':'))
        # Printed, then appended to the re-validated operator log, before the single child starts.
        print(line, flush=True)
        append_commitment_line(options.commitment_log, run_dir, line)
        config = child_config(run_dir, ffmpeg=options.ffmpeg, ffprobe=options.ffprobe, lock_fd=lock_fd,
                              token_fd=token_fd, token_sha256=token_sha)
        config_path = run_dir / 'diagnostic-config.json'
        _write(config_path, config)
        runtime = snapshot / 'runtime'
        bootstrap = ('import runpy,sys;sys.dont_write_bytecode=True;sys.path.insert(0,' + repr(str(runtime))
                     + ');runpy.run_module("kpharness.capture_diagnostic",run_name="__main__")')
        command = [str(Path(sys.executable).resolve()), '-I', '-S', '-B', '-c', bootstrap,
                   '--child', str(config_path)]
        environment = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
        environment['KP_GAMESCOPE_REPO_ROOT'] = str(Path(deps.lock_path()).parents[2])
        _write(run_dir / 'invocation.json', {'command': command, 'cwd': str(snapshot)})
        # The spawn-window signal block below holds only for a single-threaded supervisor.
        # Counted from /proc/self/task, so a native _thread thread is seen too.
        threads = supervisor_thread_count()
        result['supervisor_threads_at_spawn'] = threads
        if threads != 1:
            raise DiagnosticRefused('the supervisor must be single-threaded for the spawn signal block')
        result['launches'] = 1
        with (run_dir / 'driver.log').open('xb') as driver_log:
            # Its own session: a terminal Ctrl-C reaches only this supervisor,
            # which forwards one SIGINT and waits for the ordered cleanup.
            # The interrupt set stays blocked from before the fork until the child
            # is registered, so a signal in the spawn window is held, not lost, and
            # is delivered (and forwarded) only once the child can be supervised.
            # The child inherits the blocked mask and unblocks it only after its
            # own handlers are installed (run_child). This assumes a
            # single-threaded supervisor: a second thread with the set unblocked
            # could take the signal and run the handler early.
            previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, INTERRUPT_SIGNALS)
            try:
                process = deps.spawn_child(command, cwd=str(snapshot), env=environment,
                                           pass_fds=(lock_fd, token_fd), start_new_session=True,
                                           stdout=driver_log, stderr=subprocess.STDOUT)
                signals.child = process
                try:
                    child_identity = {'role': 'child', 'pid': process.pid,
                                      'start': _proc_start(Path('/proc'), process.pid)}
                except (OSError, ValueError, IndexError):
                    child_identity = {'role': 'child', 'pid': process.pid, 'start': None}
                result['child'] = child_identity
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
            os.close(token_fd); token_fd = None
            if child_identity.get('start') is None:
                child_identity = None
            wait = _wait_for_child(process, signals, deps)
        result['child_returncode'] = wait['returncode']
    except DiagnosticInterrupted as error:
        result['errors'].append(f'interrupted before launch: {error}')
    except (DiagnosticRefused, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        result['errors'].append(f'{type(error).__name__}: {error}')
    finally:
        if token_fd is not None:
            os.close(token_fd)
        if process is not None and wait is None:
            # Interrupted between spawn and wait: still forward and allow the full budget.
            signals.child = process
            signals.forward()
            try:
                wait = _wait_for_child(process, signals, deps)
            except BaseException as error:  # never leave the child without the kill path
                result['errors'].append(f'wait: {type(error).__name__}: {error}')
                wait = {'returncode': None, 'budget_exhausted': True}
            result['child_returncode'] = wait['returncode']
        result['interrupts'] = list(signals.received)
        observation = {'error': None if not result['errors'] else result['errors'][0],
                       'protected_before': protected_before, 'owned_survivors': [], 'recorder': None}
        if signals.received and observation['error'] is None:
            observation['error'] = 'interrupted: ' + ','.join(signals.received)
            result['errors'].append(observation['error'])
        if result['launches']:
            try:
                run_evidence = json.loads((run_dir / 'diagnostic-run.json').read_text())
            except (OSError, ValueError) as error:
                run_evidence = {'error': f'child evidence missing: {type(error).__name__}: {error}'}
            observation.update(recorder=run_evidence.get('recorder'), window=run_evidence.get('window'),
                               cleanup=run_evidence.get('cleanup'),
                               error=observation['error'] or run_evidence.get('error'))
            lease = run_evidence.get('lease') or {}
            observation['lease'] = {'lease_id': lease.get('lease_id'),
                                    'display': (lease.get('x11') or {}).get('display'),
                                    'width': (lease.get('requested_geometry') or [None, None])[0],
                                    'height': (lease.get('requested_geometry') or [None, None])[1]}
            try:
                deps.verify_snapshot(Path(options.snapshot).resolve(), Path(options.source_root).resolve(),
                                     SNAPSHOT_ENTRIES)
                observation['snapshot_unchanged'] = True
            except (OSError, ValueError, RuntimeError) as error:
                observation['snapshot_unchanged'] = False
                result['errors'].append(f'snapshot: {type(error).__name__}: {error}')
            owned = _all_owned(run_dir, run_evidence, child_identity)
            result['cleanup_budget'] = {'seconds': deps.cleanup_budget,
                                        'components': dict(CLEANUP_BUDGET_COMPONENTS),
                                        'exhausted': bool(wait and wait['budget_exhausted'])}
            alive_before = [identity for identity in owned if deps.alive(identity['pid'], identity['start'])]
            result['owned_alive_after_child'] = alive_before
            child_cleanup_passed = (run_evidence.get('cleanup') or {}).get('status') == 'passed'
            # After the budget, or when the child ended without a passed ordered
            # cleanup, kill what this run owns and nothing else.
            if process is not None and (wait is None or wait['budget_exhausted']
                                        or (alive_before and not child_cleanup_passed)):
                result['cleanup_budget']['kill'] = _kill_owned_after_budget(process, owned, deps)
            survivors = [identity for identity in owned if deps.alive(identity['pid'], identity['start'])]
            survivors += forbidden_processes(process_inventory(deps.proc_root, tools=tools),
                                             exclude=_launch_chain(deps.proc_root, os.getpid()))
            observation['owned_survivors'] = survivors
            result['owned_survivors'] = survivors
            observation['protected_after'] = deps.protected_displays()
            observation['ledger_clear'] = head is not None and cleanup_state_clear(run_dir, head)
            media = run_dir / 'continuous.mp4'
            observation['media_sha256'] = (hashlib.sha256(media.read_bytes()).hexdigest()
                                           if media.is_file() and not media.is_symlink() else None)
            try:
                observation['ffmpeg_log'] = (run_dir / 'ffmpeg.log').read_text(errors='replace')
            except OSError:
                observation['ffmpeg_log'] = None
            observation['route'] = {'acceptance_pair': ['pattern_start', 'pattern_end'],
                                    'acceptance_seconds': ACCEPTANCE_SECONDS}
            result['media_sha256'] = observation['media_sha256']
        evaluation = evaluate(observation)
        result['criteria'] = evaluation['criteria']
        result['failing_criteria'] = evaluation['failing_criteria']
        result['content_separation'] = evaluation['content_separation']
        result['content_level_sequence'] = evaluation['content_level_sequence']
        result['cadence_recomputed_apart_from_content'] = evaluation['cadence_recomputed_apart_from_content']
        result['verdict'] = evaluation['verdict'] if result['launches'] else 'FAIL'
        result['finished_utc'] = _utc()
        _write(run_dir / 'diagnostic-result.json', result)
        if lock_fd is not None:
            os.close(lock_fd)
        signals.restore()
    print(json.dumps({'kind': RESULT_KIND, 'verdict': result['verdict'], 'run_dir': str(run_dir),
                      'media_sha256': result['media_sha256'], 'errors': result['errors'],
                      'failing_criteria': result.get('failing_criteria', []),
                      'owned_survivors': result.get('owned_survivors', [])}), flush=True)
    return 0 if result['verdict'] == 'PASS' else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ['--child'] and len(argv) == 2:
        try:
            return _child_main(argv[1])
        except DiagnosticRefused as error:
            print(json.dumps({'ok': False, 'error': f'refusing --child: {error}'}), flush=True)
            return 2
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run', help='run the single authorized diagnostic on this host')
    run.add_argument('--run-root', required=True)
    run.add_argument('--snapshot', required=True, help='new directory for the verified harness snapshot')
    run.add_argument('--cleanup-commitment-log', required=True, dest='commitment_log')
    run.add_argument('--source-root', default=str(Path(__file__).resolve().parents[1]))
    run.add_argument('--ffmpeg', default=DEFAULT_FFMPEG)
    run.add_argument('--ffprobe', required=True,
                     help='absolute path of a native FFprobe ELF (not a wrapper); recorded by path and SHA-256')
    run.add_argument('--authorized-single-run', action='store_true',
                     help='required: confirms this one host run is authorized')
    options = parser.parse_args(argv)
    if not options.authorized_single_run:
        print(json.dumps({'ok': False, 'error': 'refusing to launch: pass --authorized-single-run only '
                          'when this single diagnostic run is authorized'}))
        return 2
    return supervise(options, Dependencies.host())


if __name__ == '__main__':
    raise SystemExit(main())
