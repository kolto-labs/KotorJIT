#!/usr/bin/python3
"""Private K2 GOG PE + installed Steam-assets startup probe. Never loads a save."""
import fcntl,hashlib,json,os,re,shutil,subprocess,sys,time,traceback
from pathlib import Path
BASE=Path('/home/brunner56/kp-live-20260922')
ROOT=Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation')
SOURCE=Path('/run/media/brunner56/MyBook/SteamLibrary/steamapps/common/Knights of the Old Republic II/steamassets')
EXE=Path('/home/brunner56/swkotor-multiplayer-investigation/artifacts/k2_gog_aspyr_20260917/swkotor2-client.exe')
RELEASE=Path('/home/brunner56/kp-release-20260922')
EXPECTED='777bee235a9e8bdd9863f6741bc3ac54bb6a113b62b1d2e4d12bbe6db963a914'
sys.path.insert(0,str(ROOT/'scripts/harness'))
from kpharness.session import GameSession,pids_by_name
from gpu_display import GPUDisplay

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def receipt():
    return {str(p.relative_to(SOURCE)):{'size':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns} for p in SOURCE.rglob('*') if p.is_file()}
class Session(GPUDisplay,GameSession):
    def game_pids(self):
        result=[]
        for pid in pids_by_name(self.target.process_name):
            try:
                if ('WINEPREFIX='+str(self.wineprefix)).encode() in (Path('/proc')/str(pid)/'environ').read_bytes().split(b'\0'):result.append(pid)
            except OSError:pass
        return result
    def process_alive(self):return bool(self.game_pids()) or (self.launcher is not None and self.launcher.poll() is None)
    def _ensure_executable(self,install):
        assert sha(EXE)==EXPECTED
        p=self.game_dir/'swkotor2.exe'
        if p.is_symlink():p.unlink()
        shutil.copy2(EXE,p)
        assert sha(p)==EXPECTED
        return p
    def _install_runtime(self):
        super()._install_runtime()
        table=self.game_dir/'kotorphasor/addresses'
        shutil.rmtree(table)
        table.mkdir()
        shutil.copy2(RELEASE/'source/data/addresses/k2_gog_aspyr.json',table/'k2_gog_aspyr.json')
    def stage(self,resources=None):
        super().stage(resources)
        for folder in ('override','Override'):
            d=self.game_dir/folder
            if d.is_symlink():
                d.unlink()
                d.mkdir()
            elif d.exists() and any(d.iterdir()):
                raise RuntimeError('Startup-only smoke requires an empty private Override: '+str(d))
        (self.run_dir/'provenance.json').write_text(json.dumps({'asset_source':str(SOURCE),'exe_source':str(EXE),'exe_sha256':sha(self.game_dir/'swkotor2.exe'),'dll_sha256':sha(self.game_dir/'kphasor.dll'),'proxy_sha256':sha(self.game_dir/'binkw32.dll'),'table_sha256':sha(self.game_dir/'kotorphasor/addresses/k2_gog_aspyr.json'),'source_override_mods_omitted':True,'override_policy':'empty private directory; installed source mods omitted for no-save startup smoke','scope':'mixed exact GOG PE / installed Steam assets; boot only, no save load'},indent=2))

def main():
    assert os.environ.get('KP_PRIVATE_CONTROLLER_RUN'),'Run through private_k2_gpu_controller.py'
    assert sha(EXE)==EXPECTED
    assert sha(RELEASE/'build/kphasor.dll')=='895471980503fb87576b2e3b1b2645c48a0b150c247541559b72357feec57bf5'
    assert sha(RELEASE/'build/binkw32.dll')=='765385d145af9a308eb9c11d2ef8db86d26c157949518a3cebf91510add2618c'
    for name in ('swkotor.exe','swkotor2.exe','kotor2'):
        if pids_by_name(name):raise RuntimeError('Existing game process: '+name)
    os.environ['KOTOR2_DIR']=str(SOURCE);os.environ['KP_K2_EXE']=str(EXE)
    os.environ['KP_CHANNEL_TIMEOUT']='30'
    run=Path(os.environ['KP_PRIVATE_CONTROLLER_RUN'])
    lock=Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp/harness-locks/live-game.lock')
    with lock.open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        before=receipt();(run/'k2-source-before.json').write_text(json.dumps(before))
        session=Session('k2-wine',build_dir=str(RELEASE/'build'),staged=str(run/'k2-stage'),wineprefix=str(run/'k2-prefix'),boot_timeout=120,screen=(1024,768),log=print)
        result={'ok':False,'save_loaded':False};code=2
        try:
            ch=session.boot()
            result['status']=ch.request('status')
            tree=subprocess.check_output(['xwininfo','-root','-tree'],env=session.env,text=True)
            (run/'k2-windows.txt').write_text(tree)
            matches=re.findall(r'(0x[0-9a-fA-F]+) \"([^\"]*)\".*?(\d+)x(\d+)\+',tree)
            matches=[x for x in matches if x[1] and int(x[2])>=800 and int(x[3])>=600]
            if not matches:raise RuntimeError('No owned K2 window')
            window=max(matches,key=lambda x:int(x[2])*int(x[3]))[0]
            def key(*args):subprocess.run(['xdotool',*args],env=session.env,check=True,timeout=10)
            key('windowfocus','--sync',window,'key','F12')
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                status=ch.request('devtools',op='status')
                if status['open']:break
                time.sleep(.1)
            else:raise RuntimeError('F12 overlay did not open')
            request=int(status['submitted'])+1
            key('type','--clearmodifiers','--delay','2','--','1 + 1');key('key','Return')
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                output=ch.request('devtools',op='output')
                if int(output['completed'])>=request:break
                time.sleep(.1)
            else:raise RuntimeError('Keyboard request did not complete')
            lines=[x for x in output['lines'] if int(x['request'])==request]
            result['console_output']=output
            if any(x['kind']=='error' for x in lines) or not any('number' in x['text'] and '2' in x['text'] for x in lines):raise RuntimeError('Missing typed number2 result')
            if int(output['submitted'])!=request:raise RuntimeError('Unexpected extra submission')
            result['ok']=True;code=0
        except Exception as e:result['error']=str(e);traceback.print_exc()
        finally:
            session.teardown()
            after=receipt();result['source_unchanged']=before==after
            (run/'k2-source-after.json').write_text(json.dumps(after))
            if before!=after:code=3;result['ok']=False
            (run/'k2-startup-result.json').write_text(json.dumps(result,indent=2))
        raise SystemExit(code)
if __name__=='__main__':main()
