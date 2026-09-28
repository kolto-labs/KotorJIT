"""R10 extras: hard-link trigger for R10-1, xwininfo title injection, pidfd-held reuse with a real fd."""
import io, json, os, sys, types, contextlib, tempfile
from pathlib import Path
from unittest import mock
W='/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W+'/tools'); sys.path.insert(0, W+'/scripts/harness')
import kpharness_gamescope_backend_test as T
from kpharness import creative_accept as A, recording as R
# (a) operator hard-links (backs up) the log while the probe runs
with tempfile.TemporaryDirectory() as t:
    b = Path(t); run = b/'run'; run.mkdir(); op = b/'op'; op.mkdir(); log = op/'c.log'; log.touch()
    (run/'continuous.mp4').write_bytes(b'frames'); (run/'creative-run.json').write_text(json.dumps(T.completed_receipt(run)))
    (run/A.CLEANUP_LEDGER).unlink(missing_ok=True)
    e = io.StringIO()
    with contextlib.redirect_stderr(e): A.initialize_cleanup_ledger(run, commitment_log=log)
    head = T.head_lines(e.getvalue())[0]['cleanup_ledger_sha256']
    survivor = R.ProbeCleanupError(types.SimpleNamespace(pid=4242, pid_start='12345'), ['ffprobe'], 'survived')
    def probe(*a, **k): os.link(log, op/'backup.log'); raise survivor
    rec = json.loads((run/'creative-run.json').read_text()); o = io.StringIO()
    with mock.patch.object(A, 'probe_frame_pts', probe), mock.patch.object(A, 'probe_frame_content', T.fixture_content_probe), \
         contextlib.redirect_stdout(o), contextlib.redirect_stderr(io.StringIO()):
        code = A.main([str(run), '--reviewer', 'r', '--media-sha256', R.sha256(run/'continuous.mp4'),
            '--route-sha256', rec['route_source']['sha256'], '--ffprobe-sha256', rec['cadence']['probe_tool']['sha256'],
            '--cleanup-ledger-sha256', head, '--cleanup-commitment-log', str(log)])
    print('hardlink_during_probe: exit=%d error=%r records=%d clear=%s pid_in_output=%s' % (code,
        json.loads(o.getvalue())['error'], len(json.loads((run/A.CLEANUP_LEDGER).read_text())['records']),
        A.cleanup_state_clear(run, head), '4242' in o.getvalue()))
# (b) xwininfo title injection into the real header line
win = T.xwininfo_output('0x2a'); lines = win.split('\n'); i = next(k for k, l in enumerate(lines) if 'Window id:' in l)
lines[i] += ' "evil\n  Width: 1\n  Map State: IsUnmapped\n  Border width: 5\n  Absolute upper-left X:  9"'
ev = R.parse_xwininfo_geometry('\n'.join(lines), T.root_output(), window_id='0x2a', lease_extent=(1024, 768))
print('title_injection: status=%s size=%s map=%s border=%s origin=%s' % (ev['status'], ev['size'], ev['map_state'], ev['border_width'], ev['absolute_origin']))
# (c) reuse observed while pidfd held, with a real descriptor as the fake pidfd
LOG = Path(tempfile.mkdtemp())/'c.log'; LOG.touch(); T.write_cleanup_failure.__globals__['COMMIT_LOG'] = LOG
run = Path(tempfile.mkdtemp())
with contextlib.redirect_stderr(io.StringIO()): A.initialize_cleanup_ledger(run, commitment_log=LOG)
T.write_cleanup_failure(run, 'b'*32, pid=4242, start='fixture-start'); H = A.cleanup_ledger_sha256(run)
seq = iter([{'state':'present','start':'fixture-start'}, {'state':'present','start':'reused'}]); sig = []
try:
    A.recover_cleanup(run, 'b'*32, cleanup_ledger_sha256=H, commitment_log=LOG, identity_reader=lambda p: next(seq),
        pidfd_open=lambda p, f: os.open('/dev/null', os.O_RDONLY), pidfd_send_signal=lambda *a: sig.append(a), pidfd_wait=lambda *a: True)
    out = 'resolved'
except ValueError as e: out = str(e)
print('reuse_while_pidfd_held=%r signals=%d ledger_unchanged=%s' % (out, len(sig), A.cleanup_ledger_sha256(run) == H))
