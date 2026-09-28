#!/usr/bin/python3
"""Private experiment controller: SSD /tmp for owned GPU display and its clients.
No product changes. Run `smoke` before `run <k2_startup_gpu.py arguments>`.
"""
import hashlib, json, os, runpy, signal, subprocess, sys, time
from pathlib import Path
BASE=Path('/home/brunner56/kp-live-20260922')
ROOT=Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation')

def verified_preflight():
    backing=Path(os.environ['KP_PRIVATE_TMP_BACKING'])
    a,b=Path('/tmp').stat(),backing.stat()
    if (a.st_dev,a.st_ino)!=(b.st_dev,b.st_ino) or b.st_uid!=os.getuid():
        return 'private /tmp mount identity mismatch'
    if backing.parent!=Path(os.environ['KP_PRIVATE_CONTROLLER_RUN']):
        return 'private /tmp backing is outside this owned controller run'
    if os.statvfs('/tmp').f_bavail*os.statvfs('/tmp').f_frsize<64*1024*1024:
        return 'private /tmp has less than 64 MiB free'
    # Probe the exact mounted filesystem, not unrelated quota rows.
    probe=Path('/tmp')/f'.owned-write-probe-{os.getpid()}'
    try:
        with probe.open('xb') as f:
            f.write(b'\0'*(1024*1024));f.flush();os.fsync(f.fileno())
    except OSError as e:
        return f'private /tmp write/fsync failed: {e}'
    finally:
        probe.unlink(missing_ok=True)
    return None

def child(mode,args):
    run=Path(os.environ['KP_PRIVATE_CONTROLLER_RUN'])
    problem=verified_preflight()
    if problem:raise RuntimeError(problem)
    mount=subprocess.check_output(['findmnt','-J','-T','/tmp','-o','TARGET,SOURCE,FSTYPE,OPTIONS'],text=True)
    (run/'mount.json').write_text(mount)
    (run/'child-namespaces.json').write_text(json.dumps({n:os.readlink('/proc/self/ns/'+n) for n in ('mnt','net','pid')},indent=2))
    import socket
    with socket.socket() as server:
        server.bind(('127.0.0.1',0));server.listen(1)
        with socket.create_connection(server.getsockname(),timeout=3):
            connection,_=server.accept();connection.close()
    sys.path.insert(0,str(ROOT/'scripts/harness'))
    import kpharness.session as session
    if mode=='run':
        session.preflight_tmp_write=verified_preflight
        # Failure must not enter product fallback that borrows an existing X.
        original_boot=session.GameSession.boot
        def owned_boot(self,*a,**kw):
            problem=verified_preflight()
            if problem:raise RuntimeError(problem)
            return original_boot(self,*a,**kw)
        session.GameSession.boot=owned_boot
        sys.argv=[str(BASE/'k2_startup_gpu.py')]+args
        runpy.run_path(sys.argv[0],run_name='__main__')
        return
    from gpu_display import GPUDisplay
    display=GPUDisplay();display.screen=(1024,768);display.run_dir=run;display.log=print;display.xvfb=None
    result={'game_launched':False,'mount_verified':True,'loopback_verified':True}
    try:
        display.start_xvfb()
        result.update(display=display.gpu_env['DISPLAY'],accelerated=True,gamescope_pid=display.xvfb.pid)
        env=dict(os.environ,**display.gpu_env)
        check=subprocess.run(['xdpyinfo'],env=env,text=True,capture_output=True,timeout=10)
        (run/'xdpyinfo.txt').write_text(check.stdout+check.stderr)
        if check.returncode:raise RuntimeError('owned X display probe failed')
        game=run/'smoke-game';prefix=run/'smoke-prefix'
        game.mkdir();prefix.mkdir()
        nested=session.wine_command(['glxinfo','-B'],game,prefix)
        (run/'nested-command.json').write_text(json.dumps(nested,indent=2))
        check=subprocess.run(nested,env=env,text=True,capture_output=True,timeout=10)
        (run/'nested-renderer.txt').write_text(check.stdout+check.stderr)
        if check.returncode or 'Accelerated: yes' not in check.stdout:raise RuntimeError('nested Wine namespace cannot access accelerated owned X display')
        result['nested_wine_display_verified']=True
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(3)
            code='import socket; s=socket.create_connection(("127.0.0.1",'+str(listener.getsockname()[1])+'),3); s.sendall(b"owned"); s.close()'
            subprocess.run(session.wine_command(['/usr/bin/python3','-c',code],game,prefix),env=env,check=True,timeout=5)
            connection,_=listener.accept()
            with connection:assert connection.recv(16)==b'owned'
        result['nested_loopback_verified']=True

    finally:
        if display.xvfb and display.xvfb.poll() is None:
            if os.getpgid(display.xvfb.pid)!=display.xvfb.pid:raise RuntimeError('display process-group ownership mismatch')
            os.killpg(display.xvfb.pid,signal.SIGTERM)
            try:display.xvfb.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(display.xvfb.pid,signal.SIGKILL);display.xvfb.wait(timeout=5)
        result['display_parent_reaped']=display.xvfb is None or display.xvfb.poll() is not None
        (run/'smoke.json').write_text(json.dumps(result,indent=2)+'\n')

