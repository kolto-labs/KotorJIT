import sys
W='/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W+'/scripts/harness')
from kpharness import display_backends as D
P = D.CONTENT_POLICIES
def row(d, black=False): return {'ymin': 16.0, 'ymax': 16.0 if black else 235.0, 'yavg': 100.0, 'ydif': d, 'udif': d/3, 'vdif': d/3}
def ev(rows, pol, start=1.0, end=None):
    pts = [i/60 for i in range(len(rows))]; end = pts[-1] if end is None else end
    e = D.evaluate_content(rows, pts, start, end, P[pol]); a = e['acceptance']
    return e['status'], round(a['distinct_ratio'], 4), e['failures'][:1]
N = 60*34
cases = {
 'half_dup_with_I_dup_0.76_every_250': [row(0)] + [row(0.76 if i % 250 == 0 else (1.9 if i % 2 else 0.14)) for i in range(1, N)],
 'stale_1.2pct_P_dup_0.33': [row(0)] + [row(0.33 if i % 83 == 0 else 1.9) for i in range(1, N)],
 'stale_0.8pct': [row(0)] + [row(0.33 if i % 125 == 0 else 1.9) for i in range(1, N)],
 'dup_exactly_at_floor_1.2_every_2nd': [row(0)] + [row(1.2 if i % 2 == 0 else 1.9) for i in range(1, N)],
 'dup_just_above_floor_1.2001': [row(0)] + [row(1.2001 if i % 2 == 0 else 1.9) for i in range(1, N)],
 'black_startup_then_live': [row(0, True)] * 60 + [row(1.9) for _ in range(N - 60)],
 'black_first_acceptance_frame': [row(1.9)] * 60 + [row(0, True)] + [row(1.9) for _ in range(N - 61)],
 'chroma_only_change': [row(0)] + [{'ymin': 16.0, 'ymax': 235.0, 'yavg': 100.0, 'ydif': 0.1, 'udif': 1.5, 'vdif': 0.1} for _ in range(N - 1)],
}
for name, rows in cases.items():
    print(name, {pol: ev(rows, pol) for pol in P})
rows = [row(1.9)] * 100
print('interval_after_last_frame', ev(rows, 'animated-diagnostic-v1', start=5.0, end=6.0))
