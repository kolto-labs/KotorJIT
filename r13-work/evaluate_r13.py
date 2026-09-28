"""Evaluate cached synthetic rows (writer r13 encodes + adversarial r12 p18 cache) with the PRODUCTION
evaluate_content under the diagnostic policy. Acceptance 1 s .. last-1 s (34 s clip: 3..33 s)."""
import glob, json, sys
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import display_backends as D
P = D.CONTENT_POLICIES['animated-diagnostic-v2']
print('policy', dict(P))
for directory in sys.argv[1:]:
    for f in sorted(glob.glob(directory + '/*.rows.json')):
        c = json.load(open(f)); rows, pts = c['rows'], c['pts']
        name = Path(f).name[:-10]
        start, end = (3.0, 33.0) if pts[-1] > 30 else (1.0, pts[-1] - 1.0)
        r = D.evaluate_content(rows, pts, start, end, P)
        s, q = r['separation'], r['level_sequence']; lad = q['ladder']
        res = lad['resolution']
        print(f"{name:26s} {r['status']:6s} fails={[x.split(':')[0] for x in r['failures']]} "
              f"sep={s['status']} b/i/a={s['below_band']}/{s['inside_band']}/{s['above_band']} "
              f"dupmax={s['duplicate_max']} freshmin={s['fresh_min']} | seq={q['status']} "
              f"res={'none' if res is None else round(res, 2)} gap={lad['minimum_level_gap'] and round(lad['minimum_level_gap'], 2)} "
              f"within={lad['maximum_within_level_gap'] and round(lad['maximum_within_level_gap'], 2)} "
              f"steps={q['steps']} repeats={q['repeats']} viol={q['violation_count']} "
              f"kinds={sorted({v['kind'] for v in q['violations']})} "
              f"hist={[h['count'] for h in q['level_histogram']] if q['level_histogram'] else None}", flush=True)
