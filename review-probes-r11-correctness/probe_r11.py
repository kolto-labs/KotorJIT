"""Round-10 correctness probes. Heads come ONLY from captured CLI stdout/stderr or the commitment log."""
import sys, json, types, tempfile, hashlib, io, contextlib, os, threading
from pathlib import Path
from unittest import mock
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path[:0] = [W + '/scripts/harness', W + '/tools']
import kpharness_gamescope_backend_test as T
from kpharness import creative_accept as A, recording as R, creative_export as E

_fp, _fc = T.fixture_pts_probe, T.fixture_content_probe
# R11 adaptation: the CLI's default probes now pass deadline_seconds (recording.probe_deadline_seconds).
T.fixture_pts_probe = lambda path, exe, *, pass_fds=(), deadline_seconds=None: _fp(path, exe, pass_fds=pass_fds)
T.fixture_content_probe = lambda path, exe, *, pass_fds=(), deadline_seconds=None: _fc(path, exe, pass_fds=pass_fds)
def out(k, v): print(f'{k}={v}')
OPS = Path(tempfile.mkdtemp(prefix='r11c-operator-'))

def heads(text):
    res = []
    for line in text.splitlines():
        try: v = json.loads(line)
        except ValueError: continue
        if isinstance(v, dict) and v.get('kind') == A.LEDGER_HEAD_KIND: res.append(v)
    return res

def new_run(tmp, log):
    run = Path(tmp); (run / 'continuous.mp4').write_bytes(b'frames')
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        A.initialize_cleanup_ledger(run, commitment_log=log)
    launch = heads(err.getvalue())
    # completed_receipt skips init because the ledger exists (it must not re-init)
    rc = T.completed_receipt(run); (run / 'creative-run.json').write_text(json.dumps(rc))
    return run, rc, launch

def cli_accept(run, rc, head, log, probe):
    argv = [str(run), '--reviewer', 'r', '--media-sha256', R.sha256(run / 'continuous.mp4'),
            '--route-sha256', rc['route_source']['sha256'], '--ffprobe-sha256', rc['cadence']['probe_tool']['sha256'],
            '--cleanup-ledger-sha256', head, '--cleanup-commitment-log', str(log)]
    so, se = io.StringIO(), io.StringIO()
    with mock.patch.object(A, 'probe_frame_pts', probe), mock.patch.object(A, 'probe_frame_content', T.fixture_content_probe), \
            contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
        code = A.main(argv)
    return code, so.getvalue(), se.getvalue()

def survivor_probe(pid=4242, start='fixture-start'):
    err = R.ProbeCleanupError(types.SimpleNamespace(pid=pid, pid_start=start), ['ffprobe'], 'survived')
    def p(*a, **k): raise err
    return p

def log_heads(log, run): return [h for h in heads(Path(log).read_text()) if h['run_dir'] == str(Path(run).resolve())]

# P1 launch heads unique and emitted before use
log = OPS / 'c.log'; log.touch()
with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
    _, _, la = new_run(a, log); _, _, lb = new_run(b, log)
    out('P1_launch_lines', (len(la), len(lb)))
    out('P1_launch_heads_differ', la[0]['cleanup_ledger_sha256'] != lb[0]['cleanup_ledger_sha256'])
    out('P1_launch_logged', log_heads(log, a)[0] == la[0])

# P0 positive control: honest flow with the logged head accepts, verifies, export-admits
with tempfile.TemporaryDirectory() as t:
    run, rc, launch = new_run(t, log)
    code, so, _ = cli_accept(run, rc, launch[0]['cleanup_ledger_sha256'], log, T.fixture_pts_probe)
    out('P0_honest_accept_exit', code)
    acc = json.loads((run / 'creative-run.json').read_text())
    h = launch[0]['cleanup_ledger_sha256']
    out('P0_honest_verifies', A.verify_acceptance(acc, route_sha256=rc['route_source']['sha256'],
        ffprobe_sha256=rc['cadence']['probe_tool']['sha256'], cleanup_ledger_sha256=h))

