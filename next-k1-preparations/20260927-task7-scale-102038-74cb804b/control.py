import os, sys, json, hashlib, subprocess, shutil, fcntl, time, signal, traceback
from pathlib import Path
from datetime import datetime, timezone

PREP = Path(__file__).resolve().parent
C = json.loads((PREP/'config.json').read_text())
ROOT, SNAP = Path(C['root']), Path(C['snapshot'])
SOURCE, BUILD = Path(C['source']), Path(C['build'])
PYTHON = str(Path('/usr/bin/python3').resolve())

def utc(): return datetime.now(timezone.utc).isoformat()
def write(name, data): (PREP/name).write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def identity(path):
    s=Path(path).lstat()
    return {k:getattr(s,'st_'+k) for k in ('dev','ino','mode','uid','gid','size','mtime_ns','ctime_ns')}
def processes():
    rows=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdecimal(): continue
        try:
            name=(p/'comm').read_text().strip(); low=name.lower()
            if low not in {'gamescope','gamescopereaper','xwayland','xvfb','swkotor.exe','swkotor2.exe','wine','wine64','wineserver','wineserver64','ffmpeg','wine-preloader','wine64-preloade'}: continue
            a=(p/'stat').read_text().rsplit(')',1)[1].split()
            args=(p/'cmdline').read_bytes().decode(errors='replace').rstrip('\0').split('\0')
            for i,v in enumerate(args[:-1]):
                if v=='-auth': args[i+1]='<authority-path-redacted>'
            rows.append(dict(pid=int(p.name),name=name,state=a[0],ppid=int(a[1]),pgid=int(a[2]),sid=int(a[3]),start=a[19],argv=args))
        except FileNotFoundError: continue
    return rows
def protected():
    rows=Path('/proc/net/unix').read_text().splitlines(); result={}
    for n in (0,94,100):
        p=Path('/tmp/.X11-unix')/('X'+str(n))
        result[str(p)]=dict(identity=identity(p), rows=sorted(r for r in rows if r.split()[-1] in {str(p),'@'+str(p)}))
    for p in (Path('/tmp/.X11-unix/.task7-quarantine-20260927-100845-8cd691c3-X1'),Path('/tmp/.task7-quarantine-20260927-100845-8cd691c3-X1-lock')):
        result[str(p)]={'identity':identity(p)}
        if p.is_file(): result[str(p)]['sha256']=sha(p)
    return result
def expected_inputs():
    d={
      str(BUILD/'kphasor.dll'):'fd8e069a1ff5a7b489f32a6492222f396f85e7b74539deb56228395b297dfac2',
      str(BUILD/'binkw32.dll'):'1b25f37125237aefb67271533f88c48dcf07ddd37bf180743a3b0dfa2ff729d9',
      str(SOURCE/'swkotor.exe'):'9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435',
      C['helper']:'07c533c28bb588507b473918b90abdb1a440d6099083155e7a86cfff32584a0e'}
    for name,h in {'k1_gog_103.json':'44a5984b71bf994dd5ee520e49198ced4953a3ff2e385673e9264a44ee36d4f2','k1_steam_103_unpacked.json':'541c5c3e7890406ce08d2959ed90cd3a97eee8974ceff6d34ae8522ccb7182c5'}.items():
        for root in (ROOT,BUILD.parent/'source'): d[str(root/'data/addresses'/name)]=h
    for name,h in {'GLOBALVARS.res':'fcdab52917af2125e7349609ad1a8b11f2f07f13705f48fb1298bd6cf7828e07','PARTYTABLE.res':'f380d0217e2db39d105b6851cd2fce4b48258291e68c654d822e4694820a2477','SAVEGAME.sav':'d879c65a63144a8668c1b7c566cb47fb3d66af3da0721d486701d4b2ace95bae','pifo.ifo':'a181c82c1a8d74d79344df5c8e99d9b277517f5fc048eccca39e82bea1b14676','savenfo.res':'d4d04f597d279266ebcd2ceb8a1917524f68e0dac780994eba6280e0b24b4c39'}.items():
        d[str(SOURCE/'Saves/000001 - AUTOSAVE'/name)]=h
    return d
