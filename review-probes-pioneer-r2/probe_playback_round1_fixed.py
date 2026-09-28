#!/usr/bin/env python3
"""Adversarial probes for Pioneer Stage 0+5 (reviewer-owned, read-only on source).

Run: PYTHONPATH=<wt>/scripts/harness:<wt>/tools python3 probe_playback.py
Each probe prints PROBE <name>: <observations>. Uses the synthetic engine
from tools/kpharness_playback_test.py; no Wine/game.
"""
import json, os, signal, socket, subprocess, sys, time, unittest
from pathlib import Path

import kpharness_playback_test as T


def owner_pid(out):
    r = subprocess.run(['pgrep', '-f', f'kpharness.playback --serve {Path(out).resolve()}'],
                       capture_output=True, text=True)
    pids = [int(x) for x in r.stdout.split()]
    return pids[0] if pids else None


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # zombie?
    try:
        return Path(f'/proc/{pid}/stat').read_text().split()[2] != 'Z'
    except OSError:
        return False


def raw_control(PB, out, request):
    """Control request that skips the client-side route hash check."""
    d = PB.private_read(PB.paths(out)[0])
    with socket.create_connection(('127.0.0.1', d['port']), timeout=2) as s:
        s.sendall(json.dumps(dict(request, token=d['token'])).encode() + b'\n')
        return json.loads(s.makefile('rb').readline())


WAIT = '[[step]]\nwait = "phase"\nequals = "never"\ntimeout = 60\n'


class Probes(T.PlaybackCase):
    def kill_owner(self):
        pid = owner_pid(self.out)
        if pid and alive(pid):
            os.kill(pid, signal.SIGKILL)

    def test_a_accepted_but_different_readback_restore(self):
        self.engine.stop()
        self.engine = self.start_engine(clamp=3.0)
        self.info.port = self.engine.port
        self.write_route(T.lua_step('s1'))
        self.attach()
        state = self.play(op='fastforward', speed=8, verify_current='return true')
        print(f"PROBE A clamp: prior=2.0 op={state['operation_state']} observed={state['observed_speed']} "
              f"speed_after_job={state['speed_after_job']} engine_scale_now={self.engine.scale()} "
              f"world_uncertain={state['world_uncertain']}")

    def test_b_route_edit_blocks_stop(self):
        self.write_route(T.lua_step('s1'))
        self.attach()
        pid = owner_pid(self.out)
        with self.out.open('a') as f:
            f.write('# edited by user\n')
        try:
            self.PB.control(self.out, {'op': 'stop'})
            res = 'stop accepted'
        except Exception as e:  # noqa
            res = f'stop refused: {type(e).__name__}: {e}'
        time.sleep(1)
        print(f"PROBE B route-edit-then-stop: {res}; owner_alive={alive(pid)}; "
              f"descriptor={self.PB.paths(self.out)[0].exists()}")
        other = None
        try:
            other = self.write_route(T.lua_step('x'), self.root / 'other.toml')
            self.PB.start(other, self.info)
            print('PROBE B other route attach: succeeded')
        except Exception as e:  # noqa
            print(f'PROBE B other route attach while zombie owner: {type(e).__name__}: {e}')
        # Round 1 accidentally left the successfully attached second route
        # running.  This copy owns both cleanup paths explicitly.
        self.addCleanup(self.kill_owner)
        if other is not None:
            self.addCleanup(self.detach, other)

    def test_c_route_edit_during_fastforward_speed(self):
        self.write_route(WAIT)
        self.attach()
        self.PB.control(self.out, {'op': 'fastforward', 'speed': 12, 'verify_current': 'return true'})
        self.wait_state(lambda s: s.get('active_step') == 1)
        with self.out.open('a') as f:
            f.write('# edited\n')
        reply = raw_control(self.PB, self.out, {'op': 'stop'})
        deadline = time.monotonic() + 10
        while self.PB.paths(self.out)[0].exists() and time.monotonic() < deadline:
            time.sleep(.05)
        j = self.PB.private_read(self.PB.paths(self.out)[1])
        print(f"PROBE C route-edit mid-job then raw stop ok={reply.get('ok')}: engine_scale_now={self.engine.scale()} "
              f"(prior 2.0) speed_after_job={j.get('speed_after_job')} op={j.get('operation_state')} "
              f"last_error={j.get('last_error')!r}")

    def _signal_probe(self, sig, name):
        self.write_route(WAIT)
        self.attach()
        self.PB.control(self.out, {'op': 'fastforward', 'speed': 12, 'verify_current': 'return true'})
        self.wait_state(lambda s: s.get('active_step') == 1)
        pid = owner_pid(self.out)
        os.kill(pid, sig)
        deadline = time.monotonic() + 10
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(.05)
        desc = self.PB.paths(self.out)[0].exists()
        j = self.PB.private_read(self.PB.paths(self.out)[1])
        try:
            st = self.PB.status(self.out)
            st_res = st.get('operation_state')
        except Exception as e:  # noqa
            st_res = f'{type(e).__name__}: {e}'
        try:
            self.PB.start(self.out, self.info)
            re = 'reattach ok'
        except Exception as e:  # noqa
            re = f'{type(e).__name__}: {e}'
        lockfile = self.PB.engine_lock_path(self.info)
        print(f"PROBE {name}: owner_alive={alive(pid)} engine_scale_now={self.engine.scale()} (prior 2.0) "
              f"descriptor_left={desc} journal_op={j.get('operation_state')} journal_active={j.get('active_step')} "
              f"status={st_res!r} reattach={re!r} journal_has_prior_speed={'speed_before_job' in j}")
        if desc:
            # clean up for next test without touching source
            self.PB.paths(self.out)[0].unlink()

    def test_d_sigterm(self):
        self._signal_probe(signal.SIGTERM, 'D SIGTERM')

    def test_e_sigint(self):
        self._signal_probe(signal.SIGINT, 'E SIGINT')

    def test_f_sigkill(self):
        self._signal_probe(signal.SIGKILL, 'F SIGKILL')

    def test_g_journal_write_failure_kills_worker(self):
        self.write_route(T.lua_step('s1') + T.lua_step('s2'))
        self.attach()
        pid = owner_pid(self.out)
        self.play(verify_current='return true', until=1)
        journal = self.PB.paths(self.out)[1]
        os.chmod(journal, 0o644)
        try:
            job = self.PB.control(self.out, {'op': 'play'})
            print(f"PROBE G play accepted job={job['job_id'][:8]} state={job['operation_state']}")
        except Exception as e:  # noqa
            print(f'PROBE G play refused: {e}')
        time.sleep(2)
        st = self.PB.control(self.out, {'op': 'status'})
        stop = self.PB.control(self.out, {'op': 'stop'})
        time.sleep(3)
        print(f"PROBE G after journal chmod 644: status_op={st['operation_state']} stop_reply_op={stop['operation_state']} "
              f"owner_alive_3s_after_stop={alive(pid)} descriptor={self.PB.paths(self.out)[0].exists()}")
        os.chmod(journal, 0o600)
        self.addCleanup(self.kill_owner)

    def test_h_other_user_style_unauth(self):
        self.write_route(T.lua_step('s1'))
        self.attach()
        d = self.PB.private_read(self.PB.paths(self.out)[0])
        out = []
        for payload in (b'{"op":"stop"}\n', b'{"op":"stop","token":"' + b'0' * 64 + b'"}\n', b'[1]\n',
                        b'{"op":"status","token":' + json.dumps(d['token'][:-1]).encode() + b'}\n'):
            with socket.create_connection(('127.0.0.1', d['port']), timeout=3) as s:
                s.sendall(payload)
                out.append(json.loads(s.makefile('rb').readline()))
        # slow-loris: hold a connection open without a newline; does status still answer?
        hog = socket.create_connection(('127.0.0.1', d['port']), timeout=3)
        hog.sendall(b'{"op":')
        t0 = time.monotonic()
        try:
            self.PB.status(self.out); dt = f'{time.monotonic() - t0:.2f}s ok'
        except Exception as e:  # noqa
            dt = f'{type(e).__name__} after {time.monotonic() - t0:.2f}s'
        hog.close()
        print(f"PROBE H unauth replies={[r.get('error') for r in out]} still_attached={self.PB.paths(self.out)[0].exists()} "
              f"status_with_one_hog={dt}")

    def test_i_stop_when_uncertain_overwrites_state(self):
        self.write_route(T.lua_step('s1') + T.lua_step('fail x'))
        self.attach()
        state = self.play(verify_current='return true')
        self.PB.control(self.out, {'op': 'stop'})
        final = self.wait_state(lambda s: s.get('detached') is True)
        print(f"PROBE I stop after uncertain: pre={state['operation_state']} final_op={final['operation_state']} "
              f"final_world_uncertain={final['world_uncertain']}")

    def test_j_queued_job_then_stop_mutates(self):
        self.write_route(T.lua_step('s1') + T.lua_step('s2'))
        self.attach()
        before = len(self.engine.mutations())
        self.PB.control(self.out, {'op': 'play', 'verify_current': 'return true', 'until': 1})
        self.PB.control(self.out, {'op': 'stop'})
        final = self.wait_state(lambda s: s.get('detached') is True)
        muts = self.engine.mutations()[before:]
        print(f"PROBE J play-then-immediate-stop: final={final['operation_state']} boundary={final['completed_boundary']} "
              f"mutations={[(m['cmd'], (m.get('code') or '')[:12], m.get('scale')) for m in muts]}")