# P2 R9-1 rollback family, head only from CLI stdout / log
def attack(name, mutate):
    with tempfile.TemporaryDirectory() as t:
        run, rc, launch = new_run(t, log)
        code, so, se = cli_accept(run, rc, launch[0]['cleanup_ledger_sha256'], log, survivor_probe())
        res = json.loads(so.strip().splitlines()[-1])
        stdout_head = res.get('cleanup_ledger_sha256'); fid = res.get('failure_id')
        stderr_heads = heads(se)
        if name == 'baseline':
            out('P2_fail_exit', code); out('P2_fail_stdout_has_id_and_head', bool(fid) and bool(stdout_head))
            out('P2_stderr_event', [h['event'] for h in stderr_heads])
            out('P2_stdout_head_eq_stderr_eq_log', stdout_head == stderr_heads[-1]['cleanup_ledger_sha256'] == log_heads(log, run)[-1]['cleanup_ledger_sha256'])
            out('P2_stdout_id_eq_log', fid == log_heads(log, run)[-1]['failure_id'])
        mutate(run, launch)
        code2, so2, _ = cli_accept(run, rc, stdout_head, log, T.fixture_pts_probe)
        pending = json.loads((run / 'creative-run.json').read_text())['visual_review']['status']
        out(f'P2_{name}_accept_with_tool_head', f'exit={code2} ok={json.loads(so2.strip().splitlines()[-1])["ok"]} receipt={pending}')
        out(f'P2_{name}_gate_clear_tool_head', A.cleanup_state_clear(run, stdout_head))
        code3, so3, _ = cli_accept(run, rc, launch[0]['cleanup_ledger_sha256'], log, T.fixture_pts_probe)
        out(f'P2_{name}_accept_with_STALE_launch_head', f'exit={code3}')

def reset_launch(run, launch):
    p = run / A.CLEANUP_LEDGER; L = json.loads(p.read_text()); L['records'] = []
    p.write_bytes(A._canonical_bytes(L))
def fresh(run, launch):
    (run / A.CLEANUP_LEDGER).unlink(); alog = OPS / 'attacker.log'; alog.touch()
    with contextlib.redirect_stderr(io.StringIO()): A.initialize_cleanup_ledger(run, commitment_log=alog)
def delete(run, launch): (run / A.CLEANUP_LEDGER).unlink()
def forged_pair(run, launch):
    p = run / A.CLEANUP_LEDGER; L = json.loads(p.read_text()); f = L['records'][0]
    r = {'schema': 1, 'type': 'resolution', 'sequence': 2, 'id': f['id'], 'prev_digest': f['record_digest'],
         'timestamp_utc': f['timestamp_utc'], 'payload': {'failure_id': f['id'], 'failure_digest': f['record_digest'],
         'pid': f['payload']['pid'], 'pid_start': f['payload']['pid_start'], 'outcome': 'already_exited',
         'pidfd': 'not_needed', 'signal': 'not_sent', 'wait': 'confirmed_absent'}}
    r['record_digest'] = A._record_digest(r); L['records'].append(r); p.write_bytes(A._canonical_bytes(L))
def drop_rechain(run, launch):
    p = run / A.CLEANUP_LEDGER; L = json.loads(p.read_text()); L['records'] = []
    L['nonce'] = 'f' * 32; p.write_bytes(A._canonical_bytes(L))
for n, m in [('baseline', lambda r, l: None), ('reset_to_launch', reset_launch), ('fresh_nonce', fresh),
             ('delete', delete), ('forged_pair', forged_pair), ('drop_new_nonce', drop_rechain)]:
    attack(n, m)

# P2b attacker appends a forged head line to the commitment log (operational boundary)
with tempfile.TemporaryDirectory() as t:
    run, rc, launch = new_run(t, log)
    code, so, _ = cli_accept(run, rc, launch[0]['cleanup_ledger_sha256'], log, survivor_probe())
    true_head = json.loads(so.strip().splitlines()[-1])['cleanup_ledger_sha256']
    reset_launch(run, launch)
    forged_line = dict(log_heads(log, run)[-1], cleanup_ledger_sha256=launch[0]['cleanup_ledger_sha256'], event='recovery_resolution')
    with open(log, 'a') as s: s.write(json.dumps(forged_line, sort_keys=True, separators=(',', ':')) + '\n')
    out('P2b_log_last_head_is_forged', log_heads(log, run)[-1]['cleanup_ledger_sha256'] == launch[0]['cleanup_ledger_sha256'])
    out('P2b_stdout_head_still_refuses', not A.cleanup_state_clear(run, true_head))