def preflight(label):
    receipt={'utc':utc(),'launches':0,'checks':{},'protected':protected(),'processes':processes()}
    receipt['conflicting_processes']=[p for p in receipt['processes'] if p['name'].lower() not in {'xwayland','xvfb'}]
    receipt['memory']={k:int(v.split()[0])*1024 for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())}
    receipt['free_bytes']=shutil.disk_usage(PREP).free
    receipt['inputs']={p:dict(expected=h,actual=sha(p)) for p,h in expected_inputs().items()}
    receipt['tools']={name:shutil.which(name) for name in ('gamescope','Xwayland','xdotool','glxinfo','wine','wineserver','ffmpeg','ffprobe','xprop','xwininfo')}
    with Path(C['lock']).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        receipt['canonical_lock_free']=True
    receipt['checks']={'inputs_exact':all(v['actual']==v['expected'] for v in receipt['inputs'].values()),'no_conflicting_workload':not receipt['conflicting_processes'],'memory_available_4GiB':receipt['memory']['MemAvailable']>=4*1024**3,'swap_available_1GiB':receipt['memory']['SwapFree']>=1024**3,'storage_available_10GiB':receipt['free_bytes']>=10*1024**3,'tools':all(receipt['tools'].values()),'no_display_reuse':not os.environ.get('KP_HARNESS_REUSE_DISPLAY'),'lock_free':True}
    previous=json.loads(Path('/home/brunner56/kp-live-20260922/display-only-runs/20260927-100845-8cd691c3/historical-x1-quarantine.json').read_text())
    receipt['checks']['historical_quarantines_unchanged']=all(identity(e['new_path'])==e['after'] for e in previous['entries'])
    manifest=json.loads((BUILD.parent/'build-artifacts.json').read_text())
    receipt['checks']['build_manifest']=all(manifest[n]==sha(BUILD/n) for n in ('kphasor.dll','binkw32.dll'))
    receipt['status']='passed' if all(receipt['checks'].values()) else 'refused'
    write(label+'.json',receipt)
    if receipt['status']!='passed': raise RuntimeError('preflight refused: '+str([k for k,v in receipt['checks'].items() if not v]))
    return receipt
def verify_and_receipt(name):
    from kpharness.gamescope_snapshot import verify_snapshot
    manifest=verify_snapshot(SNAP,source_root=ROOT/'scripts/harness')
    out={'manifest':manifest,'manifest_sha256':sha(SNAP/'gamescope-harness-manifest.json'),'all_files':{str(p.relative_to(SNAP)):sha(p) for p in SNAP.rglob('*') if p.is_file()},'source_equal':True}
    write(name+'.json',out); return out
def prepare():
    preflight('preflight-preparation')
    for name in ('build-artifacts.json','baseline-source-provenance.json','reviewed-overlay.json','build.log'):
        shutil.copyfile(BUILD.parent/name,PREP/name)
    env=dict(os.environ,KP_TASK7_ROUTE=C['route'])
    subprocess.run([PYTHON,'-I','-S','-B',str(PREP/'generate-route.py')],env=env,check=True)
    sys.path.insert(0,str(ROOT/'scripts/harness'))
    from kpharness.gamescope_snapshot import create_snapshot
    create_snapshot(ROOT/'scripts/harness',SNAP)
    manifest=verify_and_receipt('snapshot-prepared')['manifest']
    required={'gamescope_socket','gamescope_processes','gamescope_xwayland','physical_console','console_protocol','console_steps','owned_x11','creative','creative_wine','recording','scenario'}
    assert required <= {Path(p['path']).stem for p in manifest['files']}
    code="import sys,json;from pathlib import Path;sys.path.insert(0,"+repr(str(SNAP/'runtime'))+");from kpharness.scenario import Scenario;s=Scenario.load(Path("+repr(C['route'])+"));print(json.dumps({'target':s.target,'settings':s.settings,'steps':[dict(index=x.index,kind=x.kind,raw=x.raw) for x in s.steps]}))"
    parsed=json.loads(subprocess.run([PYTHON,'-I','-S','-B','-c',code],check=True,capture_output=True,text=True).stdout)
    physical=[s for s in parsed['steps'] if s['raw'].get('do')=='console_command']
    assert len(physical)==3 and all(s['raw']['expect_values']==[{'type':'Boolean','value':True}] and s['raw']['return_count']==1 for s in physical)
    assert parsed['target']=='k1' and parsed['settings']['game_speed']==1.0
    allowed={'load_save','clear_auto_pause','advance_dialog','assert_lua','advance_ticks','console_open','console_command','mark_log','await_log'}
    assert all(s['raw'].get('do') in allowed or s['raw'].get('wait')=='phase' for s in parsed['steps'])
    write('route-validation.json',parsed)
    from kpharness.creative_wine import source_receipt
    write('independent-source-before.json',source_receipt(SOURCE))
    for p in SNAP.rglob('*'):
        if p.is_file(): p.chmod(0o444)
    for p in sorted([p for p in SNAP.rglob('*') if p.is_dir()],reverse=True): p.chmod(0o555)
    SNAP.chmod(0o555)
    selected={str(p):sha(p) for p in [Path(C['route']),Path(C['helper']),*(PREP/n for n in ('build-artifacts.json','baseline-source-provenance.json','reviewed-overlay.json','build.log'))]}
    write('prepared-inputs.json',selected)
    print(json.dumps({'prepared':str(PREP),'steps':len(parsed['steps']),'physical_commands':len(physical),'modules':len(manifest['files']),'launches':0}))
