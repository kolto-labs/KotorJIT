"""Worked example: the reviewer's round-11 OLD-pattern encodes (plain testsrc2), re-judged by the v2
policy's separation rule. Rows are rebuilt from the recorded per-frame max(Y,U,V) DIF (the only value
the rule reads); frame 0 is 0. Acceptance interval as in calib_r11.py: [pts0+1, ptsN-1] at 60 FPS."""
import json, sys
sys.path.insert(0, '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness')
from kpharness import display_backends as D
pol = D.CONTENT_POLICIES['animated-diagnostic-v2']
for name in ('slow_quarter', 'slow_half', 'fresh60', 'r30_k1'):
    d = json.load(open(f'/home/brunner56/kp-live-20260922/review-probes-r11-correctness/cal/{name}.json'))
    ms = [0.0] + [m for _, _, _, m in d['labels']]
    rows = [{'ymin': 16.0, 'ymax': 235.0, 'yavg': 120.0, 'ydif': m, 'udif': 0.0, 'vdif': 0.0} for m in ms]
    pts = [i / 60 for i in range(len(rows))]
    ev = D.evaluate_content(rows, pts, pts[0] + 1.0, pts[-1] - 1.0, pol)
    sep = ev['separation']
    print(f"OLD-pattern {name:13s} v2: status={ev['status']} ratio={ev['acceptance']['distinct_ratio']:.4f} "
          f"sep={sep['status']} below={sep['below_band']} inside={sep['inside_band']} above={sep['above_band']} "
          f"failures={[f.split(':')[0] for f in ev['failures']]}")