# P3 recovery: tri-state, pid reuse, pidfd-held mismatch, boot/ns binding
with tempfile.TemporaryDirectory() as t:
    run, rc, launch = new_run(t, log)
    code, so, _ = cli_accept(run, rc, launch[0]['cleanup_ledger_sha256'], log, survivor_probe())
    res = json.loads(so.strip().splitlines()[-1]); h = res['cleanup_ledger_sha256']; fid = res['failure_id']
    def tryrec(label, **kw):
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                r = A.recover_cleanup(run, fid, cleanup_ledger_sha256=h, commitment_log=log, **kw)
            out(label, f"RESOLVED {r['record']['payload']['outcome']}"); return r
        except Exception as e: out(label, f'refused ({type(e).__name__}: {e})')
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError('must not be called'))
    tryrec('P3_unreadable', identity_reader=lambda p: {'state': 'unreadable', 'error': 'EACCES'})
    tryrec('P3_other_boot', identity_reader=boom, host_reader=lambda: {'boot_id': 'x', 'pid_namespace': A._host_identity()['pid_namespace']})
    tryrec('P3_other_ns', identity_reader=boom, host_reader=lambda: {'boot_id': A._host_identity()['boot_id'], 'pid_namespace': 'pid:[1]'})
    tryrec('P3_held_start_changes', identity_reader=(lambda it: (lambda p: next(it)))(iter([{'state': 'present', 'start': 'fixture-start'}, {'state': 'present', 'start': 'x'}])),
           pidfd_open=lambda p, f: os.open('/dev/null', 0), pidfd_send_signal=boom, pidfd_wait=boom)
    tryrec('P3_survivor', identity_reader=lambda p: {'state': 'present', 'start': 'fixture-start'},
           pidfd_open=lambda p, f: os.open('/dev/null', 0), pidfd_send_signal=lambda *a: None, pidfd_wait=lambda *a: False)
    out('P3_gate_blocked_after_refusals', not A.cleanup_state_clear(run, h))
    r = tryrec('P3_pid_reuse', identity_reader=lambda p: {'state': 'present', 'start': 'other'}, pidfd_open=boom, pidfd_send_signal=boom)
    out('P3_reuse_shape', (r['record']['payload']['pidfd'], r['record']['payload']['signal'], r['record']['payload']['wait']))
    out('P3_reuse_head_logged', log_heads(log, run)[-1]['cleanup_ledger_sha256'] == r['cleanup_ledger_sha256'])
    out('P3_gate_clear_with_new_head', A.cleanup_state_clear(run, r['cleanup_ledger_sha256']))
    out('P3_real_reader_pid1', A._process_identity(1).get('state'))
    out('P3_same_start_parser', A._process_identity(os.getpid()).get('start') == __import__('kpharness.session', fromlist=['x']).pid_start(os.getpid()))

