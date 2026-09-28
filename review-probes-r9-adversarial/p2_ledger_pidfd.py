import json, sys, types, hashlib, os, subprocess, signal, errno, copy
from pathlib import Path
import tempfile
W='/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W+'/tools'); sys.path.insert(0, W+'/scripts/harness')
import kpharness_gamescope_backend_test as T
from kpharness import creative_accept as A, recording as R, session as S
def load(run):
    try: A._load_cleanup_ledger(run); return 'loads'
    except Exception as e: return type(e).__name__
def rewrite(run, obj, raw=None):
    p = run/A.CLEANUP_LEDGER; p.unlink(); p.write_bytes(raw if raw is not None else (json.dumps(obj)+'\n').encode())
def fresh():
    t = tempfile.mkdtemp(); run = Path(t); A.initialize_cleanup_ledger(run); return run
res = {}
# R8-1 counterexamples at code level with external head retained
run = fresh(); f = T.write_cleanup_failure(run, 'a'*32); H = A.cleanup_ledger_sha256(run)
res['r8_legit_failure_clear'] = A.cleanup_state_clear(run, H)
rewrite(run, None, b'{"records":[],"schema":1}\n'); res['r8_deleted_clear_with_retained_head'] = A.cleanup_state_clear(run, H)
# hard link
run = fresh(); os.link(run/A.CLEANUP_LEDGER, run/'x'); res['hardlink'] = load(run)
# duplicate keys / non-canonical whitespace
run = fresh(); rewrite(run, None, b'{"schema":1,"records":[],"schema":1}\n'); res['dup_keys'] = load(run)
run = fresh(); rewrite(run, None, b'{ "records" : [ ] , "schema" : 1 }'); res['noncanonical_ws'] = load(run)
run = fresh(); rewrite(run, None, b'{"records":[],"schema":true}'); res['schema_bool'] = load(run)
run = fresh(); rewrite(run, None, b'{"records":[],"schema":1.0}'); res['schema_float'] = load(run)
# record-level type confusion: rebuild record with sequence True / schema 1.0 / waits [2.0,2.0]
def build(records):
    return {'schema': 1, 'records': records}
def mk(rtype, seq, prev, payload, ident, **over):
    r = {'schema': 1, 'type': rtype, 'sequence': seq, 'id': ident, 'prev_digest': prev,
         'timestamp_utc': '2026-09-27T00:00:00+00:00', 'payload': payload}; r.update(over)
    r['record_digest'] = A._record_digest(r); return r
fp = {'failure_type': 'ffprobe_cleanup_failed', 'pid': 42, 'pid_start': '7', 'command': ['ffprobe'],
      'tool': {'command': 'ffprobe', 'resolved_path': '/usr/bin/ffprobe', 'sha256': '1'*64},
      'bounded_wait_seconds': [2, 2], 'signal_errors': [], 'recovery': A.RECOVERY_REQUIREMENT}
for name, over, pay in [('seq_bool', {'sequence': True}, fp), ('rec_schema_float', {'schema': 1.0}, fp),
        ('waits_float', {}, {**fp, 'bounded_wait_seconds': [2.0, 2.0]}),
        ('ts_offset_+01', {'timestamp_utc': '2026-09-27T01:00:00+01:00'}, fp),
        ('ts_Z', {'timestamp_utc': '2026-09-27T00:00:00Z'}, fp),
        ('ts_naive', {'timestamp_utc': '2026-09-27T00:00:00'}, fp),
        ('seq_gap', {'sequence': 2}, fp), ('pid_bool', {}, {**fp, 'pid': True})]:
    run = fresh(); rewrite(run, build([mk('failure', 1, A.ZERO_DIGEST, pay, 'a'*32, **over)])); res[name] = load(run)
# resolution before failure; two resolutions
rp = lambda f: {'failure_id': f['id'], 'failure_digest': f['record_digest'], 'pid': 42, 'pid_start': '7',
    'outcome': 'already_exited', 'pidfd': 'not_needed', 'signal': 'not_sent', 'wait': 'confirmed_absent'}
f1 = mk('failure', 1, A.ZERO_DIGEST, fp, 'a'*32)
r1 = mk('resolution', 2, f1['record_digest'], rp(f1), 'a'*32)
r2 = mk('resolution', 3, r1['record_digest'], rp(f1), 'a'*32)
run = fresh(); rewrite(run, build([f1, r1, r2])); res['two_resolutions'] = load(run)
rb = mk('resolution', 1, A.ZERO_DIGEST, rp(f1), 'a'*32)
run = fresh(); rewrite(run, build([rb])); res['resolution_before_failure'] = load(run)
# resolution timestamp earlier than failure (time order)
f1b = mk('failure', 1, A.ZERO_DIGEST, fp, 'a'*32, timestamp_utc='2026-09-27T05:00:00+00:00')
r1b = mk('resolution', 2, f1b['record_digest'], rp(f1b), 'a'*32, timestamp_utc='2020-01-01T00:00:00+00:00')
run = fresh(); rewrite(run, build([f1b, r1b])); res['resolution_timestamp_before_failure'] = load(run)
# pidfd paths
def rec_run():
    run = fresh(); T.write_cleanup_failure(run, 'b'*32, pid=4242, start='fixture-start'); return run
