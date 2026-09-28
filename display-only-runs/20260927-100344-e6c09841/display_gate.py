import sys, os, json, hashlib, subprocess, fcntl, shutil, traceback, time, stat
from pathlib import Path
from datetime import datetime, timezone

RUN = Path(__file__).resolve().parent
C = json.loads((RUN / 'config.json').read_text())
SNAP = Path(C['snapshot'])
SOURCE = Path(C['source'])

def write(name, value):
    (RUN / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def inventory():
    result = []
    for path in Path('/proc').iterdir():
        if not path.name.isdecimal():
            continue
        try:
            stat = (path / 'stat').read_text().rsplit(')', 1)[1].split()
            comm = (path / 'comm').read_text().strip()
            argv = (path / 'cmdline').read_bytes().decode(errors='replace').rstrip('\0').split('\0')
            row = dict(pid=int(path.name), comm=comm, state=stat[0], ppid=int(stat[1]), pgid=int(stat[2]), sid=int(stat[3]), start=stat[19])
            if comm.lower() in {'gamescope', 'gamescopereaper', 'xwayland', 'swkotor.exe', 'swkotor2.exe', 'wine', 'wine64', 'wineserver', 'ffmpeg'}:
                # Never copy host authority paths or arbitrary environment data.
                for i, arg in enumerate(argv[:-1]):
                    if arg == '-auth':
                        argv[i + 1] = '<authority-path-redacted>'
                row['argv'] = argv
            result.append(row)
        except FileNotFoundError:
            continue
    return result

def selected(rows):
    return [r for r in rows if 'argv' in r]

def blocked(rows):
    return [r for r in selected(rows) if r['comm'].lower() != 'xwayland']

def error_value(error):
    return dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())

def protected_sockets():
    rows = Path('/proc/net/unix').read_text().splitlines()
    result = {}
    for name in ('X0', 'X1', 'X94', 'X100'):
        path = Path('/tmp/.X11-unix') / name
        try:
            value = path.lstat()
            identity = {field: getattr(value, 'st_' + field) for field in ('dev','ino','mode','uid','gid','size','mtime_ns','ctime_ns')}
        except FileNotFoundError:
            identity = None
        result[name] = dict(identity=identity, socket_rows=sorted(line for line in rows if line.split()[-1] in {str(path), '@'+str(path)}))
    path = Path('/tmp/.X1-lock')
    try:
        value = path.lstat()
        result['.X1-lock'] = dict(identity={field: getattr(value, 'st_'+field) for field in ('dev','ino','mode','uid','gid','size','mtime_ns','ctime_ns')}, sha256=digest(path))
    except FileNotFoundError:
        result['.X1-lock'] = None
    return result

def node_identity(path):
    value = path.lstat()
    return {field: getattr(value, 'st_'+field) for field in ('dev','ino','mode','uid','gid','size','mtime_ns','ctime_ns')}

