"""Content-gate attacks with real encodes. Host only: lavfi -> bgr0 rawvideo -> /usr/bin/ffmpeg with the
recorder's exact codec -> production probe_frame_content/probe_frame_pts (brew FFprobe) -> evaluate_content.
No display, no x11grab."""
import json, os, subprocess, sys, time
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import recording as R
from kpharness.display_backends import evaluate_content, CONTENT_POLICIES
FFMPEG = '/usr/bin/ffmpeg'; FFPROBE = '/home/linuxbrew/.linuxbrew/bin/ffprobe'
CODEC = ['-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-pix_fmt', 'yuv420p', '-threads', '2']
OUT = Path('/tmp/kp-r11-adv-content'); OUT.mkdir(exist_ok=True)
S = '1024x768'
BOX = "drawbox=x='mod(t*600\\,900)':y=300:w={w}:h={w}:color=white:t=fill"
STILL = f'testsrc2=s={S}:r=60,trim=end_frame=1,loop=loop=-1:size=1,setpts=N/60/TB'
SOURCES = [
    # stale content that should FAIL the diagnostic gate
    ('alternating_two_frames', f'testsrc2=s={S}:r=60,trim=end_frame=2,loop=loop=-1:size=2,setpts=N/60/TB', 10),
    ('half_dup_temporal_noise_4', f'testsrc2=s={S}:r=30,fps=60,noise=alls=4:allf=t', 10),
    ('half_dup_temporal_noise_1', f'testsrc2=s={S}:r=30,fps=60,noise=alls=1:allf=t', 10),
    ('still_moving_box_64', STILL + ',' + BOX.format(w=64), 10),
    ('still_moving_box_128', STILL + ',' + BOX.format(w=128), 10),
    ('still_moving_box_200', STILL + ',' + BOX.format(w=200), 10),
    ('half_dup_plus_live_box_128', f'testsrc2=s={S}:r=30,fps=60,' + BOX.format(w=128), 10),
    # fresh content that should PASS
    ('testsrc2_60_yuv_path', f'testsrc2=s={S}:r=60,format=yuv420p', 10),
    ('testsrc2_640x480_upscaled', 'testsrc2=s=640x480:r=60,scale=1024:768', 10),
    ('testsrc2_60_long', f'testsrc2=s={S}:r=60', 40),
    ('testsrc_v1_60', f'testsrc=s={S}:r=60', 10),
    ('testsrc2_fade_in_2s', f'testsrc2=s={S}:r=60,fade=in:st=0:d=2', 10),
]

def encode(name, graph, seconds):
    out = OUT / f'{name}.mp4'
    if out.exists():
        return out
    src = [FFMPEG, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', graph, '-t', str(seconds), '-pix_fmt', 'bgr0',
           '-f', 'rawvideo', '-']
    enc = [FFMPEG, '-nostdin', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr0', '-video_size', S,
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
for name, graph, seconds in SOURCES:
    if only and name not in only:
        continue
    t0 = time.monotonic(); rows, pts = probe(encode(name, graph, seconds))
    end = seconds - 1.0
    d = evaluate_content(rows, pts, 1.0, end, CONTENT_POLICIES['animated-diagnostic-v1'])
    g = evaluate_content(rows, pts, 1.0, end, CONTENT_POLICIES['game-capture-v1'])
    sel = [i for i, v in enumerate(pts) if 1.0 <= v <= end][1:]
    m = sorted(max(rows[i]['ydif'], rows[i]['udif'], rows[i]['vdif']) for i in sel)
    print(f'{name}: diag={d["status"]} ratio={d["acceptance"]["distinct_ratio"]:.4f} '
          f'game={g["status"]} ratio={g["acceptance"]["distinct_ratio"]:.4f} '
          f'maxdif[min,p10,p50]=[{m[0]:.3f},{m[len(m)//10]:.3f},{m[len(m)//2]:.3f}] n={len(m)+1} '
          f'fails={d["failures"]} probe_s={time.monotonic()-t0:.0f}', flush=True)
    if name == 'testsrc2_fade_in_2s':
        for start in (0.0, 0.05, 0.1, 0.2, 0.3, 0.5):
            e = evaluate_content(rows, pts, start, end, CONTENT_POLICIES['game-capture-v1'])
            print(f'  fade start={start}: first_ymax={e["first_frame"]["ymax"]} black_fail='
                  f'{any("black" in f for f in e["failures"])}')
    if name == 'testsrc2_60_long':
        for a, b in ((1, 11), (11, 21), (21, 31), (29, 39)):
            s2 = [i for i, v in enumerate(pts) if a <= v <= b][1:]
            mm = min(max(rows[i]['ydif'], rows[i]['udif'], rows[i]['vdif']) for i in s2)
            print(f'  window {a}-{b}s min_fresh_maxdif={mm:.3f}')
