#!/usr/bin/env python3
"""Pioneer playback owner regressions (Stage 0 + Stage 5), host-only.

Every test runs a real synthetic engine subprocess that speaks the harness
wire protocol over loopback TCP, and a real playback owner subprocess started
through ``playback.start``. Nothing here launches Wine, a game or a display.

  PYTHONPATH=scripts/harness python3 tools/kpharness_playback_test.py
"""
from __future__ import annotations

import contextlib
import json
import os
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / 'scripts/harness'
sys.path.insert(0, str(HARNESS))

ENGINE_NAME = 'kp-synth-eng'


# ------------------------------------------------------- synthetic engine --

def run_engine(port_file: str, log_file: str, initial_scale: float, clamp: float) -> None:
    """A single-process stand-in for the in-game listener."""
    try:
        with open('/proc/self/comm', 'w') as comm:
            comm.write(ENGINE_NAME)
    except OSError:
        pass
    lock = threading.Lock()
    world = dict(scale=initial_scale, tick=0, connections=0, started=time.monotonic())
    log = open(log_file, 'a', buffering=1)

    def record(entry):
        with lock:
            log.write(json.dumps(entry) + '\n')

    def lua(code):
        if code == 'return kp.game_speed()':
            return {'values': [world['scale']]}
        if code.startswith('-- fail'):
            raise RuntimeError('synthetic lua failure')
        if code == 'return true':
            return {'values': [True]}
        if code == 'return false':
            return {'values': [False]}
        if code.startswith('-- slow'):
            time.sleep(float(code.split()[2]))
        return {'values': [1]}

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            with lock:
                world['connections'] += 1
                conn = world['connections']
            record({'conn': conn, 'cmd': '<connect>'})
            for raw in self.rfile:
                request = json.loads(raw)
                cmd = request.get('cmd')
                record({'conn': conn, 'cmd': cmd, 'code': request.get('code'),
                        'scale': request.get('scale')})
                try:
                    if cmd == 'status':
                        result = dict(live=True, pid=os.getpid(), build='synthetic-k1', version='t',
                                      uptime_ms=int((time.monotonic() - world['started']) * 1000))
                    elif cmd == 'state':
                        with lock:
                            world['tick'] += 1
                            tick = world['tick']
                        result = dict(phase='gameplay', client_tick=tick, server_tick=tick,
                                      module='synth')
                    elif cmd == 'events':
                        result = {'items': [], 'seq': 0}
                    elif cmd in ('subscribe', 'unsubscribe', 'ping'):
                        result = {}
                    elif cmd == 'speed':
                        requested = float(request['scale'])
                        with lock:
                            world['scale'] = min(requested, clamp)
                        # Acknowledge what was asked; readback tells the truth.
                        result = {'scale': requested}
                    elif cmd == 'lua':
                        result = lua(request.get('code', ''))
                    else:
                        raise RuntimeError(f'unknown command {cmd}')
                    reply = {'id': request.get('id'), 'ok': True, 'result': result}
                except Exception as error:  # noqa: BLE001 - report to peer
                    reply = {'id': request.get('id'), 'ok': False, 'error': str(error)}
                self.wfile.write((json.dumps(reply) + '\n').encode())

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True
        allow_reuse_address = True

    with Server(('127.0.0.1', 0), Handler) as server:
        Path(port_file + '.tmp').write_text(str(server.server_address[1]))
        os.replace(port_file + '.tmp', port_file)
        server.serve_forever(poll_interval=0.05)


# ----------------------------------------------------------------- helpers --

def env_for(state_home: Path, repo_root: Path | None = None) -> dict:
    env = dict(os.environ)
    env['PYTHONPATH'] = str(HARNESS)
    env['XDG_STATE_HOME'] = str(state_home)
    env['KP_CHANNEL_TIMEOUT'] = '5'
    if repo_root is not None:
        env['KP_GAMESCOPE_REPO_ROOT'] = str(repo_root)
    return env


class Engine:
    def __init__(self, root: Path, scale: float = 2.0, clamp: float = 16.0):
        tag = f'engine-{time.monotonic_ns()}'
        self.port_file = root / f'{tag}.port'
        self.log_file = root / f'{tag}.log'
        self.process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), '--engine', str(self.port_file),
             str(self.log_file), str(scale), str(clamp)])
        # Generous: the shared hosts run at a high load average.
        deadline = time.monotonic() + 60
        while not self.port_file.exists():
            if time.monotonic() > deadline or self.process.poll() is not None:
                raise RuntimeError('synthetic engine did not start')
            time.sleep(0.02)
        self.port = int(self.port_file.read_text())

    def entries(self):
        if not self.log_file.exists():
            return []
        return [json.loads(line) for line in self.log_file.read_text().splitlines() if line]

    def connections(self):
        return sum(1 for e in self.entries() if e['cmd'] == '<connect>')

    def mutations(self):
        """Commands that could change the world: speed and non-readback Lua."""
        return [e for e in self.entries()
                if e['cmd'] == 'speed' or (e['cmd'] == 'lua' and e['code'] != 'return kp.game_speed()')]

    def lua_codes(self):
        return [e['code'] for e in self.entries()
                if e['cmd'] == 'lua' and e['code'] != 'return kp.game_speed()']

    def scale(self):
        with socket.create_connection(('127.0.0.1', self.port), timeout=5) as sock:
            sock.sendall(b'{"id":1,"cmd":"lua","code":"return kp.game_speed()"}\n')
            reply = json.loads(sock.makefile('rb').readline())
        return reply['result']['values'][0]

    def stop(self):
        self.process.terminate()
        self.process.wait(timeout=5)


