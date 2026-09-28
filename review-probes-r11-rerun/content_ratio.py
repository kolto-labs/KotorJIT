import os, sys, json
sys.path.insert(0, "/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness")
from kpharness import recording as R, display_backends as D
FP = "/home/linuxbrew/.linuxbrew/bin/ffprobe"
for clip in sys.argv[1:]:
    fd = os.open(clip, os.O_RDONLY)
    rows = R.probe_frame_content(f"/proc/self/fd/{fd}", FP, pass_fds=(fd,), deadline_seconds=R.probe_deadline_seconds(600))
    pts = R.probe_frame_pts(f"/proc/self/fd/{fd}", FP, pass_fds=(fd,), deadline_seconds=R.probe_deadline_seconds(600))
    os.close(fd)
    out = {}
    for pol in ("game-capture-v1", "animated-diagnostic-v1"):
        ev = D.evaluate_content(rows, pts, pts[0] + 1.0, pts[-1] - 1.0, D.CONTENT_POLICIES[pol])
        out[pol] = (ev["status"], round(ev["acceptance"]["distinct_ratio"], 4) if ev["acceptance"] else None, ev["failures"])
    floor = D.CONTENT_POLICIES["animated-diagnostic-v1"]["distinct_noise_floor"]
    nz = [r for r in rows[1:] if any(r[k] > 0 for k in ("ydif", "udif", "vdif"))]
    above = [r for r in rows[1:] if max(r[k] for k in ("ydif", "udif", "vdif")) > floor]
    small = [r["ydif"] for r in nz if r["ydif"] < 0.5]
    print(json.dumps({"clip": clip, "frames": len(rows), "pts": len(pts), "nonzero_dif_frames": len(nz), "above_floor_frames": len(above), "floor": floor,
                      "max_ydif": max(r["ydif"] for r in rows[1:]), "min_nonzero_ydif": min(small) if small else None,
                      "first": {k: rows[0][k] for k in ("ymin", "ymax")}, "verdicts": out}))
