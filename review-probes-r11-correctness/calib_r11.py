"""R11 correctness reviewer: independent noise-floor calibration (host only, lavfi synthetic).
Encode with the recorder's exact codec args (recording.py:1160-1161), probe with the production
probe_frame_content over /proc/self/fd/N (brew ffprobe), label fresh/dup from an independent
source-frame counter (drawtext-free: a second decode of the *source* graph hashed per frame)."""
import hashlib, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import recording as R, display_backends as D
FF = '/usr/bin/ffmpeg'; FP = '/home/linuxbrew/.linuxbrew/bin/ffprobe'
CODEC = ['-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-pix_fmt', 'yuv420p', '-threads', '2']
OUT = Path(__file__).parent / 'cal'; SEC = 20
S = 'size=1024x768'
SOURCES = {
  'fresh60': f'testsrc2={S}:rate=60',
  'r30_k0': f'testsrc2={S}:rate=30,fps=60',
  'r30_k1': f'testsrc2={S}:rate=30,fps=60,trim=start_frame=1,setpts=PTS-STARTPTS',
  'r20_k0': f'testsrc2={S}:rate=20,fps=60',
  'r20_k1': f'testsrc2={S}:rate=20,fps=60,trim=start_frame=1,setpts=PTS-STARTPTS',
  'r20_k2': f'testsrc2={S}:rate=20,fps=60,trim=start_frame=2,setpts=PTS-STARTPTS',
  'r50': f'testsrc2={S}:rate=50,fps=60',
  'r58': f'testsrc2={S}:rate=58,fps=60',
  'r3': f'testsrc2={S}:rate=3,fps=60',
  'slow_half': f'testsrc2={S}:rate=120,setpts=2*PTS,fps=60',
  'slow_quarter': f'testsrc2={S}:rate=240,setpts=4*PTS,fps=60',
}
def raw_hashes(graph):
    """Ground truth: md5 of each bgr0 source frame (what x11grab would hand the encoder)."""
    p = subprocess.run([FF, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', graph, '-t', str(SEC),
                        '-pix_fmt', 'bgr0', '-f', 'framemd5', '-'], capture_output=True, text=True, check=True)
    return [l.rsplit(',', 1)[1].strip() for l in p.stdout.splitlines() if l and not l.startswith('#')]
def work(name):
    graph = SOURCES[name]; mp4 = OUT / f'{name}.mp4'; t0 = time.monotonic()
    if not mp4.exists():
        src = subprocess.Popen([FF, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', graph, '-t', str(SEC),
                                '-pix_fmt', 'bgr0', '-f', 'rawvideo', '-'], stdout=subprocess.PIPE)
        subprocess.run([FF, '-nostdin', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr0', '-video_size',
                        '1024x768', '-framerate', '60', '-i', '-', *CODEC, str(mp4)], stdin=src.stdout, check=True)
        src.wait(); assert src.returncode == 0
    hashes = raw_hashes(graph)
    fd = os.open(mp4, os.O_RDONLY)
    try:
        rows = R.probe_frame_content(f'/proc/self/fd/{fd}', FP, pass_fds=(fd,), deadline_seconds=3000)
        pts = R.probe_frame_pts(f'/proc/self/fd/{fd}', FP, pass_fds=(fd,), deadline_seconds=3000)
    finally:
        os.close(fd)
    keys = subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'frame=pict_type',
                           '-of', 'csv=p=0', str(mp4)], capture_output=True, text=True, check=True).stdout.split()
    assert len(rows) == len(hashes) == len(keys) == len(pts), (name, len(rows), len(hashes), len(keys), len(pts))
    lab = []
    for i in range(1, len(rows)):
        m = max(rows[i][k] for k in ('ydif', 'udif', 'vdif'))
        lab.append((i, 'fresh' if hashes[i] != hashes[i - 1] else 'dup', keys[i].strip(','), round(m, 4)))
    ev = D.evaluate_content(rows, pts, pts[0] + 1.0, pts[-1] - 1.0, D.CONTENT_POLICIES['animated-diagnostic-v1'])
    json.dump({'name': name, 'graph': graph, 'labels': lab, 'seconds': time.monotonic() - t0,
               'diag': [ev['status'], ev['acceptance']['distinct_ratio'], ev['failures']]},
              open(OUT / f'{name}.json', 'w'))
    return name
names = sys.argv[1:] or list(SOURCES)
with ThreadPoolExecutor(3) as ex:
    for n in ex.map(work, names): print('done', n, flush=True)
