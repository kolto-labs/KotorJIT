"""One authenticated attached owner; route interpretation stays in ScenarioRunner.

The owner is the only engine connection while it lives. It holds the
per-engine lock (under a user-private state directory) and the route lock
for its whole life, so Pioneer `step`/`commit`/`discard` for its route are
sent to it over the control socket instead of opening a second connection.

`stop` stops *execution*: the current wait is cancelled and no further step
is issued. It does not pause the game world; the game keeps running.
Speeds are the engine's configured multiplier, read back with
`kp.game_speed()`, not a measured simulation rate.
"""
from __future__ import annotations

import argparse
import contextlib
import hmac
import json
import math
import os
from pathlib import Path
import queue
import secrets
import socket
import socketserver
import subprocess
import sys
import threading
import time
import uuid

from . import pioneer as P, scenario as S
from .client import Channel
from .oracle import Watchdog
from .session import SessionInfo, channel_timeout

LIMIT = 65536
TERMINAL = {'completed', 'uncertain', 'execution_stopped', 'idle'}
SPEED_LABEL = 'configured multiplier'
OK_STATUSES = {'ok', 'expected_failure'}


class PlaybackError(Exception):
    pass


def paths(out):
    out = Path(out).resolve()
    return (out.with_name(out.name + '.playback.json'),
            out.with_name(out.name + '.playback-state.json'))


def private_read(path):
    path = Path(path)
    if path.is_symlink():
        raise PlaybackError('playback sidecar must not be a symlink')
    stat = path.stat()
    if os.name != 'nt' and (stat.st_uid != os.getuid() or stat.st_mode & 0o077):
        raise PlaybackError('playback sidecar must be owned by this user with mode600')
    if stat.st_size > 1024 * 1024:
        raise PlaybackError('playback sidecar exceeds limit')
    return json.loads(path.read_text())


def private_write(path, value):
    if Path(path).exists():
        private_read(path)
    P._atomic_write(Path(path), json.dumps(value, allow_nan=False).encode())


def state_root():
    """User-private state directory; never a shared temp directory."""
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    else:
        selected = os.environ.get('XDG_STATE_HOME')
        base = Path(selected) if selected and os.path.isabs(selected) else Path.home() / '.local' / 'state'
    return base / 'kpharness' / 'playback-locks'


def engine_lock_path(info):
    # All routes targeting the same local engine port contend before connect.
    root = state_root()
    root.parent.parent.mkdir(parents=True, exist_ok=True)
    for directory in (root.parent, root):
        if directory.is_symlink():
            raise PlaybackError('playback lock directory must not be a symlink')
        directory.mkdir(mode=0o700, exist_ok=True)
    if os.name != 'nt':
        stat = root.stat()
        if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
            raise PlaybackError(f'playback lock directory {root} is not private (need owner-only 0700)')
    return root / f'localhost-{int(info.port)}.lock'


@contextlib.contextmanager
def engine_guard(info):
    """Exclusive, non-blocking claim on one local engine port."""
    path = engine_lock_path(info)
    if path.is_symlink():
        raise PlaybackError('engine lock must not be a symlink')
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        try:
            P._lock_file(fd)
        except P.PioneerError as error:
            raise PlaybackError(f'another playback owner or Pioneer command holds engine '
                                f'127.0.0.1:{info.port}; stop it first') from error
        yield
    finally:
        os.close(fd)


def validate_speed(speed):
    if type(speed) not in (int, float) or not math.isfinite(speed) or not 0 < speed <= 16:
        raise PlaybackError('speed must be a finite configured multiplier in (0,16]')
    return float(speed)


def validate_options(sc, operation, until, speed, verify_current, restart):
    if operation not in {'play', 'fastforward'}:
        raise PlaybackError('unknown playback operation')
    if until is not None and (type(until) is not int or not 1 <= until <= len(sc.steps)):
        raise PlaybackError('until must identify a committed step')
    if operation == 'fastforward':
        validate_speed(speed)
    elif speed is not None:
        raise PlaybackError('play uses the route speed; use fastforward to choose a multiplier')
    if verify_current is not None and (not isinstance(verify_current, str) or not verify_current.strip()
                                       or len(verify_current.encode()) > 8192):
        raise PlaybackError('verify-current requires a bounded Lua predicate')
    if type(restart) is not bool:
        raise PlaybackError('restart must be boolean')
    if restart and verify_current:
        raise PlaybackError('choose initial-state restart or current-state verification')


def _cancel_is_read_only(step):
    """A cancelled wait/expect/sleep issued nothing the world must undo."""
    return step.kind in {'wait', 'expect_events'} or step.raw.get('do') == 'sleep'


