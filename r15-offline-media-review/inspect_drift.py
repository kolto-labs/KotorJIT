import json, os, sys, time, hashlib
from pathlib import Path
root=Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'); sys.path.insert(0,str(root/'scripts/harness'))
from kpharness import recording as R
from kpharness import display_backends as D
media=Path('/tmp/kp-r15-offline-media/drift_pair8.mp4'); ff='/home/linuxbrew/.linuxbrew/bin/ffprobe'; fd=os.open(media,os.O_RDONLY); p=Path(f'/proc/self/fd/{fd}')
try:
 t=time.monotonic(); pts=R.probe_frame_pts(p,ff,pass_fds=(fd,),deadline_seconds=438); rows=R.probe_frame_content(p,ff,pass_fds=(fd,),deadline_seconds=438,index_policy={'bits':14,'cell':32,'inset':6},height=768)
finally: os.close(fd)
sel=[i for i,x in enumerate(pts) if 1<=x<=7]; pol=dict(D.CONTENT_POLICIES['animated-diagnostic-v2']); ev=D.evaluate_content(rows,pts,1,7,pol); idx=ev['index_sequence']
local=[]
for i in range(55,70):
 top,_,_=D.decode_index_cells(rows[i]['index_top'],pol['index_luma_threshold'],pol['index_bits']); bot,_,_=D.decode_index_cells(rows[i]['index_bottom'],pol['index_luma_threshold'],pol['index_bits']); local.append({'i':i,'pts':pts[i],'top':top,'bottom':bot,'delta':None if i==0 else top-(D.decode_index_cells(rows[i-1]['index_top'],pol['index_luma_threshold'],pol['index_bits'])[0])})
out={'media_sha256':hashlib.sha256(media.read_bytes()).hexdigest(),'frames':len(rows),'pts_first':pts[0],'pts_last':pts[-1],'eval_status':ev['status'],'index_status':idx['status'],'ratio':idx['source_drop_ratio'],'max_gap':idx['maximum_source_gap_seconds'],'violations':idx['violations'],'local':local}
Path('/home/brunner56/kp-live-20260922/r15-offline-media-review/drift_pair_receipt.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
