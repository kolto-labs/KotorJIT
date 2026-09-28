import os, sys, subprocess, tempfile, shutil
sys.path.insert(0, "/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness")
sys.path.insert(0, "/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/tools")
from kpharness import capture_diagnostic as CD
from kpharness import display_backends as D
from kpharness import recording as R

REAL_FFMPEG = '/usr/bin/ffmpeg'
REAL_FFPROBE = '/home/linuxbrew/.linuxbrew/bin/ffprobe'
if not os.path.exists(REAL_FFPROBE):
    REAL_FFPROBE = shutil.which('ffprobe')

pattern = CD.PATTERN_GRAPH
seven_loop = pattern + ',trim=end_frame=7,loop=loop=-1:size=7,setpts=N/60/TB'

directory = tempfile.mkdtemp(prefix='kp-r13-7loop-')
out = os.path.join(directory, 'continuous.mp4')
seconds = 34
source = subprocess.Popen([REAL_FFMPEG, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', seven_loop,
    '-t', str(seconds), '-pix_fmt', 'bgr0', '-f', 'rawvideo', '-'], stdout=subprocess.PIPE)
subprocess.run([REAL_FFMPEG, '-nostdin', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr0',
    '-video_size', '1024x768', '-framerate', '60', '-i', '-',
    '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-pix_fmt', 'yuv420p', '-threads', '2',
    out], stdin=source.stdout, check=True, timeout=600)
source.stdout.close(); assert source.wait(timeout=60) == 0

descriptor = os.open(out, os.O_RDONLY)
path = f'/proc/self/fd/{descriptor}'
frames = int(seconds * 60)
deadline = R.probe_deadline_seconds(frames)
rows = R.probe_frame_content(path, REAL_FFPROBE, pass_fds=(descriptor,), deadline_seconds=deadline)
pts = R.probe_frame_pts(path, REAL_FFPROBE, pass_fds=(descriptor,), deadline_seconds=deadline)
os.close(descriptor)

result = D.evaluate_content(rows, pts, 3.0, pts[-1] - 1.0, D.CONTENT_POLICIES['animated-diagnostic-v2'])
print("status:", result['status'])
print("failures:", result['failures'])
print("distinct_ratio:", result['acceptance']['distinct_ratio'])
if 'separation' in result:
    print("separation:", result['separation']['status'], result['separation'].get('inside_band'))
if 'level_sequence' in result:
    ls = result['level_sequence']
    print("level_sequence status:", ls['status'], "violation_count:", ls['violation_count'])
    print("histogram:", ls['level_histogram'])
    print("ladder resolved:", ls['ladder']['resolved'], "resolution:", ls['ladder']['resolution'])
print("kept encode at:", out)
