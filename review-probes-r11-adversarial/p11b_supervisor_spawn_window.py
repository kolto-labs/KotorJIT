"""The p11a window at the supervisor's own spawn: a SIGINT that lands inside deps.spawn_child after
fork. Modelled by a spawn wrapper that starts the real dummy child, then raises the supervisor's
own handler (os.kill(self, SIGINT)) before returning, which is what p11a shows CPython doing.
Real supervise(), real run_child in the dummy child, sleep grandchildren. No display."""
import json, os, signal, subprocess, sys, tempfile, time
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/tools'); sys.path.insert(0, W + '/scripts/harness')
import kpharness_capture_diagnostic_test as T
from kpharness import capture_diagnostic as CD

base = Path(tempfile.mkdtemp(prefix='kp-r11-p11b-'))
for name in ('proc', 'runs', 'operator'):
    (base / name).mkdir()
(base / 'operator' / 'commitments.log').touch()
script = T.SUPERVISOR_SCRIPT.replace(
    "    return subprocess.Popen([sys.executable, str(base / 'dummy_child.py'), sys.argv[1], command[-1], mode],\n                            **kwargs)",
    "    child = subprocess.Popen([sys.executable, str(base / 'dummy_child.py'), sys.argv[1], command[-1], mode],\n                             **kwargs)\n"
    "    (base / 'leaked-child-pid').write_text(str(child.pid))\n"
    "    import os, signal; os.kill(os.getpid(), signal.SIGINT)  # lands before Popen returns\n"
    "    return child")
assert 'leaked-child-pid' in script
(base / 'supervisor.py').write_text(script); (base / 'dummy_child.py').write_text(T.DUMMY_CHILD_SCRIPT)
p = subprocess.Popen([sys.executable, str(base / 'supervisor.py'), W + '/scripts/harness', str(base), 'normal', '60'],
                     start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
out = p.communicate(timeout=120)[0].decode(errors='replace')
run, = list((base / 'runs').iterdir())
result = json.loads((run / 'diagnostic-result.json').read_text())
child = int((base / 'leaked-child-pid').read_text())
child_alive = Path(f'/proc/{child}').exists()
time.sleep(2)
owned = json.loads((run / CD.OWNED_FILE).read_text()) if (run / CD.OWNED_FILE).exists() else []
print(f'supervisor_exit={p.returncode} errors={result["errors"]} launches={result["launches"]} '
      f'child_returncode={result.get("child_returncode")} owned_survivors={result.get("owned_survivors")}')
print(f'child_alive_after_supervisor_exit={child_alive} owned_started_after_supervisor_exit={[o["role"] for o in owned]}')
# The dummy child finishes its own run (~34 s) and ordered cleanup; wait for its evidence.
deadline = time.monotonic() + 90
while not (run / 'diagnostic-run.json').exists() and time.monotonic() < deadline:
    time.sleep(.5)
steps = (run / 'cleanup-steps.log').read_text().split() if (run / 'cleanup-steps.log').exists() else []
print(f'unsupervised_child_completed_run={(run / "diagnostic-run.json").exists()} its_cleanup_steps={steps} '
      f'result_file_rewritten={json.loads((run / "diagnostic-result.json").read_text()) != result}')
for o in owned:
    if CD.process_alive(o['pid'], o['start']):
        CD.kill_owned_identity(o)
