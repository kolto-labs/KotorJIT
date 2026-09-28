import sys, json, types, tempfile, hashlib, io, contextlib, os, threading
W='/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path[:0]=[W+'/scripts/harness', W+'/tools']
import kpharness_gamescope_backend_test as T
from kpharness import creative_accept as A, recording as R, creative_export as E
from pathlib import Path
def out(k,v): print(f'{k}={v}')
def mkrun(tmp):
    run=Path(tmp); media=run/'continuous.mp4'; media.write_bytes(b'frames')
    rc=T.completed_receipt(run); (run/'creative-run.json').write_text(json.dumps(rc))
    (run/A.CLEANUP_LEDGER).exists() or A.initialize_cleanup_ledger(run); return run, media, rc
def kw(rc, media): return dict(reviewer='r', media_sha256=R.sha256(media),
    route_sha256=rc['route_source']['sha256'], ffprobe_sha256=rc['cadence']['probe_tool']['sha256'])

# P1: initial head emitted? constant across runs?
with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
    out('initial_head_same_across_runs', A.initialize_cleanup_ledger(Path(a))==A.initialize_cleanup_ledger(Path(b)))
    out('initial_head', A.cleanup_ledger_sha256(Path(a)))

# P2: rollback attack after accept-time failure; operator hashes file "at review" per docs
with tempfile.TemporaryDirectory() as t:
    run, media, rc = mkrun(t); head0=A.cleanup_ledger_sha256(run); empty=(run/A.CLEANUP_LEDGER).read_bytes()
    child=types.SimpleNamespace(pid=4242, pid_start='fixture-start')
    fail=R.ProbeCleanupError(child, ['ffprobe'], 'survived')
    try:
        A.accept(run, cleanup_ledger_sha256=head0, pts_probe=lambda *a, **k: (_ for _ in ()).throw(fail), **kw(rc,media))
    except ValueError as e:
        msg=str(e); out('failure_error_message', repr(msg))
        ids=list(A._load_cleanup_ledger(run)[2]); head1=A.cleanup_ledger_sha256(run)
        out('message_contains_failure_id', any(i in msg for i in ids)); out('message_contains_new_head', head1 in msg)
    out('retry_with_initial_head_blocked', not A.cleanup_state_clear(run, head0))
    (run/A.CLEANUP_LEDGER).unlink(); (run/A.CLEANUP_LEDGER).write_bytes(empty)
    head_at_review=hashlib.sha256((run/A.CLEANUP_LEDGER).read_bytes()).hexdigest()
    out('rollback_head_equals_initial', head_at_review==head0)
    try:
        acc=A.accept(run, cleanup_ledger_sha256=head_at_review, pts_probe=T.fixture_pts_probe, **kw(rc,media))
        out('rollback_accepted', acc['ok'])
        out('rollback_verifies', A.verify_acceptance(acc, route_sha256=rc['route_source']['sha256'], ffprobe_sha256=rc['cadence']['probe_tool']['sha256'], cleanup_ledger_sha256=head_at_review))
        out('rollback_export_admission', bool(E.accepted_receipt(run, route_sha256=rc['route_source']['sha256'], ffprobe_sha256=rc['cadence']['probe_tool']['sha256'], cleanup_ledger_sha256=head_at_review)))
    except Exception as e: out('rollback_accepted', f'False {e}')

# P3: CLI failure output
with tempfile.TemporaryDirectory() as t:
    run, media, rc = mkrun(t); head0=A.cleanup_ledger_sha256(run)
    orig=A.probe_frame_pts
    A.accept.__defaults__  # default pts_probe bound at def; patch via kwdefaults
    d=A.accept.__kwdefaults__; saved=d['pts_probe']
    d['pts_probe']=lambda *a, **k: (_ for _ in ()).throw(R.ProbeCleanupError(types.SimpleNamespace(pid=4242,pid_start='s'),['ffprobe'],'survived'))
    buf=io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            A.main([str(run),'--reviewer','r','--media-sha256',R.sha256(media),'--route-sha256',rc['route_source']['sha256'],'--ffprobe-sha256',rc['cadence']['probe_tool']['sha256'],'--cleanup-ledger-sha256',head0])
    except BaseException as e: out('cli_failure_exception', type(e).__name__)
    finally: d['pts_probe']=saved
    out('cli_failure_stdout', repr(buf.getvalue()))