def lua_step(tag: str, code: str = 'return 1') -> str:
    return f'[[step]]\ndo = "lua"\ncode = "-- {tag}\\n{code}"\n'


class PlaybackCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kpharness_playback_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state_home = self.root / 'state'
        self.state_home.mkdir(mode=0o700)
        self.previous_env = {k: os.environ.get(k) for k in ('XDG_STATE_HOME', 'KP_CHANNEL_TIMEOUT')}
        os.environ['XDG_STATE_HOME'] = str(self.state_home)
        os.environ['KP_CHANNEL_TIMEOUT'] = '5'
        self.addCleanup(self._restore_env)
        from kpharness import playback as PB, pioneer as P
        from kpharness.session import SessionInfo
        self.PB, self.P = PB, P
        self.engine = self.start_engine()
        self.info = SessionInfo(target='k1', staged=str(self.root), game_dir=str(self.root),
                                save_dir='', run_dir=str(self.root), display=0, port=self.engine.port,
                                xvfb_pid=0, launcher_pid=0, lock_path='', process_name=ENGINE_NAME,
                                build='host-build', started=time.time())
        self.out = self.root / 'route.toml'

    def start_engine(self, **kwargs):
        engine = Engine(self.root, **kwargs)
        self.addCleanup(engine.stop)
        return engine

    def _restore_env(self):
        for key, value in self.previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def write_route(self, body: str, path: Path | None = None) -> Path:
        path = path or self.out
        path.write_text('schema_version = 1\nname = "playback test"\ntarget = "k1"\n' + body)
        return path

    def attach(self, out: Path | None = None):
        out = out or self.out
        state = self.PB.start(out, self.info)
        self.addCleanup(self.detach, out)
        return state

    def detach(self, out: Path):
        descriptor, _ = self.PB.paths(out)
        if descriptor.exists():
            try:
                self.PB.control(out, {'op': 'stop'})
            except Exception:  # noqa: BLE001 - best effort cleanup
                pass
            deadline = time.monotonic() + 10
            while descriptor.exists() and time.monotonic() < deadline:
                time.sleep(0.05)

    def play(self, out=None, **request):
        out = out or self.out
        request.setdefault('op', 'play')
        state = self.PB.control(out, request)
        return self.PB.wait_job(out, state['job_id'], timeout=30)

    def wait_state(self, predicate, out=None, timeout=15):
        deadline = time.monotonic() + timeout
        state = None
        while time.monotonic() < deadline:
            state = self.PB.status(out or self.out)
            if predicate(state):
                return state
            time.sleep(0.05)
        self.fail(f'state never matched: {state}')


# ---------------------------------------------------------- Stage 0 tests --

