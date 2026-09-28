#!/usr/bin/python3
"""Private K2 GOG PE + installed Steam-assets one-save read-only Lua probe."""
import fcntl,hashlib,json,os,re,shutil,subprocess,sys,time,traceback
from pathlib import Path
BASE=Path('/home/brunner56/kp-live-20260922')
ROOT=Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation')
SOURCE=Path('/run/media/brunner56/MyBook/SteamLibrary/steamapps/common/Knights of the Old Republic II/steamassets')
EXE=Path('/home/brunner56/swkotor-multiplayer-investigation/artifacts/k2_gog_aspyr_20260917/swkotor2-client.exe')
RELEASE=Path('/home/brunner56/kp-release-20260922')
SAVE=SOURCE.parent/'cloudsaves/84888698/000013 - game12'
SAVE_NAME='000013 - game12'
TABLE=Path(os.environ.get('KP_K2_TABLE',str(RELEASE/'source/data/addresses/k2_gog_aspyr.json'))).resolve()
EXPECTED='777bee235a9e8bdd9863f6741bc3ac54bb6a113b62b1d2e4d12bbe6db963a914'
sys.path.insert(0,str(ROOT/'scripts/harness'))
from kpharness.session import GameSession,pids_by_name
from gpu_display import GPUDisplay

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save_receipt():
    assert SAVE.is_dir(),str(SAVE)
    assert not any(p.is_symlink() for p in SAVE.rglob('*'))
    files={str(p.relative_to(SAVE)):sha(p) for p in SAVE.rglob('*') if p.is_file()}
    assert {'savegame.sav','savenfo.res','globalvars.res','partytable.res'} <= set(files)
    return files
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
        shutil.copy2(TABLE,table/'k2_gog_aspyr.json')
    def stage(self,resources=None):
        super().stage(resources)
        for folder in ('override','Override'):
            d=self.game_dir/folder
            if d.is_symlink():
                d.unlink()
                d.mkdir()
            elif d.exists() and any(d.iterdir()):
                raise RuntimeError('Startup-only smoke requires an empty private Override: '+str(d))
        target=self.save_dir/SAVE_NAME
        shutil.copytree(SAVE,target)
        expected=save_receipt()
        assert {str(p.relative_to(target)):sha(p) for p in target.rglob('*') if p.is_file()}==expected
        (self.run_dir/'copied-save.json').write_text(json.dumps({'source':str(SAVE),'target':str(target),'sha256':expected},indent=2))
        (self.run_dir/'provenance.json').write_text(json.dumps({'build_source':str(self.build_dir),'asset_source':str(SOURCE),'exe_source':str(EXE),'exe_sha256':sha(self.game_dir/'swkotor2.exe'),'dll_sha256':sha(self.game_dir/'kphasor.dll'),'proxy_sha256':sha(self.game_dir/'binkw32.dll'),'table_source':str(TABLE),'experimental_table':bool(os.environ.get('KP_K2_TABLE')),'table_sha256':sha(self.game_dir/'kotorphasor/addresses/k2_gog_aspyr.json'),'source_override_mods_omitted':True,'override_policy':'empty private directory; installed source mods omitted for one copied save smoke; missing mod assets may prevent loading','scope':'mixed exact GOG PE / installed Steam assets; one copied Steam cloud save; read-only native calls'},indent=2))

