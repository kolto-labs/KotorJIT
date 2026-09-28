"""Post-capture human acceptance for one immutable creative-run recording."""
from __future__ import annotations

import argparse
import copy
import datetime
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import signal
import select
import time
import uuid
from pathlib import Path

from .recording import (ProbeCleanupError, probe_deadline_seconds, probe_frame_content,
                        probe_frame_pts, sha256)
from .display_backends import execution_evidence_ready, geometry_precondition_sha256

REVIEW_SCOPE = "native behavior, framing, readability, cadence, defining effect, and transitions"
CLEANUP_LEDGER = 'ffprobe-cleanup-ledger.json'
CLEANUP_LEDGER_SCHEMA = 2
RECORD_SCHEMA = 1
LEDGER_HEAD_KIND = 'kpharness.cleanup-ledger-head.v1'
SURVIVOR_KIND = 'kpharness.ffprobe-survivor.v1'
UNRECORDED_SURVIVOR_GLOB = 'ffprobe-cleanup-unrecorded-*.json'
SURVIVOR_INSTRUCTION = ('do not accept or export this run; retain this line, the ledger head, '
                        'and the survivor PID/start out of band')
LEDGER_EVENTS = ('run_initialized', 'acceptance_failure', 'signal_error_reaped', 'recovery_resolution')
LEDGER_LOCK_TIMEOUT_SECONDS = 10.0
RECOVERY_REQUIREMENT = ('retain this exact failure record and use pidfd recovery only after '
                        'verifying the recorded PID/start identity')
UNRECOVERABLE_REQUIREMENT = ('start identity was unavailable; this failure is permanently '
                             'unrecoverable and blocks acceptance and export for this run')
_UTC = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}\+00:00')
_DEFAULT_PIDFD = object()


class CleanupLedgerChanged(ValueError):
    """A ledger transition happened; the operator must retain the emitted head."""
    def __init__(self, message: str, *, failure_id: str | None, cleanup_ledger_sha256: str | None,
                 head_line: dict, survivor: dict | None = None):
        super().__init__(message)
        self.failure_id = failure_id
        self.cleanup_ledger_sha256 = cleanup_ledger_sha256
        self.head_line = head_line
        self.survivor = survivor


class CommitmentLogFailed(ValueError):
    """The ledger changed and its head reached stderr, but the log append failed."""
    def __init__(self, message: str, *, record: dict, cleanup_ledger_sha256: str, head_changed: bool):
        super().__init__(message)
        self.record = record
        self.cleanup_ledger_sha256 = cleanup_ledger_sha256
        self.head_changed = head_changed


