"""Deterministic: eviction after the handler consumed the line but before admitted().
Real ControlServer/Handler. Only hook: sleep WIDEN inside admitted() (before the
original body) to hold the recv->admitted window open; everything else unmodified."""
import json, socket, sys, threading, time
sys.path.insert(0, '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness')
from kpharness import playback as PB
WIDEN = float(sys.argv[1]) if len(sys.argv) > 1 else 0.3
TOKEN = 't'*64; executed = []
class O:
    token = TOKEN
    def command(self, r): executed.append(r.get('op')); return {'op': r.get('op')}
orig = PB.ControlServer.admitted
def admitted(self, req):
    time.sleep(WIDEN); return orig(self, req)
PB.ControlServer.admitted = admitted
srv = PB.ControlServer(('127.0.0.1', 0), PB.Handler); srv.owner = O()
threading.Thread(target=srv.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True).start()
port = srv.server_address[1]
# legit client first (oldest), then 15 idle sockets fill the rest of the slots
legit = socket.create_connection(('127.0.0.1', port), timeout=5)
legit.sendall(json.dumps({'op': 'play', 'token': TOKEN}).encode() + b'\n')
time.sleep(0.05)  # handler has recv'd the line and is inside the widened window
idle = [socket.create_connection(('127.0.0.1', port)) for _ in range(15)]
time.sleep(0.05)
trigger = socket.create_connection(('127.0.0.1', port))  # 17th: forces _evict_one
t0 = time.monotonic(); raw = legit.makefile('rb').readline()
time.sleep(WIDEN + 0.2)
print(json.dumps(dict(widen=WIDEN, legit_reply=raw.decode(errors='replace'), reply_wait=round(time.monotonic()-t0, 3),
                      executed=executed)))
for s in idle + [trigger, legit]: s.close()
srv.shutdown(); srv.server_close()
