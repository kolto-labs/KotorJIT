"""Round 12 calibration: the reviewer's calib_r11.py (review-probes-r11-correctness) with its
SOURCES rewritten onto the NEW diagnostic pattern, plus extra capture families.

Host only, synthetic lavfi. Each source is rendered to bgr0 rawvideo (x11grab's pixel format) and
encoded with the recorder's exact codec args (recording.py X11WindowRecorder.start). The production
probe_frame_content / probe_frame_pts read each master over /proc/self/fd/N with brew FFprobe.
Ground truth: fresh/dup labels come from framemd5 of every bgr0 source frame, never from a rate formula.
The step filter is applied at the pattern output (what mpv displays); capture duplication/skips
(fps=R,fps=60) and I-frame alignment trims are applied after it, like x11grab repeating a displayed frame."""
import hashlib, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import recording as R, display_backends as D
FF = '/usr/bin/ffmpeg'; FP = '/home/linuxbrew/.linuxbrew/bin/ffprobe'
CODEC = ['-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-pix_fmt', 'yuv420p', '-threads', '2']
OUT = Path(__file__).parent / 'cal'; OUT.mkdir(exist_ok=True)
SEC = float(os.environ.get('CAL_SECONDS', '18'))   # >= 17 s so trims put dups on I-frames 250..1000
S = 'size=1024x768'
# Must equal capture_diagnostic.PATTERN_STEP / PATTERN_GRAPH (checked at the end).
STEP = 'eq=contrast=0.4:brightness=(3*n-7*floor(3*n/7)-3)*0.11:eval=frame'
P = f'testsrc2={S}:rate=60,{STEP}'
T1 = 'trim=start_frame=1,setpts=PTS-STARTPTS'; T2 = 'trim=start_frame=2,setpts=PTS-STARTPTS'
SOURCES = {
  # reviewer's names, rewritten on the new pattern
  'fresh60': P,
  'r30_k0': f'{P},fps=30,fps=60',
  'r30_k1': f'{P},fps=30,fps=60,{T1}',
  'r20_k0': f'{P},fps=20,fps=60',
  'r20_k1': f'{P},fps=20,fps=60,{T1}',
  'r20_k2': f'{P},fps=20,fps=60,{T2}',
  'r50': f'{P},fps=50,fps=60',
  'r58': f'{P},fps=58,fps=60',
  'r3': f'{P},fps=3,fps=60',
  'slow_half': f'testsrc2={S}:rate=120,setpts=2*PTS,fps=60,{STEP}',
  'slow_quarter': f'testsrc2={S}:rate=240,setpts=4*PTS,fps=60,{STEP}',
  # round-12 additions
  'frozen': f'testsrc2={S}:rate=1,fps=60,{STEP}',          # testsrc2 changes once per second
  'r12_d5': f'{P},fps=12,fps=60',                            # source distance 5: one-level steps
  'r12_d5_k1': f'{P},fps=12,fps=60,{T1}',
  'r15': f'{P},fps=15,fps=60',
  'r45': f'{P},fps=45,fps=60',
  'r30_k1_slowq': f'testsrc2={S}:rate=240,setpts=4*PTS,fps=60,{STEP},fps=30,fps=60,{T1}',
}
def raw_hashes(graph):
    p = subprocess.run([FF, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', graph, '-t', str(SEC),
                        '-pix_fmt', 'bgr0', '-f', 'framemd5', '-'], capture_output=True, text=True, check=True)
    return [l.rsplit(',', 1)[1].strip() for l in p.stdout.splitlines() if l and not l.startswith('#')]
def work(name):
    graph = SOURCES[name]; mp4 = OUT / f'{name}.mp4'; t0 = time.monotonic(); enc_s = None
    if not mp4.exists():
        src = subprocess.Popen([FF, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', graph, '-t', str(SEC),
                                '-pix_fmt', 'bgr0', '-f', 'rawvideo', '-'], stdout=subprocess.PIPE)
        e0 = time.monotonic()
        subprocess.run([FF, '-nostdin', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr0', '-video_size',
                        '1024x768', '-framerate', '60', '-i', '-', *CODEC, str(mp4)], stdin=src.stdout, check=True)
        src.wait(); assert src.returncode == 0
        enc_s = time.monotonic() - e0
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
    evs = {}
    for pid, pol in D.CONTENT_POLICIES.items():
        ev = D.evaluate_content(rows, pts, pts[0] + 1.0, pts[-1] - 1.0, pol)
        evs[pid] = [ev['status'], ev['acceptance']['distinct_ratio'], ev['failures'], ev.get('separation')]
    json.dump({'name': name, 'graph': graph, 'labels': lab, 'seconds': time.monotonic() - t0, 'encode_seconds': enc_s,
               'rows': rows, 'pts': pts, 'evaluations': evs}, open(OUT / f'{name}.json', 'w'))
    return name
if __name__ == '__main__':
    names = sys.argv[1:] or list(SOURCES)
    with ThreadPoolExecutor(int(os.environ.get('CAL_JOBS', '3'))) as ex:
        for n in ex.map(work, names): print('done', n, flush=True)
