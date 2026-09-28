import os, sys, json, subprocess
sys.path.insert(0, "/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness")
from kpharness import recording
clip = sys.argv[1]
fd = os.open(clip, os.O_RDONLY)
rows = recording.probe_frame_content(f"/proc/self/fd/{fd}", "/home/linuxbrew/.linuxbrew/bin/ffprobe", pass_fds=(fd,))
pts = recording.probe_frame_pts(f"/proc/self/fd/{fd}", "/home/linuxbrew/.linuxbrew/bin/ffprobe", pass_fds=(fd,)) if hasattr(recording,'probe_frame_pts') else None
print(json.dumps({"clip": clip, "content_rows": len(rows), "pts_rows": None if pts is None else len(pts), "first": rows[0], "second": rows[1], "last": rows[-1]}))