# P4 exact-schema mutations, each rechained with its own self-computed head
with tempfile.TemporaryDirectory() as t:
    run, rc, launch = new_run(t, log)
    code, so, _ = cli_accept(run, rc, launch[0]['cleanup_ledger_sha256'], log, survivor_probe())
    res = json.loads(so.strip().splitlines()[-1])
    with contextlib.redirect_stderr(io.StringIO()):
        good = A.recover_cleanup(run, res['failure_id'], cleanup_ledger_sha256=res['cleanup_ledger_sha256'], commitment_log=log, identity_reader=lambda p: {'state': 'absent'})
    base = json.loads((run / A.CLEANUP_LEDGER).read_text())
    def rechain(L):
        prev = hashlib.sha256(A._launch_bytes(L['nonce'])).hexdigest() if isinstance(L.get('nonce'), str) else A.ZERO_DIGEST if hasattr(A, 'ZERO_DIGEST') else '0' * 64
        for rec in L['records']:
            if isinstance(rec, dict):
                rec['prev_digest'] = prev; rec['record_digest'] = A._record_digest(rec); prev = rec['record_digest']
        return L
    enc = lambda L: A._canonical_bytes(L)
    muts = {
        'bool_sequence': lambda L: L['records'][0].__setitem__('sequence', True),
        'float_schema': lambda L: L['records'][0].__setitem__('schema', 1.0),
        'bool_ledger_schema': lambda L: L.__setitem__('schema', True) or None,
        'float_wait': lambda L: L['records'][0]['payload'].__setitem__('bounded_wait_seconds', [2.0, 2]),
        'bool_pid': lambda L: L['records'][0]['payload'].__setitem__('pid', True),
        'res_bool_pid': lambda L: L['records'][1]['payload'].__setitem__('pid', True),
        'payload_int': lambda L: L['records'][1].__setitem__('payload', 5),
        'payload_list': lambda L: L['records'][0].__setitem__('payload', []),
        'z_timestamp': lambda L: L['records'][1].__setitem__('timestamp_utc', L['records'][1]['timestamp_utc'].replace('+00:00', 'Z')),
        'no_micro_ts': lambda L: L['records'][1].__setitem__('timestamp_utc', L['records'][1]['timestamp_utc'][:19] + '+00:00'),
        'res_before_failure': lambda L: L['records'][1].__setitem__('timestamp_utc', '2000-01-01T00:00:00.000000+00:00'),
        'offset_ts': lambda L: L['records'][1].__setitem__('timestamp_utc', L['records'][1]['timestamp_utc'].replace('+00:00', '+01:00')),
        'unhashable_failure_id': lambda L: L['records'][1]['payload'].__setitem__('failure_id', ['x']),
        'empty_boot_resolved': lambda L: L['records'][0]['payload'].__setitem__('boot_id', 5),
        'unavailable_resolved': lambda L: (L['records'][0]['payload'].update(identity='unavailable', pid_start='', recovery=A.UNRECOVERABLE_REQUIREMENT), L['records'][1]['payload'].__setitem__('pid_start', '')),
    }
    for n, m in muts.items():
        L = json.loads(json.dumps(base)); m(L); L = rechain(L)
        (run / A.CLEANUP_LEDGER).write_bytes(enc(L)); hh = hashlib.sha256(enc(L)).hexdigest()
        try: v = A.cleanup_state_clear(run, hh)
        except Exception as e: v = f'EXC {type(e).__name__}'
        out(f'P4_{n}_gate_clear_selfhead', v)
    raw = enc(base)
    for n, blob in [('dup_key', raw.replace(b'{"nonce"', b'{"nonce":"' + b'0' * 32 + b'","nonce"', 1)),
                    ('noncanonical_space', raw.replace(b'","', b'", "', 1)),
                    ('no_trailing_newline', raw[:-1]),
                    ('nan', raw.replace(b'"sequence":1', b'"sequence":NaN', 1))]:
        (run / A.CLEANUP_LEDGER).write_bytes(blob)
        try: v = A.cleanup_state_clear(run, hashlib.sha256(blob).hexdigest())
        except Exception as e: v = f'EXC {type(e).__name__}'
        out(f'P4_{n}_gate_clear_selfhead', v)
    (run / A.CLEANUP_LEDGER).write_bytes(raw)
    out('P4_base_restored_clear_with_good_head', A.cleanup_state_clear(run, good['cleanup_ledger_sha256']))

# P5 signal error + reap -> failure + bound resolution, two head lines
with tempfile.TemporaryDirectory() as t:
    run, rc, launch = new_run(t, log)
    proc = types.SimpleNamespace(pid=4545, pid_start='s45', kill=lambda: (_ for _ in ()).throw(PermissionError('EPERM')), wait=lambda timeout: 0)
    def p(*a, **k): R._bounded_probe_cleanup(proc, ['ffprobe'])
    code, so, se = cli_accept(run, rc, launch[0]['cleanup_ledger_sha256'], log, p)
    out('P5_events', [h['event'] for h in heads(se)])
    res = json.loads(so.strip().splitlines()[-1])
    out('P5_stdout_head_is_final', res.get('cleanup_ledger_sha256') == heads(se)[-1]['cleanup_ledger_sha256'])
    out('P5_gate_clear_final_head', A.cleanup_state_clear(run, res.get('cleanup_ledger_sha256')))

