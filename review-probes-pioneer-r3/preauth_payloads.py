"""Pre-auth parse cost: complete-but-huge hostile lines against the real Handler."""
import json, socket, sys, threading, time
sys.path.insert(0, '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness')
from kpharness import playback as PB
class O:
    token = 't'*64
    def command(self, r): return {'ok': 1}
srv = PB.ControlServer(('127.0.0.1', 0), PB.Handler); srv.owner = O()
threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]
L = PB.LIMIT
cases = {
 'deep_nesting': b'[' * (L - 2) + b'\n',
 'huge_int': b'{"op":' + b'9' * (L - 20) + b'}\n',
 'many_keys': (b'{' + b','.join(b'"k%d":1' % i for i in range(7000)) + b'}')[:L-1] + b'\n',
 'long_string': b'{"token":"' + b'a' * (L - 20) + b'"}\n',
 'exact_limit': b'x' * (L - 1) + b'\n',
 'over_limit': b'x' * L + b'\n',
}
for name, line in cases.items():
    t0 = time.monotonic()
    with socket.create_connection(('127.0.0.1', port), timeout=5) as s:
        s.sendall(line); reply = s.makefile('rb').readline()
    print(f'{name:14s} len={len(line):6d} {time.monotonic()-t0:.4f}s reply={reply[:70]!r}')
print('threads_after', threading.active_count())
srv.shutdown(); srv.server_close()
