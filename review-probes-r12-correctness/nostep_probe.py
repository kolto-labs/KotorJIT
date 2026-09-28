"""If mpv rendered the graph WITHOUT the per-frame step (eval ignored / step dropped), what does v2 say?
Encodes with the recorder's codec args at 1024x768, probes with production functions."""
import os, subprocess, sys, tempfile
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import recording as R, display_backends as D
FF = '/usr/bin/ffmpeg'; FP = '/home/linuxbrew/.linuxbrew/bin/ffprobe'
CODEC = ['-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-pix_fmt', 'yuv420p', '-threads', '2']
S = 'testsrc2=size=1024x768:rate=60'
CASES = {
  'step_dropped_contrast04': f'{S},eq=contrast=0.4',
  'step_eval_init': f'{S},eq=contrast=0.4:brightness=(3*n-7*floor(3*n/7)-3)*0.11:eval=init',
  'step_dropped_slowq': f'testsrc2=size=1024x768:rate=240,setpts=4*PTS,fps=60,eq=contrast=0.4',
}
for name, g in CASES.items():
    d = tempfile.mkdtemp(prefix='r12c-nostep-'); mp4 = os.path.join(d, 'a.mp4')
    subprocess.run([FF, '-nostdin', '-y', '-v', 'error', '-f', 'lavfi', '-i', g, '-frames:v', '480', *CODEC, mp4], check=True)
    fd = os.open(mp4, os.O_RDONLY)
    try:
        rows = R.probe_frame_content(f'/proc/self/fd/{fd}', FP, pass_fds=(fd,), deadline_seconds=900)
        pts = R.probe_frame_pts(f'/proc/self/fd/{fd}', FP, pass_fds=(fd,), deadline_seconds=900)
    finally:
        os.close(fd)
    ev = D.evaluate_content(rows, pts, pts[0], pts[-1], D.CONTENT_POLICIES['animated-diagnostic-v2'])
    vals = sorted(max(r[k] for k in ('ydif', 'udif', 'vdif')) for r in rows[1:])
    s = ev['separation']
    print(name, ev['status'], round(ev['acceptance']['distinct_ratio'], 4), [f.split(':')[0] for f in ev['failures']],
          s['status'], 'b/i/a=%d/%d/%d' % (s['below_band'], s['inside_band'], s['above_band']),
          'min/med/max=%.3f/%.3f/%.3f' % (vals[0], vals[len(vals)//2], vals[-1]), flush=True)
    os.unlink(mp4); os.rmdir(d)