class Stage0PlaybackTests(PlaybackCase):
    def test_one_engine_connection_and_ordered_steps(self):
        self.write_route(lua_step('s1') + lua_step('s2') + lua_step('s3') + lua_step('s4'))
        self.attach()
        state = self.play(verify_current='return true', until=3)
        self.assertEqual(state['operation_state'], 'completed', state)
        self.assertEqual(state['completed_boundary'], 3)
        self.assertEqual([r['status'] for r in state['results']], ['ok'] * 3)
        codes = [c for c in self.engine.lua_codes() if c.startswith('-- s')]
        self.assertEqual([c.split('\n')[0] for c in codes], ['-- s1', '-- s2', '-- s3'])
        state = self.play(until=4)
        self.assertEqual(state['completed_boundary'], 4)
        for _ in range(5):
            self.PB.status(self.out)
        self.assertEqual(self.engine.connections(), 1,
                         'owner must be the only engine connection; status goes over the control socket')

    def test_status_during_wait_then_stop_is_clean_execution_stop(self):
        self.write_route(lua_step('s1') +
                         '[[step]]\nwait = "phase"\nequals = "never"\ntimeout = 60\n' + lua_step('s3'))
        self.attach()
        job = self.PB.control(self.out, {'op': 'play', 'verify_current': 'return true'})
        running = self.wait_state(lambda s: s.get('active_step') == 2 and s['operation_state'] == 'running')
        self.assertEqual(running['job_id'], job['job_id'])
        self.assertEqual(running['completed_boundary'], 1)
        started = time.monotonic()
        self.PB.control(self.out, {'op': 'stop'})
        final = self.wait_state(lambda s: s.get('detached') is True)
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(final['operation_state'], 'execution_stopped')
        self.assertFalse(final['world_uncertain'], 'a cancelled read-only wait is not world uncertainty')
        self.assertEqual(final['completed_boundary'], 1)
        self.assertIsNone(final['active_step'])
        self.assertEqual(final['results'][-1]['status'], 'cancelled')
        self.assertFalse(final['world_paused'])
        self.assertNotIn('-- s3\nreturn 1', self.engine.lua_codes())
        self.assertEqual(self.engine.scale(), 2.0, 'prior speed restored on stop')
        self.assertFalse(self.PB.paths(self.out)[0].exists())

    def test_speed_restored_after_failed_step(self):
        self.write_route(lua_step('s1') +
                         '[[step]]\ndo = "assert_lua"\ncode = "return false"\nequals = true\n')
        self.attach()
        state = self.play(verify_current='return true')
        self.assertEqual(state['operation_state'], 'uncertain')
        self.assertTrue(state['world_uncertain'])
        self.assertEqual(state['completed_boundary'], 1)
        self.assertEqual(self.engine.scale(), 2.0)
        self.assertEqual(state['speed_after_job'], 2.0)

    def test_stale_descriptor_rejected_without_spawning(self):
        self.write_route(lua_step('s1'))
        descriptor, _ = self.PB.paths(self.out)
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        dead_port = listener.getsockname()[1]
        listener.close()
        self.PB.private_write(descriptor, dict(schema=1, owner_id='0' * 32, route=str(self.out.resolve()),
            route_sha256='f' * 64, port=dead_port, token='x' * 64, runtime_identity={}))
        # A job request still checks the route bytes client-side; status and
        # stop do not (review I2), so they fail on the dead port instead.
        with self.assertRaisesRegex(self.PB.PlaybackError, 'stale'):
            self.PB.control(self.out, {'op': 'play'})
        with self.assertRaises(OSError):
            self.PB.control(self.out, {'op': 'status'})
        with self.assertRaises((self.PB.PlaybackError, OSError)):
            self.PB.start(self.out, self.info)
        self.assertTrue(descriptor.exists(), 'never silently replace a stale descriptor')
        self.assertEqual(self.engine.connections(), 0)
        # A descriptor whose route hash matches but whose owner is gone fails
        # the connection without a retry and without a new owner.
        data = self.PB.private_read(descriptor)
        data['route_sha256'] = self.P._digest(self.out.read_bytes())
        self.PB.private_write(descriptor, data)
        with self.assertRaises(OSError):
            self.PB.control(self.out, {'op': 'status'})
        self.assertEqual(self.engine.connections(), 0)

    def test_second_owner_for_other_route_is_refused(self):
        self.write_route(lua_step('a1'))
        other = self.write_route(lua_step('b1'), self.root / 'other.toml')
        self.attach()
        with self.assertRaisesRegex(self.PB.PlaybackError, 'engine'):
            self.PB.start(other, self.info)
        self.assertFalse(self.PB.paths(other)[0].exists())
        self.assertEqual(self.engine.connections(), 1)

    def test_invalid_arguments_rejected_before_mutation(self):
        self.write_route(lua_step('s1') + lua_step('s2'))
        self.attach()
        before = len(self.engine.mutations())
        bad = [dict(op='fastforward', speed=0), dict(op='fastforward', speed=16.5),
               dict(op='fastforward', speed=-1), dict(op='fastforward', speed=True),
               dict(op='fastforward', speed='4'), dict(op='play', until=0),
               dict(op='play', until=3), dict(op='play', until=1.0), dict(op='play', restart='yes'),
               dict(op='play', restart=True, verify_current='return true'), dict(op='rewind')]
        for request in bad:
            with self.subTest(request=request):
                with self.assertRaises(self.PB.PlaybackError):
                    self.PB.control(self.out, request)
        self.assertEqual(len(self.engine.mutations()), before)
        state = self.PB.status(self.out)
        self.assertFalse(state['world_uncertain'])
        # Execution-time validation (no initial load, no verify predicate)
        # is also a rejection, not world uncertainty.
        state = self.play()
        self.assertEqual(state['operation_state'], 'idle', state)
        self.assertFalse(state['world_uncertain'])
        self.assertIn('verify-current', state['last_error'])
        self.assertEqual(len(self.engine.mutations()), before)
        state = self.play(verify_current='return true')
        self.assertEqual(state['operation_state'], 'completed')

    def test_failed_step_is_not_retried(self):
        self.write_route(lua_step('s1') + lua_step('fail boom') + lua_step('s3'))
        self.attach()
        state = self.play(verify_current='return true')
        self.assertEqual(state['operation_state'], 'uncertain')
        self.assertEqual(self.engine.lua_codes().count('-- fail boom\nreturn 1'), 1)
        self.assertNotIn('-- s3\nreturn 1', self.engine.lua_codes())
        with self.assertRaisesRegex(self.PB.PlaybackError, 'uncertain|busy'):
            self.PB.control(self.out, {'op': 'play'})
        self.assertEqual(self.engine.lua_codes().count('-- fail boom\nreturn 1'), 1)

    def test_engine_lock_lives_in_private_state_dir(self):
        path = self.PB.engine_lock_path(self.info)
        self.assertTrue(str(path).startswith(str(self.state_home)), path)
        self.assertFalse(str(path).startswith(tempfile.gettempdir() + '/kpharness-playback'))
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        os.chmod(path.parent, 0o755)
        try:
            with self.assertRaisesRegex(self.PB.PlaybackError, 'private'):
                self.PB.engine_lock_path(self.info)
        finally:
            os.chmod(path.parent, 0o700)

    def test_step_and_commit_route_through_attached_owner(self):
        self.write_route(lua_step('s1'))
        self.attach()
        state = self.play(verify_current='return true')
        self.assertEqual(state['completed_boundary'], 1)
        state = self.PB.author(self.out, {'op': 'step', 'step': {'do': 'lua', 'code': '-- new\nreturn 1'}})
        self.assertEqual(state['authoring']['result']['status'], 'ok', state)
        self.assertEqual(self.P.load_pending(self.out).phase, 'executed')
        state = self.PB.author(self.out, {'op': 'commit'})
        self.assertTrue(state['authoring']['appended'], state)
        self.assertIn('-- new', self.out.read_text())
        self.assertEqual(state['authored_steps'], 2)
        self.assertEqual(state['completed_boundary'], 2)
        self.assertEqual(self.PB.status(self.out)['route_sha256'], self.P._digest(self.out.read_bytes()))
        self.assertEqual(self.engine.connections(), 1)