def launch():
    if (PREP/'launch-once.json').exists(): raise RuntimeError('one launch invocation already consumed')
    sys.path.insert(0,str(ROOT/'scripts/harness'))
    initial=verify_and_receipt('snapshot-before-launch')
    selected=json.loads((PREP/'prepared-inputs.json').read_text())
    if not all(sha(p)==h for p,h in selected.items()): raise RuntimeError('prepared input changed')
    from kpharness.creative_wine import source_receipt
    if source_receipt(SOURCE)!=json.loads((PREP/'independent-source-before.json').read_text()): raise RuntimeError('source changed after preparation')
    prior=preflight('preflight-launch')
    args=['--backend','linux-wine-k1-gamescope','--target','k1','--script',C['helper'],'--route',C['route'],'--build-dir',C['build'],'--source',C['source'],'--staged',str(PREP/'stage-k1'),'--wineprefix',str(PREP/'wineprefix-k1'),'--checkpoint-root',str(PREP/'checkpoints-k1'),'--output',str(PREP/'runs'),'--width','1024','--height','768','--capture-fps','60','--boot-timeout','120','--marker',r'\[model-scene:task7scale\] phase=1 actor=1']
    for n in ('stage-k1','wineprefix-k1','checkpoints-k1','runs'):
        if (PREP/n).exists(): raise RuntimeError('fresh destination already exists: '+n)
    bootstrap='import sys,runpy;sys.path.insert(0,'+repr(str(ROOT/'scripts/harness'))+");runpy.run_module('kpharness.gamescope_snapshot',run_name='__main__')"
    command=[PYTHON,'-I','-S','-B','-c',bootstrap,'driver','--snapshot',str(SNAP),'--',*args]
    with (PREP/'launch-once.json').open('x') as f: json.dump({'utc':utc(),'command':command,'supervisor_pid':os.getpid(),'deadline_seconds':1800,'invocations':1},f,indent=2)
    started=time.monotonic(); timed_out=False; observed=[]
    with (PREP/'launcher.log').open('xb') as log:
        child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,cwd=PREP,start_new_session=True)
        write('launcher-process.json',{'pid':child.pid,'utc':utc(),'stat':Path('/proc',str(child.pid),'stat').read_text()})
        while child.poll() is None:
            if time.monotonic()-started>1800 and not timed_out:
                children=Path('/proc',str(child.pid),'task',str(child.pid),'children').read_text().split()
                if len(children)!=1: raise RuntimeError('cannot identify unique creative controller for graceful deadline')
                controller=int(children[0]); os.kill(controller,signal.SIGTERM); timed_out=True
                write('deadline.json',{'utc':utc(),'controller_pid':controller,'signal':'SIGTERM','automatic_retry':False})
            time.sleep(1)
        child.wait()
    after=verify_and_receipt('snapshot-after-run')
    source_after=source_receipt(SOURCE); write('independent-source-after.json',source_after)
    post={'utc':utc(),'launcher_returncode':child.returncode,'elapsed_seconds':time.monotonic()-started,'deadline_triggered':timed_out,'processes':processes(),'protected':protected(),'snapshot_unchanged':initial['all_files']==after['all_files'],'source_unchanged':source_after==json.loads((PREP/'independent-source-before.json').read_text()),'selected_inputs_unchanged':all(sha(p)==h for p,h in selected.items()),'exact_brief_inputs_unchanged':all(sha(p)==h for p,h in expected_inputs().items())}
    post['protected_unchanged']=prior['protected']==post['protected']
    with Path(C['lock']).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB); post['canonical_lock_free']=True
    write('postflight.json',post)
    print(json.dumps(post,indent=2))

if __name__=='__main__':
    try:
        launch() if sys.argv[1:]==['--launch'] else prepare()
    except BaseException as e:
        write('control-failure-'+('launch' if sys.argv[1:]==['--launch'] else 'prepare')+'.json',{'utc':utc(),'error':str(e),'traceback':traceback.format_exc(),'launch_invocation_recorded':(PREP/'launch-once.json').exists()})
        raise
