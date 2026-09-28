import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness')
from kpharness import capture_diagnostic as CD, display_backends as D, recording as R

FFMPEG = '/usr/bin/ffmpeg'
FFPROBE = shutil.which('ffprobe') or '/usr/bin/ffprobe'
POLICY = D.CONTENT_POLICIES['animated-diagnostic-v2']
INDEX_POLICY = {'bits': 14, 'cell': 32, 'inset': 6}
ROOT = Path(tempfile.mkdtemp(prefix='kp-r14-8s-', dir='/tmp'))

def encode(name, graph):
    output = ROOT / (name + '.mp4')
    subprocess.run([FFMPEG, '-nostdin', '-y', '-v', 'error', '-f', 'lavfi', '-i', graph,
                    '-t', '8', '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
                    '-pix_fmt', 'yuv420p', '-threads', '2', str(output)], check=True, timeout=90)
    descriptor = os.open(output, os.O_RDONLY)
    try:
        media = f'/proc/self/fd/{descriptor}'
        deadline = R.probe_deadline_seconds(480)
        rows = R.probe_frame_content(media, FFPROBE, pass_fds=(descriptor,),
                                     deadline_seconds=deadline, index_policy=INDEX_POLICY,
                                     height=CD.HEIGHT)
        pts = R.probe_frame_pts(media, FFPROBE, pass_fds=(descriptor,), deadline_seconds=deadline)
    finally:
        os.close(descriptor)
    result = D.evaluate_content(rows, pts, 1.0, 7.0, POLICY)
    index = result.get('index_sequence', {})
    luma = [value for row in rows for region in ('index_top', 'index_bottom') for value in row[region]]
    print(name, json.dumps({'status': result['status'], 'failures': result['failures'],
        'index_status': index.get('status'), 'index_violations': index.get('violation_count'),
        'index_kinds': sorted(set(item['kind'] for item in index.get('violations', []))),
        'separation': result.get('separation', {}).get('status'),
        'bit_margin': max(luma) - min(luma)}), flush=True)
    return rows

healthy = encode('healthy', CD.PATTERN_GRAPH)
encode('loop7', CD.PATTERN_GRAPH + ',trim=end_frame=7,loop=loop=-1:size=7,setpts=N/60/TB')
encode('loop14', CD.PATTERN_GRAPH + ',trim=end_frame=14,loop=loop=-1:size=14,setpts=N/60/TB')
rows = [dict(row, index_bottom=list(healthy[0]['index_bottom'])) if index >= 60 else row
        for index, row in enumerate(healthy)]
pts = [index / 60 for index in range(len(rows))]
result = D.evaluate_content(rows, pts, 1.0, 7.0, POLICY)
index = result['index_sequence']
print('half_freeze', json.dumps({'status': result['status'], 'failures': result['failures'],
    'index_status': index['status'], 'index_violations': index['violation_count'],
    'index_kinds': sorted(set(item['kind'] for item in index['violations']))}), flush=True)
