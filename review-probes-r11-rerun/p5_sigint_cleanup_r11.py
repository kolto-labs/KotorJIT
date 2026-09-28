"""p5 adapted to round 11: the real CD.supervise parent (Popen, own session for the child,
forward-and-wait) with a harmless dummy child that runs the real CD.run_child over fake
lease/recorder objects whose cleanup steps take 0.3 s each and stop real `sleep` grandchildren.
No display, mpv, Gamescope, FFmpeg or game. Ctrl-C / hangup go to the supervisor's group."""
import json, os, signal, subprocess, sys, tempfile, time
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/tools'); sys.path.insert(0, W + '/scripts/harness')
import kpharness_capture_diagnostic_test as T
from kpharness import capture_diagnostic as CD

def run(mode, budget, signals, gap=.15):
    base = Path(tempfile.mkdtemp(prefix='kp-r11-p5-'))
    for name in ('proc', 'runs', 'operator'):
        (base / name).mkdir()
    (base / 'operator' / 'commitments.log').touch()
    (base / 'supervisor.py').write_text(T.SUPERVISOR_SCRIPT); (base / 'dummy_child.py').write_text(T.DUMMY_CHILD_SCRIPT)
    p = subprocess.Popen([sys.executable, str(base / 'supervisor.py'), W + '/scripts/harness', str(base), mode, str(budget)],
                         start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    while not list((base / 'runs').glob('*/child-ready')):
        time.sleep(.05)
    rundir, = list((base / 'runs').iterdir())
    owned = json.loads((rundir / CD.OWNED_FILE).read_text())
    for number in signals:
        os.killpg(p.pid, number); time.sleep(gap)
    p.wait(timeout=120)
    result = json.loads((rundir / 'diagnostic-result.json').read_text())
    steps = (rundir / 'cleanup-steps.log').read_text().split() if (rundir / 'cleanup-steps.log').exists() else []
    alive = [o['role'] for o in owned if CD.process_alive(o['pid'], o['start'])]
    for o in owned:
        if CD.process_alive(o['pid'], o['start']):
            CD.kill_owned_identity(o)
    print(f'{mode} {[signal.Signals(s).name for s in signals]}: parent_exit={p.returncode} '
          f'parent_finally_ran={(rundir / "diagnostic-result.json").exists()} child_cleanup_steps_completed={steps} '
          f'interrupts={result["interrupts"]} budget_exhausted={result["cleanup_budget"]["exhausted"]} '
          f'owned_alive_after={alive} result_owned_survivors={[(s["role"], s["pid"]) for s in result["owned_survivors"]]}')

run('cooperative', 60, [signal.SIGINT])
run('cooperative', 60, [signal.SIGHUP])
run('cooperative', 60, [signal.SIGTERM])
run('cooperative', 60, [signal.SIGINT] * 3)
run('stubborn', 2, [signal.SIGINT])
run('survivor', 2, [signal.SIGINT])
print('production_budget_seconds=%s components=%s' % (CD.CLEANUP_BUDGET_SECONDS, CD.CLEANUP_BUDGET_COMPONENTS))
