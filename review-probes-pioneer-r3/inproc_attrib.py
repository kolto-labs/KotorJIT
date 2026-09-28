"""Attribute legit-client failures under a multi-process idle flood (no widening).
Real ControlServer/Handler; fake owner counts command() executions.
Instrumentation: wraps _evict_one to log evicted sockets that had already been
read (bytes consumed) and TCPServer.shutdown_request no-slot closes."""
import contextlib, json, multiprocessing as mp, os, socket, sys, threading, time
sys.path.insert(0, '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness')
from kpharness import playback as PB
CALLS, FLOODERS = int(sys.argv[1]), int(sys.argv[2])
TOKEN = 't'*64
executed = []
class O:
    token = TOKEN
    def command(self, r):
        executed.append(r.get('n')); return {'n': r.get('n')}
noslot = [0]
orig_ps = PB.ControlServer.process_request
def process_request(self, request, addr):
    before = self._slots._value
    return orig_ps(self, request, addr)
base_shut = PB.socketserver.TCPServer.shutdown_request
def flooder(port, i, stop):
    socks = []
    while not stop.is_set():
        try:
            s = socket.create_connection(('127.0.0.1', port), timeout=2)
            if i % 2: s.send(b'{"op":')
            socks.append(s)
        except OSError: time.sleep(0.001)
        if len(socks) > 24: socks.pop(0).close()
if __name__ == '__main__':
    srv = PB.ControlServer(('127.0.0.1', 0), PB.Handler); srv.owner = O()
    threading.Thread(target=srv.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True).start()
    port = srv.server_address[1]
    stop = mp.Event()
    ps = [mp.Process(target=flooder, args=(port, i, stop), daemon=True) for i in range(FLOODERS)]
    for p in ps: p.start()
    time.sleep(1)
    fails = {}; failed_ns = []
    for n in range(CALLS):
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=5) as s:
                s.sendall(json.dumps({'op': 'play', 'n': n, 'token': TOKEN}).encode() + b'\n')
                raw = s.makefile('rb').readline()
            if json.loads(raw)['result']['n'] != n: raise RuntimeError('mismatch')
        except Exception as e:
            k = type(e).__name__; fails[k] = fails.get(k, 0) + 1; failed_ns.append(n)
    stop.set(); [p.join(3) or (p.is_alive() and p.kill()) for p in ps]
    time.sleep(0.5)
    ex = set(executed)
    print(json.dumps(dict(calls=CALLS, flooders=FLOODERS, failures=len(failed_ns), kinds=fails,
        failed_but_command_executed=[n for n in failed_ns if n in ex])))
    srv.shutdown(); srv.server_close()
