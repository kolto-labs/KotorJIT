"""R12 spawn-window attacks on the real supervise(): (a) two different signals (SIGINT then SIGTERM) land
after fork/before Popen returns; (b) SIGHUP lands in the window; (c) a normal run gets an external SIGTERM
after child-ready, and we read SigBlk of child and grandchildren (must be 0 = unblocked).
Dummy child tree only (sleep), no display. Only processes this probe started are ever signalled."""
import json, os, signal, subprocess, sys, tempfile, time
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/tools'); sys.path.insert(0, W + '/scripts/harness')
import kpharness_capture_diagnostic_test as T
from kpharness import capture_diagnostic as CD
KILL_LINE = "        os.kill(os.getpid(), getattr(signal, mode.split('-', 1)[1]))  # after fork, before Popen returns\n"
assert KILL_LINE in T.SUPERVISOR_SCRIPT

def run_case(label, mode, script, external=None):
    base = Path(tempfile.mkdtemp(prefix=f'kp-r12-p15-{label}-'))
    for name in ('proc', 'runs', 'operator'):
        (base / name).mkdir()
    (base / 'operator' / 'commitments.log').touch()
    (base / 'supervisor.py').write_text(script); (base / 'dummy_child.py').write_text(T.DUMMY_CHILD_SCRIPT)
    p = subprocess.Popen([sys.executable, str(base / 'supervisor.py'), W + '/scripts/harness', str(base), mode, '60'],
                         start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if external:
        run = None; deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            runs = list((base / 'runs').iterdir())
            if runs and (runs[0] / 'child-ready').exists():
                run = runs[0]; break
            time.sleep(.2)
        p.send_signal(external)
    out = p.communicate(timeout=240)[0].decode(errors='replace')
    run, = list((base / 'runs').iterdir())
    result = json.loads((run / 'diagnostic-result.json').read_text())
    owned = json.loads((run / CD.OWNED_FILE).read_text()) if (run / CD.OWNED_FILE).exists() else []
    alive = [o for o in owned if CD.process_alive(o['pid'], o['start'])]
    child = result.get('child') or {}
    child_alive = bool(child.get('start')) and CD.process_alive(child['pid'], child['start'])
    steps = (run / 'cleanup-steps.log').read_text().split() if (run / 'cleanup-steps.log').exists() else []
    runev = json.loads((run / 'diagnostic-run.json').read_text()) if (run / 'diagnostic-run.json').exists() else {}
    sigblk = json.loads((run / 'sigblk.json').read_text()) if (run / 'sigblk.json').exists() else None
    print(f'{label}: exit={p.returncode} verdict={result["verdict"]} errors={result["errors"]} '
          f'interrupts={result.get("interrupts")} child_rc={result.get("child_returncode")} '
          f'budget_exhausted={(result.get("cleanup_budget") or {}).get("exhausted")} '
          f'child_alive_after={child_alive} owned_alive_after={alive} child_interrupts={runev.get("interrupts")} '
          f'child_error={runev.get("error")} cleanup_steps={steps} sigblk={sigblk}', flush=True)
    for o in alive:
        CD.kill_owned_identity(o)

double = T.SUPERVISOR_SCRIPT.replace(KILL_LINE,
    "        os.kill(os.getpid(), signal.SIGINT); os.kill(os.getpid(), signal.SIGTERM)\n")
run_case('double_SIGINT_SIGTERM_in_window', 'spawnwindow-SIGINT', double)
run_case('SIGHUP_in_window', 'spawnwindow-SIGHUP', T.SUPERVISOR_SCRIPT)
run_case('external_SIGTERM_after_ready', 'normal', T.SUPERVISOR_SCRIPT, external=signal.SIGTERM)
