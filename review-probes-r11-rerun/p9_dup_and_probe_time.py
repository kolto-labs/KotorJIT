"""R10 cross-check: duplicated-frame sources vs the content gate, and content-probe wall time vs its fixed 30 s bound."""
import os, sys, subprocess, tempfile, time
from pathlib import Path
W='/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W+'/scripts/harness')
from kpharness import recording as R, display_backends as D
FFMPEG='/usr/bin/ffmpeg'; FFPROBE='/home/linuxbrew/.linuxbrew/bin/ffprobe'
CODEC=['-an','-c:v','libx264','-preset','ultrafast','-crf','28','-pix_fmt','yuv420p','-threads','2']
def encode(graph, seconds):
    d = Path(tempfile.mkdtemp(prefix='kp-r10-')); out = d/'continuous.mp4'
    p1 = subprocess.Popen([FFMPEG,'-nostdin','-v','error','-f','lavfi','-i',graph,'-t',str(seconds),'-pix_fmt','bgr0','-f','rawvideo','-'], stdout=subprocess.PIPE)
    subprocess.run([FFMPEG,'-nostdin','-y','-v','error','-f','rawvideo','-pix_fmt','bgr0','-video_size','1024x768','-framerate','60','-i','-',*CODEC,str(out)], stdin=p1.stdout, check=True); p1.wait()
    return out
def probe(out, fn):
    fd = os.open(out, os.O_RDONLY)
    try:
        t = time.monotonic(); v = fn(Path(f'/proc/self/fd/{fd}'), FFPROBE, pass_fds=(fd,), deadline_seconds=DEADLINE[0]); return v, time.monotonic() - t
    finally: os.close(fd)
DEADLINE = [R.probe_deadline_seconds(600)]
for name, graph in (('half_dup_30_to_60','testsrc2=size=1024x768:rate=30,fps=60'), ('tenth_fresh_6_to_60','testsrc2=size=1024x768:rate=6,fps=60')):
    out = encode(graph, 10)
    rows, _ = probe(out, R.probe_frame_content); pts, _ = probe(out, R.probe_frame_pts)
    for pol in ('animated-diagnostic-v1', 'game-capture-v1'):
        ev = D.evaluate_content(rows, pts, 1.0, 9.0, D.CONTENT_POLICIES[pol])
        print(f'{name} {pol}: {ev["status"]} ratio={ev["acceptance"]["distinct_ratio"]:.4f} floor={ev["acceptance"]["distinct_noise_floor"]}')
out = encode('testsrc2=size=1024x768:rate=60', 35)
DEADLINE[0] = R.probe_deadline_seconds(2100)
try:
    rows, dt = probe(out, R.probe_frame_content); print(f'content_probe_35s_1024x768: {dt:.1f}s frames={len(rows)} (scaled bound {DEADLINE[0]:.0f} s)')
except subprocess.TimeoutExpired: print(f'content_probe_35s_1024x768: TimeoutExpired at {DEADLINE[0]:.0f} s bound')
print('nproc=%d loadavg=%s' % (os.cpu_count(), os.getloadavg()))
