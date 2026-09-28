"""R10 re-run of R9 p1: head taken only from CLI stderr/stdout or the commitment log."""
import io, json, os, sys, types, contextlib, hashlib, tempfile
from pathlib import Path
from unittest import mock
W='/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W+'/tools'); sys.path.insert(0, W+'/scripts/harness')
import kpharness_gamescope_backend_test as T
from kpharness import creative_accept as A, recording as R

def heads(text): return T.head_lines(text)

def cli(run, log, head, probe, extra=()):
    rec = json.loads((run/'creative-run.json').read_text())
    argv = [str(run), '--reviewer', 'r', '--media-sha256', R.sha256(run/'continuous.mp4'),
            '--route-sha256', rec['route_source']['sha256'], '--ffprobe-sha256', rec['cadence']['probe_tool']['sha256'],
            '--cleanup-ledger-sha256', head, '--cleanup-commitment-log', str(log), *extra]
    o, e = io.StringIO(), io.StringIO()
    with mock.patch.object(A, 'probe_frame_pts', probe), mock.patch.object(A, 'probe_frame_content', T.fixture_content_probe), \
         contextlib.redirect_stdout(o), contextlib.redirect_stderr(e):
        code = A.main(argv)
    return code, o.getvalue(), e.getvalue()

def setup(base):
    run = base/'run'; run.mkdir(); op = base/'op'; op.mkdir(); log = op/'c.log'; log.touch()
    (run/'continuous.mp4').write_bytes(b'frames')
    (run/'creative-run.json').write_text(json.dumps(T.completed_receipt(run)))
    (run/A.CLEANUP_LEDGER).unlink(missing_ok=True)  # fixture pre-initializes; re-launch through the API
    e = io.StringIO()
    with contextlib.redirect_stderr(e):
        A.initialize_cleanup_ledger(run, commitment_log=log)
    return run, log, heads(e.getvalue())[0]

survivor = R.ProbeCleanupError(types.SimpleNamespace(pid=4242, pid_start='12345'), ['ffprobe'], 'survived')
def failing(*a, **k): raise survivor

with tempfile.TemporaryDirectory() as t:
    base = Path(t); run, log, launch = setup(base)
    other = base/'run2'; other.mkdir(); e = io.StringIO()
    with contextlib.redirect_stderr(e): A.initialize_cleanup_ledger(other, commitment_log=log)
    print('launch_heads_unique=%s' % (heads(e.getvalue())[0]['cleanup_ledger_sha256'] != launch['cleanup_ledger_sha256']))
    code, out, err = cli(run, log, launch['cleanup_ledger_sha256'], failing)
    stderr_head = heads(err)[-1]; stdout_json = json.loads(out.strip().splitlines()[-1])
    print('failed_cli_exit=%d stdout_ok=%s' % (code, stdout_json['ok']))
    print('stderr_head_has_failure_id=%s stdout_matches_stderr=%s' % (bool(stderr_head['failure_id']),
          stdout_json['cleanup_ledger_sha256'] == stderr_head['cleanup_ledger_sha256'] and stdout_json['failure_id'] == stderr_head['failure_id']))
    captured = stderr_head['cleanup_ledger_sha256']   # the only head we keep
    path = run/A.CLEANUP_LEDGER
    good = path.read_bytes()
    def attempt(name):
        c, o, _ = cli(run, log, captured, T.fixture_pts_probe)
        st = json.loads((run/'creative-run.json').read_text())['visual_review']['status']
        print('%s: exit=%d ok=%s receipt=%s' % (name, c, json.loads(o.strip().splitlines()[-1])['ok'], st))
    # reset to launch bytes
    L = json.loads(good); L['records'] = []; path.write_bytes(T.canonical_ledger_bytes(L)); attempt('reset_to_launch')
    # fresh empty ledger with a new nonce
    path.unlink(); e = io.StringIO(); alog = base/'op'/'attacker.log'; alog.touch()
    with contextlib.redirect_stderr(e): A.initialize_cleanup_ledger(run, commitment_log=alog)
    attempt('fresh_empty')
    # forged pair (rechained)
    L = json.loads(good); f = L['records'][0]
    L['records'].append({'schema':1,'type':'resolution','sequence':2,'id':f['id'],'prev_digest':f['record_digest'],
        'timestamp_utc':f['timestamp_utc'],'payload':{'failure_id':f['id'],'failure_digest':f['record_digest'],
        'pid':4242,'pid_start':'12345','outcome':'already_exited','pidfd':'not_needed','signal':'not_sent','wait':'confirmed_absent'}})
    path.write_bytes(T.canonical_ledger_bytes(T.rechain(L))); attempt('forged_pair')
    # deletion
    path.unlink(); attempt('deleted')
    # v1 downgrade
    path.write_bytes(b'{"records":[],"schema":1}\n'); attempt('v1_downgrade')
    # nonce reuse: transplant run2's clear ledger
    path.write_bytes((other/A.CLEANUP_LEDGER).read_bytes()); attempt('transplant_other_run')
    # trust root: same-user attacker also appends a forged head line to the commitment log
    L = json.loads(good); L['records'].append({'schema':1,'type':'resolution','sequence':2,'id':f['id'],'prev_digest':f['record_digest'],
        'timestamp_utc':f['timestamp_utc'],'payload':{'failure_id':f['id'],'failure_digest':f['record_digest'],
        'pid':4242,'pid_start':'12345','outcome':'already_exited','pidfd':'not_needed','signal':'not_sent','wait':'confirmed_absent'}})
    forged = T.canonical_ledger_bytes(T.rechain(L)); path.write_bytes(forged)
    line = dict(stderr_head, event='recovery_resolution', sequence=2, cleanup_ledger_sha256=hashlib.sha256(forged).hexdigest())
    with log.open('a') as s: s.write(json.dumps(line, sort_keys=True, separators=(',',':'))+'\n')
    run_s = str(run.resolve())
    last_for_nonce = [l for l in heads(log.read_text()) if l['run_dir']==run_s and l['nonce']==launch['nonce']][-1]
    c, o, _ = cli(run, log, last_for_nonce['cleanup_ledger_sha256'], T.fixture_pts_probe)
    print('log_appended_forgery_following_doc_last_line_for_nonce: exit=%d ok=%s' % (c, json.loads(o.strip().splitlines()[-1])['ok']))