class Stage0CliTests(PlaybackCase):
    def setUp(self):
        super().setUp()
        self.repo = self.root / 'repo'
        session_dir = self.repo / 'tmp' / 'k1_harness'
        session_dir.mkdir(parents=True)
        (session_dir / 'session.json').write_text(json.dumps(self.info.to_dict()))

    def cli(self, *args, timeout=60):
        return subprocess.run([sys.executable, '-m', 'kpharness.cli', 'pioneer', *args],
                              env=env_for(self.state_home, self.repo), capture_output=True,
                              text=True, timeout=timeout)

    def test_cli_play_status_stop_end_to_end(self):
        self.write_route(lua_step('s1') + lua_step('s2') + lua_step('s3'))
        self.addCleanup(self.detach, self.out)
        run = self.cli('play', '--out', str(self.out), '--verify-current', 'return true', '--until', '2')
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        self.assertEqual(json.loads(run.stdout)['completed_boundary'], 2)
        run = self.cli('fastforward', '--out', str(self.out), '--speed', '8')
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        state = json.loads(run.stdout)
        self.assertEqual(state['effective_speed'], 8.0)
        self.assertEqual(state['speed_label'], 'configured multiplier')
        run = self.cli('status', '--out', str(self.out))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['playback']['completed_boundary'], 3)
        run = self.cli('fastforward', '--out', str(self.out), '--speed', '17')
        self.assertNotEqual(run.returncode, 0)
        run = self.cli('stop', '--out', str(self.out))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('does not pause', run.stdout)
        self.wait_state(lambda s: s.get('detached') is True)
        self.assertEqual(self.engine.connections(), 1)
        self.assertEqual(self.engine.scale(), 2.0)

    def test_cli_step_without_owner_takes_engine_guard(self):
        self.write_route(lua_step('s1'))
        other = self.write_route('', self.root / 'other.toml')
        self.attach()
        run = self.cli('step', '--out', str(other), '{"do":"lua","code":"return 1"}')
        self.assertEqual(run.returncode, 1, run.stdout)
        self.assertIn('engine', run.stderr)
        self.assertEqual(self.engine.connections(), 1)
        self.assertIsNone(self.P.load_pending(other))

    def test_cli_step_commit_route_through_owner(self):
        self.write_route(lua_step('s1'))
        self.attach()
        self.play(verify_current='return true')
        run = self.cli('step', '--out', str(self.out), '{"do":"lua","code":"return 7"}')
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        run = self.cli('commit', '--out', str(self.out))
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        self.assertIn('return 7', self.out.read_text())
        self.assertEqual(self.engine.connections(), 1)


# ---------------------------------------------------------- Stage 5 tests --

class Stage5SpeedTests(PlaybackCase):
    def test_fastforward_reads_back_before_publishing_and_restores(self):
        self.write_route(lua_step('s1') + lua_step('s2'))
        self.attach()
        state = self.play(op='fastforward', speed=8, verify_current='return true')
        self.assertEqual(state['operation_state'], 'completed')
        self.assertEqual(state['requested_speed'], 8.0)
        self.assertEqual(state['effective_speed'], 8.0)
        self.assertEqual(state['speed_label'], 'configured multiplier')
        self.assertEqual(state['speed_after_job'], 2.0)
        self.assertEqual(self.engine.scale(), 2.0)
        entries = self.engine.entries()
        set_at = next(i for i, e in enumerate(entries) if e['cmd'] == 'speed' and e['scale'] == 8)
        step_at = next(i for i, e in enumerate(entries) if e['cmd'] == 'lua' and (e['code'] or '').startswith('-- s1'))
        self.assertTrue(any(e['cmd'] == 'lua' and e['code'] == 'return kp.game_speed()'
                            for e in entries[set_at + 1:step_at]), 'readback between set and first step')

    def test_acknowledged_but_not_applied_speed_is_not_published(self):
        self.engine.stop()
        self.engine = self.start_engine(clamp=3.0)
        self.info.port = self.engine.port
        self.write_route(lua_step('s1'))
        self.attach()
        state = self.play(op='fastforward', speed=8, verify_current='return true')
        self.assertNotEqual(state['effective_speed'], 8.0)
        self.assertEqual(state['observed_speed'], 3.0)
        self.assertEqual(state['operation_state'], 'uncertain')
        self.assertIn('readback', state['last_error'])
        self.assertNotIn('-- s1\nreturn 1', self.engine.lua_codes())

    def test_explicit_speed_step_keeps_its_setting(self):
        self.write_route(lua_step('s1') + '[[step]]\ndo = "speed"\nscale = 3.0\n' + lua_step('s3'))
        self.attach()
        state = self.play(op='fastforward', speed=6, verify_current='return true')
        self.assertEqual(state['operation_state'], 'completed')
        self.assertEqual(self.engine.scale(), 3.0)
        self.assertEqual(state['speed_after_job'], 3.0)

    def test_speed_restored_after_stop_during_fastforward(self):
        self.write_route('[[step]]\nwait = "phase"\nequals = "never"\ntimeout = 60\n')
        self.attach()
        self.PB.control(self.out, {'op': 'fastforward', 'speed': 12, 'verify_current': 'return true'})
        self.wait_state(lambda s: s.get('active_step') == 1)
        self.assertEqual(self.engine.scale(), 12.0)
        self.PB.control(self.out, {'op': 'stop'})
        final = self.wait_state(lambda s: s.get('detached') is True)
        self.assertEqual(final['operation_state'], 'execution_stopped')
        self.assertEqual(self.engine.scale(), 2.0)

    def test_speed_bounds_accept_upper_edge(self):
        self.write_route(lua_step('s1'))
        self.attach()
        state = self.play(op='fastforward', speed=16, verify_current='return true')
        self.assertEqual(state['effective_speed'], 16.0)
        self.assertEqual(self.engine.scale(), 2.0)


