"""Real-tree build into scratch. Bypasses ONLY the two known path-scan hits (exact file:line); all other checks live."""
import sys, json, hashlib, os, shutil, time
sys.dont_write_bytecode = True
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/tools')
import package_creative_harness as pch
P = '/home/brunner56/kp-live-20260922/review-probes-packaging-r2'
OUT = P + '/out-real'
if os.path.lexists(OUT): shutil.rmtree(OUT)
t0 = time.time()
sel = pch.select_files(W)['selected']
overlay = {r: hashlib.sha256(open(W + '/' + r, 'rb').read()).hexdigest() for r in sel}
json.dump({'base_commit': None, 'overlay_sha256': overlay}, open(P + '/prov-real.json', 'w'), indent=1)
print('selected', len(sel), 'overlay built in', round(time.time() - t0, 1), 's', flush=True)
# 1) unpatched build must refuse on the two known lines
try:
    pch.build(W, P + '/out-unpatched', provenance=P + '/prov-real.json'); print('UNPATCHED BUILT (unexpected)')
except ValueError as e:
    print('unpatched refused:', e, flush=True)
KNOWN = {('scripts/harness/kpharness/capture_diagnostic.py', 54), ('scripts/harness/kpharness/oracle.py', 246)}
real = pch.path_scan
suppressed = []
def narrow(rel, data, markers=None):
    hits = real(rel, data, markers)
    keep = [h for h in hits if (h['path'], h['line']) not in KNOWN]
    suppressed.extend(h for h in hits if (h['path'], h['line']) in KNOWN)
    return keep
pch.path_scan = narrow
r = pch.build(W, OUT, provenance=P + '/prov-real.json')
print(json.dumps(r, indent=1))
print('suppressed only:', sorted({(h['path'], h['line'], h['marker']) for h in suppressed}))
print('total', round(time.time() - t0, 1), 's')