# P6 empty start identity survivor (R9-4)
for reaped in (False, True):
    with tempfile.TemporaryDirectory() as t:
        run, rc, launch = new_run(t, log)
        import kpharness.session as S
        with mock.patch.object(S, 'pid_start', lambda pid: ''):
            err = R.ProbeCleanupError(types.SimpleNamespace(pid=4646), ['ffprobe'], 'survived')
        err.reaped = reaped
        def p(*a, **k): raise err
        code, so, se = cli_accept(run, rc, launch[0]['cleanup_ledger_sha256'], log, p)
        res = json.loads(so.strip().splitlines()[-1]); h = res.get('cleanup_ledger_sha256')
        L = json.loads((run / A.CLEANUP_LEDGER).read_text())
        out(f'P6_reaped{reaped}_records', [(r['type'], r['payload'].get('identity')) for r in L['records']])
        out(f'P6_reaped{reaped}_gate_clear_tool_head', A.cleanup_state_clear(run, h))
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                A.recover_cleanup(run, res['failure_id'], cleanup_ledger_sha256=h, commitment_log=log, identity_reader=lambda p: {'state': 'absent'})
            out(f'P6_reaped{reaped}_recover', 'RESOLVED')
        except Exception as e: out(f'P6_reaped{reaped}_recover', f'refused ({e})')

# P7 concurrent appends with the same supplied head
with tempfile.TemporaryDirectory() as t:
    run, rc, launch = new_run(t, log); h0 = launch[0]['cleanup_ledger_sha256']
    barrier = threading.Barrier(2); results = []
    real = A._load_cleanup_ledger
    def w(i):
        payload = {'failure_type': 'ffprobe_cleanup_failed', 'identity': 'exact', 'pid': 100 + i, 'pid_start': 's',
                   **A._host_identity(), 'command': ['ffprobe'], 'tool': {'command': 'f', 'resolved_path': '/f', 'sha256': '1' * 64},
                   'bounded_wait_seconds': [2, 2], 'signal_errors': [], 'recovery': A.RECOVERY_REQUIREMENT}
        barrier.wait()
        try:
            A._append_cleanup_record(run, 'failure', payload, expected_head=h0, commitment_log=log, event='acceptance_failure'); results.append('ok')
        except Exception as e: results.append(f'refused {e}')
    with contextlib.redirect_stderr(io.StringIO()):
        th = [threading.Thread(target=w, args=(i,)) for i in range(2)]; [x.start() for x in th]; [x.join() for x in th]
    out('P7_results', sorted(results)); out('P7_failures_retained', len(real(run)[2]))

# P8 commitment log disappears during the probe: is the surviving child recorded?
with tempfile.TemporaryDirectory() as t:
    vlog = OPS / 'vanish.log'; vlog.touch()
    run, rc, launch = new_run(t, vlog); h0 = launch[0]['cleanup_ledger_sha256']
    err = R.ProbeCleanupError(types.SimpleNamespace(pid=4747, pid_start='s47'), ['ffprobe'], 'survived')
    def p(*a, **k):
        vlog.unlink(); raise err
    code, so, se = cli_accept(run, rc, h0, vlog, p)
    out('P8_exit_stdout', (code, so.strip()[-160:]))
    out('P8_stderr_heads', len(heads(se)))
    out('P8_ledger_records', len(json.loads((run / A.CLEANUP_LEDGER).read_text())['records']))
    out('P8_gate_clear_with_launch_head', A.cleanup_state_clear(run, h0))
    vlog.touch()
    code2, so2, _ = cli_accept(run, rc, h0, vlog, T.fixture_pts_probe)
    out('P8_next_accept_with_launch_head_exit', code2)
    # log hard-linked (e.g. backup with cp -l) during the probe
    blog = OPS / 'hl.log'; blog.touch()
with tempfile.TemporaryDirectory() as t:
    run, rc, launch = new_run(t, blog); h0 = launch[0]['cleanup_ledger_sha256']
    def p2(*a, **k):
        os.link(blog, OPS / 'hl-backup.log'); raise R.ProbeCleanupError(types.SimpleNamespace(pid=4848, pid_start='s48'), ['ffprobe'], 'survived')
    code, so, se = cli_accept(run, rc, h0, blog, p2)
    out('P8b_hardlinked_log_records', len(json.loads((run / A.CLEANUP_LEDGER).read_text())['records']))
    out('P8b_gate_clear_with_launch_head', A.cleanup_state_clear(run, h0))
