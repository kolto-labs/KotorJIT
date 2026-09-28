"""Does a Python signal handler that raises (as _ChildSignals / _SupervisorSignals do) ever fire
inside subprocess.Popen after the child was created, losing the Popen object?
Children are /bin/sleep only, in their own session (like mpv/Gamescope launches), and are
reaped by this probe through their recorded PIDs."""
import os, random, signal, subprocess, sys, time

class Interrupted(BaseException):
    pass

armed = [False]
def handler(signum, frame):
    if armed[0]:
        raise Interrupted()

signal.signal(signal.SIGALRM, handler)
lock_r, lock_w = os.pipe()  # stands in for the inherited lock descriptor
trials = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
leaked, returned, raised_before_fork = [], 0, 0
for _ in range(trials):
    before = set(int(x) for x in open(f'/proc/self/task/{os.getpid()}/children').read().split())
    process = None
    try:
        armed[0] = True
        signal.setitimer(signal.ITIMER_REAL, random.uniform(1e-5, 0.004))
        process = subprocess.Popen(['/bin/sleep', '5'], pass_fds=(lock_r,), start_new_session=True,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        armed[0] = False
    except Interrupted:
        armed[0] = False
    signal.setitimer(signal.ITIMER_REAL, 0)
    after = set(int(x) for x in open(f'/proc/self/task/{os.getpid()}/children').read().split())
    new = after - before
    if process is None and new:
        leaked.extend(new)
    elif process is None:
        raised_before_fork += 1
    else:
        returned += 1
        process.kill(); process.wait()
for pid in leaked:
    try:
        os.kill(pid, signal.SIGKILL); os.waitpid(pid, 0)
    except (ProcessLookupError, ChildProcessError):
        pass
print(f'python={sys.version.split()[0]} trials={trials} popen_returned={returned} '
      f'interrupted_before_fork={raised_before_fork} interrupted_after_fork_child_leaked={len(leaked)}')