# ------------------------------------------- round 2 (review I1-I5, M2-M5) --
#
# Each test mirrors one reviewer probe (review-probes-pioneer/probe_playback.py)
# and asserts the actual ENGINE speed, not only journal fields. The synthetic
# engine starts at 2.0x, so 2.0 is always the prior speed.

WAIT_FOREVER = '[[step]]\nwait = "phase"\nequals = "never"\ntimeout = 60\n'


def owner_pid(out):
    found = subprocess.run(['pgrep', '-f', f'kpharness.playback --serve {Path(out).resolve()}'],
                           capture_output=True, text=True).stdout.split()
    return int(found[0]) if found else None


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        if Path(f'/proc/{pid}/stat').read_text().split()[2] != 'Z':
            return True
        # A zombie group leader can outlive its other threads' exit, and
        # those still hold the process's fds (and so its flocks). It is
        # only dead once it is the last task left.
        return len(os.listdir(f'/proc/{pid}/task')) > 1
    except OSError:
        return False


def wait_dead(pid, timeout=20):
    deadline = time.monotonic() + timeout
    while alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    return not alive(pid)


class Round2Case(PlaybackCase):
    def kill_owner(self, out=None):
        pid = owner_pid(out or self.out)
        if pid and alive(pid):
            os.kill(pid, 9)
            wait_dead(pid)

    def attach(self, out=None):
        # Registered first so it runs last: stop (detach) is tried first.
        self.addCleanup(self.kill_owner, out)
        return super().attach(out)

    def raw_control(self, request, out=None):
        """Control request that skips every client-side descriptor check."""
        descriptor = self.PB.paths(out or self.out)[0]
        data = json.loads(descriptor.read_text())
        with socket.create_connection(('127.0.0.1', data['port']), timeout=10) as sock:
            sock.sendall(json.dumps(dict(request, token=data['token'])).encode() + b'\n')
            return json.loads(sock.makefile('rb').readline())

    def fastforward_into_wait(self, speed=12):
        self.write_route(WAIT_FOREVER)
        self.attach()
        self.PB.control(self.out, {'op': 'fastforward', 'speed': speed, 'verify_current': 'return true'})
        self.wait_state(lambda s: s.get('active_step') == 1 and s.get('effective_speed') == float(speed))
        self.assertEqual(self.engine.scale(), float(speed))
        return owner_pid(self.out)


class Round2RestoreTests(Round2Case):
    def test_probe_a_readback_mismatch_restores_prior_engine_speed(self):
        # I1: the engine acks 8x but applies 3x. The owner holds the engine
        # lock, so it restores the prior speed regardless of the readback.
        self.engine.stop()
        self.engine = self.start_engine(clamp=3.0)
        self.info.port = self.engine.port
        self.write_route(lua_step('s1'))
        self.attach()
        state = self.play(op='fastforward', speed=8, verify_current='return true')
        self.assertEqual(self.engine.scale(), 2.0, 'engine left at the clamped speed')
        self.assertEqual(state['operation_state'], 'uncertain')
        self.assertEqual(state['observed_speed'], 3.0)
        self.assertEqual(state['speed_before_job'], 2.0)
        self.assertEqual(state['speed_after_job'], 2.0)
        self.assertFalse(state['speed_restore_owed'])

    def test_probe_b_route_edit_does_not_block_stop(self):
        # I2: stop and status do not depend on the route bytes.
        self.write_route(lua_step('s1'))
        self.attach()
        pid = owner_pid(self.out)
        with self.out.open('a') as stream:
            stream.write('# edited by user\n')
        self.assertIn(self.PB.status(self.out)['operation_state'], {'idle'})
        self.PB.control(self.out, {'op': 'stop'})
        self.assertTrue(wait_dead(pid), 'owner still alive after stop')
        self.assertFalse(self.PB.paths(self.out)[0].exists())
        other = self.write_route(lua_step('x'), self.root / 'other.toml')
        self.attach(other)
        self.assertEqual(self.engine.scale(), 2.0)

    def test_probe_c_route_edit_mid_job_still_restores_speed(self):
        # I3: a route edit makes validate_owner fail; the restore must not
        # depend on it.
        pid = self.fastforward_into_wait()
        with self.out.open('a') as stream:
            stream.write('# edited\n')
        # Raw stop, as in the probe: isolates I3 from the client check (I2).
        self.raw_control({'op': 'stop'})
        self.assertTrue(wait_dead(pid))
        self.assertEqual(self.engine.scale(), 2.0, 'route edit skipped the speed restore')
        journal = self.PB.private_read(self.PB.paths(self.out)[1])
        self.assertEqual(journal['speed_after_job'], 2.0)
        self.assertFalse(journal['speed_restore_owed'])