def quarantine_historical():
    socket_path = Path('/tmp/.X11-unix/X1')
    lock_path = Path('/tmp/.X1-lock')
    original = node_identity(socket_path)
    lock_original = node_identity(lock_path)
    content = lock_path.read_bytes()
    expected_content = b'    816616\0'
    if not (original['dev'] == 34 and original['ino'] == 1231594 and original['uid'] == 1000
            and original['gid'] == 1000 and stat.S_ISSOCK(original['mode'])
            and stat.S_IMODE(original['mode']) == 0o755
            and original['mtime_ns'] == original['ctime_ns'] == 1790501406951145127):
        raise RuntimeError('historical X1 identity no longer matches audited failed run')
    if not (stat.S_ISREG(lock_original['mode']) and stat.S_IMODE(lock_original['mode']) == 0o444
            and lock_original['uid'] == lock_original['gid'] == 1000 and content == expected_content):
        raise RuntimeError('historical X1 lock identity/content differs')
    from kpharness.gamescope_socket import socket_rows
    if socket_rows(str(socket_path)):
        raise RuntimeError('historical X1 has a live named endpoint')
    old_pids = (816616,816722,816778,816785,816853,816854)
    if any(Path('/proc', str(pid)).exists() for pid in old_pids) or blocked(inventory()):
        raise RuntimeError('historical owner identity or conflicting workload is present')
    receipt = dict(status='prepared', source_run='20260927-092903-52fe911a', utc=datetime.now(timezone.utc).isoformat(),
                   checks=dict(original_socket_matches_audit=True, lock_content_matches_leader=True, named_endpoint_rows=[], old_owned_pids_absent=True, canonical_lock_held=True),
                   lock_content_hex=content.hex(), lock_content_pid=816616, entries=[])
    write('historical-x1-quarantine.json', receipt)
    for kind, path, expected in (('socket',socket_path,original),('lock',lock_path,lock_original)):
        target = path.parent / ('.task7-quarantine-' + RUN.name + '-' + path.name.lstrip('.'))
        if target.exists() or target.is_symlink():
            raise RuntimeError('quarantine destination already exists')
        if node_identity(path) != expected or socket_rows(str(socket_path)):
            raise RuntimeError('historical identity/endpoint changed before rename')
        if kind == 'lock' and path.read_bytes() != content:
            raise RuntimeError('historical lock content changed before rename')
        entry = dict(kind=kind, old_path=str(path), new_path=str(target), before=expected)
        if kind == 'lock': entry['sha256'] = digest(path)
        os.rename(path, target)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
        entry['after'] = node_identity(target)
        if any(entry['after'][key] != expected[key] for key in expected if key != 'ctime_ns'):
            raise RuntimeError('quarantine changed identity beyond rename ctime')
        receipt['entries'].append(entry)
        write('historical-x1-quarantine.json', receipt)
    receipt['status'] = 'quarantined'
    write('historical-x1-quarantine.json', receipt)
    return receipt

def child():
    sys.path.insert(0, str(SNAP / 'runtime'))
    from kpharness.gamescope_snapshot import verify_snapshot
    from kpharness.gamescope_xwayland import GamescopeXwaylandLease
    manifest = verify_snapshot(SNAP, source_root=SOURCE)
    if manifest['repository_root'] != str(SOURCE.parents[1]):
        raise RuntimeError('snapshot repository context differs from selected source')
    os.environ['KP_GAMESCOPE_REPO_ROOT'] = manifest['repository_root']
    from kpharness.gamescope_socket import canonical_lock_guard
    from kpharness.gamescope_processes import verify_private_xwayland
    lock_proof = canonical_lock_guard()
    evidence = dict(boot_error=None, cleanup_error=None, evidence_error=None, boot_passed=False,
                    interpreter=str(Path(sys.executable).resolve()), flags=dict(isolated=sys.flags.isolated, no_site=sys.flags.no_site, dont_write_bytecode=sys.dont_write_bytecode),
                    module=str(sys.modules[GamescopeXwaylandLease.__module__].__file__))
    def verify_candidate(display, *args, **kwargs):
        if display.split('.')[0] in {':0', ':94', ':100'}:
            raise RuntimeError('protected display selected; refusing admission')
        return verify_private_xwayland(display, *args, **kwargs)
    lease = GamescopeXwaylandLease(RUN, 1024, 768, xwayland_verifier=verify_candidate)
    evidence['canonical_lock'] = lock_proof
    evidence['repository_root'] = manifest['repository_root']
    try:
        try:
            lease.start()
            evidence['boot_passed'] = True
        except BaseException as error:
            evidence['boot_error'] = error_value(error)
        if evidence['boot_passed']:
            evidence['lease_alive_before_close'] = lease.is_alive()
            geometry = subprocess.run(['/usr/bin/xdotool', 'getdisplaygeometry'], env=dict(lease.environment), capture_output=True, text=True, timeout=5)
            evidence['geometry'] = dict(returncode=geometry.returncode, stdout=geometry.stdout.strip(), stderr=geometry.stderr.strip())
            evidence['lease'] = lease.receipt()
            evidence['controller'] = lease.controller
            rows = inventory()
            evidence['owned_topology'] = [r for r in rows if r['pgid'] == lease.pgid or r['sid'] == lease.session_id or r['pid'] in lease._known_members]
            evidence['forbidden_processes_during_lease'] = [r for r in blocked(rows) if r['comm'].lower() not in {'gamescope', 'gamescopereaper'}]
            write('lease-before-close.json', evidence)
    except BaseException as error:
        evidence['evidence_error'] = error_value(error)
    finally:
        evidence['controller'] = lease.controller
        evidence['candidate_display'] = lease.candidate_display
        evidence['forbidden_processes_during_lease'] = [r for r in blocked(inventory()) if r['comm'].lower() not in {'gamescope', 'gamescopereaper'}]
        # start() itself closes on failure. A failed internal close receives one
        # separately retained finally cleanup attempt; a closed lease is untouched.
        evidence['cleanup_attempts_before_finally'] = list(lease.cleanup_attempts)
        if not lease._closed:
            try:
                lease.close()
            except BaseException as error:
                evidence['cleanup_error'] = error_value(error)
        evidence['lease_closed'] = lease._closed
        evidence['cleanup_attempts'] = lease.cleanup_attempts
        evidence['lease_after_close'] = lease.receipt()
        evidence['known_members'] = [dict(pid=i.pid, start=i.start) for i in lease._known_members.values()]
        evidence['leader_returncode'] = None if lease.process is None else lease.process.poll()
        evidence['socket_cleanup'] = lease.socket_cleanup
        write('driver-result.json', evidence)
    return 0 if evidence['boot_passed'] and not any(evidence[k] for k in ('boot_error', 'cleanup_error', 'evidence_error')) and lease._closed else 1