def snapshot_manifest(directory):
    directory=Path(directory)
    if not directory.is_dir() or not (directory/'kpharness/__init__.py').is_file():
        raise RuntimeError('harness snapshot must contain an actual kpharness package')
    files={}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():raise RuntimeError('harness snapshot contains symlink: '+str(path))
        if path.is_file():files[str(path.relative_to(directory))]=hashlib.sha256(path.read_bytes()).hexdigest()
    if not files:raise RuntimeError('empty harness snapshot')
    return files

def main():
    if len(sys.argv)>1 and sys.argv[1]=='--child':
        child(sys.argv[2],sys.argv[3:]);return
    mode=sys.argv[1] if len(sys.argv)>1 else 'smoke'
    if mode not in ('smoke','run'):raise SystemExit('usage: private_gpu_controller.py smoke | run <live driver arguments>')
    if mode=='run' and subprocess.run(['pgrep','-x','swkotor.exe'],stdout=subprocess.DEVNULL).returncode==0:
        raise SystemExit('Existing host K1 process: refusing private live run')
    run=BASE/'private-gpu-runs'/time.strftime('%Y%m%d-%H%M%S')
    run.mkdir(parents=True,exist_ok=False,mode=0o700)
    for name in ('tmp','runtime','cache','backups'):(run/name).mkdir(mode=0o700)
    snapshot=os.environ.get('KP_PRIVATE_HARNESS_SNAPSHOT')
    snapshot=Path(snapshot).resolve(strict=True) if snapshot else None
    snapshot_before=snapshot_manifest(snapshot) if snapshot else None
    if snapshot:
        (run/'harness-snapshot.json').write_text(json.dumps({'source':str(snapshot),'target':str(ROOT/'scripts/harness'),'files':snapshot_before},indent=2))
    sources=[BASE/n for n in ('gpu_display.py','gpu_display_child.py','k2_startup_gpu.py','live_preflight.py')]
    for p in sources:(run/'backups'/p.name).write_bytes(p.read_bytes())
    receipt={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    (run/'originals-before.json').write_text(json.dumps(receipt,indent=2))
    env=dict(os.environ)
    for name in ('DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','KP_HARNESS_REUSE_DISPLAY','DBUS_SESSION_BUS_ADDRESS'):
        env.pop(name,None)
    env.update(KP_PRIVATE_CONTROLLER_RUN=str(run),KP_PRIVATE_TMP_BACKING=str(run/'tmp'),XDG_RUNTIME_DIR=str(run/'runtime'),XDG_CACHE_HOME=str(run/'cache'),TMPDIR='/tmp')
    command=['bwrap','--die-with-parent','--unshare-pid','--unshare-net','--bind','/','/','--proc','/proc','--dev','/dev','--dev-bind','/dev/dri','/dev/dri','--bind',str(run/'tmp'),'/tmp','--','/usr/bin/python3',str(Path(__file__).resolve()),'--child',mode]+sys.argv[2:]
    split=command.index('--')
    asset='/run/media/brunner56/MyBook/SteamLibrary/steamapps/common/Knights of the Old Republic II/steamassets'
    command[split:split]=['--ro-bind',asset,asset]
    if snapshot:
        split=command.index('--')
        command[split:split]=['--ro-bind',str(snapshot),str(ROOT/'scripts/harness')]
    (run/'parent-namespaces.json').write_text(json.dumps({n:os.readlink('/proc/self/ns/'+n) for n in ('mnt','net','pid')},indent=2))
    (run/'command.json').write_text(json.dumps(command,indent=2));print(f'OWNED_CONTROLLER_RUN={run}',flush=True)
    with (run/'controller.log').open('wb') as log:
        result=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT)
    if snapshot:
        snapshot_after=snapshot_manifest(snapshot)
        (run/'harness-snapshot-after.json').write_text(json.dumps({'files':snapshot_after,'unchanged':snapshot_after==snapshot_before},indent=2))
        if snapshot_after!=snapshot_before:raise RuntimeError('harness snapshot changed during controller run')
    after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    (run/'originals-after.json').write_text(json.dumps(after,indent=2))
    if receipt!=after:raise RuntimeError('private original file receipt mismatch')
    remaining=[]
    marker=('KP_PRIVATE_CONTROLLER_RUN='+str(run)).encode()
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            if marker in (proc/'environ').read_bytes().split(b'\0'):remaining.append(int(proc.name))
        except (OSError,PermissionError):pass
    (run/'teardown.json').write_text(json.dumps({'remaining_owned_pids':remaining,'originals_unchanged':receipt==after},indent=2))
    if remaining:raise RuntimeError('owned namespace descendants remain: '+str(remaining))
    print((run/'controller.log').read_text(),end='')
    print(f'Controller exit={result.returncode}; namespace exit tears down remaining owned descendants',flush=True)
    raise SystemExit(result.returncode)
if __name__=='__main__':main()