present = lambda pid: {'state': 'present', 'start': 'fixture-start'}
for label, opener in [('ENOSYS', OSError(errno.ENOSYS, 'nosys')), ('EPERM', PermissionError(errno.EPERM, 'perm'))]:
    run = rec_run(); H = A.cleanup_ledger_sha256(run)
    def op(pid, flags, e=opener): raise e
    try: A.recover_cleanup(run, 'b'*32, cleanup_ledger_sha256=H, identity_reader=present, pidfd_open=op,
                           pidfd_send_signal=lambda *a: None, pidfd_wait=lambda *a: True); out = 'resolved'
    except Exception as e: out = type(e).__name__
    res['pidfd_open_'+label] = (out, A.cleanup_ledger_sha256(run) == H)
# reuse between check and pidfd_open
run = rec_run(); H = A.cleanup_ledger_sha256(run); seq = iter([present(0), {'state': 'present', 'start': 'reused'}]); sig = []
try: A.recover_cleanup(run, 'b'*32, cleanup_ledger_sha256=H, identity_reader=lambda p: next(seq), pidfd_open=lambda p, f: 90,
        pidfd_send_signal=lambda *a: sig.append(a), pidfd_wait=lambda *a: True); out='resolved'
except Exception as e: out = f'{type(e).__name__}: {e}'
res['reuse_before_pidfd'] = (out, len(sig))
# fd leak on every exception path
closed = []; real_close = os.close
for label, kw in [('wait_raises', dict(pidfd_wait=lambda *a: (_ for _ in ()).throw(OSError('poll')))),
                  ('signal_raises_then_survive', dict(pidfd_send_signal=lambda *a: (_ for _ in ()).throw(PermissionError()), pidfd_wait=lambda *a: False)),
                  ('reader_raises', dict(identity_reader=None))]:
    run = rec_run(); H = A.cleanup_ledger_sha256(run); closed.clear()
    calls = iter([present(0)])
    reader = present if kw.get('identity_reader', 1) is not None else (lambda p: next(calls))
    k = dict(identity_reader=reader, pidfd_open=lambda p, f: 91, pidfd_send_signal=lambda *a: None, pidfd_wait=lambda *a: True)
    k.update({a: b for a, b in kw.items() if a != 'identity_reader'})
    A.os.close = lambda fd: (closed.append(fd), real_close(fd) if fd != 91 else None)
    try: A.recover_cleanup(run, 'b'*32, cleanup_ledger_sha256=H, **k); out='resolved'
    except BaseException as e: out = type(e).__name__
    A.os.close = real_close
    res['fdclose_'+label] = (out, 91 in closed)
# PID reuse after real exit: present with different start (original provably gone) -> stuck?
run = rec_run(); H = A.cleanup_ledger_sha256(run)
try: A.recover_cleanup(run, 'b'*32, cleanup_ledger_sha256=H, identity_reader=lambda p: {'state':'present','start':'other'}); out='resolved'
except Exception as e: out = f'{type(e).__name__}: {e}'
res['reused_pid_long_lived'] = out
# repeated recovery with mismatched resolution? (loader binds) ; repeated recovery with stale head
run = rec_run(); H = A.cleanup_ledger_sha256(run)
r = A.recover_cleanup(run, 'b'*32, cleanup_ledger_sha256=H, identity_reader=lambda p: {'state': 'absent'})
try: A.recover_cleanup(run, 'b'*32, cleanup_ledger_sha256=H); out='returned'
except Exception as e: out = type(e).__name__
res['repeat_with_stale_head'] = out
res['repeat_with_new_head'] = A.recover_cleanup(run, 'b'*32, cleanup_ledger_sha256=r['cleanup_ledger_sha256'])['record'] == r['record']
# /proc stat parser with ')' and spaces in comm, real zombie-free self check
import types as _t
raw = b'123 (a) b (c)) R ' + b' '.join(str(i).encode() for i in range(4, 60))
orig_open, orig_read = os.open, os.read
A.os.open = lambda *a, **k: 77; A.os.read = lambda fd, n: raw; A.os.close = lambda fd: None
res['stat_paren_comm'] = A._process_identity(123)
A.os.open, A.os.read, A.os.close = orig_open, orig_read, real_close
res['self_identity_matches_session'] = A._process_identity(os.getpid()).get('start') == S.pid_start(os.getpid())
# R8-3: real-Popen-shaped child, signal error then successful reap
class P:
    def __init__(s): s.pid = os.getpid(); s.stdout = None; s.waits = []
    def poll(s): return None
    def kill(s): raise PermissionError('eperm')
    def wait(s, timeout=None): s.waits.append(timeout); return 0
p = P()
try: R.probe_frame_pts(Path('/x'), 'ffprobe', popen=lambda *a, **k: p)
except R.ProbeCleanupError as e: res['r8_3_reaped_pid_start_nonempty'] = (bool(e.pid_start), e.reaped, p.waits)
# R7-2 exit race: kill raises ProcessLookupError
class Q(P):
    def kill(s): raise ProcessLookupError()
q = Q()
try: R.probe_frame_pts(Path('/x'), 'ffprobe', popen=lambda *a, **k: q); res['r7_2'] = 'no-raise?'
except Exception as e: res['r7_2_exit_race'] = (type(e).__name__, q.waits)
for k, v in res.items(): print(f'{k}={v}')
