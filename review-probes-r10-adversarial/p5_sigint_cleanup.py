"""R10 Part C: Ctrl-C (SIGINT to the foreground group) during supervise()'s subprocess.run.
Harmless stand-in: the child mimics run_child (catch BaseException, then a 1.5 s ordered
cleanup that writes a marker per step). The parent mimics supervise's spawn_child=subprocess.run."""
import os, signal, subprocess, sys, time, tempfile
from pathlib import Path
d = Path(tempfile.mkdtemp(prefix='kp-r10-sigint-'))
child = d/'child.py'
child.write_text('''
import time, sys
from pathlib import Path
d = Path(sys.argv[1])
try:
    time.sleep(30)
except BaseException:
    pass
finally:
    for step in ("recorder", "source_process", "display"):
        time.sleep(0.5); (d/("cleaned-"+step)).write_text("ok")
''')
parent = d/'parent.py'
parent.write_text(f'''
import subprocess, sys
try:
    subprocess.run([sys.executable, {str(child)!r}, {str(d)!r}], check=False)
finally:
    open({str(d/"parent-finally")!r}, "w").write("ok")
''')
p = subprocess.Popen([sys.executable, str(parent)], start_new_session=True)
time.sleep(1.0)
os.killpg(p.pid, signal.SIGINT)          # what a terminal Ctrl-C does to the foreground group
p.wait(); time.sleep(2.5)
print('parent_exit=%s' % p.returncode)
print('parent_finally_ran=%s' % (d/'parent-finally').exists())
print('child_cleanup_steps_completed=%s' % sorted(x.name for x in d.glob('cleaned-*')))