# P4: tri-state / unreadable
with tempfile.TemporaryDirectory() as t:
    run=Path(t); A.initialize_cleanup_ledger(run); i='3'*32; T.write_cleanup_failure(run,i)
    h=A.cleanup_ledger_sha256(run)
    for name,reader in [('unreadable',lambda p:{'state':'unreadable','error':'EACCES'}),('bogus',lambda p:{'state':'gone'}),('nondict',lambda p:None)]:
        try: A.recover_cleanup(run,i,cleanup_ledger_sha256=h,identity_reader=reader); out(f'{name}_resolved',True)
        except Exception as e: out(f'{name}_resolved', f'False ({type(e).__name__})')
    out('gate_after_unreadable', A.cleanup_state_clear(run,h))
    # held becomes absent/unreadable
    seq=iter([{'state':'present','start':'fixture-start'},{'state':'unreadable','error':'x'}])
    try: A.recover_cleanup(run,i,cleanup_ledger_sha256=h,identity_reader=lambda p:next(seq),pidfd_open=lambda p,f:os.open('/dev/null',0),pidfd_send_signal=lambda *a:None,pidfd_wait=lambda *a:True); out('held_unreadable_resolved',True)
    except Exception as e: out('held_unreadable_resolved',f'False ({e})')
    # no pidfd
    try: A.recover_cleanup(run,i,cleanup_ledger_sha256=h,identity_reader=lambda p:{'state':'present','start':'fixture-start'},pidfd_open=None); out('no_pidfd_resolved',True)
    except Exception as e: out('no_pidfd_resolved',f'False ({e})')
    # pidfd wait timeout
    try: A.recover_cleanup(run,i,cleanup_ledger_sha256=h,identity_reader=lambda p:{'state':'present','start':'fixture-start'},pidfd_open=lambda p,f:os.open('/dev/null',0),pidfd_send_signal=lambda *a:None,pidfd_wait=lambda *a:False); out('survivor_resolved',True)
    except Exception as e: out('survivor_resolved',f'False ({e})')
    # reuse before pidfd
    try: A.recover_cleanup(run,i,cleanup_ledger_sha256=h,identity_reader=lambda p:{'state':'present','start':'other'}); out('reuse_resolved',True)
    except Exception as e: out('reuse_resolved',f'False ({e})')
    out('gate_still_blocked', not A.cleanup_state_clear(run,h))
    # real reader on a permission-denied path simulation: pid 1 on host
    out('real_reader_pid1', A._process_identity(1).get('state'))
    out('real_reader_absent', A._process_identity(2**22+12345).get('state'))

# P5: exact schema mutations (round-8 R8-2 replays)
with tempfile.TemporaryDirectory() as t:
    run=Path(t); A.initialize_cleanup_ledger(run); i='4'*32; T.write_cleanup_failure(run,i)
    h=A.cleanup_ledger_sha256(run)
    r=A.recover_cleanup(run,i,cleanup_ledger_sha256=h,identity_reader=lambda p:{'state':'absent'})
    base=json.loads((run/A.CLEANUP_LEDGER).read_text())
    def rechain(L):
        prev=A.ZERO_DIGEST
        for rec in L['records']:
            rec['prev_digest']=prev; rec['record_digest']=A._record_digest(rec); prev=rec['record_digest']
        return L
    muts={
      'res_bad_time': lambda L: L['records'][1].__setitem__('timestamp_utc','not-a-timestamp'),
      'res_naive_time': lambda L: L['records'][1].__setitem__('timestamp_utc','2026-09-27T00:00:00'),
      'res_extra': lambda L: L['records'][1]['payload'].__setitem__('x',{}),
      'fail_missing_cmd': lambda L: L['records'][0]['payload'].pop('command'),
      'fail_bad_tool': lambda L: L['records'][0]['payload']['tool'].__setitem__('sha256','zz'),
      'fail_bad_wait': lambda L: L['records'][0]['payload'].__setitem__('bounded_wait_seconds',[1]),
      'res_cross_pid': lambda L: L['records'][1]['payload'].__setitem__('pid',9999),
      'res_cross_start': lambda L: L['records'][1]['payload'].__setitem__('pid_start','other'),
      'res_bad_outcome': lambda L: L['records'][1]['payload'].__setitem__('outcome','ok'),
      'payload_int': lambda L: L['records'][1].__setitem__('payload',5),
      'bool_pid_fail': lambda L: L['records'][0]['payload'].__setitem__('pid',True),
      'drop_failure': lambda L: L.__setitem__('records',[]),
    }
    for n,m in muts.items():
        L=json.loads(json.dumps(base)); m(L); L=rechain(L)
        (run/A.CLEANUP_LEDGER).unlink(); (run/A.CLEANUP_LEDGER).write_text(json.dumps(L))
        for lab,hh in (('selfhead',None),('realhead',r['cleanup_ledger_sha256'])):
            try: out(f'mut_{n}_gate_clear_{lab}', A.cleanup_state_clear(run, hh))
            except Exception as e: out(f'mut_{n}_gate_clear_{lab}', f'EXC {type(e).__name__}: {e}')
    (run/A.CLEANUP_LEDGER).unlink(); (run/A.CLEANUP_LEDGER).write_text(json.dumps(base))
    # repeated recovery returns only validated binding
    out('repeat_returns_same', A.recover_cleanup(run,i,cleanup_ledger_sha256=A.cleanup_ledger_sha256(run))['record']==base['records'][1])

