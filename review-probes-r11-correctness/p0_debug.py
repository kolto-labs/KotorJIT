exec(open('probe_r10.py').read().split('# P1 launch')[0])
log = OPS / 'c.log'; log.touch()
with tempfile.TemporaryDirectory() as t:
    run, rc, launch = new_run(t, log)
    code, so, se = cli_accept(run, rc, launch[0]['cleanup_ledger_sha256'], log, T.fixture_pts_probe)
    print('exit', code); print('stdout', so[:1500]); print('stderr', se[:800])
