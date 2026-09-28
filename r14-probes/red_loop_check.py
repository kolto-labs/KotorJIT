import sys, os
sys.path.insert(0, sys.argv[1])
pass
from kpharness import recording as REC
from kpharness import display_backends as D

media = sys.argv[2]
policy = dict(D.CONTENT_POLICIES['animated-diagnostic-v2'])
index_policy = ({'bits': policy['index_bits'], 'cell': policy['index_cell'], 'inset': policy['index_inset']}
               if 'index_bits' in policy else None)

fd = os.open(media, os.O_RDONLY)
try:
    kwargs = {}
    if index_policy is not None:
        kwargs = dict(index_policy=index_policy, height=768)
    rows = REC.probe_frame_content(f'/proc/self/fd/{fd}', '/home/brunner56/.local/bin/ffprobe',
                                   pass_fds=(fd,), deadline_seconds=600.0, **kwargs)
finally:
    os.close(fd)

pts = [i / 60.0 for i in range(len(rows))]
result = D.evaluate_content(rows, pts, 0.0, pts[-1], policy)
print(media, 'status:', result['status'], 'failures:', result['failures'])
if 'index_sequence' in result:
    print('  index_sequence:', result['index_sequence']['status'], result['index_sequence']['violation_count'])
