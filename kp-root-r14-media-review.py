import sys,os,json,time,hashlib
from pathlib import Path
sys.dont_write_bytecode=True
root=Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation')
sys.path.insert(0,str(root/'scripts/harness'))
from kpharness import recording as r,display_backends as d
out=Path('/tmp/kp-root-r14-media-review.json')
result={'source_hashes':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'scripts/harness/kpharness/recording.py',root/'scripts/harness/kpharness/display_backends.py']},'cases':{}}
for name in ('healthy','loop7'):
 p=Path('/tmp/kp-r14-8s-2291a5l9')/(name+'.mp4'); start=time.monotonic()
 with p.open('rb') as f:
  fd=f.fileno(); path=Path('/proc/self/fd')/str(fd)
  rows=r.probe_frame_content(path,'/home/linuxbrew/.linuxbrew/bin/ffprobe',pass_fds=(fd,),deadline_seconds=r.probe_deadline_seconds(480),index_policy={'bits':14,'cell':32,'inset':6},height=768)
  pts=r.probe_frame_pts(path,'/home/linuxbrew/.linuxbrew/bin/ffprobe',pass_fds=(fd,),deadline_seconds=30)
 ev=d.evaluate_content(rows,pts,1,7,d.CONTENT_POLICIES['animated-diagnostic-v2'])
 result['cases'][name]={'media_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'frames':len(rows),'elapsed_seconds':time.monotonic()-start,'evaluation':ev}
 out.write_text(json.dumps(result,indent=2)+'\n')
 print(name,ev['status'],ev['failures'],f'{time.monotonic()-start:.2f}s',flush=True)
 assert (ev['status']=='passed')==(name=='healthy')
