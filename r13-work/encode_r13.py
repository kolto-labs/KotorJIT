"""R13 writer: synthetic encodes of PATTERN_GRAPH shapes for the level-sequence check (host only).
Frames are built by an explicit index map (out[i] = src[map[i]]) on raw bgr0 buffers, then encoded with the
recorder's exact codec args and read by the production probes (probe_frame_content / probe_frame_pts over
/proc/self/fd/N). Rows and PTS are cached as JSON; evaluation is done separately with production code.
No display, no x11grab, no mpv."""
import hashlib, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import recording as R, capture_diagnostic as CD
FF = '/usr/bin/ffmpeg'; FP = sys.argv[1] if len(sys.argv) > 1 else '/home/linuxbrew/.linuxbrew/bin/ffprobe'
CODEC = ['-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-pix_fmt', 'yuv420p', '-threads', '2']
OUT = Path('/home/brunner56/kp-live-20260922/r13-work/content'); OUT.mkdir(exist_ok=True)
FB = 1024 * 768 * 4; ROW = 1024 * 4
STEP = CD.PATTERN_STEP; S = 'size=1024x768'
assert CD.PATTERN_GRAPH == f'testsrc2={S}:rate=60,{STEP}'
SPEED = {'native': CD.PATTERN_GRAPH,
         'slowq': f'testsrc2={S}:rate=240,setpts=4*PTS,fps=60,{STEP}',
         'fast4': f'testsrc2={S}:rate=240,fps=60,{STEP}',
         'static': f'testsrc2={S}:rate=60,trim=end_frame=1,loop=loop=-1:size=1,{STEP}',
         'nostep_contrast04': f'testsrc2={S}:rate=60,eq=contrast=0.4',
         'nostep_eval_init': f'testsrc2={S}:rate=60,eq=contrast=0.4:brightness=(3*n-7*floor(3*n/7)-3)*0.11:eval=init',
         'nostep_slowq': f'testsrc2={S}:rate=240,setpts=4*PTS,fps=60,eq=contrast=0.4'}
N = 480
def ident(n=N): return [(i, None) for i in range(n)]
def fam():
    f = {}
    f['clean_native_long'] = ('native', ident(34 * 60))
    for sp in ('slowq', 'fast4', 'static'):
        f[f'clean_{sp}'] = (sp, ident())
    for sp, ks in (('native', (0, 1)), ('slowq', (0,)), ('static', (0,))):
        for k in ks:   # duplicates on x264 I-frames (250) and P-frames (100, 400)
            m = [i + k for i in range(N)]
            for d in (100, 250, 400):
                m[d] = m[d - 1]
            f[f'isodup_{sp}_k{k}'] = (sp, [(j, None) for j in m])
    f['r30_native_k0'] = ('native', [(2 * (i // 2), None) for i in range(N)])
    f['pingpong_native'] = ('native', [(i % 2, None) for i in range(N)])
    f['cycle3_native'] = ('native', [(i % 3, None) for i in range(N)])
    f['skip1_once_native'] = ('native', [(i if i < 240 else i + 1, None) for i in range(N)])
    # clock drift: every 120 frames one duplicate, then the next frame skips one source frame
    m = []; j = 0
    for i in range(N):
        if i and i % 120 == 0:
            m.append(j - 1); continue          # duplicate of the previous source frame
        if i > 1 and i % 120 == 1:
            j += 1                             # then skip one source frame
        m.append(j); j += 1
    f['drift_dup_skip_native'] = ('native', [(x, None) for x in m])
    # torn frame: every 100th output frame shows the top half of frame i over the bottom half of frame i-1
    f['torn_half_every100'] = ('native', [(i, (i - 1, 384) if i and i % 100 == 0 else None) for i in range(N)])
    f['torn_quarter_every100'] = ('native', [(i, (i - 1, 192) if i and i % 100 == 0 else None) for i in range(N)])
    for sp in ('nostep_contrast04', 'nostep_eval_init', 'nostep_slowq'):
        f[sp] = (sp, ident())
    return f
FAM = fam()
def work(name):
    out = OUT / f'{name}.rows.json'
    if out.exists(): return name, 'cached'
    sp, m = FAM[name]; mp4 = OUT / f'{name}.mp4'; t0 = time.monotonic()
    need = max(max(a, b[0] if b else 0) for a, b in m) + 1
    src = subprocess.Popen([FF, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', SPEED[sp], '-frames:v', str(need),
                            '-pix_fmt', 'bgr0', '-f', 'rawvideo', '-'], stdout=subprocess.PIPE)
    enc = subprocess.Popen([FF, '-nostdin', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr0',
                            '-video_size', '1024x768', '-framerate', '60', '-i', '-', *CODEC, str(mp4)],
                           stdin=subprocess.PIPE)
    frames = {}; j = 0; maxback = 3
    for a, tear in m:
        want = max(a, tear[0] if tear else 0)
        while j <= want:
            buf = src.stdout.read(FB); assert len(buf) == FB, (name, j)
            frames[j] = buf; j += 1
            for old in [k for k in frames if k < j - maxback - 3]: del frames[old]
        cur = frames[a]
        if tear:
            prev, rows = tear
            cur = cur[:rows * ROW] + frames[prev][rows * ROW:]
        enc.stdin.write(cur)
    enc.stdin.close(); assert enc.wait() == 0, name
    src.stdout.close(); src.kill(); src.wait()
    fd = os.open(mp4, os.O_RDONLY)
    try:
        p = Path(f'/proc/self/fd/{fd}')
        pts = R.probe_frame_pts(p, FP, pass_fds=(fd,), deadline_seconds=3600)
        rows = R.probe_frame_content(p, FP, pass_fds=(fd,), deadline_seconds=3600)
    finally:
        os.close(fd)
    out.write_text(json.dumps({'name': name, 'speed': sp, 'map': m, 'rows': rows, 'pts': pts}))
    mp4.unlink()
    return name, '%.0fs' % (time.monotonic() - t0)
only = sys.argv[2:] or list(FAM)
with ThreadPoolExecutor(int(os.environ.get('JOBS', '2'))) as pool:
    for name, how in pool.map(work, only):
        print(name, how, flush=True)
