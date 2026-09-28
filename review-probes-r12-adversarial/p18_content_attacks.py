"""R12 content-gate attacks on the NEW pattern. Host only, synthetic lavfi: PATTERN_GRAPH -> bgr0 rawvideo ->
/usr/bin/ffmpeg with the recorder's exact codec -> production probe_frame_content/probe_frame_pts (brew FFprobe)
-> evaluate_content under animated-diagnostic-v2. No display, no x11grab."""
import json, os, subprocess, sys, time
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import recording as R
from kpharness.display_backends import evaluate_content, CONTENT_POLICIES
from kpharness.capture_diagnostic import PATTERN_GRAPH as P
FFMPEG = '/usr/bin/ffmpeg'; FFPROBE = '/home/linuxbrew/.linuxbrew/bin/ffprobe'
CODEC = ['-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-pix_fmt', 'yuv420p', '-threads', '2']
OUT = Path('/tmp/kp-r12-adv-content'); OUT.mkdir(exist_ok=True)
FROZEN = 'trim=end_frame=1,loop=loop=-1:size=1,setpts=N/60/TB'
def region(rows):  # top `rows` fresh, the rest frozen at frame 0
    return f'{P},split[a][b];[b]{FROZEN},crop=1024:{768-rows}:0:{rows}[bot];[a]crop=1024:{rows}:0:0[top];[top][bot]vstack'
SOURCES = [
    ('fresh', P),
    ('abab_two_frames', f'{P},trim=end_frame=2,loop=loop=-1:size=2,setpts=N/60/TB'),
    ('skip7_every_frame', f'{P},framestep=7,setpts=N/60/TB'),
    ('half_frozen_bottom', region(384)),
    ('quarter_fresh_top', region(192)),
    ('tenth_fresh_top', region(80)),
    ('every_other_dup_noise3', f'{P},framestep=2,setpts=N/30/TB,fps=60,noise=alls=3:allf=t'),
    ('tblend_average', f'{P},tblend=all_mode=average'),
]
SECONDS = 8
def encode(name, graph):
    out = OUT / f'{name}.mp4'
    if out.exists(): return out
    src = [FFMPEG, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', graph, '-t', str(SECONDS), '-pix_fmt', 'bgr0',
           '-f', 'rawvideo', '-']
    enc = [FFMPEG, '-nostdin', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr0', '-video_size', '1024x768',
           '-framerate', '60', '-i', '-', *CODEC, str(out)]
    p1 = subprocess.Popen(src, stdout=subprocess.PIPE); p2 = subprocess.run(enc, stdin=p1.stdout); p1.wait()
    assert p1.returncode == 0 and p2.returncode == 0, name
    return out
def probe(path):
    cache = path.with_suffix('.rows.json')
    if cache.exists():
        c = json.loads(cache.read_text()); return c['rows'], c['pts']
    fd = os.open(path, os.O_RDONLY)
    try:
        fdp = Path(f'/proc/self/fd/{fd}')
        pts = R.probe_frame_pts(fdp, FFPROBE, pass_fds=(fd,), deadline_seconds=3600)
        rows = R.probe_frame_content(fdp, FFPROBE, pass_fds=(fd,), deadline_seconds=3600)
    finally:
        os.close(fd)
    cache.write_text(json.dumps({'rows': rows, 'pts': pts})); return rows, pts
only = set(sys.argv[1:])
for name, graph in SOURCES:
    if only and name not in only: continue
    t0 = time.monotonic(); rows, pts = probe(encode(name, graph))
    d = evaluate_content(rows, pts, 1.0, SECONDS - 1.0, CONTENT_POLICIES['animated-diagnostic-v2'])
    s = d.get('separation') or {}
    sel = [i for i, v in enumerate(pts) if 1.0 <= v <= SECONDS - 1.0][1:]
    m = sorted(max(rows[i]['ydif'], rows[i]['udif'], rows[i]['vdif']) for i in sel)
    yavg = [round(rows[i]['yavg'], 1) for i in sel[:8]]
    print(f'{name}: status={d["status"]} ratio={d["acceptance"]["distinct_ratio"]:.4f} sep={s.get("status")} '
          f'below/inside/above={s.get("below_band")}/{s.get("inside_band")}/{s.get("above_band")} '
          f'maxdif[min,p50,max]=[{m[0]:.2f},{m[len(m)//2]:.2f},{m[-1]:.2f}] yavg[:8]={yavg} '
          f'fails={[f.split(":")[0] for f in d["failures"]]} t={time.monotonic()-t0:.0f}s', flush=True)
