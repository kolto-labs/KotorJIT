"""evaluate(): an ambiguous content separation outranks every other failed criterion (cadence, survivors, cleanup,
driver error). The separation recomputation is stubbed; everything else is the production evaluate()."""
import sys
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import capture_diagnostic as CD
CD.content_separation_status = lambda *a: {'status': 'ambiguous', 'inside_band': 1}
obs = {'error': 'interrupted: SIGTERM', 'owned_survivors': [{'role': 'display:gamescope', 'pid': 4242, 'start': '1'}],
       'cleanup': {'status': 'failed'}, 'ledger_clear': False, 'protected_before': {'0': 1}, 'protected_after': {'0': 2},
       'recorder': None}
e = CD.evaluate(obs)
print('verdict=', e['verdict'], '| failed criteria=', sorted(k for k, v in e['criteria'].items() if not v))
CD.content_separation_status = lambda *a: {'status': 'separated'}
print('same observation, separated ->', CD.evaluate(obs)['verdict'])