# P6: signal error + reap produces failure+resolution
with tempfile.TemporaryDirectory() as t:
    run, media, rc = mkrun(t); h=A.cleanup_ledger_sha256(run)
    proc=types.SimpleNamespace(pid=4545, pid_start='s45', kill=lambda: (_ for _ in ()).throw(PermissionError('EPERM')), wait=lambda timeout: 0)
    def p(*a, **k): R._bounded_probe_cleanup(proc, ['ffprobe'])
    try: A.accept(run, cleanup_ledger_sha256=h, pts_probe=p, **kw(rc,media))
    except ValueError as e: out('sigerr_msg', str(e))
    L,_,F,Rs=A._load_cleanup_ledger(run); out('sigerr_failures_resolutions', (len(F),len(Rs)))
    out('sigerr_gate_clear_filehead', A.cleanup_state_clear(run, A.cleanup_ledger_sha256(run)))

# P7: empty start identity for a surviving child
with tempfile.TemporaryDirectory() as t:
    run, media, rc = mkrun(t); h=A.cleanup_ledger_sha256(run)
    import kpharness.session as S
    saved=S.pid_start; S.pid_start=lambda pid: ''
    try:
        err=R.ProbeCleanupError(types.SimpleNamespace(pid=4646), ['ffprobe'], 'survived')
        try: A.accept(run, cleanup_ledger_sha256=h, pts_probe=lambda *a, **k: (_ for _ in ()).throw(err), **kw(rc,media))
        except Exception as e: out('empty_start_error', f'{type(e).__name__}: {e}')
    finally: S.pid_start=saved
    out('empty_start_ledger_records', len(json.loads((run/A.CLEANUP_LEDGER).read_text())['records']))
    out('empty_start_gate_clear_initial_head', A.cleanup_state_clear(run, h))

# P8: concurrent append lost update (interleaved loads)
with tempfile.TemporaryDirectory() as t:
    run=Path(t); A.initialize_cleanup_ledger(run)
    real=A._load_cleanup_ledger; barrier=threading.Barrier(2); calls={'n':0}; lock=threading.Lock()
    def slow(rd):
        res=real(rd)
        with lock: calls['n']+=1; first = calls['n']<=2
        if first:
            try: barrier.wait(timeout=2)
            except threading.BrokenBarrierError: pass
        return res
    A._load_cleanup_ledger=slow
    errs=[]
    def w(i):
        try: T.write_cleanup_failure(run, i*32)
        except Exception as e: errs.append(repr(e))
    th=[threading.Thread(target=w,args=(c,)) for c in 'ab']; [x.start() for x in th]; [x.join() for x in th]
    A._load_cleanup_ledger=real
    try: out('concurrent_failures_retained', len(real(run)[2]))
    except Exception as e: out('concurrent_ledger', f'invalid {e}')
    out('concurrent_errors', errs)
