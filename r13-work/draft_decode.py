import json, glob, statistics, sys
def decode(y, period=7):
    o = sorted(y)
    gaps = [(o[i+1]-o[i], i) for i in range(len(o)-1)]
    ch = sorted(gaps, key=lambda g: (-g[0], g[1]))[:period-1]
    cuts = sorted(i for _, i in ch); cs = set(cuts)
    th = [(o[i]+o[i+1])/2 for i in cuts]
    groups = []; s = 0
    for c in cuts: groups.append(o[s:c+1]); s = c+1
    groups.append(o[s:])
    centers = [statistics.median(g) for g in groups]
    lg = min(g for g, _ in ch); within = max((g for g, i in gaps if i not in cs), default=0.0)
    sp = min(b-a for a, b in zip(centers, centers[1:]))
    return th, centers, lg, within, sp
import bisect
for f in sorted(glob.glob(sys.argv[1] + '/*.rows.json')):
    c = json.load(open(f)); r, pts = c['rows'], c['pts']
    sel = [i for i, v in enumerate(pts) if 1.0 <= v <= pts[-1] - 1.0]
    y = [r[i]['yavg'] for i in sel]
    th, centers, lg, within, sp = decode(y)
    L = [bisect.bisect_right(th, v) - 3 for v in y]
    viol = 0
    for k in range(1, len(sel)):
        d = (L[k]-L[k-1]) % 7; v = max(r[sel[k]][x] for x in ('ydif','udif','vdif'))
        fresh = v > 3.9
        if not ((fresh and d == 3) or (not fresh and d == 0)): viol += 1
    print(f.split('/')[-1][:-10].ljust(24), 'n=%d gap=%.2f within=%.2f ratio=%s spacing=%.2f viol=%d' % (len(sel), lg, within, 'inf' if within == 0 else '%.1f' % (lg/within), sp, viol), [round(x,1) for x in centers])
