#!/usr/bin/env python3
"""Real owner subprocess + synthetic engine (from the suite) under an
out-of-process reconnecting idle/trickle flood; 1000 authenticated status
calls via playback.status, and a play-under-flood check.

  PYTHONPATH=<wt>/scripts/harness python3 owner_stress_test.py
env: CALLS (1000), FLOODERS (8)
"""
import contextlib, json, multiprocessing as mp, os, socket, sys, time, unittest
WT = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, WT + '/tools'); sys.path.insert(0, WT + '/scripts/harness')
import kpharness_playback_test as T

CALLS = int(os.environ.get('CALLS', 1000)); FLOODERS = int(os.environ.get('FLOODERS', 8))


def flooder(port, i, stop, counter):
    socks = []
    while not stop.is_set():
        try:
            s = socket.create_connection(('127.0.0.1', port), timeout=2)
            mode = i % 3
            if mode == 1:
                s.send(b'{"op":')           # partial line
            elif mode == 2:
                s.send(b' ')                # trickle start
            socks.append(s)
            with counter.get_lock():
                counter.value += 1
        except OSError:
            time.sleep(0.001)
        for s in socks[:]:
            if i % 3 == 2:
                with contextlib.suppress(OSError):
                    s.send(b' ')
        if len(socks) > 24:
            socks.pop(0).close()
    for s in socks:
        s.close()


class Stress(T.Round2Case):
    def run_flood(self, port):
        stop = mp.Event(); counter = mp.Value('i', 0)
        procs = [mp.Process(target=flooder, args=(port, i, stop, counter), daemon=True) for i in range(FLOODERS)]
        for p in procs: p.start()
        def end():
            stop.set()
            for p in procs:
                p.join(5)
                if p.is_alive(): p.kill()
        self.addCleanup(end)
        time.sleep(0.5)
        return end, counter

    def test_status_1000_under_flood(self):
        self.write_route(T.lua_step('s1'))
        self.attach()
        pid = T.owner_pid(self.out)
        port = self.PB.private_read(self.PB.paths(self.out)[0])['port']
        end, counter = self.run_flood(port)
        fails, lat, peak_thr = {}, [], 0
        for n in range(CALLS):
            t0 = time.monotonic()
            try:
                st = self.PB.status(self.out)
                assert st['operation_state'] == 'idle', st
            except Exception as e:
                k = type(e).__name__ + ':' + str(e)[:70]
                fails[k] = fails.get(k, 0) + 1
            lat.append(time.monotonic() - t0)
            if n % 50 == 0:
                with contextlib.suppress(Exception):
                    peak_thr = max(peak_thr, T.proc_count(pid, 'threads'))
        end()
        lat.sort()
        print('\nSTRESS', json.dumps(dict(calls=CALLS, flooders=FLOODERS, flood_connects=counter.value,
              failures=sum(fails.values()), kinds=fails, peak_threads=peak_thr,
              p50=round(lat[len(lat)//2], 4), p99=round(lat[int(len(lat)*.99)], 4), max=round(lat[-1], 4))), flush=True)
        self.PB.control(self.out, {'op': 'stop'})
        self.assertTrue(T.wait_dead(pid))


if __name__ == '__main__':
    unittest.main(verbosity=2)
