#!/usr/bin/env python3
"""In-process stress of playback.ControlServer (read-only on source).

Runs the real ControlServer + Handler with a fake owner, so the code under
test is unmodified. Instrumentation only wraps socket.shutdown to record
evictions that hit a closed socket, and optionally widens the window between
the handler's recv and admitted() (WIDEN env, seconds) to prove it exists.

usage: inproc_stress.py CALLS FLOOD_THREADS [WIDEN]
"""
import contextlib, json, os, socket, sys, threading, time
sys.path.insert(0, '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness')
from kpharness import playback as PB

CALLS = int(sys.argv[1]); FLOODERS = int(sys.argv[2]); WIDEN = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0

class FakeOwner:
    token = 't' * 64
    def command(self, request):
        return {'owner_id': 'x', 'op': request.get('op')}

closed_evictions = []
evictions = [0]
orig_evict = PB.ControlServer._evict_one
def evict(self):
    with self._guard:
        cands = [s for s in self._idle if s.fileno() == -1]
    if cands:
        closed_evictions.append(len(cands))
    evictions[0] += 1
    return orig_evict(self)
PB.ControlServer._evict_one = evict

if WIDEN:
    orig_admitted = PB.ControlServer.admitted
    def admitted(self, request):
        time.sleep(WIDEN)  # line already consumed from the kernel buffer
        return orig_admitted(self, request)
    PB.ControlServer.admitted = admitted

server = PB.ControlServer(('127.0.0.1', 0), PB.Handler)
server.owner = FakeOwner()
port = server.server_address[1]
t = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
t.start()

stop = threading.Event()
flood_conns = [0]
def flooder(i):
    socks = []
    while not stop.is_set():
        try:
            s = socket.create_connection(('127.0.0.1', port), timeout=2)
            if i % 2:
                with contextlib.suppress(OSError):
                    s.send(b'{"op":')
            socks.append(s); flood_conns[0] += 1
        except OSError:
            pass
        if len(socks) > 32:
            socks.pop(0).close()
    for s in socks:
        s.close()

threads = [threading.Thread(target=flooder, args=(i,), daemon=True) for i in range(FLOODERS)]
for th in threads: th.start()
time.sleep(0.5)

fails = {}; lat = []
for n in range(CALLS):
    start = time.monotonic()
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=5) as sock:
            sock.sendall(json.dumps({'op': 'status', 'token': FakeOwner.token}).encode() + b'\n')
            raw = sock.makefile('rb').readline(1 << 20)
        reply = json.loads(raw)
        if reply.get('ok') is not True:
            raise RuntimeError(reply)
    except Exception as e:
        key = type(e).__name__ + ':' + str(e)[:60]
        fails[key] = fails.get(key, 0) + 1
    lat.append(time.monotonic() - start)
stop.set()
for th in threads: th.join(5)
server.shutdown(); server.server_close()
lat.sort()
print(json.dumps(dict(calls=CALLS, flooders=FLOODERS, widen=WIDEN, flood_connects=flood_conns[0],
    evict_calls=evictions[0], evict_saw_closed_socket=len(closed_evictions), failures=sum(fails.values()),
    failure_kinds=fails, p50=round(lat[len(lat)//2], 4), p99=round(lat[int(len(lat)*.99)], 4), max=round(lat[-1], 4)), indent=1))
