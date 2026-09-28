"""R12 correctness reviewer: independent recalibration of the NEW diagnostic pattern (host only).

Differs from the writer's calib_r12.py: frames are manipulated by an explicit index map in Python
(out[i] = src[map[i]]), so duplicates are placed exactly on x264's I-frames (keyint 250 -> 0,250,500,750)
for EVERY one of the 7 levels, at slow/native/fast/fully-static underlying motion, and the capture
families that skip exactly 7 source frames are built directly. Labels come from the index map
(dup iff map[i] == map[i-1]) and are cross-checked by md5 of the raw bgr0 frame.
The pattern string is imported from the production module, not retyped.
Encode: recorder's exact codec args (recording.py:1160-1161). Probe: production probe_frame_content /
probe_frame_pts over /proc/self/fd/N with brew ffprobe; verdict: production evaluate_content under v2."""
import hashlib, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import recording as R, display_backends as D, capture_diagnostic as CD
FF = '/usr/bin/ffmpeg'; FP = '/home/linuxbrew/.linuxbrew/bin/ffprobe'
CODEC = ['-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-pix_fmt', 'yuv420p', '-threads', '2']
OUT = Path(__file__).parent / 'cal'; OUT.mkdir(exist_ok=True)
FB = 1024 * 768 * 4
STEP = CD.PATTERN_STEP
S = 'size=1024x768'
assert CD.PATTERN_GRAPH == f'testsrc2={S}:rate=60,{STEP}'
SPEED = {  # underlying testsrc2 motion; the step is applied at the 60 FPS pattern output, like mpv
    'native': f'testsrc2={S}:rate=60,{STEP}',
    'slowq': f'testsrc2={S}:rate=240,setpts=4*PTS,fps=60,{STEP}',
    'fast4': f'testsrc2={S}:rate=240,fps=60,{STEP}',
    'static': f'testsrc2={S}:rate=60,trim=end_frame=1,loop=loop=-1:size=1,{STEP}',
}
N = 760
IDUP = (250, 500, 750); PDUP = (100, 400, 600)

def maps():
    fam = {}
    for sp in SPEED:
        for k in {'native': range(14), 'fast4': range(7)}.get(sp, range(3)):
            m = [i + k for i in range(N)]
            for d in IDUP + PDUP:
                m[d] = m[d - 1]
            fam[f'isodup_{sp}_k{k}'] = (sp, m)
    for sp in ('native', 'slowq', 'static'):
        for k in range(3):   # 30 FPS capture: each source frame held twice, I-frames on dups for some k
            fam[f'r30_{sp}_k{k}'] = (sp, [2 * ((i + k) // 2) for i in range(N)])
    fam['skip7_sparse_native'] = ('native', [7 * (i // 7) for i in range(N)])        # 8.57 FPS capture
    fam['skip7_every_native'] = ('native', [7 * i for i in range(300)])              # every frame 7 apart
    fam['skip7_every_slowq'] = ('slowq', [7 * i for i in range(300)])
    fam['skip7_once_native'] = ('native', [i if i < 400 else i + 6 for i in range(N)])  # one 7-frame jump
    fam['skip7_once_slowq'] = ('slowq', [i if i < 400 else i + 6 for i in range(N)])
    fam['pingpong_native'] = ('native', [i % 2 for i in range(N)])     # stale two-buffer capture
    fam['cycle3_native'] = ('native', [i % 3 for i in range(N)])
    for sp in SPEED:
        fam[f'clean_{sp}'] = (sp, list(range(N)))
    return fam

FAM = maps()

def work(name):
    sp, m = FAM[name]; mp4 = OUT / f'{name}.mp4'; t0 = time.monotonic()
    need = max(m) + 1
    src = subprocess.Popen([FF, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', SPEED[sp], '-frames:v', str(need),
                            '-pix_fmt', 'bgr0', '-f', 'rawvideo', '-'], stdout=subprocess.PIPE)
    enc = subprocess.Popen([FF, '-nostdin', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr0',
                            '-video_size', '1024x768', '-framerate', '60', '-i', '-', *CODEC, str(mp4)],
                           stdin=subprocess.PIPE)
    wanted = {}
    for j in m:
        wanted[j] = wanted.get(j, 0) + 1
    cache = {}; md5 = {}
    j = 0; i = 0
    while i < len(m):
        while m[i] not in cache:
            buf = src.stdout.read(FB); assert len(buf) == FB, (name, j)
            if j in wanted:
                cache[j] = buf; md5[j] = hashlib.md5(buf).hexdigest()
            j += 1
        enc.stdin.write(cache[m[i]])
        wanted[m[i]] -= 1
        if not wanted[m[i]]:
            del cache[m[i]]
        i += 1
    enc.stdin.close(); assert enc.wait() == 0
    src.stdout.close(); src.kill(); src.wait()
    fd = os.open(mp4, os.O_RDONLY)
    try:
        rows = R.probe_frame_content(f'/proc/self/fd/{fd}', FP, pass_fds=(fd,), deadline_seconds=3000)
        pts = R.probe_frame_pts(f'/proc/self/fd/{fd}', FP, pass_fds=(fd,), deadline_seconds=3000)
    finally:
        os.close(fd)
    keys = subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'frame=pict_type',
                           '-of', 'csv=p=0', str(mp4)], capture_output=True, text=True, check=True).stdout.split()
    assert len(rows) == len(m) == len(keys) == len(pts), (name, len(rows), len(m), len(keys), len(pts))
    lab = []
    for i in range(1, len(rows)):
        v = max(rows[i][k] for k in ('ydif', 'udif', 'vdif'))
        fresh = m[i] != m[i - 1]
        assert fresh == (md5[m[i]] != md5[m[i - 1]]) or sp == 'static' and fresh, (name, i)
        lvl = lambda n: (3 * n) % 7 - 3
        lab.append({'i': i, 'fresh': fresh, 'dist': m[i] - m[i - 1], 'lvl_prev': lvl(m[i - 1]), 'lvl': lvl(m[i]),
                    'key': keys[i].strip(','), 'v': round(v, 4)})
    ev = D.evaluate_content(rows, pts, pts[0], pts[-1], D.CONTENT_POLICIES['animated-diagnostic-v2'])
    json.dump({'name': name, 'speed': sp, 'labels': lab, 'seconds': time.monotonic() - t0,
               'keyframes': [i for i, k in enumerate(keys) if k.strip(',') == 'I'],
               'diag': [ev['status'], ev['acceptance']['distinct_ratio'], ev['failures'],
                        {k: ev['separation'][k] for k in ('below_band', 'inside_band', 'above_band',
                                                          'duplicate_max', 'fresh_min', 'status')}]},
              open(OUT / f'{name}.json', 'w'))
    os.unlink(mp4)
    return name, round(time.monotonic() - t0, 1)

if __name__ == '__main__':
    names = sys.argv[1:] or [n for n in FAM if not (OUT / f'{n}.json').exists()]
    with ThreadPoolExecutor(int(os.environ.get('JOBS', '3'))) as ex:
        for r in ex.map(work, names): print('done', *r, flush=True)
