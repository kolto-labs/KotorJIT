"""R11 correctness: SIGINT while the supervisor is inside Popen (fork done, exec pending).
Real CD.supervise + test dummy child (sleep grandchildren, no display). preexec_fn widens the
fork->exec window to 1.5 s; CPython blocks on the errpipe read, a signal handler that raises
propagates out of Popen.__init__ without killing the forked child (subprocess.py errpipe loop)."""
import json, os, signal, subprocess, sys, tempfile, time
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path[:0] = [W + '/tools', W + '/scripts/harness']
import kpharness_capture_diagnostic_test as T
from kpharness import capture_diagnostic as CD
base = Path(tempfile.mkdtemp(prefix='kp-r11c-race-'))
for n in ('proc', 'runs', 'operator'): (base / n).mkdir()
(base / 'operator' / 'commitments.log').touch()
sup = T.SUPERVISOR_SCRIPT.replace("""    return subprocess.Popen([sys.executable, str(base / 'dummy_child.py'), sys.argv[1], command[-1], mode],
                            **kwargs)""", """    import time as _t
    def slow_exec():
        (base / 'spawning').write_text('x'); _t.sleep(1.5)
    return subprocess.Popen([sys.executable, str(base / 'dummy_child.py'), sys.argv[1], command[-1], mode],
                            preexec_fn=slow_exec, **kwargs)""")
assert 'slow_exec' in sup
(base / 'supervisor.py').write_text(sup); (base / 'dummy_child.py').write_text(T.DUMMY_CHILD_SCRIPT)
p = subprocess.Popen([sys.executable, str(base / 'supervisor.py'), W + '/scripts/harness', str(base), 'cooperative', '60'],
                     start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
while not (base / 'spawning').exists(): time.sleep(.01)
time.sleep(.3)
os.kill(p.pid, signal.SIGINT)          # Ctrl-C to the supervisor only (the child has its own session)
out, _ = p.communicate(timeout=120)
rundir, = list((base / 'runs').iterdir())
res = json.loads((rundir / 'diagnostic-result.json').read_text())
print('supervisor_exit', p.returncode)
print('result_errors', res['errors'])
print('result_launches', res['launches'], 'child_returncode', res.get('child_returncode'))
print('result_owned_survivors', res.get('owned_survivors'))
print('result_cleanup_budget', res.get('cleanup_budget'))
time.sleep(3)
print('child_ready_after_supervisor_exit', (rundir / 'child-ready').exists())
owned = json.loads((rundir / CD.OWNED_FILE).read_text()) if (rundir / CD.OWNED_FILE).exists() else []
alive = [(o['role'], o['pid']) for o in owned if CD.process_alive(o['pid'], o['start'])]
print('owned_alive_3s_after_supervisor_exit', alive)
# was the ordered cleanup ever triggered by the Ctrl-C?  wait for the dummy to finish naturally
t0 = time.monotonic()
while not (rundir / 'diagnostic-run.json').exists() and time.monotonic() - t0 < 90: time.sleep(.5)
run = json.loads((rundir / 'diagnostic-run.json').read_text()) if (rundir / 'diagnostic-run.json').exists() else None
print('child_ran_unsupervised_seconds', round(time.monotonic() - t0 + 3, 1), 'child_interrupts', run and run['interrupts'],
      'child_error', run and run['error'], 'cleanup_steps', (rundir / 'cleanup-steps.log').read_text().split() if (rundir / 'cleanup-steps.log').exists() else None)
for o in owned:
    if CD.process_alive(o['pid'], o['start']): CD.kill_owned_identity(o)
