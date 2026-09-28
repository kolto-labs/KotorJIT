import hashlib, json, os, sys
from pathlib import Path

root = Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation')
sys.path.insert(0, str(root / 'scripts/harness'))
from kpharness import display_backends as D
from kpharness import recording as R

policy = dict(D.CONTENT_POLICIES['animated-diagnostic-v2'])
policy = {'bits': policy['index_bits'], 'cell': policy['index_cell'], 'inset': policy['index_inset'],
          'index_bits': policy['index_bits'], 'index_cell': policy['index_cell'],
          'index_inset': policy['index_inset'], 'index_luma_threshold': policy['index_luma_threshold'],
          'index_fps': policy['index_fps'], 'index_step_tolerance_frames': policy['index_step_tolerance_frames'],
          **policy}
results = []
for name in ('healthy.mp4', 'loop7.mp4', 'loop14.mp4'):
    path = Path('/tmp/kp-r14-8s-2291a5l9') / name
    fd = os.open(path, os.O_RDONLY)
    try:
        probe_path = f'/proc/self/fd/{fd}'
        rows = R.probe_frame_content(probe_path, pass_fds=(fd,), index_policy=policy,
                                     height=768, deadline_seconds=R.probe_deadline_seconds(480))
    finally:
        os.close(fd)
    pts_path = path.with_suffix('.pts.json')
    # The retained clips have ordinary CFR PTS; use ffprobe through the public helper.
    fd = os.open(path, os.O_RDONLY)
    try:
        pts = R.probe_frame_pts(f'/proc/self/fd/{fd}', pass_fds=(fd,), deadline_seconds=R.probe_deadline_seconds(480))
    finally:
        os.close(fd)
    out = D.evaluate_content(rows, pts, 1.0, 7.0, policy)
    results.append({'name': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                    'bytes': path.stat().st_size, 'frames': len(rows), 'result': out})
Path('/home/brunner56/kp-live-20260922/r14-replay-results.json').write_text(
    json.dumps(results, indent=2, sort_keys=True) + '\n')
print(json.dumps([{'name': r['name'], 'status': r['result']['status'],
                   'index_status': r['result'].get('index_sequence', {}).get('status'),
                   'failures': r['result']['failures']} for r in results], indent=2))
