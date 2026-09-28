import json, glob, math, sys, os
sys.path.insert(0, '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness')
from kpharness import display_backends as D
EXCLUDED = set()  # every family is in the calibration envelope
F, Dp = [], []
for f in sorted(glob.glob('cal/*.json')):
    d = json.load(open(f)); L = d['labels']
    fr = [m for _, k, t, m in L if k == 'fresh']; du = [(m, t) for _, k, t, m in L if k == 'dup']
    dI = [m for m, t in du if t == 'I']; Is = [i for i, k, t, m in L if t == 'I']
    pol = D.CONTENT_POLICIES.get('animated-diagnostic-v2') or D.CONTENT_POLICIES['animated-diagnostic-v1']
    ev = D.evaluate_content(d['rows'], d['pts'], d['pts'][0] + 1.0, d['pts'][-1] - 1.0, pol)
    sep = ev.get('separation') or {}
    print(f"{d['name']:13s} fresh n={len(fr):4d} min={min(fr) if fr else None!s:8s} | dup n={len(du):4d} max={max((m for m,_ in du), default=None)!s:7s} "
          f"| I-dup n={len(dI)} max={max(dI, default=None)} | I at {Is} | {pol['id']} {ev['status']} ratio={round(ev['acceptance']['distinct_ratio'],4)} "
          f"sep={sep.get('status')} band_n={sep.get('inside_band')} | enc_s={None if d.get('encode_seconds') is None else round(d['encode_seconds'])} total_s={round(d['seconds'])}")
    F += fr; Dp += [m for m, _ in du]
if F and Dp:
    fmin, dmax = min(F), max(Dp); g = math.sqrt(fmin * dmax)
    print(f'ALL fresh n={len(F)} min={fmin} | dup n={len(Dp)} max={dmax} | fresh/dup={fmin/dmax:.2f} geometric midpoint={g:.3f}')
    fl = pol['distinct_noise_floor']
    print(f'policy floor={fl} margin_dup={fl/dmax:.2f}x margin_fresh={fmin/fl:.2f}x')
