from pathlib import Path
import json, subprocess, hashlib, collections, math
import numpy as np

HERE=Path(__file__).resolve().parent
RUN=HERE.parent/'runs/20260927-102706-0523fa70'
MASTER=RUN/'continuous.mp4'
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before=digest(MASTER)
probe=json.loads(subprocess.check_output(['/usr/bin/ffprobe','-v','error','-show_format','-show_streams','-of','json',str(MASTER)]))
(HERE/'probe.json').write_text(json.dumps(probe,indent=2)+'\n')
frames=json.loads((HERE/'frame-timestamps.json').read_text())['frames']
pts=[float(x['best_effort_timestamp_time']) for x in frames]
delta=np.diff(pts)
gaps=[{'after_frame':i,'from_seconds':pts[i],'to_seconds':pts[i+1],'gap_seconds':float(v)} for i,v in enumerate(delta) if v>1/60+.000002]
command=['/usr/bin/ffmpeg','-nostdin','-v','error','-threads','2','-i',str(MASTER),'-vf','crop=512:600:256:80,scale=128:150:flags=area,format=gray','-fps_mode','passthrough','-threads','2','-f','rawvideo','-pix_fmt','gray','pipe:1']
measurements=[]; hashes=[]; previous=None; count=0
with (HERE/'decode-errors.log').open('wb') as err:
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=err)
    while True:
        raw=process.stdout.read(128*150)
        if not raw: break
        if len(raw)!=128*150: raise RuntimeError('partial raw frame')
        pixels=np.frombuffer(raw,dtype=np.uint8).astype(np.int16)
        hashes.append(hashlib.sha256(raw).hexdigest())
        if previous is None: measurements.append(None)
        else: measurements.append(float(np.mean(np.abs(pixels-previous))))
        previous=pixels; count+=1
    status=process.wait()
if status or count!=len(pts): raise RuntimeError(f'decode/count failure {status} {count} {len(pts)}')
(HERE/'roi-frame-measurements.json').write_text(json.dumps({'pts':pts,'roi_sha256':hashes,'mean_absolute_delta_8bit':measurements},separators=(',',':'))+'\n')

def interval(start,end):
    indexes=[i for i,t in enumerate(pts) if start<=t<end]
    bucket={}
    for i in indexes: bucket.setdefault(math.floor(pts[i]),set()).add(hashes[i])
    longest={}; near_longest={}
    for name,threshold,target in [('exact',0.0,longest),('near',0.20,near_longest)]:
        run_start=None; run_end=None
        for i in indexes:
            repeated=i>0 and (hashes[i]==hashes[i-1] if name=='exact' else measurements[i]<=threshold)
            if repeated:
                if run_start is None: run_start=pts[i-1]
                run_end=pts[i]
                duration=run_end-run_start+1/60
                if duration>target.get('duration_seconds',0): target.update(start_seconds=run_start,end_seconds=run_end,duration_seconds=duration)
            else: run_start=None
    return {'start':start,'end':end,'decoded_frames':len(indexes),'decoded_frames_per_second':len(indexes)/(end-start),
            'exact_distinct_total':len({hashes[i] for i in indexes}),'exact_distinct_per_second':{str(k):len(v) for k,v in bucket.items()},
            'mean_per_second_exact_distinct':sum(map(len,bucket.values()))/len(bucket) if bucket else None,
            'longest_exact_repeat':longest,'longest_near_repeat_mean_delta_le_0_20':near_longest,
            'timestamp_gaps_over_200ms':[g for g in gaps if start<=g['from_seconds']<end and g['gap_seconds']>.2]}

result={'master_sha256':before,'master_unchanged':digest(MASTER)==before,'roi':{'source_xywh':[256,80,512,600],'scaled_size':[128,150],'purpose':'central gameplay excluding HUD; no HUD clock hash','near_repeat_mean_absolute_delta_threshold_8bit':.20,'limitation':'quantized/compressed pixel differences do not alone prove native animation cadence'},
        'command':command,'decoder_returncode':status,'decoder_errors_bytes':(HERE/'decode-errors.log').stat().st_size,
        'frame_count':count,'pts_first':pts[0],'pts_last':pts[-1],'nonpositive_pts_deltas':int(np.count_nonzero(delta<=0)),
        'pts_delta_min':float(delta.min()),'pts_delta_max':float(delta.max()),'pts_delta_median':float(np.median(delta)),
        'pts_delta_histogram_microseconds':dict(collections.Counter(str(round(x*1e6)) for x in delta)),
        'gaps_over_nominal':gaps,'unobscured_gameplay':interval(200,224),'giant_phase_sample':interval(212,216)}
(HERE/'cadence.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
summary={k:result[k] for k in ('frame_count','pts_delta_min','pts_delta_max','pts_delta_median','nonpositive_pts_deltas','decoder_returncode','decoder_errors_bytes','master_sha256','master_unchanged','unobscured_gameplay','giant_phase_sample')}
print(json.dumps(summary,indent=2))
