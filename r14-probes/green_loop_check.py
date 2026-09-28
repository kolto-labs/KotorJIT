import sys, os
sys.path.insert(0, '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness')
from kpharness import recording as REC
from kpharness import display_backends as D

media = sys.argv[1]
policy = dict(D.CONTENT_POLICIES['animated-diagnostic-v2'])
index_policy = {'bits': policy['index_bits'], 'cell': policy['index_cell'], 'inset': policy['index_inset']}

fd = os.open(media, os.O_RDONLY)
try:
    rows = REC.probe_frame_content(f'/proc/self/fd/{fd}', '/home/brunner56/.local/bin/ffprobe',
                                   pass_fds=(fd,), deadline_seconds=600.0,
                                   index_policy=index_policy, height=768)
finally:
    os.close(fd)

pts = [i / 60.0 for i in range(len(rows))]
result = D.evaluate_content(rows, pts, 0.0, pts[-1], policy)
print(media, 'status:', result['status'], 'failures:', result['failures'])
print('  index_sequence:', result['index_sequence']['status'], 'violations:', result['index_sequence']['violation_count'])
if result['index_sequence']['violations']:
    print('  first violation:', result['index_sequence']['violations'][0])
print('  level_sequence:', result['level_sequence']['status'])
