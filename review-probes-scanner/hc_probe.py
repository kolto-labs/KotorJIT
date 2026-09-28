import sys, time, resource
sys.dont_write_bytecode = True
sys.path.insert(0, '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/tools')
import creative_host_check as H
cases = {'flood': ['/home/brunner56/kp-live-20260922/review-probes-scanner/prior/hc/flood'],
         'drip_forever': ['/bin/sh', '-c', 'while :; do printf x; sleep 1; done'],
         'close_stdout_then_sleep': ['/bin/sh', '-c', 'exec >&-; sleep 30'],
         'bg_child_holds_pipe': ['/bin/sh', '-c', '(sleep 30; echo late) & echo "ffmpeg version fake"'],
         'exact_64k_then_exit': ['/bin/sh', '-c', 'head -c 65536 /dev/zero | tr "\\0" x']}
for k, c in cases.items():
    t = time.monotonic(); r = H._run_version(c)
    print(f'{k:24} rc={r.returncode} bytes={len(r.stdout)} secs={time.monotonic()-t:.2f}')
print('maxrss_kb', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
