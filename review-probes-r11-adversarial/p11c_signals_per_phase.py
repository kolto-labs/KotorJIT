"""Signals at each cleanup phase, signals sent to the child directly, and SIGKILL of the supervisor.
Real supervise() + real run_child (dummy lease/recorder, 0.3 s per cleanup step, sleep grandchildren)."""
import json, os, signal, subprocess, sys, tempfile, time
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/tools'); sys.path.insert(0, W + '/scripts/harness')
import kpharness_capture_diagnostic_test as T
from kpharness import capture_diagnostic as CD

def start(mode, budget):
    base = Path(tempfile.mkdtemp(prefix='kp-r11-p11c-'))
    for name in ('proc', 'runs', 'operator'):
        (base / name).mkdir()
    (base / 'operator' / 'commitments.log').touch()
    (base / 'supervisor.py').write_text(T.SUPERVISOR_SCRIPT); (base / 'dummy_child.py').write_text(T.DUMMY_CHILD_SCRIPT)
    p = subprocess.Popen([sys.executable, str(base / 'supervisor.py'), W + '/scripts/harness', str(base), mode, str(budget)],
                         start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    while not list((base / 'runs').glob('*/child-ready')):
        time.sleep(.05)
    run, = list((base / 'runs').iterdir())
    owned = json.loads((run / CD.OWNED_FILE).read_text())
    child = int(json.loads((run / 'diagnostic-config.json').read_text()) and 0) or None
    return base, p, run, owned

def child_pid(supervisor_pid):
    kids = open(f'/proc/{supervisor_pid}/task/{supervisor_pid}/children').read().split()
    return int(kids[0])

def finish(label, p, run, owned, extra=''):
    try:
        p.wait(timeout=120)
    except subprocess.TimeoutExpired:
        p.kill(); p.wait()
    result = json.loads((run / 'diagnostic-result.json').read_text()) if (run / 'diagnostic-result.json').exists() else None
    evidence = json.loads((run / 'diagnostic-run.json').read_text()) if (run / 'diagnostic-run.json').exists() else {}
    steps = (run / 'cleanup-steps.log').read_text().split() if (run / 'cleanup-steps.log').exists() else []
    alive = [o['role'] for o in owned if CD.process_alive(o['pid'], o['start'])]
    for o in owned:
        if CD.process_alive(o['pid'], o['start']):
            CD.kill_owned_identity(o)
    print(f'{label}: exit={p.returncode} steps={steps} child_interrupts={evidence.get("interrupts")} '
          f'cleanup={(evidence.get("cleanup") or {}).get("status")} '
          f'sup_interrupts={result and result["interrupts"]} exhausted={result and result["cleanup_budget"]["exhausted"]} '
          f'owned_alive_after={alive} result_written={result is not None} {extra}')

# 1. First SIGINT, then one more during each later phase (recorder .3 s, client .3 s, display .3 s).
base, p, run, owned = start('cooperative', 60)
for delay in (0, .45, .75, 1.05, 1.5):
    time.sleep(delay if delay == 0 else .3 if delay < 1.5 else .45)
    os.killpg(p.pid, signal.SIGINT)
finish('sigint_in_every_phase', p, run, owned)

# 2. SIGTERM straight to the child (e.g. pkill -f kpharness), then SIGINT to the terminal group.
base, p, run, owned = start('cooperative', 60)
c = child_pid(p.pid)
os.kill(c, signal.SIGTERM); time.sleep(.4); os.killpg(p.pid, signal.SIGINT)
finish('sigterm_to_child_then_sigint_group', p, run, owned)

# 3. pkill-style SIGTERM to both at once, then a SIGHUP to the child during cleanup.
base, p, run, owned = start('cooperative', 60)
c = child_pid(p.pid)
os.kill(c, signal.SIGTERM); os.kill(p.pid, signal.SIGTERM); time.sleep(.4); os.kill(c, signal.SIGHUP)
finish('sigterm_both_then_sighup_child_mid_cleanup', p, run, owned)

# 4. Signal to the supervisor while it is killing after an exhausted budget.
base, p, run, owned = start('stubborn', 1.5)
os.killpg(p.pid, signal.SIGINT); time.sleep(1.6); os.killpg(p.pid, signal.SIGINT); time.sleep(.05)
os.killpg(p.pid, signal.SIGHUP)
finish('signals_during_budget_kill', p, run, owned)

# 5. SIGKILL of the supervisor mid-run: does the child keep the lock and finish alone?
base, p, run, owned = start('normal', 60)
c = child_pid(p.pid)
os.kill(p.pid, signal.SIGKILL); p.wait()
time.sleep(1)
alive_now = Path(f'/proc/{c}').exists()
deadline = time.monotonic() + 90
while not (run / 'diagnostic-run.json').exists() and time.monotonic() < deadline:
    time.sleep(.5)
finish('supervisor_sigkilled', p, run, owned, extra=f'child_alive_after_supervisor_death={alive_now}')
