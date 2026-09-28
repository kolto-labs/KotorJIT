import json, glob
from pathlib import Path
ALL = {'fresh': [], 'dup': [], 'dupI': [], 'dupP': []}
diag_set = ['fresh60','r30_k0','r30_k1','r20_k0','r20_k1','r20_k2','r50','r58','r3']
for f in sorted(glob.glob('cal/*.json')):
    d = json.load(open(f)); n = d['name']; L = d['labels']
    fr = [m for _, k, t, m in L if k == 'fresh']; du = [(m, t, i) for i, k, t, m in L if k == 'dup']
    dI = [x for x in du if x[1] == 'I']; Ikeys = [i for i, k, t, m in L if t == 'I']
    print(f"{n:13s} fresh n={len(fr):4d} min={min(fr) if fr else None!s:7s} | dup n={len(du):4d} max={max((m for m,_,_ in du), default=None)!s:7s} "
          f"| I-dup n={len(dI)} vals={[m for m,_,_ in dI]} | I at {Ikeys} | diag={d['diag'][0]} ratio={round(d['diag'][1],4)} probe_s={round(d['seconds'])}")
    if n in diag_set:
        ALL['fresh'] += fr; ALL['dup'] += [m for m,_,_ in du]; ALL['dupI'] += [m for m,_,_ in dI]; ALL['dupP'] += [m for m,t,_ in du if t != 'I']
print('testsrc2 native-speed set: fresh n=%d min=%s | dup n=%d max=%s | P-dup max=%s | I-dup n=%d max=%s' % (
    len(ALL['fresh']), min(ALL['fresh']), len(ALL['dup']), max(ALL['dup']), max(ALL['dupP']), len(ALL['dupI']), max(ALL['dupI'], default=None)))
fs = sorted(ALL['fresh']); print('fresh quantiles p0.1/p1/p50:', fs[len(fs)//1000], fs[len(fs)//100], fs[len(fs)//2])