def execution_receipt_sha256(receipt: dict) -> str:
    """Digest completed execution fields, excluding later review decisions."""
    execution = copy.deepcopy(receipt)
    for key in ("visual_review", "ok", "acceptance_ready"):
        execution.pop(key, None)
    encoded = json.dumps(execution, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def acceptance_receipt_sha256(receipt: dict) -> str:
    review = copy.deepcopy(receipt.get("visual_review", {}))
    review.pop("acceptance_receipt_sha256", None)
    encoded = json.dumps(review, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _regular_nonsymlink(path: Path) -> bool:
    try:
        info = path.lstat()
        return stat.S_ISREG(info.st_mode) and not path.is_symlink()
    except OSError:
        return False


def _read_regular(path: Path, *, maximum_bytes: int = 8 * 1024 * 1024) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum_bytes:
            raise OSError('receipt is not a bounded regular file')
        data = os.read(descriptor, info.st_size + 1)
        if len(data) != info.st_size:
            raise OSError('receipt changed while reading')
        return data
    finally:
        os.close(descriptor)


def _atomic_regular_write(path: Path, payload: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        if not _regular_nonsymlink(temporary):
            raise OSError('acceptance temporary file is not regular')
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        if not _regular_nonsymlink(path) or _read_regular(path) != payload:
            raise OSError('published acceptance receipt identity or bytes changed')
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _exclusive_regular_write(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, 'wb', closefd=False) as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _utc_now() -> str:
    """The one accepted ledger timestamp form: microseconds and an explicit +00:00."""
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f+00:00')


def _utc(value: object) -> datetime.datetime | None:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        return None


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and re.fullmatch(f'[0-9a-f]{{{length}}}', value) is not None


def _exact_int(value: object) -> bool:
    return type(value) is int


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def _record_digest(record: dict) -> str:
    unsigned = {key: value for key, value in record.items() if key != 'record_digest'}
    return hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False).encode()).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('FFprobe cleanup ledger contains a duplicate JSON key')
        result[key] = value
    return result


def _reject_constant(name: str) -> object:
    raise ValueError('FFprobe cleanup ledger contains a nonfinite number: ' + name)


def _host_identity() -> dict:
    """Boot and PID-namespace identity that makes /proc absence meaningful."""
    try:
        boot_id = Path('/proc/sys/kernel/random/boot_id').read_text(encoding='ascii').strip()
    except (OSError, UnicodeError):
        boot_id = ''
    try:
        namespace = os.readlink('/proc/self/ns/pid')
    except OSError:
        namespace = ''
    return {'boot_id': boot_id, 'pid_namespace': namespace}


def _validate_tool(tool: object) -> bool:
    return (isinstance(tool, dict) and set(tool) == {'command', 'resolved_path', 'sha256'}
            and all(isinstance(tool[key], str) and tool[key] for key in ('command', 'resolved_path'))
            and _hex(tool.get('sha256'), 64))


_FAILURE_KEYS = {'failure_type', 'identity', 'pid', 'pid_start', 'boot_id', 'pid_namespace',
                 'command', 'tool', 'bounded_wait_seconds', 'signal_errors', 'recovery'}
_RESOLUTION_KEYS = {'failure_id', 'failure_digest', 'pid', 'pid_start', 'outcome',
                    'pidfd', 'signal', 'wait'}
_RESOLUTION_SHAPES = {
    ('already_exited', 'not_needed', 'not_sent', 'confirmed_absent'),
    ('original_exited_pid_reused', 'not_needed', 'not_sent', 'start_mismatch'),
    ('pidfd_reaped', 'held', 'SIGKILL', 'pidfd_readable'),
    ('signal_error_reaped', 'held', 'SIGKILL_error', 'pidfd_readable'),
    ('signal_error_reaped', 'not_needed', 'SIGKILL_error', 'confirmed_absent'),
}


def _validate_failure_payload(payload: object) -> bool:
    if not isinstance(payload, dict) or set(payload) != _FAILURE_KEYS:
        return False
    identity = payload['identity']
    if identity == 'exact':
        identity_ok = (_exact_int(payload['pid']) and payload['pid'] > 0
                       and isinstance(payload['pid_start'], str) and bool(payload['pid_start'])
                       and payload['recovery'] == RECOVERY_REQUIREMENT)
    elif identity == 'unavailable':
        identity_ok = (_exact_int(payload['pid']) and payload['pid'] >= 0
                       and payload['pid_start'] == '' and payload['recovery'] == UNRECOVERABLE_REQUIREMENT)
    else:
        return False
    waits = payload['bounded_wait_seconds']
    return bool(identity_ok and payload['failure_type'] == 'ffprobe_cleanup_failed'
        and isinstance(payload['boot_id'], str) and isinstance(payload['pid_namespace'], str)
        and isinstance(payload['command'], list) and payload['command']
        and all(isinstance(item, str) and item for item in payload['command'])
        and _validate_tool(payload['tool'])
        and isinstance(waits, list) and len(waits) == 2
        and all(_exact_int(item) and item == 2 for item in waits)
        and isinstance(payload['signal_errors'], list)
        and all(isinstance(item, str) and item for item in payload['signal_errors']))


def _validate_cleanup_record(record: object, sequence: int, previous: str,
                             failures: dict[str, dict], resolutions: dict[str, dict]) -> dict:
    keys = {'schema', 'type', 'sequence', 'id', 'prev_digest', 'timestamp_utc',
            'payload', 'record_digest'}
    if (not isinstance(record, dict) or set(record) != keys
            or not _exact_int(record['schema']) or record['schema'] != RECORD_SCHEMA
            or not _exact_int(record['sequence']) or record['sequence'] != sequence
            or not _hex(record['id'], 32) or record['prev_digest'] != previous
            or _utc(record['timestamp_utc']) is None
            or record['record_digest'] != _record_digest(record)):
        raise ValueError('malformed FFprobe cleanup ledger record')
    payload = record['payload']
    if record['type'] == 'failure':
        if not _validate_failure_payload(payload) or record['id'] in failures:
            raise ValueError('malformed FFprobe cleanup failure')
        failures[record['id']] = record
    elif record['type'] == 'resolution':
        if not isinstance(payload, dict) or set(payload) != _RESOLUTION_KEYS:
            raise ValueError('malformed FFprobe cleanup resolution')
        failure_id = payload['failure_id']
        failure = failures.get(failure_id) if isinstance(failure_id, str) else None
        if (failure is None or failure_id in resolutions or record['id'] != failure_id
                or failure['payload']['identity'] != 'exact'
                or payload['failure_digest'] != failure['record_digest']
                or not _exact_int(payload['pid']) or payload['pid'] != failure['payload']['pid']
                or payload['pid_start'] != failure['payload']['pid_start']
                or (payload['outcome'], payload['pidfd'], payload['signal'], payload['wait'])
                    not in _RESOLUTION_SHAPES
                or _utc(record['timestamp_utc']) < _utc(failure['timestamp_utc'])):
            raise ValueError('malformed FFprobe cleanup resolution')
        resolutions[failure_id] = record
    else:
        raise ValueError('unknown FFprobe cleanup ledger record type')
    return record


def _launch_bytes(nonce: str) -> bytes:
    return _canonical_bytes({'schema': CLEANUP_LEDGER_SCHEMA, 'nonce': nonce, 'records': []})


def _load_cleanup_ledger(run_dir: Path) -> tuple[dict, bytes, dict[str, dict], dict[str, dict]]:
    path = Path(run_dir) / CLEANUP_LEDGER
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ValueError('FFprobe cleanup ledger must be a unique regular file')
    raw = _read_regular(path, maximum_bytes=2 * 1024 * 1024)
    after = path.lstat()
    if _stat_identity(before) != _stat_identity(after):
        raise ValueError('FFprobe cleanup ledger changed while reading')
    try:
        ledger = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        if raw != _canonical_bytes(ledger):
            raise ValueError('FFprobe cleanup ledger is not canonically encoded')
        if (not isinstance(ledger, dict) or set(ledger) != {'schema', 'nonce', 'records'}
                or not _exact_int(ledger['schema']) or ledger['schema'] != CLEANUP_LEDGER_SCHEMA
                or not _hex(ledger['nonce'], 32) or not isinstance(ledger['records'], list)):
            raise ValueError('malformed FFprobe cleanup ledger')
        # The chain starts at the nonce-bound launch head, so records never
        # transplant between runs.
        previous = hashlib.sha256(_launch_bytes(ledger['nonce'])).hexdigest()
        failures: dict[str, dict] = {}; resolutions: dict[str, dict] = {}
        for sequence, record in enumerate(ledger['records'], 1):
            checked = _validate_cleanup_record(record, sequence, previous, failures, resolutions)
            previous = checked['record_digest']
    except (TypeError, KeyError, AttributeError, IndexError, RecursionError, UnicodeDecodeError) as error:
        raise ValueError(f'malformed FFprobe cleanup ledger: {type(error).__name__}') from error
    return ledger, raw, failures, resolutions


def validate_commitment_log(path: object, run_dir: Path) -> tuple[Path, tuple[int, int]]:
    """Admit only an existing, unique, regular operator file outside the run directory."""
    if path is None or (isinstance(path, str) and not path):
        raise ValueError('cleanup commitment log is required and must be outside the run directory')
    candidate = Path(os.path.abspath(Path(path).expanduser()))
    try:
        info = os.lstat(candidate)
    except FileNotFoundError as error:
        raise ValueError('cleanup commitment log is missing; create it outside the run directory') from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError('cleanup commitment log must be a unique regular non-symlink file')
    resolved = candidate.resolve(strict=True)
    run = Path(os.path.abspath(Path(run_dir))).resolve()
    if resolved == run or resolved.is_relative_to(run):
        raise ValueError('cleanup commitment log must be outside the run directory')
    if _aliases_run_tree(resolved, (info.st_dev, info.st_ino), run):
        raise ValueError('cleanup commitment log must be outside the run directory '
                         '(it aliases the run tree by device and inode, for example a bind mount)')
    return resolved, (info.st_dev, info.st_ino)


def _aliases_run_tree(log: Path, log_identity: tuple[int, int], run: Path) -> bool:
    """Compare the log and its parent chain with every run-tree inode (catches bind mounts)."""
    try:
        run_info = os.stat(run)
    except FileNotFoundError:
        return False  # No run directory yet, so nothing can alias it.
    tree = {(run_info.st_dev, run_info.st_ino)}
    for directory, names, files in os.walk(run, followlinks=False):
        for name in (*names, *files):
            try:
                entry = os.lstat(os.path.join(directory, name))
            except FileNotFoundError:
                continue
            tree.add((entry.st_dev, entry.st_ino))
    chain = {log_identity}
    for parent in log.parents:
        try:
            entry = os.stat(parent)
        except OSError:
            continue
        chain.add((entry.st_dev, entry.st_ino))
    return bool(chain & tree)


def _emit_head(run_dir: Path, commitment_log: object, *, event: str, nonce: str, sequence: int,
               head: str, failure_id: str | None) -> dict:
    """Write one machine-readable head line to stderr and the operator commitment log."""
    if event not in LEDGER_EVENTS:
        raise ValueError('unknown cleanup ledger event')
    line = {'kind': LEDGER_HEAD_KIND, 'event': event,
            'run_dir': str(Path(os.path.abspath(Path(run_dir))).resolve()), 'nonce': nonce,
            'sequence': sequence, 'cleanup_ledger_sha256': head, 'failure_id': failure_id,
            'utc': _utc_now()}
    encoded = json.dumps(line, sort_keys=True, separators=(',', ':'))
    # stderr is written first so a failing log append still leaves the head visible.
    print(encoded, file=sys.stderr, flush=True)
    append_commitment_line(commitment_log, run_dir, encoded)
    return line


def append_commitment_line(commitment_log: object, run_dir: Path, encoded: str) -> None:
    """Re-validate the operator log, then append one line with a single O_APPEND write."""
    path, identity = validate_commitment_log(commitment_log, run_dir)
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if (info.st_dev, info.st_ino) != identity or info.st_nlink != 1 or not stat.S_ISREG(info.st_mode):
            raise ValueError('cleanup commitment log identity changed while opening')
        # One O_APPEND write per line keeps concurrent writers from interleaving.
        payload = (encoded + '\n').encode()
        if os.write(descriptor, payload) != len(payload):
            raise OSError('short cleanup commitment log write')
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ledger_lock(run_dir: Path) -> int:
    """Hold an exclusive lock on the run directory for one ledger transition."""
    descriptor = os.open(run_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    deadline = time.monotonic() + LEDGER_LOCK_TIMEOUT_SECONDS
    try:
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return descriptor
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ValueError('FFprobe cleanup ledger lock is held by another transition')
                time.sleep(.05)
    except BaseException:
        os.close(descriptor)
        raise


def initialize_cleanup_ledger(run_dir: Path, *, commitment_log: object) -> str:
    run_dir = Path(run_dir)
    validate_commitment_log(commitment_log, run_dir)
    nonce = uuid.uuid4().hex
    payload = _launch_bytes(nonce)
    _exclusive_regular_write(run_dir / CLEANUP_LEDGER, payload)
    head = hashlib.sha256(payload).hexdigest()
    _emit_head(run_dir, commitment_log, event='run_initialized', nonce=nonce, sequence=0,
               head=head, failure_id=None)
    return head


def cleanup_ledger_sha256(run_dir: Path) -> str:
    _, raw, _, _ = _load_cleanup_ledger(run_dir)
    return hashlib.sha256(raw).hexdigest()


def unrecorded_survivors(run_dir: Path) -> list[str]:
    """Survivor records that could not enter the ledger; each blocks the run permanently."""
    return sorted(path.name for path in Path(run_dir).glob(UNRECORDED_SURVIVOR_GLOB))


def cleanup_state_clear(run_dir: Path, expected_sha256: str | None = None) -> bool:
    try:
        if unrecorded_survivors(run_dir):
            return False
        _, raw, failures, resolutions = _load_cleanup_ledger(run_dir)
        return bool((expected_sha256 is None or (_hex(expected_sha256, 64)
                    and hashlib.sha256(raw).hexdigest() == expected_sha256))
                    and set(failures) == set(resolutions))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def _append_cleanup_record(run_dir: Path, record_type: str, payload: dict, *, expected_head: str,
                           commitment_log: object, event: str,
                           identifier: str | None = None, survivor: bool = False) -> tuple[dict, str]:
    """Append one record under the ledger lock, then emit its head.

    A survivor (``failure``) record is written before, and independently of,
    commitment-log validation, and even when another transition moved the head
    during the probe: recording a failure can only block. If the head cannot
    reach the log afterwards, CommitmentLogFailed carries the new head, which
    is already on stderr.
    """
    run_dir = Path(run_dir)
    if not survivor:
        validate_commitment_log(commitment_log, run_dir)
    lock = _ledger_lock(run_dir)
    head_changed = False
    try:
        ledger, raw, _, _ = _load_cleanup_ledger(run_dir)
        # Re-verify the caller's independently supplied head under the lock.
        if not _hex(expected_head, 64) or hashlib.sha256(raw).hexdigest() != expected_head:
            if not survivor:
                raise ValueError('cleanup ledger head changed; refusing to extend an unanchored chain')
            head_changed = True
        records = ledger['records']
        previous = (records[-1]['record_digest'] if records
                    else hashlib.sha256(_launch_bytes(ledger['nonce'])).hexdigest())
        record = {'schema': RECORD_SCHEMA, 'type': record_type, 'sequence': len(records) + 1,
            'id': identifier or uuid.uuid4().hex, 'prev_digest': previous,
            'timestamp_utc': _utc_now(), 'payload': copy.deepcopy(payload)}
        record['record_digest'] = _record_digest(record)
        records.append(record)
        encoded = _canonical_bytes(ledger)
        _atomic_regular_write(run_dir / CLEANUP_LEDGER, encoded)
        _, published, _, _ = _load_cleanup_ledger(run_dir)
        if published != encoded:
            raise ValueError('published FFprobe cleanup ledger differs from the validated chain')
    finally:
        os.close(lock)
    head = hashlib.sha256(encoded).hexdigest()
    try:
        _emit_head(run_dir, commitment_log, event=event, nonce=ledger['nonce'], sequence=len(records),
                   head=head, failure_id=record['id'] if record_type == 'failure' else payload['failure_id'])
    except (OSError, ValueError) as error:
        raise CommitmentLogFailed(f'{error}', record=record, cleanup_ledger_sha256=head,
                                  head_changed=head_changed) from error
    if head_changed:
        raise CommitmentLogFailed('', record=record, cleanup_ledger_sha256=head, head_changed=True)
    return record, head


def _stat_identity(info) -> tuple[int, int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_nlink)


def _fd_identity_and_sha(descriptor: int) -> tuple[tuple[int, int, int, int, int, int], str]:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError('accepted master is not a regular file')
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    while block := os.read(descriptor, 1024 * 1024):
        digest.update(block)
    after = os.fstat(descriptor)
    if _stat_identity(before) != _stat_identity(after):
        raise ValueError('accepted master changed while hashing')
    return _stat_identity(after), digest.hexdigest()


def _regular_identity_and_sha(path: Path) -> tuple[tuple[int, int, int, int, int, int], str]:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        return _fd_identity_and_sha(descriptor)
    finally:
        os.close(descriptor)


def _stable_regular_copy(source: Path, destination: Path, expected_sha256: str) -> tuple[int, ...]:
    """Copy one retained O_NOFOLLOW source identity into private exclusive staging."""
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink < 1:
            raise ValueError('accepted master is not a regular file')
        digest = hashlib.sha256()
        output = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            while block := os.read(descriptor, 1024 * 1024):
                digest.update(block)
                view = memoryview(block)
                while view:
                    written = os.write(output, view)
                    if written <= 0:
                        raise OSError('short stable-copy write')
                    view = view[written:]
            os.fsync(output)
        finally:
            os.close(output)
        after = os.fstat(descriptor)
        identity = _stat_identity(before)
        if identity != _stat_identity(after):
            raise ValueError('accepted master changed while creating stable input')
        if digest.hexdigest() != expected_sha256:
            raise ValueError('accepted master digest changed while creating stable input')
        copied_identity, copied_sha = _regular_identity_and_sha(destination)
        if copied_sha != expected_sha256 or copied_identity[2] != before.st_size:
            raise ValueError('stable accepted-master copy failed digest verification')
        return identity
    finally:
        os.close(descriptor)


def _stable_unlinked_fd(source: Path, directory: Path, expected_sha256: str) -> tuple[tuple[int, ...], int, tuple[int, ...]]:
    """Create one verified private inode, reopen read-only, and unlink it before probing."""
    stable = directory / 'accepted-master.mp4'
    source_identity = _stable_regular_copy(source, stable, expected_sha256)
    descriptor = os.open(stable, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        linked_identity, copied_sha = _fd_identity_and_sha(descriptor)
        if linked_identity[5] != 1 or copied_sha != expected_sha256:
            raise ValueError('private accepted-master copy lacks a unique verified link')
        stable.unlink()
        unlinked_identity, copied_sha = _fd_identity_and_sha(descriptor)
        if (unlinked_identity[:4] != linked_identity[:4]
                or unlinked_identity[4] < linked_identity[4] or unlinked_identity[5] != 0
                or copied_sha != expected_sha256):
            raise ValueError('private accepted-master descriptor changed while unlinking')
        return source_identity, descriptor, unlinked_identity
    except BaseException:
        os.close(descriptor)
        raise


def verify_acceptance(receipt: dict, *, route_sha256: str, ffprobe_sha256: str,
                      cleanup_ledger_sha256: str) -> bool:
    try:
        review = receipt["visual_review"]
        continuous = receipt["media"]["continuous"]
        run_dir = Path(receipt["run_dir"]).resolve()
        media_path = Path(continuous["path"])
        media = media_path.resolve()
        accepted = datetime.datetime.fromisoformat(review["accepted_utc"])
        if (not _regular_nonsymlink(media_path) or not media.is_relative_to(run_dir)
                or not review["reviewer"].strip() or review["reviewer"] != review["reviewer"].strip()
                or accepted.tzinfo is None or review["scope"] != REVIEW_SCOPE):
            return False
        actual = sha256(media)
        return bool(cleanup_state_clear(run_dir, cleanup_ledger_sha256)
                    and receipt.get("ok") is True and review.get("status") == "accepted"
                    and execution_evidence_ready(receipt, require_completion=True)
                    and review.get("execution_receipt_sha256") == execution_receipt_sha256(receipt)
                    and review.get("acceptance_receipt_sha256") == acceptance_receipt_sha256(receipt)
                    and review.get('pts_artifact_sha256') == receipt['cadence']['pts_artifact']['sha256']
                    and review.get('route_sha256') == route_sha256 == receipt['route_source']['sha256']
                    and review.get('ffprobe_sha256') == ffprobe_sha256 == receipt['cadence']['probe_tool']['sha256']
                    and review.get('cleanup_ledger_sha256') == cleanup_ledger_sha256
                    and review.get('content_artifact_sha256')
                        == receipt['cadence']['content']['artifact']['sha256']
                    and review.get('geometry_precondition_sha256')
                        == geometry_precondition_sha256(receipt['capture']['geometry_precondition'])
                    and actual == review.get("media_sha256") == continuous.get("sha256"))
    except (KeyError, TypeError, ValueError, OSError):
        return False


def _verified_tool_fd(tool: dict, expected_sha256: str) -> tuple[int, tuple[int, ...], str]:
    path = Path(tool['resolved_path'])
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o111
                or os.pread(descriptor, 4, 0) != b'\x7fELF'):
            raise ValueError('configured FFprobe must be a native executable ELF file')
        identity, digest = _fd_identity_and_sha(descriptor)
        if digest != tool['sha256'] or digest != expected_sha256:
            raise ValueError('configured FFprobe descriptor digest changed')
        return descriptor, identity, digest
    except BaseException:
        os.close(descriptor)
        raise


def _persist_probe_cleanup_failure(run_dir: Path, error: ProbeCleanupError, tool: dict, *,
                                   expected_head: str, commitment_log: object,
                                   host_reader=_host_identity, survivor: bool = False) -> tuple[dict, str]:
    """Durably record a surviving child; missing start identity is permanently blocking."""
    exact = (type(error.pid) is int and error.pid > 0
             and isinstance(error.pid_start, str) and bool(error.pid_start))
    host = host_reader()
    payload = {'failure_type': 'ffprobe_cleanup_failed',
        'identity': 'exact' if exact else 'unavailable',
        'pid': error.pid if type(error.pid) is int and error.pid > 0 else 0,
        'pid_start': error.pid_start if exact else '',
        'boot_id': host.get('boot_id', '') if isinstance(host, dict) else '',
        'pid_namespace': host.get('pid_namespace', '') if isinstance(host, dict) else '',
        'command': [str(item) for item in error.command] or ['ffprobe'], 'tool': copy.deepcopy(tool),
        'bounded_wait_seconds': [2, 2], 'signal_errors': list(error.signal_errors),
        'recovery': RECOVERY_REQUIREMENT if exact else UNRECOVERABLE_REQUIREMENT}
    return _append_cleanup_record(run_dir, 'failure', payload, expected_head=expected_head,
                                  commitment_log=commitment_log, event='acceptance_failure',
                                  survivor=survivor)


def _record_surviving_probe(run_dir: Path, error: ProbeCleanupError, tool: dict, *,
                            expected_head: str, commitment_log: object) -> CleanupLedgerChanged:
    """Always leave a blocking record for a surviving FFprobe child, and always say so on stderr."""
    pid = error.pid if type(error.pid) is int and error.pid > 0 else 0
    start = error.pid_start if isinstance(error.pid_start, str) else ''
    command = [str(item) for item in error.command] or ['ffprobe']
    survivor = {'kind': SURVIVOR_KIND, 'run_dir': str(Path(run_dir).resolve()), 'pid': pid,
                'pid_start': start, 'command': command, 'recorded_in_ledger': False,
                'failure_id': None, 'cleanup_ledger_sha256': None, 'head_changed_during_probe': False,
                'ledger_error': None, 'commitment_log_error': None,
                'instruction': SURVIVOR_INSTRUCTION}
    failure = head = None
    try:
        failure, head = _persist_probe_cleanup_failure(run_dir, error, tool, expected_head=expected_head,
                                                       commitment_log=commitment_log, survivor=True)
    except CommitmentLogFailed as log_error:
        failure, head = log_error.record, log_error.cleanup_ledger_sha256
        survivor['head_changed_during_probe'] = log_error.head_changed
        if str(log_error):
            survivor['commitment_log_error'] = str(log_error)
    except (OSError, ValueError) as ledger_error:
        survivor['ledger_error'] = f'{type(ledger_error).__name__}: {ledger_error}'
    if failure is not None:
        survivor.update(recorded_in_ledger=True, failure_id=failure['id'], cleanup_ledger_sha256=head)
        if (error.reaped and failure['payload']['identity'] == 'exact'
                and survivor['commitment_log_error'] is None and not survivor['head_changed_during_probe']):
            payload = {'failure_id': failure['id'], 'failure_digest': failure['record_digest'],
                'pid': failure['payload']['pid'], 'pid_start': failure['payload']['pid_start'],
                'outcome': 'signal_error_reaped', 'pidfd': 'not_needed', 'signal': 'SIGKILL_error',
                'wait': 'confirmed_absent'}
            try:
                _, head = _append_cleanup_record(run_dir, 'resolution', payload, expected_head=head,
                    commitment_log=commitment_log, event='signal_error_reaped', identifier=failure['id'])
            except CommitmentLogFailed as log_error:
                head = log_error.cleanup_ledger_sha256
                survivor['commitment_log_error'] = str(log_error)
            except (OSError, ValueError) as resolution_error:
                # The failure stays unresolved, which keeps the gate blocked.
                survivor['ledger_error'] = f'resolution: {type(resolution_error).__name__}: {resolution_error}'
            survivor['cleanup_ledger_sha256'] = head
    else:
        # The ledger could not take the record: leave an exclusive blocking sidecar.
        try:
            sidecar = Path(run_dir) / f'ffprobe-cleanup-unrecorded-{uuid.uuid4().hex}.json'
            _exclusive_regular_write(sidecar, _canonical_bytes({key: value for key, value in survivor.items()
                                                                if key != 'kind'} | {'utc': _utc_now()}))
            survivor['unrecorded_sidecar'] = sidecar.name
        except OSError as sidecar_error:
            survivor['unrecorded_sidecar_error'] = f'{type(sidecar_error).__name__}: {sidecar_error}'
    print(json.dumps(survivor, sort_keys=True, separators=(',', ':')), file=sys.stderr, flush=True)
    line = {'kind': LEDGER_HEAD_KIND, 'run_dir': survivor['run_dir'], 'failure_id': survivor['failure_id'],
            'cleanup_ledger_sha256': survivor['cleanup_ledger_sha256']}
    return CleanupLedgerChanged(
        f'canonical PTS re-probe cleanup failed: {error}; surviving ffprobe pid={pid} start={start or "unavailable"}; '
        f'failure_id={survivor["failure_id"]}; cleanup_ledger_sha256={survivor["cleanup_ledger_sha256"]}; '
        f'{SURVIVOR_INSTRUCTION}',
        failure_id=survivor['failure_id'], cleanup_ledger_sha256=survivor['cleanup_ledger_sha256'],
        head_line=line, survivor=survivor)


def _process_identity(pid: int) -> dict:
    """Return present/absent/unreadable without treating arbitrary I/O as process exit."""
    try:
        descriptor = os.open(f'/proc/{pid}/stat', os.O_RDONLY | os.O_NOFOLLOW)
        try:
            raw = os.read(descriptor, 64 * 1024)
        finally:
            os.close(descriptor)
    except (FileNotFoundError, ProcessLookupError):
        return {'state': 'absent'}
    except OSError as error:
        return {'state': 'unreadable', 'error': f'{type(error).__name__}: {error}'}
    try:
        text = raw.decode('ascii')
        closing = text.rindex(')')
        fields = text[closing + 1:].split()
        start = fields[19]
        if not start or not start.isdecimal():
            raise ValueError('nondecimal start field')
        return {'state': 'present', 'start': start}
    except (UnicodeError, ValueError, IndexError) as error:
        return {'state': 'unreadable', 'error': f'malformed stat: {error}'}


def _wait_pidfd(descriptor: int, timeout_seconds: float) -> bool:
    poller = select.poll(); poller.register(descriptor, select.POLLIN)
    return bool(poller.poll(int(timeout_seconds * 1000)))


def recover_cleanup(run_dir: Path, failure_id: str, *, cleanup_ledger_sha256: str,
                    commitment_log: object, identity_reader=_process_identity,
                    host_reader=_host_identity, pidfd_open=_DEFAULT_PIDFD,
                    pidfd_send_signal=_DEFAULT_PIDFD, pidfd_wait=_wait_pidfd) -> dict:
    """Resolve one exact retained child through a held Linux pidfd."""
    run_dir = Path(run_dir).resolve()
    validate_commitment_log(commitment_log, run_dir)
    if not _hex(failure_id, 32):
        raise ValueError('cleanup failure id must be 32 lowercase hex characters')
    ledger, raw, failures, resolutions = _load_cleanup_ledger(run_dir)
    if hashlib.sha256(raw).hexdigest() != cleanup_ledger_sha256:
        raise ValueError('cleanup ledger does not match independently selected head digest')
    failure = failures.get(failure_id)
    if failure is None:
        raise ValueError('selected cleanup failure is absent from the anchored ledger')
    expected_resolution = resolutions.get(failure_id)
    if expected_resolution is not None:
        # Loading validated the exact failure digest, PID, and start binding.
        return {'record': expected_resolution, 'cleanup_ledger_sha256': hashlib.sha256(raw).hexdigest()}
    payload = failure['payload']; pid, expected = payload['pid'], payload['pid_start']
    if payload['identity'] != 'exact':
        raise ValueError('cleanup failure has no start identity; it is unrecoverable for this run')
    host = host_reader()
    if (not isinstance(host, dict) or not payload['boot_id'] or not payload['pid_namespace']
            or host.get('boot_id') != payload['boot_id']):
        raise ValueError('cleanup recovery runs on a different or unknown boot; refusing')
    if host.get('pid_namespace') != payload['pid_namespace']:
        raise ValueError('cleanup recovery runs in a different or unknown PID namespace; refusing')

    def resolve(outcome: str, pidfd: str, signal_state: str, wait: str) -> dict:
        resolution_payload = {'failure_id': failure_id, 'failure_digest': failure['record_digest'],
            'pid': pid, 'pid_start': expected, 'outcome': outcome,
            'pidfd': pidfd, 'signal': signal_state, 'wait': wait}
        record, head = _append_cleanup_record(run_dir, 'resolution', resolution_payload,
            expected_head=cleanup_ledger_sha256, commitment_log=commitment_log,
            event='recovery_resolution', identifier=failure_id)
        return {'record': record, 'cleanup_ledger_sha256': head}

    state = identity_reader(pid)
    if not isinstance(state, dict) or state.get('state') not in ('present', 'absent', 'unreadable'):
        raise ValueError('cleanup process identity reader returned malformed state')
    if state['state'] == 'unreadable':
        raise ValueError('cleanup process identity is unreadable; failure remains unresolved')
    if state['state'] == 'absent':
        return resolve('already_exited', 'not_needed', 'not_sent', 'confirmed_absent')
    current = state.get('start')
    if not isinstance(current, str) or not current:
        raise ValueError('cleanup process identity reader returned malformed start')
    if current != expected:
        # A PID cannot be reused while its original holder exists, even as a
        # zombie, in the same boot and PID namespace: this proves the exit.
        return resolve('original_exited_pid_reused', 'not_needed', 'not_sent', 'start_mismatch')
    open_pidfd = getattr(os, 'pidfd_open', None) if pidfd_open is _DEFAULT_PIDFD else pidfd_open
    send_pidfd = (getattr(signal, 'pidfd_send_signal', None)
                  if pidfd_send_signal is _DEFAULT_PIDFD else pidfd_send_signal)
    if open_pidfd is None or send_pidfd is None:
        raise ValueError('Linux pidfd recovery is unavailable; failure remains unresolved')
    descriptor = None; signal_state = 'SIGKILL'; outcome = 'pidfd_reaped'
    try:
        try:
            descriptor = open_pidfd(pid, 0)
        except (FileNotFoundError, ProcessLookupError):
            after = identity_reader(pid)
            if not isinstance(after, dict) or after.get('state') != 'absent':
                raise ValueError('process changed while opening pidfd; failure remains unresolved')
            return resolve('already_exited', 'not_needed', 'not_sent', 'confirmed_absent')
        held = identity_reader(pid)
        if not isinstance(held, dict) or held.get('state') == 'unreadable':
            raise ValueError('cleanup process identity became unreadable while pidfd held')
        if held.get('state') != 'present' or held.get('start') != expected:
            raise ValueError('cleanup PID identity changed while pidfd held')
        try:
            send_pidfd(descriptor, signal.SIGKILL, None, 0)
        except ProcessLookupError:
            signal_state = 'SIGKILL_error'; outcome = 'signal_error_reaped'
        except OSError:
            signal_state = 'SIGKILL_error'; outcome = 'signal_error_reaped'
        if not pidfd_wait(descriptor, 2.0):
            if signal_state == 'SIGKILL_error':
                raise ValueError('pidfd signal failed and target was not reaped')
            raise ValueError('matching cleanup process survived bounded pidfd recovery')
        return resolve(outcome, 'held', signal_state, 'pidfd_readable')
    finally:
        if descriptor is not None:
            os.close(descriptor)


def accept(run_dir: Path, *, reviewer: str, media_sha256: str, route_sha256: str,
           ffprobe_sha256: str, cleanup_ledger_sha256: str, commitment_log: object,
           pts_probe=None, content_probe=None) -> dict:
    run_dir = Path(run_dir).resolve()
    # Refuse before any child runs if a ledger change could not be committed externally.
    validate_commitment_log(commitment_log, run_dir)
    path = run_dir / "creative-run.json"
    if not _regular_nonsymlink(path):
        raise ValueError("execution receipt must be a regular non-symlink file")
    receipt = json.loads(_read_regular(path))
    if receipt.get("schema") != 2 or receipt.get("backend") != "linux-wine-k1-gamescope":
        raise ValueError("visual acceptance requires a Gamescope schema-2 run")
    if Path(receipt.get("run_dir", "")).resolve() != run_dir:
        raise ValueError("receipt run identity does not match selected directory")
    if receipt.get("ok") is not False or receipt.get("visual_review", {}).get("status") != "pending":
        raise ValueError("run is not pending visual acceptance")
    if not cleanup_state_clear(run_dir, cleanup_ledger_sha256):
        raise ValueError('unresolved or malformed FFprobe cleanup evidence blocks acceptance')
    if not execution_evidence_ready(receipt, require_completion=True):
        raise ValueError("completed run execution evidence is not ready for visual acceptance")
    continuous = receipt.get("media", {}).get("continuous")
    if not isinstance(continuous, dict) or not isinstance(continuous.get("path"), str):
        raise ValueError("receipt lacks continuous-media identity")
    media_path = Path(continuous["path"])
    media = media_path.resolve()
    if not _regular_nonsymlink(media_path) or not media.is_relative_to(run_dir):
        raise ValueError("continuous media is missing or outside the selected run")
    expected_sha = continuous.get('sha256')
    if expected_sha != media_sha256:
        raise ValueError("continuous media digest does not match receipt/reviewer selection")
    if (not isinstance(route_sha256, str) or route_sha256 != receipt['route_source']['sha256']):
        raise ValueError('selected route digest does not match launch-selected route source')
    if (not isinstance(ffprobe_sha256, str)
            or ffprobe_sha256 != receipt['cadence']['probe_tool']['sha256']):
        raise ValueError('selected FFprobe digest does not match launch-configured tool')
    if not reviewer.strip():
        raise ValueError("reviewer identity must be non-empty")
    pts_identity = receipt['cadence']['pts_artifact']
    pts_raw = _read_regular(Path(pts_identity['path']), maximum_bytes=16 * 1024 * 1024)
    if hashlib.sha256(pts_raw).hexdigest() != pts_identity['sha256']:
        raise ValueError('canonical PTS artifact changed before acceptance')
    pts_artifact = json.loads(pts_raw)
    content_identity = receipt['cadence']['content']['artifact']
    content_raw = _read_regular(Path(content_identity['path']), maximum_bytes=64 * 1024 * 1024)
    if hashlib.sha256(content_raw).hexdigest() != content_identity['sha256']:
        raise ValueError('capture content artifact changed before acceptance')
    content_artifact = json.loads(content_raw)
    frames = pts_artifact.get('frame_count') if isinstance(pts_artifact, dict) else None
    if type(frames) is not int or frames < 0:
        raise ValueError('canonical PTS artifact lacks a frame count')
    # Each re-probe's deadline scales with the recorded frame count (bounded maximum).
    deadline = probe_deadline_seconds(frames)
    if pts_probe is None:
        pts_probe = lambda path, tool, *, pass_fds: probe_frame_pts(
            path, tool, pass_fds=pass_fds, deadline_seconds=deadline)
    if content_probe is None:
        content_probe = lambda path, tool, *, pass_fds: probe_frame_content(
            path, tool, pass_fds=pass_fds, deadline_seconds=deadline)
    try:
        with tempfile.TemporaryDirectory(prefix='.creative-accept-', dir=run_dir) as temporary:
            source_identity, stable_fd, stable_identity = _stable_unlinked_fd(
                media_path, Path(temporary), expected_sha)
            tool = receipt['cadence']['probe_tool']
            tool_fd = None
            try:
                tool_fd, tool_identity, tool_sha = _verified_tool_fd(tool, ffprobe_sha256)
                probe_path = Path(f'/proc/self/fd/{stable_fd}')
                tool_path = Path(f'/proc/self/fd/{tool_fd}')
                observed_pts = pts_probe(probe_path, tool_path, pass_fds=(stable_fd, tool_fd))
                # Re-probe content over the same retained media and tool descriptors.
                observed_content = content_probe(probe_path, tool_path, pass_fds=(stable_fd, tool_fd))
                after_identity, stable_sha = _fd_identity_and_sha(stable_fd)
                if after_identity != stable_identity or stable_sha != expected_sha:
                    raise ValueError('stable accepted-master descriptor changed during fresh probe')
                after_tool_identity, after_tool_sha = _fd_identity_and_sha(tool_fd)
                if after_tool_identity != tool_identity or after_tool_sha != tool_sha:
                    raise ValueError('FFprobe executable descriptor changed during fresh probe')
            finally:
                if tool_fd is not None:
                    os.close(tool_fd)
                os.close(stable_fd)
            if _regular_identity_and_sha(media_path) != (source_identity, expected_sha):
                raise ValueError('public accepted master changed during fresh probe')
            if _regular_identity_and_sha(Path(tool['resolved_path'])) != (tool_identity, tool_sha):
                raise ValueError('configured FFprobe path changed during fresh probe')
    except ProbeCleanupError as error:
        raise _record_surviving_probe(run_dir, error, receipt['cadence']['probe_tool'],
                                      expected_head=cleanup_ledger_sha256,
                                      commitment_log=commitment_log) from error
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
        raise ValueError(f"canonical PTS re-probe failed: {error}") from error
    if observed_pts != pts_artifact.get('pts_seconds'):
        raise ValueError("canonical PTS artifact does not match a fresh accepted-master probe")
    if not isinstance(content_artifact, dict) or observed_content != content_artifact.get('frames'):
        raise ValueError('capture content artifact does not match a fresh accepted-master probe')
    execution_digest = execution_receipt_sha256(receipt)
    receipt["visual_review"] = {
        "status": "accepted", "reviewer": reviewer.strip(),
        "accepted_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "media_sha256": expected_sha,
        "execution_receipt_sha256": execution_digest,
        "pts_artifact_sha256": pts_identity['sha256'],
        "route_sha256": route_sha256,
        "ffprobe_sha256": ffprobe_sha256,
        "cleanup_ledger_sha256": cleanup_ledger_sha256,
        "content_artifact_sha256": content_identity['sha256'],
        "geometry_precondition_sha256": geometry_precondition_sha256(receipt['capture']['geometry_precondition']),
        "scope": REVIEW_SCOPE,
    }
    receipt["visual_review"]["acceptance_receipt_sha256"] = acceptance_receipt_sha256(receipt)
    receipt["ok"] = True
    if not verify_acceptance(receipt, route_sha256=route_sha256, ffprobe_sha256=ffprobe_sha256,
                             cleanup_ledger_sha256=cleanup_ledger_sha256):
        raise ValueError("accepted receipt provenance did not verify")
    payload = (json.dumps(receipt, indent=2) + "\n").encode()
    _atomic_regular_write(path, payload)
    published = json.loads(_read_regular(path))
    if not verify_acceptance(published, route_sha256=route_sha256, ffprobe_sha256=ffprobe_sha256,
                             cleanup_ledger_sha256=cleanup_ledger_sha256):
        raise ValueError("published acceptance receipt provenance did not verify")
    return published


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    parser.add_argument("--reviewer")
    parser.add_argument("--media-sha256")
    parser.add_argument("--route-sha256")
    parser.add_argument("--ffprobe-sha256")
    parser.add_argument("--cleanup-ledger-sha256",
                        help="last head this tool printed or appended to the commitment log")
    parser.add_argument("--cleanup-commitment-log",
                        help="existing operator-owned file outside the run directory")
    parser.add_argument("--recover-cleanup", metavar="FAILURE_ID")
    args = parser.parse_args(argv)
    if args.recover_cleanup:
        if any(value is not None for value in (args.reviewer, args.media_sha256,
                                                args.route_sha256, args.ffprobe_sha256)):
            parser.error('--recover-cleanup cannot be combined with acceptance arguments')
        if args.cleanup_ledger_sha256 is None or args.cleanup_commitment_log is None:
            parser.error('--recover-cleanup requires --cleanup-ledger-sha256 and --cleanup-commitment-log')
        try:
            resolved = recover_cleanup(Path(args.run_dir), args.recover_cleanup,
                                       cleanup_ledger_sha256=args.cleanup_ledger_sha256,
                                       commitment_log=args.cleanup_commitment_log)
        except CommitmentLogFailed as error:
            # The resolution is in the ledger and its head is on stderr; the log append failed.
            print(json.dumps({'ok': False, 'error': f'cleanup commitment log append failed: {error}',
                              'cleanup_ledger_sha256': error.cleanup_ledger_sha256}))
            return 1
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            print(json.dumps({'ok': False, 'error': str(error)}))
            return 1
        print(json.dumps({'ok': True, 'cleanup': resolved}))
        return 0
    if any(value is None for value in (args.reviewer, args.media_sha256,
                                       args.route_sha256, args.ffprobe_sha256,
                                       args.cleanup_ledger_sha256, args.cleanup_commitment_log)):
        parser.error('acceptance requires reviewer, media, route, ffprobe, cleanup-ledger SHA-256 '
                     'values and a cleanup commitment log')
    try:
        accepted = accept(Path(args.run_dir), reviewer=args.reviewer, media_sha256=args.media_sha256,
                          route_sha256=args.route_sha256, ffprobe_sha256=args.ffprobe_sha256,
                          cleanup_ledger_sha256=args.cleanup_ledger_sha256,
                          commitment_log=args.cleanup_commitment_log)
    except CleanupLedgerChanged as error:
        print(json.dumps({'ok': False, 'error': str(error), 'failure_id': error.failure_id,
                          'cleanup_ledger_sha256': error.cleanup_ledger_sha256,
                          'cleanup_ledger_head': error.head_line, 'survivor': error.survivor}))
        return 1
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        return 1
    print(json.dumps({"ok": accepted["ok"], "run_dir": accepted["run_dir"],
                      "media_sha256": accepted["visual_review"]["media_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
