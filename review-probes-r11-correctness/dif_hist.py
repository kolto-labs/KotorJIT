import os, sys, json
sys.path.insert(0, "/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness")
from kpharness import recording as R
FP = "/home/linuxbrew/.linuxbrew/bin/ffprobe"
for clip in sys.argv[1:]:
    fd = os.open(clip, os.O_RDONLY)
    rows = R.probe_frame_content(f"/proc/self/fd/{fd}", FP, pass_fds=(fd,)); os.close(fd)
    y = [r["ydif"] for r in rows[1:]]
    odd = sorted(y[0::2]); even = sorted(y[1::2])
    q = lambda s: [round(s[int(len(s)*p)], 4) for p in (0, .1, .5, .9)] + [round(s[-1], 4)]
    print(json.dumps({"clip": clip, "idx1,3,5.. ydif quantiles": q(odd), "idx2,4,6.. ydif quantiles": q(even)}))