class Round2SignalTests(Round2Case):
    def _signal_restores(self, signum):
        pid = self.fastforward_into_wait()
        before = self.PB.private_read(self.PB.paths(self.out)[1])
        os.kill(pid, signum)
        self.assertTrue(wait_dead(pid), 'owner ignored the signal')
        self.assertEqual(self.engine.scale(), 2.0)
        self.assertEqual(before.get('speed_before_job'), 2.0, 'prior speed journaled before the first write')
        self.assertTrue(before.get('speed_restore_owed'))
        self.assertFalse(self.PB.paths(self.out)[0].exists(), 'descriptor left behind')
        journal = self.PB.private_read(self.PB.paths(self.out)[1])
        self.assertTrue(journal['detached'])
        self.assertEqual(journal['operation_state'], 'execution_stopped')
        self.assertIn(signal_name(signum), journal['stop_reason'])

    def test_probe_d_sigterm_behaves_like_stop(self):
        self._signal_restores(15)

    def test_sighup_behaves_like_stop(self):
        self._signal_restores(1)

    def test_probe_f_sigkill_then_reclaim_restores_recorded_speed(self):
        # I4: SIGKILL cannot be handled. Reclaim takes both locks, which
        # proves the owner is dead, and restores the journaled prior speed.
        pid = self.fastforward_into_wait()
        os.kill(pid, 9)
        self.assertTrue(wait_dead(pid))
        self.assertEqual(self.engine.scale(), 12.0)
        self.assertTrue(self.PB.paths(self.out)[0].exists())
        report = self.PB.reclaim(self.out, self.info)
        self.assertEqual(self.engine.scale(), 2.0)
        self.assertTrue(report['descriptor_removed'])
        self.assertEqual(report['speed_restored'], 2.0)
        self.assertFalse(self.PB.paths(self.out)[0].exists())
        journal = self.PB.private_read(self.PB.paths(self.out)[1])
        self.assertTrue(journal['world_uncertain'], 'owner died mid-job')
        self.assertFalse(journal['speed_restore_owed'])
        # The next owner refuses to resume from an uncertain cursor.
        self.attach()
        state = self.play(verify_current='return true')
        self.assertEqual(state['operation_state'], 'idle')
        self.assertIn('restart', state['last_error'])
        self.assertEqual(self.engine.scale(), 2.0)

    def test_reclaim_refused_while_owner_alive(self):
        self.write_route(lua_step('s1'))
        self.attach()
        before = self.engine.connections()
        with self.assertRaisesRegex(self.PB.PlaybackError, 'stop'):
            self.PB.reclaim(self.out, self.info)
        self.assertTrue(self.PB.paths(self.out)[0].exists())
        self.assertEqual(self.engine.connections(), before)
        self.assertEqual(self.PB.status(self.out)['operation_state'], 'idle')

    def test_reclaim_never_restores_on_a_different_game_process(self):
        pid = self.fastforward_into_wait()
        os.kill(pid, 9)
        self.assertTrue(wait_dead(pid))
        with self.assertRaisesRegex(self.PB.PlaybackError, 'reclaim'):
            self.PB.status(self.out)
        self.engine.stop()
        self.engine = self.start_engine(scale=5.0)
        self.info.port = self.engine.port
        report = self.PB.reclaim(self.out, self.info)
        self.assertIs(report['speed_restored'], False)
        self.assertEqual(report['speed_before_job'], 2.0)
        self.assertEqual([e for e in self.engine.entries() if e['cmd'] == 'speed'], [])
        self.assertEqual(self.engine.scale(), 5.0)


class Round2CleanupTests(Round2Case):
    def test_probe_g_unwritable_journal_exits_owner(self):
        # I5: a journal that cannot be written ends the owner; it never
        # keeps serving a false state.
        self.write_route(lua_step('s1') + lua_step('s2'))
        self.attach()
        pid = owner_pid(self.out)
        self.play(verify_current='return true', until=1)
        journal = self.PB.paths(self.out)[1]
        os.chmod(journal, 0o644)
        self.addCleanup(os.chmod, journal, 0o600)
        try:
            self.PB.control(self.out, {'op': 'play'})
        except (self.PB.PlaybackError, OSError):
            pass
        self.assertTrue(wait_dead(pid), 'owner kept serving with an unwritable journal')
        self.assertFalse(self.PB.paths(self.out)[0].exists())
        self.assertEqual(self.engine.scale(), 2.0)
        self.assertNotIn('-- s2\nreturn 1', self.engine.lua_codes())

    def test_probe_k_tampered_descriptor_mode_still_detaches(self):
        # I5: cleanup survives a descriptor whose mode was changed.
        pid = self.fastforward_into_wait()
        descriptor = self.PB.paths(self.out)[0]
        os.chmod(descriptor, 0o644)
        with self.assertRaisesRegex(self.PB.PlaybackError, 'mode600'):
            self.PB.control(self.out, {'op': 'stop'})
        self.raw_control({'op': 'stop'})
        self.assertTrue(wait_dead(pid), 'owner alive after stop with a tampered descriptor')
        self.assertFalse(descriptor.exists())
        self.assertEqual(self.engine.scale(), 2.0)

    def test_probe_h_idle_connection_does_not_block_status(self):
        # M3: one idle control connection must not stall status or stop.
        self.write_route(lua_step('s1'))
        self.attach()
        data = self.PB.private_read(self.PB.paths(self.out)[0])
        hog = socket.create_connection(('127.0.0.1', data['port']), timeout=10)
        self.addCleanup(hog.close)
        hog.sendall(b'{"op":')
        started = time.monotonic()
        self.assertEqual(self.PB.status(self.out)['operation_state'], 'idle')
        self.assertLess(time.monotonic() - started, 1.5)
        for payload in (b'{"op":"stop"}\n', b'{"op":"stop","token":"' + b'0' * 64 + b'"}\n'):
            with socket.create_connection(('127.0.0.1', data['port']), timeout=10) as sock:
                sock.sendall(payload)
                self.assertEqual(json.loads(sock.makefile('rb').readline())['error'],
                                 'control authentication failed')
        self.assertTrue(self.PB.paths(self.out)[0].exists())
        self.assertEqual(self.engine.scale(), 2.0)

    def test_owner_is_not_a_child_of_the_caller(self):
        # M2: the caller reaps what it spawns; the owner is not its child.
        self.write_route(lua_step('s1'))
        self.attach()
        pid = owner_pid(self.out)
        status = Path(f'/proc/{pid}/status').read_text()
        parent = int(next(line.split()[1] for line in status.splitlines() if line.startswith('PPid:')))
        self.assertNotEqual(parent, os.getpid())
        children = subprocess.run(['pgrep', '-P', str(os.getpid())], capture_output=True, text=True).stdout.split()
        self.assertNotIn(str(pid), children)


