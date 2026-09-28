"""Synthetic-row edge cases for the v2 separation rule (production evaluate_content)."""
import sys
sys.path.insert(0, '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness')
from kpharness import display_backends as D
P = D.CONTENT_POLICIES['animated-diagnostic-v2']
def row(d, black=False): return {'ymin': 16.0, 'ymax': 16.0 if black else 235.0, 'yavg': 100.0, 'ydif': d, 'udif': d/3, 'vdif': d/3}
N = 60 * 34
def ev(rows, start=1.0):
    pts = [i/60 for i in range(len(rows))]
    e = D.evaluate_content(rows, pts, start, pts[-1], P); s = e['separation']
    return e['status'], round(e['acceptance']['distinct_ratio'], 4), [f.split(':')[0] for f in e['failures']], (s['below_band'], s['inside_band'], s['above_band'])
cases = {
 'all_fresh_52': [row(52)] * N,
 'half_dup_0.9': [row(0.9 if i % 2 else 52) for i in range(N)],
 'one_dup_1.31': [row(1.31 if i == 900 else 52) for i in range(N)],
 'one_fresh_11.69': [row(11.69 if i == 900 else 52) for i in range(N)],
 'dup_exactly_1.3_every_2nd': [row(1.3 if i % 2 else 52) for i in range(N)],
 'fresh_exactly_11.7_all': [row(11.7)] * N,
 'dups_0.9pct_at_1.0': [row(1.0 if i % 111 == 0 else 52) for i in range(N)],
 'dups_1.1pct_at_1.0': [row(1.0 if i % 90 == 0 else 52) for i in range(N)],
 'black_first_plus_band': [row(52)] * 60 + [row(5, True)] + [row(52)] * (N - 61),
 'band_value_before_acceptance_only': [row(5)] * 59 + [row(52)] * (N - 59),
}
for k, v in cases.items(): print(k, ev(v))
