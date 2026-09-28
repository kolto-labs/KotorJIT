from __future__ import annotations
import json, os, subprocess, time
from pathlib import Path
import sys
root=Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation')
sys.path.insert(0,str(root/'scripts/harness'))
from kpharness import capture_diagnostic as C
from kpharness import display_backends as D
from kpharness import recording as R
OUT=Path('/tmp/kp-r15-offline-media'); OUT.mkdir(exist_ok=True)
FFM='/home/linuxbrew/.linuxbrew/bin/ffmpeg'; FFP='/home/linuxbrew/.linuxbrew/bin/ffprobe'
base=C.PATTERN_GRAPH
variants={
 'drift_pair8': f"{base},loop=loop=1:size=1:start=60,select='not(eq(n,62))',setpts=N/(60*TB),fps=60,trim=duration=8,setpts=PTS-STARTPTS",
}
results=[]
for name,graph in variants.items():
    dur=34 if name=='healthy34' else 8
    path=OUT/(name+'.mp4')
    cmd=[FFM,'-hide_banner','-loglevel','error','-threads','1','-f','lavfi','-i',graph,'-t',str(dur),'-an','-c:v','libx264','-preset','ultrafast','-crf','28','-pix_fmt','yuv420p','-movflags','+faststart','-threads','2','-y',str(path)]
    t=time.monotonic(); rec={'case':name,'encode_cmd':cmd,'graph':graph,'duration':dur}
    try:
        if path.exists():
            chk=subprocess.run([FFP,'-v','error','-count_frames','-select_streams','v:0','-show_entries','stream=nb_read_frames','-of','default=nw=1:nk=1',str(path)],capture_output=True,text=True,timeout=20,check=False)
            if chk.returncode==0 and chk.stdout.strip()==('2040' if dur==34 else '480'):
                rec.update(encode_rc='retained',encode_elapsed=0.0,encode_stderr='',bytes=path.stat().st_size)
            else:
                rec.update(encode_rc='invalid_retained',encode_elapsed=0.0,encode_stderr=chk.stderr,bytes=path.stat().st_size); results.append(rec); print(json.dumps({'case':name,'encode_rc':rec['encode_rc']})); continue
        else:
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=90,check=False)
            rec.update(encode_rc=p.returncode,encode_elapsed=time.monotonic()-t,encode_stderr=p.stderr[-4000:],bytes=path.stat().st_size if path.exists() else None)
    except subprocess.TimeoutExpired as e:
        rec.update(encode_rc='timeout',encode_elapsed=time.monotonic()-t,encode_stderr=str(e)); results.append(rec); print(json.dumps(rec)); continue
    if rec['encode_rc'] not in (0, 'retained'): results.append(rec); print(json.dumps(rec)); continue
    fd=os.open(path,os.O_RDONLY); procpath=Path(f'/proc/self/fd/{fd}')
    orig=R._bounded_probe_output; meta={};
    def wrapped(*args,**kwargs):
        started=time.monotonic(); raw=orig(*args,**kwargs); meta.update(raw_bytes=len(raw),probe_elapsed=time.monotonic()-started); return raw
    R._bounded_probe_output=wrapped
    try:
        probe_started=time.monotonic(); pts=R.probe_frame_pts(procpath,FFP,pass_fds=(fd,),deadline_seconds=R.probe_deadline_seconds(2040)); rec.update(pts_count=len(pts),pts_first=pts[0],pts_last=pts[-1]); rows=R.probe_frame_content(procpath,FFP,pass_fds=(fd,),deadline_seconds=R.probe_deadline_seconds(2040),index_policy={'bits':14,'cell':32,'inset':6},height=768); rec.update(probe_rc=0,probe_elapsed=time.monotonic()-probe_started,raw_bytes=meta.get('raw_bytes'),frame_count=len(rows))
        policy=dict(D.CONTENT_POLICIES['animated-diagnostic-v2']); end=31.0 if dur==34 else 7.0
        ev=D.evaluate_content(rows,pts,1.0,end,policy); idx=ev.get('index_sequence',{}); rec.update(eval_status=ev['status'],index_status=idx.get('status'),level_status=ev.get('level_sequence',{}).get('status'),violations=sorted({x['kind'] for x in idx.get('violations',[])}),source_drop_ratio=idx.get('source_drop_ratio'),max_gap=idx.get('maximum_source_gap_seconds'))
    except Exception as e: rec.update(probe_rc=type(e).__name__,probe_error=str(e),raw_bytes=meta.get('raw_bytes'),probe_elapsed=meta.get('probe_elapsed'))
    finally: R._bounded_probe_output=orig; os.close(fd)
    results.append(rec); Path('/home/brunner56/kp-live-20260922/r15-offline-media-review/offline-results.json').write_text(json.dumps(results,indent=2,sort_keys=True)+'\n'); print(json.dumps({'case':name,'encode_rc':rec.get('encode_rc'),'probe_rc':rec.get('probe_rc'),'pts_count':rec.get('pts_count'),'frame_count':rec.get('frame_count'),'eval_status':rec.get('eval_status'),'index_status':rec.get('index_status'),'raw_bytes':rec.get('raw_bytes'),'probe_elapsed':rec.get('probe_elapsed')},sort_keys=True))
Path('/home/brunner56/kp-live-20260922/r15-offline-media-review/offline-results.json').write_text(json.dumps(results,indent=2,sort_keys=True)+'\n')
