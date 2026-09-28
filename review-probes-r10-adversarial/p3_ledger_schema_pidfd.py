"""R10 adaptation of R9 p2: exact schema, pidfd recovery, reuse, boot/ns binding."""
import io, json, sys, types, hashlib, os, errno, contextlib, tempfile
from pathlib import Path
W='/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W+'/tools'); sys.path.insert(0, W+'/scripts/harness')
import kpharness_gamescope_backend_test as T
from kpharness import creative_accept as A, recording as R, session as S
LOG = Path(tempfile.mkdtemp())/'c.log'; LOG.touch()
Q = contextlib.redirect_stderr(io.StringIO())
def fresh():
    run = Path(tempfile.mkdtemp())
    with contextlib.redirect_stderr(io.StringIO()): A.initialize_cleanup_ledger(run, commitment_log=LOG)
    return run
def load(run):
    try: A._load_cleanup_ledger(run); return 'loads'
    except Exception as e: return type(e).__name__
def canon(o): return (json.dumps(o, sort_keys=True, separators=(',',':'))+'\n').encode()
def put(run, raw): p = run/A.CLEANUP_LEDGER; p.unlink(); p.write_bytes(raw)
res = {}
host = A._host_identity()
fp = {'failure_type':'ffprobe_cleanup_failed','identity':'exact','pid':42,'pid_start':'7','boot_id':host['boot_id'],
      'pid_namespace':host['pid_namespace'],'command':['ffprobe'],
      'tool':{'command':'ffprobe','resolved_path':'/usr/bin/ffprobe','sha256':'1'*64},
      'bounded_wait_seconds':[2,2],'signal_errors':[],'recovery':A.RECOVERY_REQUIREMENT}
TS='2026-09-27T00:00:00.000000+00:00'
def mk(rtype, seq, prev, payload, ident, **over):
    r = {'schema':1,'type':rtype,'sequence':seq,'id':ident,'prev_digest':prev,'timestamp_utc':TS,'payload':payload}; r.update(over)
    r['record_digest'] = A._record_digest(r); return r
def ledger_with(records_fn):
    run = fresh(); L = json.loads((run/A.CLEANUP_LEDGER).read_text())
    g = hashlib.sha256(A._launch_bytes(L['nonce'])).hexdigest()
    L['records'] = records_fn(g); put(run, canon(L)); return run, L
run, _ = ledger_with(lambda g: [mk('failure',1,g,fp,'a'*32)]); res['baseline_valid_failure'] = load(run)
for name, over, pay in [('seq_bool',{'sequence':True},fp),('rec_schema_float',{'schema':1.0},fp),
        ('waits_float',{},{**fp,'bounded_wait_seconds':[2.0,2.0]}),('pid_bool',{},{**fp,'pid':True}),
        ('ts_Z',{'timestamp_utc':'2026-09-27T00:00:00.000000Z'},fp),('ts_no_micro',{'timestamp_utc':'2026-09-27T00:00:00+00:00'},fp),
        ('payload_list',{},[1]),('payload_str',{},'x')]:
    run, _ = ledger_with(lambda g: [mk('failure',1,g,pay,'a'*32,**over)]); res[name] = load(run)
rp = lambda f, **o: {**{'failure_id':f['id'],'failure_digest':f['record_digest'],'pid':42,'pid_start':'7',
    'outcome':'already_exited','pidfd':'not_needed','signal':'not_sent','wait':'confirmed_absent'}, **o}
def pair(g, ts_r=TS, rpay=None):
    f = mk('failure',1,g,fp,'a'*32,timestamp_utc='2026-09-27T05:00:00.000000+00:00')
    return [f, mk('resolution',2,f['record_digest'], rpay if rpay is not None else rp(f),'a'*32,timestamp_utc=ts_r)]