def proc_count(pid, what):
    if what == 'threads':
        status = Path(f'/proc/{pid}/status').read_text()
        return int(next(line.split()[1] for line in status.splitlines() if line.startswith('Threads:')))
    return len(os.listdir(f'/proc/{pid}/fd'))


class Round3AdmissionTests(Round2Case):
    """I6: unauthenticated sockets cannot exhaust owner threads or block control."""

    FLOOD = 64

    def slots(self):
        return getattr(self.PB, 'CONTROL_SLOTS', 16)

    def flood(self, port, count):
        """Open `count` idle sockets at once; half send a partial line."""
        import select
        socks = []
        for _ in range(count):
            sock = socket.socket()
            self.addCleanup(sock.close)
            sock.setblocking(False)
            sock.connect_ex(('127.0.0.1', port))
            socks.append(sock)
        waiting, deadline = list(socks), time.monotonic() + 10
        while waiting and time.monotonic() < deadline:
            _, ready, _ = select.select([], waiting, [], 0.1)
            waiting = [sock for sock in waiting if sock not in ready]
        for index, sock in enumerate(socks):
            if index % 2:
                with contextlib.suppress(OSError):
                    sock.send(b'{"op":')  # partial line, never finished
        return socks

    def sampled(self, pid, action):
        """Run `action` while sampling the owner's peak threads and fds."""
        peak = {'threads': 0, 'fds': 0}
        done = threading.Event()

        def sample():
            while not done.is_set():
                with contextlib.suppress(OSError, StopIteration):
                    for what in peak:
                        peak[what] = max(peak[what], proc_count(pid, what))
                time.sleep(0.01)

        sampler = threading.Thread(target=sample, daemon=True)
        sampler.start()
        try:
            action()
            time.sleep(0.5)
        finally:
            done.set()
            sampler.join()
        return peak['threads'], peak['fds']

    def test_idle_flood_keeps_threads_bounded_and_control_working(self):
        self.write_route(lua_step('s1'))
        self.attach()
        pid = owner_pid(self.out)
        data = self.PB.private_read(self.PB.paths(self.out)[0])
        base_threads, base_fds = self.sampled(pid, lambda: None)
        threads, fds = self.sampled(pid, lambda: self.flood(data['port'], self.FLOOD))
        # +2: a handler that is finishing while its replacement starts.
        self.assertLessEqual(threads, base_threads + self.slots() + 2,
                             f'{threads} owner threads after {self.FLOOD} idle sockets')
        self.assertLessEqual(fds, base_fds + self.slots() + 2,
                             f'{fds} owner fds after {self.FLOOD} idle sockets')
        started = time.monotonic()
        self.assertEqual(self.PB.status(self.out)['operation_state'], 'idle')
        self.assertLess(time.monotonic() - started, 3.0)
        # Refill to the limit, then stop must still land.
        self.flood(data['port'], self.FLOOD)
        started = time.monotonic()
        self.PB.control(self.out, {'op': 'stop'})
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertTrue(wait_dead(pid), 'owner alive after stop during an idle flood')
        self.assertFalse(self.PB.paths(self.out)[0].exists())
        self.assertEqual(self.engine.scale(), 2.0)

    def test_trickling_client_is_dropped_by_total_deadline(self):
        # A client that sends one byte at a time never trips a per-read
        # timeout; the pre-auth deadline covers the whole request line.
        self.write_route(lua_step('s1'))
        self.attach()
        data = self.PB.private_read(self.PB.paths(self.out)[0])
        sock = socket.create_connection(('127.0.0.1', data['port']), timeout=10)
        self.addCleanup(sock.close)
        started = time.monotonic()
        closed = False
        while time.monotonic() - started < 4.0:
            try:
                sock.sendall(b' ')
            except OSError:
                closed = True
                break
            sock.settimeout(0.3)
            try:
                if sock.recv(4096) is not None:
                    closed = True
                    break
            except socket.timeout:
                pass
        self.assertTrue(closed, 'trickling client kept its connection past the deadline')
        self.assertLess(time.monotonic() - started, 2.5)
        self.assertEqual(self.PB.status(self.out)['operation_state'], 'idle')


