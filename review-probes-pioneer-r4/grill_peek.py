"""Round-4 reviewer probe: attack read_request_line's MSG_PEEK loop.
Real ControlServer/Handler, fake owner. No hooks unless stated."""
import json, os, resource, socket, sys, threading, time
sys.path.insert(0, os.environ.get('KPH', '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness'))
from kpharness import playback as PB
TOKEN = 't' * 64; executed = []
class O:
    token = TOKEN
    def command(self, r): executed.append(r.get('op')); return {'op': r.get('op')}
srv = PB.ControlServer(('127.0.0.1', 0), PB.Handler); srv.owner = O()
threading.Thread(target=srv.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True).start()
port = srv.server_address[1]
def line(op): return json.dumps({'op': op, 'token': TOKEN}).encode() + b'\n'
def conn():
    s = socket.create_connection(('127.0.0.1', port), timeout=5)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1); return s
def reply(s):
    s.settimeout(5); return s.makefile('rb').readline()
def cpu(): r = resource.getrusage(resource.RUSAGE_SELF); return r.ru_utime + r.ru_stime
out = {}

# 1. two segments with a pause (split mid-token, and split right before newline)
for name, cut in (('split_mid', 20), ('split_before_nl', -1)):
    executed.clear(); s = conn(); L = line('play')
    s.sendall(L[:cut]); time.sleep(0.3); s.sendall(L[cut:])
    out[name] = dict(reply=reply(s).decode(), executed=list(executed)); s.close()

# 2. pipelined: two lines in one segment -> only the first runs, parsed exactly
executed.clear(); s = conn(); s.sendall(line('play') + line('status'))
r = reply(s); time.sleep(0.2)
out['pipelined'] = dict(reply=r.decode(), executed=list(executed)); s.close()

# 2b. first line ends in segment 2, segment 2 also carries a second line
executed.clear(); s = conn(); L = line('play')
s.sendall(L[:10]); time.sleep(0.2); s.sendall(L[10:] + line('status'))
r = reply(s); time.sleep(0.2)
out['split_plus_pipelined'] = dict(reply=r.decode(), executed=list(executed)); s.close()

# 3. partial line then close (FIN) -> no command
executed.clear(); s = conn(); s.sendall(line('play')[:30]); time.sleep(0.1); s.shutdown(socket.SHUT_WR)
r = reply(s); time.sleep(0.2)
out['partial_then_fin'] = dict(reply=r.decode(), executed=list(executed)); s.close()

# 4. trickle 1 byte / 20 ms, never a newline: must be refused at ~1.0s, low CPU
executed.clear(); s = conn(); c0 = cpu(); t0 = time.monotonic(); stop = threading.Event()
def trickle():
    try:
        while not stop.is_set():
            s.send(b'x'); time.sleep(0.02)
    except OSError: pass
th = threading.Thread(target=trickle, daemon=True); th.start()
r = reply(s); t1 = time.monotonic(); stop.set(); th.join(); c1 = cpu()
out['trickle_no_newline'] = dict(reply=r.decode(), refused_after_s=round(t1 - t0, 3),
                                 process_cpu_s=round(c1 - c0, 3), executed=list(executed)); s.close()

# 5. trickle a real line 1 byte / 5 ms so it completes inside 1 s -> runs once
executed.clear(); s = conn(); L = line('play'); c0 = cpu(); t0 = time.monotonic()
for b in L: s.send(bytes([b])); time.sleep(0.005)
r = reply(s); out['trickle_full_line'] = dict(reply=r.decode(), wall_s=round(time.monotonic() - t0, 3),
    process_cpu_s=round(cpu() - c0, 3), bytes=len(L), executed=list(executed)); s.close()

# 6. slowloris past the deadline: line completes at ~1.4 s -> refused, not run
executed.clear(); s = conn(); L = line('play'); t0 = time.monotonic(); step = 1.4 / len(L)
got = []
def rd(): got.append((reply(s), time.monotonic() - t0))
rt = threading.Thread(target=rd); rt.start()
for b in L:
    try: s.send(bytes([b]))
    except OSError: break
    time.sleep(step)
rt.join(); time.sleep(0.2)
out['slow_past_deadline'] = dict(reply=got[0][0].decode(), reply_at_s=round(got[0][1], 3), executed=list(executed)); s.close()

# 7. idle connection, no bytes: CPU while it waits for the 1 s deadline
executed.clear(); s = conn(); c0 = cpu(); t0 = time.monotonic(); r = reply(s)
out['idle_no_bytes'] = dict(reply=r.decode(), refused_after_s=round(time.monotonic() - t0, 3),
                            process_cpu_s=round(cpu() - c0, 3)); s.close()

# 8. short recv after peek (fake socket): recv returns fewer bytes than peeked
class Short:
    def __init__(s): s.buf = bytearray(line('play'))
    def settimeout(s, t): pass
    def recv(s, n, flags=0):
        if flags & socket.MSG_PEEK: return bytes(s.buf[:n])
        k = min(n, 5); b = bytes(s.buf[:k]); del s.buf[:k]; return b
try:
    v = PB.read_request_line(Short(), time.monotonic() + 1); out['short_recv_fake'] = dict(returned=repr(v))
except Exception as e: out['short_recv_fake'] = dict(raised=f'{type(e).__name__}: {e}')

# 9. exactly LIMIT bytes incl newline accepted-at-read; LIMIT+1 refused
for name, n in (('limit_exact', PB.LIMIT), ('limit_plus1', PB.LIMIT + 1)):
    executed.clear(); s = conn(); body = b'{"op":"x","token":"' + TOKEN.encode() + b'","p":"'
    pad = n - len(body) - 3; s.sendall(body + b'a' * pad + b'"}\n')
    out[name] = dict(sent=len(body) + pad + 3, reply=reply(s).decode()[:80], executed=list(executed)); s.close()

srv.shutdown(); srv.server_close()
for k, v in out.items(): print(k, json.dumps(v))
