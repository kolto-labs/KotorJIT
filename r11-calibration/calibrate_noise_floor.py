"""Round 11: calibrate the content gate's distinct-frame noise floor.

Host only. Synthetic lavfi sources are rendered to bgr0 rawvideo (the pixel
format x11grab hands the encoder) and encoded with the recorder's exact codec
settings (recording.py X11WindowRecorder.start: libx264 ultrafast crf 28
yuv420p threads 2). The production probe_frame_content / probe_frame_pts then
read each master over /proc/self/fd/N with the brew FFprobe. No display, no
x11grab, no game. For each source the ground-truth fresh/duplicate label of
every output frame is known from the source rate: output frame i (60 FPS) shows
source frame floor(i * rate / 60), so it is fresh iff that index changed.
"""
import json, math, os, subprocess, sys, tempfile, time
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import recording as R
FFMPEG = '/usr/bin/ffmpeg'; FFPROBE = '/home/linuxbrew/.linuxbrew/bin/ffprobe'
CODEC = ['-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-pix_fmt', 'yuv420p', '-threads', '2']
SECONDS = float(os.environ.get('CAL_SECONDS', '12'))
SOURCES = [  # (name, graph, source rate or None when every frame is fresh)
    ('testsrc2_60', 'testsrc2=size=1024x768:rate=60', 60),
    ('testsrc2_30_to_60', 'testsrc2=size=1024x768:rate=30,fps=60', 30),
    ('testsrc2_20_to_60', 'testsrc2=size=1024x768:rate=20,fps=60', 20),
    ('testsrc2_6_to_60', 'testsrc2=size=1024x768:rate=6,fps=60', 6),
    ('testsrc2_59_to_60', 'testsrc2=size=1024x768:rate=59,fps=60', 59),
    ('testsrc2_15_to_60', 'testsrc2=size=1024x768:rate=15,fps=60', 15),
    ('testsrc2_45_to_60', 'testsrc2=size=1024x768:rate=45,fps=60', 45),
    ('testsrc_60', 'testsrc=size=1024x768:rate=60', 60),
    ('testsrc_30_to_60', 'testsrc=size=1024x768:rate=30,fps=60', 30),
]
out_dir = Path(os.environ.get('CAL_OUT', '/tmp/kp-r11-cal')); out_dir.mkdir(exist_ok=True)

def encode(name, graph):
    out = out_dir / f'{name}.mp4'
    if out.exists():
        return out
    src = [FFMPEG, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', graph, '-t', str(SECONDS),
           '-pix_fmt', 'bgr0', '-f', 'rawvideo', '-']
    enc = [FFMPEG, '-nostdin', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr0',
           '-video_size', '1024x768', '-framerate', '60', '-i', '-', *CODEC, str(out)]
    p1 = subprocess.Popen(src, stdout=subprocess.PIPE)
    p2 = subprocess.run(enc, stdin=p1.stdout); p1.wait()
    assert p1.returncode == 0 and p2.returncode == 0, name
    return out

def probe(path):
    cache = path.with_suffix('.rows.json')
    if cache.exists():
        cached = json.loads(cache.read_text())
        return cached['rows'], cached['pts']
    fd = os.open(path, os.O_RDONLY)
    try:
        fdp = Path(f'/proc/self/fd/{fd}')
        rows = R.probe_frame_content(fdp, FFPROBE, pass_fds=(fd,), **DEADLINE)
        pts = R.probe_frame_pts(fdp, FFPROBE, pass_fds=(fd,), **DEADLINE)
    finally:
        os.close(fd)
    cache.write_text(json.dumps({'rows': rows, 'pts': pts}))
    return rows, pts

import inspect
DEADLINE = {'deadline_seconds': 900} if 'deadline_seconds' in inspect.signature(R.probe_frame_content).parameters else {}
summary = {}
dup_all, fresh_all = [], []
for name, graph, rate in SOURCES:
    started = time.monotonic()
    rows, pts = probe(encode(name, graph))
    assert len(rows) == len(pts)
    fresh, dup = [], []
    channel = {'fresh': {'ydif': [], 'udif': [], 'vdif': []}, 'dup': {'ydif': [], 'udif': [], 'vdif': []}}
    for i in range(1, len(rows)):
        m = max(rows[i]['ydif'], rows[i]['udif'], rows[i]['vdif'])
        is_fresh = math.floor(i * rate / 60 + 1e-9) != math.floor((i - 1) * rate / 60 + 1e-9)
        (fresh if is_fresh else dup).append(m)
        for key in ('ydif', 'udif', 'vdif'):
            channel['fresh' if is_fresh else 'dup'][key].append(rows[i][key])
    fresh_all += fresh; dup_all += dup
    q = lambda v: ([round(sorted(v)[min(len(v) - 1, int(len(v) * p))], 4) for p in (0, .5, .9, .99)]
                   + [round(max(v), 4)]) if v else None
    summary[name] = {'frames': len(rows), 'fresh': len(fresh), 'dup': len(dup),
                     'fresh_min': min(fresh) if fresh else None, 'dup_max': max(dup) if dup else None,
                     'dup_maxdif_q[0,.5,.9,.99,max]': q(dup), 'fresh_maxdif_q[0,.5,.9,.99,max]': q(fresh),
                     'dup_channel_max': {k: max(v) for k, v in channel['dup'].items()} if dup else None,
                     'fresh_channel_min': {k: min(v) for k, v in channel['fresh'].items()} if fresh else None,
                     'probe_seconds': round(time.monotonic() - started, 1)}
    print(json.dumps({name: summary[name]}), flush=True)
print(json.dumps({'ALL': {'fresh_frames': len(fresh_all), 'dup_frames': len(dup_all),
                          'fresh_min_maxdif': min(fresh_all), 'dup_max_maxdif': max(dup_all),
                          'geometric_midpoint': math.sqrt(min(fresh_all) * max(dup_all))},
                  'loadavg': os.getloadavg()}), flush=True)
