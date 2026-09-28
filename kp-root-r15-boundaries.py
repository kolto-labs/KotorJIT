import sys,json
from pathlib import Path
root=Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation')
sys.dont_write_bytecode=True
sys.path[:0]=[str(root/'scripts/harness'),str(root/'tools')]
from kpharness import display_backends as D
import kpharness_gamescope_backend_test as B
p=dict(D.CONTENT_POLICIES['animated-diagnostic-v2'])
results=[]
def check(name,count,advances,pts_extra,expected):
 source=[0]; pts=[0.]
 for n in range(1,count):
  source.append(source[-1]+advances.get(n,1))
  pts.append((n+sum(v for k,v in pts_extra.items() if k<=n))/60)
 rows=B.with_index_fields([{} for _ in source],source)
 r=D.content_index_sequence([v['index_top'] for v in rows],[v['index_bottom'] for v in rows],[20.]*(count-1),pts,list(range(count)),p)
 assert r['status']==expected,(name,r)
 results.append({'case':name,'status':r['status'],'ratio':r['source_drop_ratio'],'gap':r['maximum_source_gap_seconds'],'kinds':[v['kind'] for v in r['violations']]})
check('drop_ratio_exact_0.005',401,{100:2,200:2},{},'passed')
check('drop_ratio_just_over',400,{100:2,200:2},{},'failed')
check('source_gap_exact_0.050',600,{100:3},{100:1},'passed')
check('source_gap_next_frame_0.0667',1000,{100:4},{100:2},'failed')
check('sustained_delta2',600,{n:2 for n in range(1,600)},{},'failed')
check('same_brightness_delta7',2000,{100:7},{100:5},'failed')
Path('/home/brunner56/kp-live-20260922/kp-root-r15-boundaries.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