def supervisor():
    outcome = dict(started_utc=datetime.now(timezone.utc).isoformat(), run=str(RUN), snapshot=str(SNAP), launches=0, errors=[])
    lock = Path(C['lock']).open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rows = inventory()
        protected_original = protected_sockets()
        write('protected-sockets-original.json', protected_original)
        free = shutil.disk_usage(RUN).free
        write('preflight.json', dict(processes=selected(rows), disk_free=free, minimum_free=1073741824, canonical_lock=str(C['lock']), lock_acquired=True))
        if blocked(rows):
            raise RuntimeError('preflight found Gamescope/game/Wine/FFmpeg process')
        if free < 1073741824:
            raise RuntimeError('less than one GiB storage available')
        sys.path.insert(0, str(SOURCE))
        from kpharness.gamescope_snapshot import create_snapshot, verify_snapshot
        create_snapshot(SOURCE, SNAP)
        manifest = verify_snapshot(SNAP, source_root=SOURCE)
        if 'kpharness/gamescope_socket.py' not in {entry['path'] for entry in manifest['files']}:
            raise RuntimeError('snapshot omitted gamescope_socket.py')
        for p in SNAP.rglob('*'):
            if p.is_file():
                p.chmod(0o444)
        for p in sorted([p for p in SNAP.rglob('*') if p.is_dir()], reverse=True):
            p.chmod(0o555)
        SNAP.chmod(0o555)
        before = {str(p.relative_to(SNAP)): digest(p) for p in SNAP.rglob('*') if p.is_file()}
        write('snapshot-before.json', dict(manifest_sha256=digest(SNAP/'gamescope-harness-manifest.json'), manifest=manifest, all_file_hashes=before, source_equal=True, read_only=True))
        command = [str(Path('/usr/bin/python3').resolve()), '-I', '-S', '-B', str(Path(__file__).resolve()), '--child']
        write('invocation.json', dict(command=command, driver_sha256=digest(Path(__file__)), inherited_lock_fd=lock.fileno()))
        quarantine = quarantine_historical()
        protected_before = protected_sockets()
        write('protected-sockets-before.json', protected_before)
        outcome['launches'] = 1
        with (RUN/'driver.log').open('xb') as log:
            proc = subprocess.run(command, cwd=RUN, stdout=log, stderr=subprocess.STDOUT, pass_fds=(lock.fileno(),))
        outcome['driver_returncode'] = proc.returncode
        try:
            verify_snapshot(SNAP, source_root=SOURCE)
            after = {str(p.relative_to(SNAP)): digest(p) for p in SNAP.rglob('*') if p.is_file()}
            outcome['snapshot_unchanged_source_equal'] = before == after
            write('snapshot-after.json', dict(all_file_hashes=after, source_equal=True, unchanged=before == after))
        except BaseException as error:
            outcome['snapshot_unchanged_source_equal'] = False
            outcome['errors'].append(error_value(error))
        result = json.loads((RUN/'driver-result.json').read_text())
        rows = inventory()
        owned = {r['pid'] for r in result.get('owned_topology', [])} | {r['pid'] for r in result.get('known_members', [])}
        if result.get('controller'):
            owned.add(result['controller']['pid'])
        outcome['owned_pid_survivors'] = [r for r in rows if r['pid'] in owned]
        outcome['post_processes'] = selected(rows)
        outcome['forbidden_processes_after'] = blocked(rows)
        display = result.get('candidate_display')
        socket_name = '/tmp/.X11-unix/X' + display[1:].split('.')[0] if display else None
        outcome['private_display'] = display
        outcome['private_socket_after'] = [line for line in Path('/proc/net/unix').read_text().splitlines() if socket_name and line.split()[-1] in {socket_name, '@'+socket_name}]
        outcome['private_socket_path_exists'] = bool(socket_name and Path(socket_name).exists())
        outcome['private_xwayland_after'] = [r for r in selected(rows) if r['comm'].lower() == 'xwayland' and (r['pid'] in owned or display in r.get('argv', []))]
        protected_after = protected_sockets()
        write('protected-sockets-after.json', protected_after)
        outcome['protected_sockets_unchanged'] = all(protected_before[name] == protected_after[name] for name in ('X0','X94','X100'))
        outcome['x1_lock_after'] = protected_after['.X1-lock']
        outcome['quarantine_unchanged'] = all(node_identity(Path(entry['new_path'])) == entry['after'] and (entry['kind'] != 'lock' or digest(Path(entry['new_path'])) == entry['sha256']) for entry in quarantine['entries'])
    except BaseException as error:
        outcome['errors'].append(error_value(error))
    finally:
        lock.close()
    with Path(C['lock']).open('a') as check:
        try:
            fcntl.flock(check, fcntl.LOCK_EX | fcntl.LOCK_NB)
            outcome['lock_free_after'] = True
        except BlockingIOError:
            outcome['lock_free_after'] = False
    result = json.loads((RUN/'driver-result.json').read_text()) if (RUN/'driver-result.json').exists() else {}
    access = result.get('lease', {}).get('x11', {}).get('access') or {}
    checks = dict(one_launch=outcome['launches']==1, driver_success=outcome.get('driver_returncode')==0,
                  geometry=result.get('geometry', {}).get('stdout')=='1024 768' and result.get('geometry', {}).get('returncode')==0,
                  lease_alive=result.get('lease_alive_before_close') is True,
                  access=access.get('access_model')=='owned-endpoint-host-local-no-cookie' and access.get('tcp')=='no-listeners' and len(access.get('peers', []))==2,
                  subreaper=result.get('controller', {}).get('subreaper') is True,
                  inherited_lock=result.get('canonical_lock', {}).get('exclusive') is True,
                  pathname_cleanup=result.get('socket_cleanup', {}).get('status') in {'removed', 'already_absent'},
                  protected_sockets=outcome.get('protected_sockets_unchanged') is True,
                  historical_quarantine=outcome.get('quarantine_unchanged') is True,
                  cleanup_passed=result.get('lease_closed') is True and len(result.get('cleanup_attempts', []))==1 and result['cleanup_attempts'][0]['status']=='passed',
                  snapshot=outcome.get('snapshot_unchanged_source_equal') is True,
                  owned_pids_absent=not outcome.get('owned_pid_survivors', [True]),
                  private_display_absent=not outcome.get('private_socket_after', [True]) and outcome.get('private_socket_path_exists') is False and not outcome.get('private_xwayland_after', [True]),
                  no_game_wine_ffmpeg=not outcome.get('forbidden_processes_after', [True]) and not result.get('forbidden_processes_during_lease', [True]),
                  lock_free=outcome.get('lock_free_after') is True, no_errors=not outcome['errors'])
    outcome['checks'] = checks
    outcome['verdict'] = 'PASS' if all(checks.values()) else 'FAIL'
    outcome['finished_utc'] = datetime.now(timezone.utc).isoformat()
    write('gate-result.json', outcome)
    print(json.dumps(outcome, indent=2))
    return 0 if outcome['verdict']=='PASS' else 1

if __name__ == '__main__':
    raise SystemExit(child() if sys.argv[1:] == ['--child'] else supervisor())