class Owner:
    def __init__(self, out, info, channel):
        self.out, self.info, self.ch = Path(out).resolve(), info, channel
        self.route_bytes = self.out.read_bytes()
        self.sc = S.Scenario.parse(self.route_bytes.decode(), self.out)
        if self.sc.target != info.target:
            raise PlaybackError('route/session target mismatch')
        pending = P.load_pending(self.out)
        if pending and pending.phase != 'committed':
            raise PlaybackError('resolve pending authoring work before playback')
        self.proof = P.session_proof(info, channel)
        self.descriptor, self.journal = paths(self.out)
        self.previous = private_read(self.journal) if self.journal.exists() else None
        self.token = secrets.token_hex(32)
        self.owner_id = uuid.uuid4().hex
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.jobs = queue.Queue()
        self.shutdown = lambda: None
        self.port = None
        self.mutation_started = False
        # (transaction, boundary, initialized) of a step executed through
        # this owner and not yet committed or discarded.
        self.authored = None
        self.runner = self._make_runner()
        self.state = dict(schema=1, owner_id=self.owner_id, route=str(self.out),
            route_sha256=P._digest(self.route_bytes), runtime_identity=self.proof['identity'],
            authored_steps=len(self.sc.steps), completed_boundary=0, active_step=None,
            operation_state='idle', job_id=None, job_finished=None, requested_speed=None,
            effective_speed=None, observed_speed=None, speed_after_job=None,
            speed_label=SPEED_LABEL, world_uncertain=False, world_paused=False,
            last_error=None, results=[], authoring=None, initialized=False)

    def _make_runner(self):
        s = self.sc.settings
        runner = S.ScenarioRunner(self.sc, self.info, self.ch, log=lambda _: None,
            watchdog=Watchdog(P._SessionProbe(self.info), self.ch,
                hang_seconds=s['hang_seconds'], load_seconds=s['load_seconds'],
                load_tick_seconds=s['load_tick_seconds'],
                stagnation_seconds=s['stagnation_seconds'], log=lambda _: None))
        runner.cancel_event = self.cancel
        return runner

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.state))

    def publish(self, **updates):
        with self.lock:
            self.state.update(updates)
            data = self.snapshot()
        private_write(self.journal, data)

    def write_descriptor(self):
        private_write(self.descriptor, dict(schema=1, owner_id=self.owner_id,
            route=str(self.out), route_sha256=self.state['route_sha256'],
            port=self.port, token=self.token, runtime_identity=self.proof['identity']))

    def validate_session(self):
        if self.out.read_bytes() != self.route_bytes:
            raise PlaybackError('route changed while attached')
        if not P._same_session(self.proof, P.session_proof(self.info, self.ch)):
            raise PlaybackError('attached runtime changed')

    def validate_owner(self):
        self.validate_session()
        pending = P.load_pending(self.out)
        if pending and pending.phase != 'committed':
            raise PlaybackError('pending authoring work appeared while attached')

    def reload_route(self):
        """Adopt route bytes this owner itself committed."""
        data = self.out.read_bytes()
        if data == self.route_bytes:
            return
        self.route_bytes = data
        self.sc = S.Scenario.parse(data.decode(), self.out)
        self.runner = self._make_runner()
        with self.lock:
            self.state.update(route_sha256=P._digest(data), authored_steps=len(self.sc.steps))
        if self.port is not None:
            self.write_descriptor()

    # ------------------------------------------------------------ control --
    def command(self, request):
        operation = request.get('op')
        if operation == 'status':
            return self.snapshot()
        if operation == 'stop':
            self.cancel.set()
            with self.lock:
                self.state['operation_state'] = 'stop_pending'
            self.jobs.put(None)
            return self.snapshot()
        if operation in {'play', 'fastforward'}:
            speed = request.get('speed', 4.0) if operation == 'fastforward' else request.get('speed')
            validate_options(self.sc, operation, request.get('until'), speed,
                             request.get('verify_current'), request.get('restart', False))
            job = dict(request, speed=speed)
        elif operation == 'step':
            if not isinstance(request.get('step'), dict) or not request['step']:
                raise PlaybackError('step requires a JSON object step body')
            job = dict(request)
        elif operation == 'commit':
            if type(request.get('force', False)) is not bool:
                raise PlaybackError('force must be boolean')
            job = dict(request)
        elif operation == 'discard':
            job = dict(request)
        else:
            raise PlaybackError('unknown playback operation')
        with self.lock:
            allowed = {'idle', 'completed'} | ({'uncertain'} if operation in {'commit', 'discard'} else set())
            if self.state['operation_state'] not in allowed:
                raise PlaybackError('owner is busy or its world requires verified restoration')
            if self.state['world_uncertain'] and operation not in {'commit', 'discard'}:
                raise PlaybackError('world is uncertain; stop and restart from native initial-state load')
            if operation in {'play', 'fastforward'}:
                if self.state['initialized'] and (request.get('restart') or request.get('verify_current')):
                    raise PlaybackError('initial boundary options only apply to a new owner')
                job['until'] = request.get('until') or len(self.sc.steps)
                if self.state['initialized'] and job['until'] <= self.state['completed_boundary']:
                    raise PlaybackError('until must be after the completed boundary')
            if operation == 'step' and self.state['initialized'] and \
                    self.state['completed_boundary'] != len(self.sc.steps):
                raise PlaybackError('play to the end of the route before authoring a new step')
            job_id = uuid.uuid4().hex
            self.state.update(operation_state='queued', job_id=job_id, last_error=None)
        job['job_id'] = job_id
        self.jobs.put(job)
        return self.snapshot()

    # --------------------------------------------------------------- jobs --
    def initialize(self, request):
        if self.state['initialized']:
            return
        first_load = self.sc.steps[0].raw.get('do') in {'load_save', 'load_checkpoint'}
        verify = request.get('verify_current')
        restart = request.get('restart', False)
        if self.previous:
            if self.previous.get('route_sha256') != self.state['route_sha256'] and not restart:
                raise PlaybackError('previous cursor belongs to different route bytes; explicit restart required')
            if self.previous.get('world_uncertain') or self.previous.get('active_step') is not None:
                if not restart:
                    raise PlaybackError('previous operation is uncertain; initial-state restart required')
            if not restart and not verify:
                raise PlaybackError('reattachment requires verify-current or explicit initial-state restart')
        if restart and not first_load:
            raise PlaybackError('restart requires an initial native load/checkpoint step')
        if not first_load and not verify:
            raise PlaybackError('route needs an initial native load/checkpoint or verify-current predicate')
        boundary = 0
        if verify:
            if self.previous:
                if self.previous.get('runtime_identity') != self.state['runtime_identity']:
                    raise PlaybackError('previous cursor belongs to a foreign runtime')
                boundary = self.previous.get('completed_boundary')
                if type(boundary) is not int or not 0 <= boundary < len(self.sc.steps):
                    raise PlaybackError('previous completed boundary cannot be resumed')
            self.publish(active_step='verify-current', operation_state='verifying')
            result = self.runner.run_step(S.Step(0, {'do': 'assert_lua', 'code': verify, 'equals': True}))
            if result.status != 'ok':
                raise PlaybackError('current-state boundary predicate did not pass')
        self.publish(initialized=True, completed_boundary=boundary, active_step=None)

    def execute(self, request):
        self.validate_owner()
        self.initialize(request)
        start = self.state['completed_boundary']
        if request['until'] <= start:
            raise PlaybackError('until is not after verified boundary')
        original_setting = self.sc.settings['game_speed']
        requested = float(request['speed']) if request['op'] == 'fastforward' else float(original_setting)
        self.sc.settings['game_speed'] = requested
        self.publish(operation_state='running', requested_speed=requested, effective_speed=None,
                     observed_speed=None, speed_after_job=None, speed_label=SPEED_LABEL)
        outcome = 'completed'
        try:
            # From here the speed policy may write to the engine.
            self.mutation_started = True
            with self.runner.attached_execution(self.validate_owner) as ownership:
                # Publish only what the engine reads back, never the request.
                observed = self.runner._read_execution_speed()
                self.publish(observed_speed=observed)
                if not math.isclose(observed, requested, rel_tol=0.0, abs_tol=1e-6):
                    raise PlaybackError(f'speed readback {observed:g}x does not match requested '
                                        f'{requested:g}x ({SPEED_LABEL}); no step was issued')
                self.publish(effective_speed=observed)
                for step in self.sc.steps[start:request['until']]:
                    if self.cancel.is_set():
                        outcome = 'execution_stopped'
                        break
                    self.validate_owner()
                    self.publish(active_step=step.index, operation_state='running', intent='issued')
                    result = self.runner.run_step(step)
                    self.validate_owner()
                    results = self.state['results'] + [result.to_dict()]
                    if result.status == 'cancelled' and _cancel_is_read_only(step):
                        # Stop request: the step never completed and issued
                        # no world mutation, so the boundary still holds.
                        self.publish(results=results, active_step=None, intent='cancelled')
                        outcome = 'execution_stopped'
                        break
                    if result.status not in OK_STATUSES:
                        self.publish(results=results, world_uncertain=True, last_error=result.detail,
                                     intent='unresolved')
                        outcome = 'uncertain'
                        break
                    if step.raw.get('do') == 'speed':
                        ownership['retain'] = True
                    self.publish(results=results, completed_boundary=step.index,
                                 active_step=None, intent='completed')
        finally:
            self.sc.settings['game_speed'] = original_setting
            try:
                after = self.runner._read_execution_speed()
            except Exception:  # noqa: BLE001 - report unknown, never guess
                after = None
            self.publish(speed_after_job=after)
        if outcome == 'completed' and self.cancel.is_set():
            outcome = 'execution_stopped'
        self.publish(operation_state=outcome)

    def author_step(self, request):
        self.validate_session()
        before = P.load_pending(self.out)
        self.publish(operation_state='running', active_step='authoring', authoring=None)
        try:
            result = P.execute_pending_locked(self.out, self.ch, self.info, request['step'])
        except Exception:
            after = P.load_pending(self.out)
            if after is not None and after.phase == 'issued' and (
                    before is None or before.provenance.get('transaction') != after.provenance.get('transaction')):
                self.mutation_started = True
            raise
        pending = P.load_pending(self.out)
        self.authored = (pending.provenance['transaction'], self.state['completed_boundary'],
                         self.state['initialized'])
        self.publish(operation_state='idle', active_step=None,
                     authoring=dict(op='step', result=result.to_dict(),
                                    transaction=pending.provenance['transaction']))

    def author_commit(self, request):
        self.validate_session()
        pending = P.load_pending(self.out)
        try:
            appended = P.commit_pending_locked(self.out, self.ch, self.info, force=request.get('force', False))
        finally:
            self.reload_route()
        updates = dict(operation_state=self.state['operation_state'] if self.state['world_uncertain'] else 'idle',
                       active_step=None, authoring=dict(op='commit', appended=appended))
        authored, self.authored = self.authored, None
        if authored and pending and authored[0] == pending.provenance.get('transaction') and authored[2]:
            index = pending.provenance.get('index')
            if (pending.result.get('status') in OK_STATUSES and index == authored[1] + 1
                    and index == len(self.sc.steps)):
                updates['completed_boundary'] = index
            else:
                updates.update(world_uncertain=True, operation_state='uncertain',
                               last_error='committed step did not complete; cursor no longer describes the world')
        self.publish(**updates)

    def author_discard(self, request):
        pending = P.load_pending(self.out)
        P.clear_pending(self.out)
        authored, self.authored = self.authored, None
        updates = dict(active_step=None, authoring=dict(op='discard'),
                       operation_state=self.state['operation_state'] if self.state['world_uncertain'] else 'idle')
        if authored and authored[2] and pending and pending.phase != 'committed':
            updates.update(world_uncertain=True, operation_state='uncertain',
                           last_error='discarded step ran live; its effects were not undone')
        self.publish(**updates)

    def run_job(self, request):
        self.mutation_started = False
        handlers = {'play': self.execute, 'fastforward': self.execute, 'step': self.author_step,
                    'commit': self.author_commit, 'discard': self.author_discard}
        try:
            handlers[request['op']](request)
        except Exception as error:  # noqa: BLE001 - the journal must say what happened
            detail = f'{type(error).__name__}: {error}'
            if self.mutation_started:
                self.publish(operation_state='uncertain', world_uncertain=True, last_error=detail)
            else:
                # Rejected before any engine write: the world is unchanged.
                self.publish(operation_state='uncertain' if self.state['world_uncertain'] else 'idle',
                             active_step=None, last_error=detail)
        finally:
            self.publish(job_finished=request['job_id'])

    def worker(self):
        try:
            while True:
                request = self.jobs.get()
                if request is None:
                    break
                self.run_job(request)
                if self.cancel.is_set():
                    break
        finally:
            self.ch.close()
            # Execution stopped; the game itself keeps running (no world pause).
            self.publish(operation_state='execution_stopped', detached=True, active_step=None)
            try:
                if private_read(self.descriptor).get('owner_id') == self.owner_id:
                    self.descriptor.unlink()
            except (OSError, ValueError):
                pass
            self.shutdown()


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(2)
        try:
            raw = self.rfile.readline(LIMIT + 1)
            if len(raw) > LIMIT or not raw.endswith(b'\n'):
                raise PlaybackError('invalid control message')
            request = json.loads(raw)
            token = request.pop('token', None)
            if not isinstance(token, str) or not hmac.compare_digest(token, self.server.owner.token):
                raise PlaybackError('control authentication failed')
            reply = {'ok': True, 'result': self.server.owner.command(request)}
        except Exception as error:
            reply = {'ok': False, 'error': str(error)}
        self.wfile.write(json.dumps(reply).encode() + b'\n')


