"""Do the recorder's real FFprobe children and xwininfo queries hold the inherited lock descriptor?
A private flocked temp file stands in for the lock (the canonical lock is never opened).
Host only: needs brew ffprobe and /usr/bin/ffmpeg for one synthetic lavfi clip."""
import fcntl, os, subprocess, sys, tempfile, threading, time
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import recording as R

tmp = Path(tempfile.mkdtemp(prefix='kp-r11-p13-'))
lock = os.open(tmp / 'lock', os.O_RDWR | os.O_CREAT, 0o600); fcntl.flock(lock, fcntl.LOCK_EX)
lock_id = os.fstat(lock); key = f'{os.major(lock_id.st_dev):02x}:{os.minor(lock_id.st_dev):02x}:{lock_id.st_ino}'
clip = tmp / 'c.mp4'
subprocess.run(['/usr/bin/ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=320x240:r=60', '-t', '20',
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-pix_fmt', 'yuv420p', str(clip)], check=True)
seen = {}
def holds_lock(pid):
    for fd in os.listdir(f'/proc/{pid}/fd'):
        try:
            st = os.stat(f'/proc/{pid}/fd/{fd}')
        except OSError:
            continue
        if (st.st_dev, st.st_ino) == (lock_id.st_dev, lock_id.st_ino):
            info = Path(f'/proc/{pid}/fdinfo/{fd}').read_text()
            return fd, ('FLOCK' in info and key in info)
    return None, False
def spying_popen(command, **kwargs):
    process = subprocess.Popen(command, **kwargs)
    try:
        seen[Path(command[0]).name + ':' + ' '.join(command[1:3])] = holds_lock(process.pid)
    except FileNotFoundError:
        seen[command[0]] = 'exited before inspection'
    return process
rec = R.X11WindowRecorder.__new__(R.X11WindowRecorder)
rec._inherited_fds = (lock,); rec._probe_frames = 1200
# Route the real default probes through the spying Popen.
pts = R.probe_frame_pts(clip, '/home/linuxbrew/.linuxbrew/bin/ffprobe', pass_fds=rec._inherit(), popen=spying_popen,
                        deadline_seconds=R.probe_deadline_seconds(rec._probe_frames))
fd = os.open(clip, os.O_RDONLY)
rows = R.probe_frame_content(Path(f'/proc/self/fd/{fd}'), '/home/linuxbrew/.linuxbrew/bin/ffprobe',
                             pass_fds=rec._inherit((fd,)), popen=spying_popen,
                             deadline_seconds=R.probe_deadline_seconds(len(pts)))
# _query: xwininfo stand-in that reports its own fds (no X server is contacted).
def run(command, **kwargs):
    return subprocess.run(['sh', '-c', 'ls /proc/self/fd'], capture_output=True, text=True, pass_fds=kwargs.get('pass_fds', ()))
rec._run = run
out = rec._query(['xwininfo', '-root'], env={}, text=True)
print(f'pts_frames={len(pts)} content_rows={len(rows)}')
for name, value in seen.items():
    print(f'{name}: lock_fd_and_flock={value}')
print(f'xwininfo_query_child_fds={out.stdout.split()} lock_fd={lock}')
# Wrapper check: does rec._inherit really pass the lock when the default probe path is used?
print('default_pts_probe_passes=', rec._inherit(), 'default_content_probe_passes=', rec._inherit((fd,)))
