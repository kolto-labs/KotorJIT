#!/usr/bin/env python3
"""Pioneer playback owner regressions (Stage 0 + Stage 5), host-only.

Every test runs a real synthetic engine subprocess that speaks the harness
wire protocol over loopback TCP, and a real playback owner subprocess started
through ``playback.start``. Nothing here launches Wine, a game or a display.

  PYTHONPATH=scripts/harness python3 tools/kpharness_playback_test.py
"""
from __future__ import annotations

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
        deadline = time.monotonic() + 10
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
        with self.assertRaisesRegex(self.PB.PlaybackError, 'stale'):
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


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--engine':
        run_engine(sys.argv[2], sys.argv[3], float(sys.argv[4]), float(sys.argv[5]))
        raise SystemExit(0)
    unittest.main(verbosity=2)