def serve(out, info):
    # The per-engine lock precedes the only engine connection, across routes.
    with engine_guard(info), P.route_lock(Path(out)):
        channel = Channel('127.0.0.1', info.port, timeout=channel_timeout())
        channel.connect()
        try:
            owner = Owner(out, info, channel)
            with socketserver.TCPServer(('127.0.0.1', 0), Handler) as server:
                server.owner = owner
                owner.shutdown = server.shutdown
                owner.port = server.server_address[1]
                owner.write_descriptor()
                worker = threading.Thread(target=owner.worker, daemon=True)
                worker.start()
                try:
                    server.serve_forever(poll_interval=0.05)
                finally:
                    owner.cancel.set(); owner.jobs.put(None); worker.join(timeout=5)
        finally:
            channel.close()


def control(out, request):
    descriptor, _ = paths(out)
    d = private_read(descriptor)
    if (d.get('schema') != 1 or d.get('route') != str(Path(out).resolve())
            or d.get('route_sha256') != P._digest(Path(out).read_bytes())
            or type(d.get('port')) is not int or not 0 < d['port'] <= 65535
            or not isinstance(d.get('token'), str)):
        raise PlaybackError('stale or invalid playback descriptor')
    with socket.create_connection(('127.0.0.1', d['port']), timeout=2) as sock:
        sock.sendall(json.dumps(dict(request, token=d['token'])).encode() + b'\n')
        with sock.makefile('rb') as stream:
            raw = stream.readline(1024 * 1024)
    reply = json.loads(raw)
    if reply.get('ok') is not True:
        raise PlaybackError(reply.get('error', 'control request failed'))
    result = reply['result']
    if (result.get('owner_id') != d.get('owner_id')
            or result.get('runtime_identity') != d.get('runtime_identity')):
        raise PlaybackError('foreign playback owner response')
    return result