run,_ = ledger_with(lambda g: pair(g)); res['resolution_before_failure_time'] = load(run)
run,_ = ledger_with(lambda g: pair(g, ts_r='2026-09-27T06:00:00.000000+00:00')); res['valid_pair'] = load(run)
run,_ = ledger_with(lambda g: pair(g, ts_r='2026-09-27T06:00:00.000000+00:00', rpay=[])); res['resolution_payload_list'] = load(run)
run = fresh(); raw = (run/A.CLEANUP_LEDGER).read_bytes(); L = json.loads(raw)
put(run, raw.replace(b'{', b'{"schema":2,', 1)); res['dup_key'] = load(run)
put(run, json.dumps(L).encode()+b'\n'); res['noncanonical_ws'] = load(run)
put(run, raw.replace(b'"schema":2', b'"schema":2.0')); res['ledger_schema_float'] = load(run)
put(run, raw.replace(b'"schema":2', b'"schema":true')); res['ledger_schema_bool'] = load(run)
put(run, b'{"records":[],"schema":1}\n'); res['v1_ledger'] = load(run)
put(run, b'[]\n'); res['toplevel_list'] = (load(run), A.cleanup_state_clear(run, hashlib.sha256(b'[]\n').hexdigest()))
# recovery
def rec_run(pid=4242, start='fixture-start'):
    run = fresh(); T.write_cleanup_failure.__globals__['COMMIT_LOG'] = LOG
    T.write_cleanup_failure(run, 'b'*32, pid=pid, start=start); return run, A.cleanup_ledger_sha256(run)
present = lambda pid: {'state':'present','start':'fixture-start'}
def rc(run, H, **k):
    sig = []
    k.setdefault('pidfd_send_signal', lambda *a: sig.append(a)); k.setdefault('pidfd_wait', lambda *a: True)
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            r = A.recover_cleanup(run, 'b'*32, cleanup_ledger_sha256=H, commitment_log=LOG, **k)
        return (r['record']['payload']['outcome'], len(sig))
    except Exception as e: return (f'{type(e).__name__}: {e}'[:70], len(sig))
run,H = rec_run(); opened=[]
res['reuse_resolves_no_signal'] = rc(run,H,identity_reader=lambda p:{'state':'present','start':'other'},pidfd_open=lambda p,f: opened.append(p) or 90) + (len(opened),)
run,H = rec_run(); res['other_boot'] = rc(run,H,identity_reader=present,host_reader=lambda:{'boot_id':'x','pid_namespace':host['pid_namespace']})
run,H = rec_run(); res['other_ns'] = rc(run,H,identity_reader=present,host_reader=lambda:{'boot_id':host['boot_id'],'pid_namespace':'pid:[1]'})
run,H = rec_run(); res['host_reader_nondict'] = rc(run,H,identity_reader=present,host_reader=lambda:None)
for label, e in [('ENOSYS',OSError(errno.ENOSYS,'nosys')),('EPERM',PermissionError(errno.EPERM,'perm'))]:
    run,H = rec_run()
    def op(p,f,e=e): raise e
    res['pidfd_open_'+label] = rc(run,H,identity_reader=present,pidfd_open=op) + (A.cleanup_ledger_sha256(run)==H,)
run,H = rec_run(); seq = iter([present(0), {'state':'present','start':'reused'}])
res['reuse_while_pidfd_held'] = rc(run,H,identity_reader=lambda p: next(seq), pidfd_open=lambda p,f: 90)
# unavailable identity: surviving child with empty start
run = fresh(); H0 = A.cleanup_ledger_sha256(run)
err = R.ProbeCleanupError(types.SimpleNamespace(pid=4243, pid_start=''), ['ffprobe'], 'survived')
with contextlib.redirect_stderr(io.StringIO()):
    f, H1 = A._persist_probe_cleanup_failure(run, err, fp['tool'], expected_head=H0, commitment_log=LOG)
res['unavailable_identity'] = (f['payload']['identity'], A.cleanup_state_clear(run, H1))
try:
    with contextlib.redirect_stderr(io.StringIO()):
        A.recover_cleanup(run, f['id'], cleanup_ledger_sha256=H1, commitment_log=LOG, identity_reader=lambda p:{'state':'absent'})
    res['unavailable_recover'] = 'resolved'
except ValueError as e: res['unavailable_recover'] = 'refused'
# R8-3 / R7-2 regressions
class P:
    def __init__(s): s.pid = os.getpid(); s.stdout=None; s.waits=[]
    def poll(s): return None
    def kill(s): raise PermissionError('eperm')
    def wait(s, timeout=None): s.waits.append(timeout); return 0
p = P()
try: R.probe_frame_pts(Path('/x'),'ffprobe',popen=lambda *a,**k: p)
except R.ProbeCleanupError as e: res['r8_3'] = (bool(e.pid_start), e.reaped, p.waits)
for k, v in res.items(): print(f'{k}={v}')
