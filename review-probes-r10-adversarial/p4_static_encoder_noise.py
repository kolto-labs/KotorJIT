"""R10 Part B: does a STATIC source pass the content gate through libx264 encoder noise?
Host only. Synthetic lavfi stills + /usr/bin/ffmpeg encode with the recorder's exact codec
settings (recording.py:1114-1115). No display, no x11grab. Then the production
probe_frame_content/probe_frame_pts over /proc/self/fd/N with the brew ffprobe."""
import os, sys, subprocess, tempfile, json
from pathlib import Path
W='/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W+'/scripts/harness')
from kpharness import recording as R, display_backends as D
FFMPEG='/usr/bin/ffmpeg'; FFPROBE='/home/linuxbrew/.linuxbrew/Cellar/ffmpeg/9.0.1_1/bin/ffprobe'
CODEC=['-an','-c:v','libx264','-preset','ultrafast','-crf','28','-pix_fmt','yuv420p','-threads','2']
SOURCES = {
  'static_testsrc2_frame': 'testsrc2=size=1024x768:rate=60,trim=end_frame=1,loop=loop=-1:size=1:start=0,setpts=N/60/TB',
  'static_textured_noise': 'testsrc2=size=1024x768:rate=60,trim=end_frame=1,noise=alls=40:allf=0,loop=loop=-1:size=1:start=0,setpts=N/60/TB',
  'static_black': 'color=c=black:size=1024x768:rate=60',
  'static_dark_fadein_hold': 'color=c=0x101010:size=1024x768:rate=60',
  'animated_testsrc2': 'testsrc2=size=1024x768:rate=60',
  'half_dup_30_to_60': 'testsrc2=size=1024x768:rate=30,fps=60',
  'tenth_fresh_6_to_60': 'testsrc2=size=1024x768:rate=6,fps=60',
  'small_blink_on_static': 'testsrc2=size=1024x768:rate=60,trim=end_frame=1,loop=loop=-1:size=1:start=0,setpts=N/60/TB,drawbox=x=10:y=10:w=8:h=8:c=white:t=fill:enable=lt(mod(t\\,1)\\,0.5)',
}
def run(name, graph, seconds=35):
    d = Path(tempfile.mkdtemp(prefix='kp-r10-')); out = d/'continuous.mp4'
    cmd = [FFMPEG,'-nostdin','-y','-v','error','-f','lavfi','-i',graph,'-t',str(seconds),'-pix_fmt','bgr0','-f','rawvideo','-']
    enc = [FFMPEG,'-nostdin','-y','-v','error','-f','rawvideo','-pix_fmt','bgr0','-video_size','1024x768','-framerate','60','-i','-',*CODEC,str(out)]
    p1 = subprocess.Popen(cmd, stdout=subprocess.PIPE); p2 = subprocess.run(enc, stdin=p1.stdout); p1.wait()
    assert p2.returncode == 0 and p1.returncode == 0, name
    fd = os.open(out, os.O_RDONLY)
    try:
        path = Path(f'/proc/self/fd/{fd}')
        rows = R.probe_frame_content(path, FFPROBE, pass_fds=(fd,))
        pts = R.probe_frame_pts(path, FFPROBE, pass_fds=(fd,))
    finally: os.close(fd)
    res = {}
    for pol in ('game-capture-v1','animated-diagnostic-v1'):
        ev = D.evaluate_content(rows, pts, 3.0, 33.0, D.CONTENT_POLICIES[pol])
        res[pol] = (ev['status'], [f.split(':')[0] for f in ev['failures']], round(ev['acceptance']['distinct_ratio'],4) if ev['acceptance'] else None)
    changed_idx = [i for i in range(1,len(rows)) if any(rows[i][k]>0 for k in ('ydif','udif','vdif'))]
    print(f'{name}: frames={len(rows)} pts={len(pts)} first=({rows[0]["ymin"]},{rows[0]["ymax"]}) nonzero_dif_frames={len(changed_idx)} '
          f'first_changed={changed_idx[:8]} max_ydif={max(r["ydif"] for r in rows):.4f}')
    for pol, v in res.items(): print(f'    {pol}: {v}')
import os as _os
ONLY = _os.environ.get('P4_ONLY')
for k, g in SOURCES.items():
    if not ONLY or k in ONLY.split(','): run(k, g)
