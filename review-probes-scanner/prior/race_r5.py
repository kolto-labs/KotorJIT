"""Brief symlink swaps: the real folder stays most of the time, the outside symlink appears for ~0.2 ms."""
import sys, os, json, hashlib, zipfile, shutil, threading, time, collections
from pathlib import Path
sys.dont_write_bytecode = True
exec(open('/home/brunner56/kp-live-20260922/review-probes-scanner/prior/race.py').read().split("rm(ROOT); ROOT.mkdir")[0])
ROOT.mkdir(parents=True, exist_ok=True)
def run(swap_dir, rounds, hold_real, hold_link, identical):
    base, src, prov = fresh('brief_' + swap_dir.replace('/', '_'))
    outside = base / 'outside'
    shutil.copytree(src / swap_dir, outside)
    if not identical:
        for p in outside.rglob('*'):
            if p.is_file(): p.write_bytes(b'-- OUTSIDE SECRET\n')
    link = src / swap_dir; real = src / (swap_dir + '.real')
    stop = threading.Event(); flips = [0]
    def flipper():
        while not stop.is_set():
            time.sleep(hold_real)
            try:
                os.rename(link, real); os.symlink(outside, link); time.sleep(hold_link)
                os.unlink(link); os.rename(real, link); flips[0] += 1
            except OSError: pass
    t = threading.Thread(target=flipper, daemon=True); t.start()
    oc = collections.Counter(); leaks = []
    try:
        for i in range(rounds):
            try:
                import io as _io, contextlib as _cl
                buf = _io.StringIO()
                with _cl.redirect_stdout(buf):
                    rc = B.main(['--source-root', str(src), '--out', str(base / f'out{i}'), '--provenance', str(prov)])
                res = json.loads(buf.getvalue())
                if rc == 0:
                    z = zipfile.ZipFile(res['zip']); blob = b''.join(z.read(n) for n in z.namelist())
                    if b'OUTSIDE' in blob: leaks.append(i); oc['BUILT_LEAK'] += 1
                    else: oc['BUILT_clean'] += 1
                else:
                    oc['JSON error: ' + res['error'].split(':')[0][:60]] += 1
            except BaseException as e:
                oc['ESCAPED main ' + type(e).__name__ + ': ' + str(e).split(':')[0][:60]] += 1
    finally:
        stop.set(); t.join()
        if os.path.islink(link): os.unlink(link)
        if real.exists() and not link.exists(): os.rename(real, link)
    print(swap_dir, 'identical' if identical else 'secret', f'flips={flips[0]}', dict(oc), 'leaks', leaks, flush=True)
run('scripts/harness/kpharness', 40, 0.004, 0.0002, identical=False)
rm(ROOT); print('cleanup done:', not ROOT.exists())