LOAD_REQUIRED={'g.app_manager','app.create_server','net.start_connect_to_session','msg.request_status','app.set_load_from_savegame','client.set_loading_savegame','client.send_load_game_request','client.net_layer','client.message_handler'}
def main():
    assert os.environ.get('KP_PRIVATE_CONTROLLER_RUN'),'Run through private_k2_save_controller.py'
    table=json.loads(TABLE.read_text())
    assert table['build']=='k2_gog_aspyr' and table['reference_sha256']==EXPECTED
    if os.environ.get('KP_K2_TABLE'):
        baseline=json.loads((RELEASE/'source/data/addresses/k2_gog_aspyr.json').read_text())
        audited=json.loads(TABLE.read_text())
        if sha(TABLE)=='4e21a72a9754ae2b1a7babfe2d7fbf0d0b0c5a165efd0b92588a997923b38187':
            assert audited['adjudicated_bindings']==baseline['adjudicated_bindings']+1
            audited['adjudicated_bindings']=baseline['adjudicated_bindings']
            for counter in ('by_adjudication','by_field','resolved'):
                assert audited['summary'][counter]==baseline['summary'][counter]+1
                audited['summary'][counter]=baseline['summary'][counter]
            assert audited['summary']['unresolved']==[n for n in baseline['summary']['unresolved'] if n!='client.net_layer']
            audited['summary']['unresolved']=baseline['summary']['unresolved']
        audited['sites']['client.net_layer']=baseline['sites']['client.net_layer']
        assert audited==baseline,'Private table may change ONLY client.net_layer and exact frozen summary changes'
        assert table['sites']['client.net_layer'].get('offset')==16 and table['sites']['client.net_layer'].get('size')==4,'Unexpected audited field geometry'
    unresolved=sorted(name for name in LOAD_REQUIRED if table['sites'].get(name,{}).get('source')=='unresolved' or name not in table['sites'])
    if unresolved:raise RuntimeError('Prelaunch load_save capability missing: '+', '.join(unresolved))
    assert sha(EXE)==EXPECTED
    build=RELEASE/'build'
    expected_artifacts={'kphasor.dll':'895471980503fb87576b2e3b1b2645c48a0b150c247541559b72357feec57bf5','binkw32.dll':'765385d145af9a308eb9c11d2ef8db86d26c157949518a3cebf91510add2618c'}
    if os.environ.get('KP_K2_BUILD'):
        build=Path(os.environ['KP_K2_BUILD']).resolve(strict=True)
        assert build==Path('/home/brunner56/kp-release-20260927/build'),'Unapproved private build directory'
        expected_artifacts=json.loads((build.parent/'build-artifacts.json').read_text())
        assert set(expected_artifacts)=={'kphasor.dll','binkw32.dll'}
    for name,digest in expected_artifacts.items():
        assert isinstance(digest,str) and len(digest)==64 and sha(build/name)==digest,name

    for name in ('swkotor.exe','swkotor2.exe','kotor2'):
        if pids_by_name(name):raise RuntimeError('Existing game process: '+name)
    os.environ['KOTOR2_DIR']=str(SOURCE);os.environ['KP_K2_EXE']=str(EXE)
    os.environ['KP_CHANNEL_TIMEOUT']='30'
    run=Path(os.environ['KP_PRIVATE_CONTROLLER_RUN'])
    lock=Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp/harness-locks/live-game.lock')
    with lock.open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        save_before=save_receipt();(run/'k2-save-before.json').write_text(json.dumps(save_before,indent=2))
        before=receipt();(run/'k2-source-before.json').write_text(json.dumps(before))
        session=Session('k2-wine',build_dir=str(build),staged=str(run/'k2-stage'),wineprefix=str(run/'k2-prefix'),boot_timeout=120,screen=(1024,768),log=print)
        result={'ok':False,'save_loaded':False};code=2
        try:
            ch=session.boot()
            result['status']=ch.request('status')
            missing=sorted(LOAD_REQUIRED.intersection(result['status'].get('missing_sites',[])))
            if missing:raise RuntimeError('Live load_save capability missing: '+', '.join(missing))
            result['load_reply']=ch.request('load_save',dir=SAVE_NAME,timeout=120)
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                state=ch.request('state');bound=ch.request('status')
                result['last_state']=state;result['last_status']=bound
                if state.get('phase')=='gameplay' and state.get('phase_detail',{}).get('main_menu')==0 and bound.get('vm_bound'):
                    result['save_loaded']=True;break
                time.sleep(.25)
            else:raise RuntimeError('Copied save did not retire main menu and reach gameplay with bound VM; inspect missing assets/mod dependencies')
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
            commands=[
                ('arithmetic','1 + 1',['number','2']),
                ('pc',"K2PC=nwscript.call('GetFirstPC'); assert(nwscript.call('GetIsObjectValid',K2PC)==1); return K2PC",['number']),
                ('tag',"local s=nwscript.call('GetTag',K2PC); assert(type(s)=='string' and not s:find(string.char(0),1,true)); return s,#s",['string','number']),
                ('npc_tag',"local npc=nwscript.call('GetPartyMemberByIndex',1); assert(nwscript.call('GetIsObjectValid',npc)==1); local t=nwscript.call('GetTag',npc); assert(t=='atton' and #t==5); return t,#t",['string: atton','number: 5']),
                ('position',"local p=nwscript.call('GetPosition',K2PC); assert(type(p.x)=='number' and type(p.y)=='number' and type(p.z)=='number'); return p.x,p.y,p.z",['number']),
                ('hp',"local hp=nwscript.call('GetCurrentHitPoints',K2PC); assert(type(hp)=='number'); return hp",['number']),
                ('native',"local c=kp.model.capabilities(); if c.available then local s,e=kp.model.snapshot(K2PC); assert(s,e); return 'native snapshot',s.id,s.base,s.effective else return 'native unsupported',c.profile,c.abi end",['string']),
                ('bridge_recovery','6 * 7',['number','42']),
            ]
            result['commands']=[]
            for label,lua,expected in commands:
                status=ch.request('devtools',op='status');request=int(status['submitted'])+1
                key('key','ctrl+a');key('type','--clearmodifiers','--delay','2','--',lua);key('key','Return')
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    output=ch.request('devtools',op='output')
                    if int(output['completed'])>=request:break
                    time.sleep(.1)
                else:raise RuntimeError('Keyboard request did not complete: '+label)
                lines=[x for x in output['lines'] if int(x['request'])==request]
                entry={'label':label,'code':lua,'request':request,'lines':lines}
                result['commands'].append(entry)
                (run/('k2-console-'+label+'.json')).write_text(json.dumps(entry,indent=2))
                if any(x['kind']=='error' for x in lines):raise RuntimeError('Console command failed: '+label)
                text='\n'.join(x['text'] for x in lines if x['kind']=='result')
                if not all(x in text for x in expected):raise RuntimeError('Missing typed output: '+label)
                if int(output['submitted'])!=request:raise RuntimeError('Unexpected extra submission')
            key('key','F12')
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                if not ch.request('devtools',op='status')['open']:break
                time.sleep(.1)
            else:raise RuntimeError('F12 did not close before world capture')
            result['final_world_state']=ch.request('state')
            if result['final_world_state'].get('phase')!='gameplay' or result['final_world_state'].get('phase_detail',{}).get('main_menu')!=0:
                raise RuntimeError('Final world is not gameplay with main menu retired')
            subprocess.run(['ffmpeg','-nostdin','-y','-f','x11grab','-window_id',window,'-i',session.env['DISPLAY'],'-frames:v','1',str(run/'k2-world.png')],env=session.env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True,timeout=15)
            key('key','F12')
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                if ch.request('devtools',op='status')['open']:break
                time.sleep(.1)
            else:raise RuntimeError('F12 did not reopen before console capture')
            subprocess.run(['ffmpeg','-nostdin','-y','-f','x11grab','-window_id',window,'-i',session.env['DISPLAY'],'-frames:v','1',str(run/'k2-gameplay-console.png')],env=session.env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True,timeout=15)
            result['ok']=True;code=0
        except Exception as e:result['error']=str(e);traceback.print_exc()
        finally:
            session.teardown()
            save_after=save_receipt();result['save_source_unchanged']=save_before==save_after
            (run/'k2-save-after.json').write_text(json.dumps(save_after,indent=2))
            if save_before!=save_after:code=3;result['ok']=False
            after=receipt();result['source_unchanged']=before==after
            (run/'k2-source-after.json').write_text(json.dumps(after))
            if before!=after:code=3;result['ok']=False
            (run/'k2-save-result.json').write_text(json.dumps(result,indent=2))
        raise SystemExit(code)
if __name__=='__main__':main()
