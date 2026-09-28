import io, json, sys, types, contextlib, hashlib, subprocess
from pathlib import Path
import tempfile
W='/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W+'/tools'); sys.path.insert(0, W+'/scripts/harness')
import kpharness_gamescope_backend_test as T
from kpharness import creative_accept as A, recording as R
EMPTY = hashlib.sha256(b'{"records":[],"schema":1}\n').hexdigest()
with tempfile.TemporaryDirectory() as t:
    run = Path(t); (run/'continuous.mp4').write_bytes(b'frames')
    rec = T.completed_receipt(run); (run/'creative-run.json').write_text(json.dumps(rec))
    launch_head = A.cleanup_ledger_sha256(run)
    print('launch_head_is_universal_constant=%s' % (launch_head == EMPTY))
    child = types.SimpleNamespace(pid=4242, pid_start='12345')
    err = R.ProbeCleanupError(child, ['/proc/self/fd/9'], 'ffprobe child survived two bounded kill/reap attempts')
    out, errs = io.StringIO(), io.StringIO()
    # simulate the CLI path: main() -> accept() with a probe that leaves a retained child
    orig = A.probe_frame_pts
    A.accept.__kwdefaults__['pts_probe'] = (lambda *a, **k: (_ for _ in ()).throw(err))
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(errs):
            A.main([str(run), '--reviewer', 'r', '--media-sha256', R.sha256(run/'continuous.mp4'),
                    '--route-sha256', rec['route_source']['sha256'], '--ffprobe-sha256',
                    rec['cadence']['probe_tool']['sha256'], '--cleanup-ledger-sha256', launch_head])
    except Exception as e:
        exc = f'{type(e).__name__}: {e}'
    A.accept.__kwdefaults__['pts_probe'] = orig
    real_head = A.cleanup_ledger_sha256(run)
    _, _, fails, _ = A._load_cleanup_ledger(run); fid = next(iter(fails))
    text = out.getvalue()+errs.getvalue()+exc
    print('failure_exception=%r' % exc)
    print('post_failure_head_emitted_out_of_band=%s' % (real_head in text))
    print('failure_id_emitted_out_of_band=%s' % (fid in text))
    # Attack A: reset ledger to the empty launch bytes (delete failure)
    (run/A.CLEANUP_LEDGER).unlink(); A.initialize_cleanup_ledger(run)
    review_head = hashlib.sha256((run/A.CLEANUP_LEDGER).read_bytes()).hexdigest()  # documented "SHA at review"
    ok = T.accept_visual(run, reviewer='r', media_sha256=R.sha256(run/'continuous.mp4'),
        cleanup_ledger_sha256=review_head, pts_probe=T.fixture_pts_probe)
    print('reset_to_empty_accepted=%s' % ok['ok'])
    print('reset_verify=%s export_head=%s' % (T.verify_acceptance(ok), ok['visual_review']['cleanup_ledger_sha256']==EMPTY))
with tempfile.TemporaryDirectory() as t:
    run = Path(t); (run/'continuous.mp4').write_bytes(b'frames')
    rec = T.completed_receipt(run); (run/'creative-run.json').write_text(json.dumps(rec))
    T.write_cleanup_failure(run, 'a'*32, pid=4242, start='12345')   # the real retained child
    # Attack B: replace with a forged, internally valid failure+resolution chain for a different child
    (run/A.CLEANUP_LEDGER).unlink(); A.initialize_cleanup_ledger(run)
    f = T.write_cleanup_failure(run, 'c'*32, pid=999999, start='1')
    A._append_cleanup_record(run, 'resolution', {'failure_id': f['id'], 'failure_digest': f['record_digest'],
        'pid': 999999, 'pid_start': '1', 'outcome': 'already_exited', 'pidfd': 'not_needed',
        'signal': 'not_sent', 'wait': 'confirmed_absent'}, identifier=f['id'])
    review_head = hashlib.sha256((run/A.CLEANUP_LEDGER).read_bytes()).hexdigest()
    ok = T.accept_visual(run, reviewer='r', media_sha256=R.sha256(run/'continuous.mp4'),
        cleanup_ledger_sha256=review_head, pts_probe=T.fixture_pts_probe)
    print('forged_pair_accepted=%s verify=%s' % (ok['ok'], T.verify_acceptance(ok)))