class Round4ReadEvictTests(unittest.TestCase):
    """M1 (round 3 review): the read -> admit gap never runs a command whose
    reply is then dropped. In-process: real ControlServer and Handler, a fake
    owner, and one hook that holds the gap open inside `admitted()`."""

    TOKEN = 't' * 64

    def setUp(self):
        from kpharness import playback as PB
        self.PB = PB
        self.executed = []
        executed, token = self.executed, self.TOKEN

        class FakeOwner:
            def command(self, request):
                executed.append(request.get('op'))
                return {'op': request.get('op')}
        FakeOwner.token = token
        self.original_admitted = PB.ControlServer.admitted
        self.addCleanup(setattr, PB.ControlServer, 'admitted', self.original_admitted)

        self.server = PB.ControlServer(('127.0.0.1', 0), PB.Handler)
        self.server.owner = FakeOwner()
        thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01},
                                  daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]

    def hook(self, before):
        original = self.original_admitted

        def admitted(server, request):
            before(server, request)
            return original(server, request)
        self.PB.ControlServer.admitted = admitted

    def connect(self):
        sock = socket.create_connection(('127.0.0.1', self.port), timeout=5)
        self.addCleanup(sock.close)
        return sock

    def reply_of(self, sock):
        sock.settimeout(5)
        return sock.makefile('rb').readline()

    def test_eviction_during_widened_gap_keeps_the_reply(self):
        # The reviewer's race: the legitimate client is the oldest slot, the
        # handler sits in the gap, then 15 idle sockets and a 17th connect
        # force an eviction. It must not pick the client whose line arrived.
        self.hook(lambda server, request: time.sleep(0.3))
        legit = self.connect()
        legit.sendall(json.dumps({'op': 'play', 'token': self.TOKEN}).encode() + b'\n')
        time.sleep(0.05)
        idle = [self.connect() for _ in range(self.PB.CONTROL_SLOTS - 1)]
        time.sleep(0.05)
        self.connect()  # forces _evict_one
        raw = self.reply_of(legit)
        time.sleep(0.5)  # past the widened gap, so a late command() is seen
        # Invariant: a command that ran always gets its reply.
        if self.executed:
            self.assertTrue(raw, f'command ran {self.executed} but the reply was dropped')
        self.assertEqual(json.loads(raw)['ok'], True, raw)
        self.assertEqual(self.executed, ['play'])
        del idle

    def test_socket_evicted_before_admission_never_runs_the_command(self):
        # Forces the other order: eviction wins the guard first (as when it
        # peeked before the line landed). The handler must see that and skip.
        def evict_this(server, request):
            with server._guard:
                server._idle.pop(request, None)
                with contextlib.suppress(OSError):
                    request.shutdown(socket.SHUT_RDWR)
        self.hook(evict_this)
        legit = self.connect()
        legit.sendall(json.dumps({'op': 'play', 'token': self.TOKEN}).encode() + b'\n')
        raw = self.reply_of(legit)
        time.sleep(0.2)
        self.assertEqual(raw, b'')
        self.assertEqual(self.executed, [], 'an evicted connection still ran its command')

    def test_control_turns_an_empty_reply_into_a_playback_error(self):
        temp = tempfile.TemporaryDirectory(prefix='kpharness_playback_r4_')
        self.addCleanup(temp.cleanup)
        out = Path(temp.name) / 'route.toml'
        out.write_text('schema_version = 1\n')
        listener = socket.create_server(('127.0.0.1', 0))
        self.addCleanup(listener.close)

        def accept_and_close():
            conn, _ = listener.accept()
            with conn:
                conn.recv(65536)
        threading.Thread(target=accept_and_close, daemon=True).start()
        self.PB.private_write(self.PB.paths(out)[0], {
            'schema': 1, 'route': str(out.resolve()), 'port': listener.getsockname()[1],
            'token': self.TOKEN, 'owner_id': 'x', 'runtime_identity': 'y'})
        with self.assertRaisesRegex(self.PB.PlaybackError, 'without a reply'):
            self.PB.control(out, {'op': 'status'})


class Round2CliTests(Round2Case):
    def setUp(self):
        super().setUp()
        self.repo = self.root / 'repo'
        session_dir = self.repo / 'tmp' / 'k1_harness'
        session_dir.mkdir(parents=True)
        (session_dir / 'session.json').write_text(json.dumps(self.info.to_dict()))

    def cli(self, *args, timeout=120):
        return self.raw_cli('pioneer', *args, timeout=timeout)

    def raw_cli(self, *args, timeout=120):
        return subprocess.run([sys.executable, '-m', 'kpharness.cli', *args],
                              env=env_for(self.state_home, self.repo), capture_output=True,
                              text=True, timeout=timeout)

    def test_exec_refused_while_owner_holds_engine(self):
        # M5: exec/reply/state/events take the engine lock.
        self.write_route(lua_step('s1'))
        self.attach()
        for args in (('exec', '--target', 'k1', 'return 1'), ('state', '--target', 'k1'),
                     ('events', '--target', 'k1'), ('reply', '--target', 'k1', '0')):
            with self.subTest(args=args):
                run = self.raw_cli(*args)
                self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
                self.assertIn('engine', run.stderr)
        self.assertEqual(self.engine.connections(), 1)

    def test_exec_without_owner_still_works(self):
        run = self.raw_cli('exec', '--target', 'k1', 'return 1')
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_cli_reclaim_after_sigkill(self):
        self.write_route(WAIT_FOREVER)
        self.attach()
        self.PB.control(self.out, {'op': 'fastforward', 'speed': 12, 'verify_current': 'return true'})
        self.wait_state(lambda s: s.get('active_step') == 1 and s.get('effective_speed') == 12.0)
        pid = owner_pid(self.out)
        os.kill(pid, 9)
        self.assertTrue(wait_dead(pid))
        run = self.cli('stop', '--out', str(self.out))
        self.assertEqual(run.returncode, 1)
        self.assertIn('reclaim', run.stderr)
        run = self.cli('reclaim', '--out', str(self.out))
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        self.assertEqual(json.loads(run.stdout)['speed_restored'], 2.0)
        self.assertEqual(self.engine.scale(), 2.0)


def signal_name(signum):
    import signal as _signal
    return _signal.Signals(signum).name


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--engine':
        run_engine(sys.argv[2], sys.argv[3], float(sys.argv[4]), float(sys.argv[5]))
        raise SystemExit(0)
    unittest.main(verbosity=2)