def start(out, info):
    descriptor, journal = paths(out)
    if descriptor.exists():
        # Never replace a live/stale descriptor or infer ownership by PID.
        return control(out, {'op': 'status'})
    with engine_guard(info), P.route_lock(Path(out)):
        pending = P.load_pending(Path(out))
        if pending and pending.phase != 'committed':
            raise PlaybackError('resolve pending edits before starting owner')
    environment = dict(os.environ)
    environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
    log_path = Path(out).with_name(Path(out).name + '.playback-owner.log')
    fd = os.open(log_path, os.O_CREAT | os.O_APPEND | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'ab') as log:
        process = subprocess.Popen([sys.executable, '-m', 'kpharness.playback', '--serve', str(Path(out).resolve())],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log, env=environment,
            start_new_session=True)
        process.stdin.write(json.dumps(info.to_dict()).encode())
        process.stdin.close()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if descriptor.exists():
            return control(out, {'op': 'status'})
        if process.poll() is not None:
            raise PlaybackError('playback owner failed to attach; inspect private owner log')
        time.sleep(.05)
    raise PlaybackError('owner startup outcome uncertain; inspect descriptor/log, do not blindly retry')


def status(out):
    descriptor, journal = paths(out)
    if descriptor.exists():
        try:
            return control(out, {'op': 'status'})
        except OSError:
            # A detaching owner writes its final journal, then removes the
            # descriptor, then exits. Only that completed exit falls back.
            if descriptor.exists():
                raise
    if journal.exists():
        return private_read(journal)
    return {'operation_state': 'not_attached', 'route': str(Path(out).resolve())}


def wait_job(out, job_id, timeout=600):
    """Poll status until this job finished. Never re-sends the request."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = status(out)
        if state.get('job_id') != job_id:
            raise PlaybackError('job identity changed while waiting')
        if state.get('job_finished') == job_id or state.get('detached') is True:
            return state
        time.sleep(.05)
    raise PlaybackError('job is still pending; request was not retried')


def author(out, request, timeout=600):
    """Send one Pioneer step/commit/discard to the attached owner and wait."""
    if request.get('op') not in {'step', 'commit', 'discard'}:
        raise PlaybackError('unknown authoring operation')
    accepted = control(out, request)
    return wait_job(out, accepted['job_id'], timeout=timeout)


def attached(out):
    """True when an owner descriptor exists for this route (live or stale)."""
    return paths(out)[0].exists()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serve', required=True)
    options = parser.parse_args()
    info = SessionInfo.from_dict(json.loads(sys.stdin.read(LIMIT)))
    try:
        serve(options.serve, info)
    except Exception as error:
        print(f'playback owner: {type(error).__name__}: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
