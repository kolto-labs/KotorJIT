"""R10: commitment-log placement, failure persistence when the log is unusable, lock/race."""
import io, json, os, sys, types, contextlib, hashlib, tempfile, threading, time
from pathlib import Path
from unittest import mock
W='/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W+'/tools'); sys.path.insert(0, W+'/scripts/harness')
import kpharness_gamescope_backend_test as T
from kpharness import creative_accept as A, recording as R

def v(path, run):
    try: A.validate_commitment_log(path, run); return 'accepted'
    except ValueError as e: return 'refused'

with tempfile.TemporaryDirectory() as t:
    b = Path(t); run = b/'run'; run.mkdir(); (run/'sub').mkdir(); out = b/'out'; out.mkdir()
    (run/'log').touch(); (out/'log').touch()
    (out/'lnk_to_run').symlink_to(run)                  # dir symlink into run
    (run/'lnk_out').symlink_to(out)                     # dir symlink inside run pointing out
    os.chdir(run)
    cases = {
      'inside_direct': run/'log',
      'relative_inside': 'log',
      'dotdot_into_run': str(out)+'/../run/log',
      'via_dir_symlink_into_run': out/'lnk_to_run'/'log',
      'lexical_dotdot_through_symlink': str(run)+'/lnk_out/../log',   # abspath -> run/log (inside) ; kernel -> b/log
      'outside_through_link_in_run': run/'lnk_out'/'log',             # resolves to out/log
      'run_dir_itself': run,
      'outside_plain': out/'log',
    }
    for k, p in cases.items(): print(f'{k}={v(p, run)}')
    # run path given through a symlink; log inside the real run
    (b/'runlink').symlink_to(run)
    print('run_given_via_symlink_log_inside=%s' % v(run/'log', b/'runlink'))

# Failure persistence when the commitment log becomes unusable during the probe
with tempfile.TemporaryDirectory() as t:
    b = Path(t); run = b/'run'; run.mkdir(); op = b/'op'; op.mkdir(); log = op/'c.log'; log.touch()
    (run/'continuous.mp4').write_bytes(b'frames'); (run/'creative-run.json').write_text(json.dumps(T.completed_receipt(run)))
    (run/A.CLEANUP_LEDGER).unlink(missing_ok=True)
    e = io.StringIO()
    with contextlib.redirect_stderr(e): A.initialize_cleanup_ledger(run, commitment_log=log)
    head = T.head_lines(e.getvalue())[0]['cleanup_ledger_sha256']
    survivor = R.ProbeCleanupError(types.SimpleNamespace(pid=4242, pid_start='12345'), ['ffprobe'], 'survived')
    def probe(*a, **k):
        log.unlink()          # operator rotates / deletes the log while the probe runs
        raise survivor
    rec = json.loads((run/'creative-run.json').read_text())
    o, er = io.StringIO(), io.StringIO()
    with mock.patch.object(A, 'probe_frame_pts', probe), mock.patch.object(A, 'probe_frame_content', T.fixture_content_probe), \
         contextlib.redirect_stdout(o), contextlib.redirect_stderr(er):
        code = A.main([str(run), '--reviewer', 'r', '--media-sha256', R.sha256(run/'continuous.mp4'),
            '--route-sha256', rec['route_source']['sha256'], '--ffprobe-sha256', rec['cadence']['probe_tool']['sha256'],
            '--cleanup-ledger-sha256', head, '--cleanup-commitment-log', str(log)])
    res = json.loads(o.getvalue().strip().splitlines()[-1])
    print('log_vanished_during_probe: exit=%d stdout_error=%r' % (code, res['error']))
    print('  survivor_mentioned_in_output=%s' % ('survived' in o.getvalue() + er.getvalue() or '4242' in o.getvalue() + er.getvalue()))
    print('  ledger_records_after=%d gate_clear_with_same_head=%s' % (len(json.loads((run/A.CLEANUP_LEDGER).read_text())['records']),
          A.cleanup_state_clear(run, head)))
    log.touch()
    o2 = io.StringIO()
    with mock.patch.object(A, 'probe_frame_pts', T.fixture_pts_probe), mock.patch.object(A, 'probe_frame_content', T.fixture_content_probe), \
         contextlib.redirect_stdout(o2), contextlib.redirect_stderr(io.StringIO()):
        code2 = A.main([str(run), '--reviewer', 'r', '--media-sha256', R.sha256(run/'continuous.mp4'),
            '--route-sha256', rec['route_source']['sha256'], '--ffprobe-sha256', rec['cadence']['probe_tool']['sha256'],
            '--cleanup-ledger-sha256', head, '--cleanup-commitment-log', str(log)])
    print('  reaccept_after_unrecorded_survivor: exit=%d ok=%s' % (code2, json.loads(o2.getvalue().strip().splitlines()[-1])['ok']))

# Concurrency: two appenders holding the same head; plus an unlocked writer racing an append
with tempfile.TemporaryDirectory() as t:
    b = Path(t); run = b/'run'; run.mkdir(); log = b/'c.log'; log.touch()
    with contextlib.redirect_stderr(io.StringIO()): head = A.initialize_cleanup_ledger(run, commitment_log=log)
    host = A._host_identity(); tool = {'command':'ffprobe','resolved_path':'/usr/bin/ffprobe','sha256':'1'*64}
    def payload(pid): return {'failure_type':'ffprobe_cleanup_failed','identity':'exact','pid':pid,'pid_start':'9',
        'boot_id':host['boot_id'],'pid_namespace':host['pid_namespace'],'command':['ffprobe'],'tool':tool,
        'bounded_wait_seconds':[2,2],'signal_errors':[],'recovery':A.RECOVERY_REQUIREMENT}
    results = []
    def go(pid):
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                A._append_cleanup_record(run, 'failure', payload(pid), expected_head=head, commitment_log=log, event='acceptance_failure')
            results.append('ok')
        except ValueError as e: results.append('refused')
    th = [threading.Thread(target=go, args=(p,)) for p in (11, 12, 13, 14)]
    [x.start() for x in th]; [x.join() for x in th]
    L = json.loads((run/A.CLEANUP_LEDGER).read_text())
    logged = [l for l in T.head_lines(log.read_text()) if l['event']=='acceptance_failure']
    print('concurrent_same_head_appends=%s records=%d logged_failures=%d log_head_matches_file=%s' % (sorted(results), len(L['records']),
          len(logged), logged[-1]['cleanup_ledger_sha256']==hashlib.sha256((run/A.CLEANUP_LEDGER).read_bytes()).hexdigest()))