class Probes2(T.PlaybackCase):
    def test_k_descriptor_chmod_blocks_stop(self):
        self.write_route(T.lua_step('s1'))
        self.attach()
        pid = owner_pid(self.out)
        d = self.PB.paths(self.out)[0]
        os.chmod(d, 0o644)
        try:
            self.PB.control(self.out, {'op': 'stop'}); res = 'stop ok'
        except Exception as e:  # noqa
            res = f'{type(e).__name__}: {e}'
        # raw stop bypassing client checks: does the worker clean up despite 0644 descriptor?
        tok = json.loads(d.read_text())
        with socket.create_connection(('127.0.0.1', tok['port']), timeout=3) as s:
            s.sendall(json.dumps({'op': 'stop', 'token': tok['token']}).encode() + b'\n')
            s.makefile('rb').readline()
        time.sleep(3)
        print(f"PROBE K descriptor 0644: client stop -> {res}; after raw stop owner_alive={alive(pid)} "
              f"descriptor_left={d.exists()}")
        if pid and alive(pid):
            os.kill(pid, signal.SIGKILL)
        if d.exists():
            d.unlink()

    def test_l_concurrent_attach_same_route(self):
        import threading
        self.write_route(T.lua_step('s1'))
        results = []
        def go():
            try:
                results.append(('ok', self.PB.start(self.out, self.info)['owner_id'][:8]))
            except Exception as e:  # noqa
                results.append(('err', f'{type(e).__name__}: {e}'))
        ts = [threading.Thread(target=go) for _ in range(2)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.addCleanup(self.detach, self.out)
        owners = subprocess.run(['pgrep', '-f', f'kpharness.playback --serve {self.out.resolve()}'],
                                capture_output=True, text=True).stdout.split()
        print(f"PROBE L two concurrent attaches: {results}; live_owner_procs={len(owners)} "
              f"engine_connections={self.engine.connections()}")


if __name__ == '__main__':
    unittest.main(verbosity=1)
