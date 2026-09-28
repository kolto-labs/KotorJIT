import sys, os, math
sys.path.insert(0, '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness')
from kpharness import recording as REC
from kpharness import display_backends as D

media = sys.argv[1]
policy = dict(D.CONTENT_POLICIES['animated-diagnostic-v2'])
index_policy = {'bits': policy['index_bits'], 'cell': policy['index_cell'], 'inset': policy['index_inset']}

fd = os.open(media, os.O_RDONLY)
try:
    rows = REC.probe_frame_content(f'/proc/self/fd/{fd}', '/home/brunner56/.local/bin/ffprobe',
                                   pass_fds=(fd,), index_policy=index_policy, height=768,
                                   deadline_seconds=600.0)
finally:
    os.close(fd)

print('frames decoded', len(rows))
print('sample row keys', sorted(rows[0].keys()))
print('sample index_top len', len(rows[0]['index_top']), 'index_bottom len', len(rows[0]['index_bottom']))

pts = [i / 60.0 for i in range(len(rows))]
result = D.evaluate_content(rows, pts, 0.0, pts[-1], policy)
print('status', result['status'])
print('failures', result['failures'])
print('index_sequence status', result['index_sequence']['status'])
print('index_sequence violation_count', result['index_sequence']['violation_count'])
print('index_sequence steps/repeats', result['index_sequence']['steps'], result['index_sequence']['repeats'])
print('level_sequence status', result['level_sequence']['status'])
