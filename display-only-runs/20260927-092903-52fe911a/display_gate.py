import sys, os, json, hashlib, subprocess, fcntl, shutil, traceback
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

def child():
    sys.path.insert(0, str(SNAP / 'runtime'))
    from kpharness.gamescope_snapshot import verify_snapshot
    from kpharness.gamescope_xwayland import GamescopeXwaylandLease
    verify_snapshot(SNAP, source_root=SOURCE)
    evidence = dict(boot_error=None, cleanup_error=None, evidence_error=None, boot_passed=False,
                    interpreter=str(Path(sys.executable).resolve()), flags=dict(isolated=sys.flags.isolated, no_site=sys.flags.no_site, dont_write_bytecode=sys.dont_write_bytecode),
                    module=str(sys.modules[GamescopeXwaylandLease.__module__].__file__))
    lease = GamescopeXwaylandLease(RUN, 1024, 768)
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
            rows = inventory()
            evidence['owned_topology'] = [r for r in rows if r['pgid'] == lease.pgid or r['sid'] == lease.session_id]
            evidence['forbidden_processes_during_lease'] = [r for r in blocked(rows) if r['comm'].lower() not in {'gamescope', 'gamescopereaper'}]
            write('lease-before-close.json', evidence)
    except BaseException as error:
        evidence['evidence_error'] = error_value(error)
    finally:
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
        write('driver-result.json', evidence)
    return 0 if evidence['boot_passed'] and not any(evidence[k] for k in ('boot_error', 'cleanup_error', 'evidence_error')) and lease._closed else 1

def supervisor():
    outcome = dict(started_utc=datetime.now(timezone.utc).isoformat(), run=str(RUN), snapshot=str(SNAP), launches=0, errors=[])
    lock = Path(C['lock']).open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rows = inventory()
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
        for p in SNAP.rglob('*'):
            if p.is_file():
                p.chmod(0o444)
        for p in sorted([p for p in SNAP.rglob('*') if p.is_dir()], reverse=True):
            p.chmod(0o555)
        SNAP.chmod(0o555)
        before = {str(p.relative_to(SNAP)): digest(p) for p in SNAP.rglob('*') if p.is_file()}
        write('snapshot-before.json', dict(manifest_sha256=digest(SNAP/'gamescope-harness-manifest.json'), manifest=manifest, all_file_hashes=before, source_equal=True, read_only=True))
        command = [str(Path('/usr/bin/python3').resolve()), '-I', '-S', '-B', str(Path(__file__).resolve()), '--child']
        write('invocation.json', dict(command=command, driver_sha256=digest(Path(__file__))))
        outcome['launches'] = 1
        with (RUN/'driver.log').open('xb') as log:
            proc = subprocess.run(command, cwd=RUN, stdout=log, stderr=subprocess.STDOUT)
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
        outcome['owned_pid_survivors'] = [r for r in rows if r['pid'] in owned]
        outcome['post_processes'] = selected(rows)
        outcome['forbidden_processes_after'] = blocked(rows)
        display = result.get('lease_after_close', {}).get('x11', {}).get('display')
        socket_name = '/tmp/.X11-unix/X' + display[1:].split('.')[0] if display else None
        outcome['private_display'] = display
        outcome['private_socket_after'] = [line for line in Path('/proc/net/unix').read_text().splitlines() if socket_name and line.split()[-1] in {socket_name, '@'+socket_name}]
        outcome['private_socket_path_exists'] = bool(socket_name and Path(socket_name).exists())
        outcome['private_xwayland_after'] = [r for r in selected(rows) if r['comm'].lower() == 'xwayland' and (r['pid'] in owned or display in r.get('argv', []))]
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
