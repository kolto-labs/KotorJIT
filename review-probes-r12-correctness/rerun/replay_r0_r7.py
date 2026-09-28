import sys, json, copy, tempfile, types
W='/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path[:0]=[W+'/scripts/harness', W+'/tools']
import kpharness_gamescope_backend_test as T
from kpharness import display_backends as D, recording as R, creative_accept as A, session as S
from pathlib import Path
with tempfile.TemporaryDirectory() as t:
    run=Path(t); (run/'continuous.mp4').write_bytes(b'frames'); base=T.completed_receipt(run)
    print('baseline_ready', D.execution_evidence_ready(base, require_completion=True))
    def cmd_insert(r, after, items):
        c=r['capture']['command']; i=c.index(after)+1; c[i:i]=items
    def rep(r, path, speed):
        rp=Path(r['route']['report']['path']); d=json.loads(rp.read_text()); d['execution']={'game_speed_requested':speed,'game_speed_effective':speed}; rp.write_text(json.dumps(d)); r['route']['report']['sha256']=R.sha256(rp)
    muts={
     'r0_markers_absent': lambda r: r['capture'].__setitem__('markers', []),
     'r0_markers_reversed': lambda r: r['capture'].__setitem__('markers', list(reversed(r['capture']['markers']))),
     'r0_terminal_drop_999': lambda r: (r['capture']['diagnostics']['terminal'].__setitem__('drop_frames',999), r['cadence']['terminal_progress'].__setitem__('drop_frames',999)),
     'r0_interval_2_frames_10s': lambda r: r['cadence']['intervals'][0].update(frame_count=2, inter_frame_count=1, span_seconds=10.0, requested_slot_count=600, missing_slots=599),
     'r0_cmd_r1': lambda r: r['capture']['command'][-1:-1].__class__ and r['capture']['command'].insert(-1,'-r') or r['capture']['command'].insert(-1,'1'),
     'r0_cmd_setpts': lambda r: (r['capture']['command'].insert(-1,'-vf'), r['capture']['command'].insert(-1,'setpts=N/60/TB')),
     'r0_marker_uncertainty_250_poll': lambda r: [m.update(poll_interval_ms=250) for m in r['capture']['markers']],
     'r1_capture_gate_failed': lambda r: r['capture_gate'].__setitem__('status','failed'),
     'r1_input_option_after_i': lambda r: (r['capture']['command'].remove('-framerate'), r['capture']['command'].remove('60'), cmd_insert(r, ':91.0', ['-framerate','60'])),
     'r2_shared_descriptor': lambda r: r['capture']['transport']['output'].__setitem__('directory_fd', 8),
     'r2_interval_end_sample_exceeds_terminal': lambda r: r['cadence']['intervals'][0]['ffmpeg']['end_sample'].update(frame=700, out_time_us=11_000_000),
     'r3_terminal_frame_lt_decoded': lambda r: (r['capture']['diagnostics']['terminal'].__setitem__('frame',100), r['cadence']['terminal_progress'].__setitem__('frame',100)),
     'r3_extra_marker_without_interval': lambda r: r['cadence']['marker_configuration']['required_order'].insert(1,'phase_2'),
     'r6_speed_8_8': lambda r: rep(r, None, 8.0),
    }
    for n,m in muts.items():
        with tempfile.TemporaryDirectory() as t2:
            run2=Path(t2); (run2/'continuous.mp4').write_bytes(b'frames'); r=T.completed_receipt(run2)
            try: m(r); print(n, 'ready=', D.execution_evidence_ready(r, require_completion=True))
            except Exception as e: print(n, 'EXC', type(e).__name__, e)
# R7-2 spaced comm parser (session.pid_start and creative_accept._process_identity)
import builtins, io, os
stat_line=b'4242 (a b) c) d) S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 424242 20\n'
real_open=builtins.open
builtins.open=lambda p,*a,**k: io.BytesIO(stat_line) if str(p)=='/proc/4242/stat' else real_open(p,*a,**k)
print('r7_2_session_pid_start', S.pid_start(4242)); builtins.open=real_open
ro, rr, rc = os.open, os.read, os.close
os.open=lambda p,*a,**k: 999 if p=='/proc/4242/stat' else ro(p,*a,**k)
os.read=lambda fd,n: stat_line if fd==999 else rr(fd,n)
os.close=lambda fd: None if fd==999 else rc(fd)
print('r7_2_process_identity', A._process_identity(4242))
os.open=lambda p,*a,**k: (_ for _ in ()).throw(PermissionError(13,'denied')) if p=='/proc/4242/stat' else ro(p,*a,**k)
print('r8_1_permission', A._process_identity(4242))
os.open=lambda p,*a,**k: 999 if p=='/proc/4242/stat' else ro(p,*a,**k); os.read=lambda fd,n: b'4242 (trunc' if fd==999 else rr(fd,n)
print('r8_1_truncated', A._process_identity(4242))
os.open, os.read, os.close = ro, rr, rc
