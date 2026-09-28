"""Serialized owned live route runner; deploy exact script bytes and retain receipts."""
from live_preflight import *
import argparse, signal, time, re
from kpharness.scenario import _StepFailure
from kpharness.checkpoints import Checkpoints

from gpu_display import GPUDisplay

class ExampleSession(GPUDisplay, OwnedSession):
    example_files=[]
    console_files=[]
    def stage(self,resources=None):
        super().stage(resources)
        for name in ('kotorphasor.log','kotorphasor-proxy.log'):
            log=self.game_dir/name
            if log.is_symlink(): raise RuntimeError('Refusing symlink log reset')
            log.write_bytes(b'')
        scripts=self.game_dir/'kotorphasor/scripts'
        for p in scripts.glob('*.lua'):p.unlink()
        manifest={}
        for relative in self.example_files:
            src=ROOT/'scripts/examples'/relative
            dst=scripts/src.name
            shutil.copy2(src,dst)
            manifest[relative]=hashlib.sha256(dst.read_bytes()).hexdigest()
        console_dir=self.game_dir/'kotorphasor/console-examples'
        if console_dir.is_symlink():raise RuntimeError('Refusing symlink console example directory')
        console_dir.mkdir(exist_ok=True)
        for item in self.console_files:
            src=Path(item).resolve()
            dst=console_dir/src.name
            if dst.is_symlink():raise RuntimeError('Refusing symlink console example')
            shutil.copy2(src,dst)
            manifest[str(src)]={'sha256':hashlib.sha256(dst.read_bytes()).hexdigest(),'mode':'console-only','path':str(dst.relative_to(self.game_dir))}
        (self.run_dir/'deployed-scripts.json').write_text(json.dumps(manifest,indent=2))
        if any(name.startswith('cursed/') for name in self.example_files):
            observer=OUT/'zz_validation_observer.lua'
            shutil.copy2(observer,scripts/observer.name)
            (self.run_dir/'observer-source.json').write_text(json.dumps({'path':str(observer),'sha256':hashlib.sha256(observer.read_bytes()).hexdigest(),'scope':'independent sampled readbacks; no event claim or actor mutation'},indent=2))
            shutil.copy2(observer,self.run_dir/observer.name)


class ValidationRunner(ScenarioRunner):
    log_offset=0
    def sync_cursor(self):
        self.ch.events(since=self.ch.cursor,limit=1)
        return self.ch.cursor
    def _do(self, step):
        raw=step.raw
        if raw.get('do')=='console_open':
            desired=bool(raw.get('open',True))
            state=self.ch.request('devtools',op='status')
            if bool(state['open'])!=desired:
                subprocess.run(['xdotool','windowfocus','--sync',self.session.capture_window,'key','F12'],env=self.session.env,check=True,timeout=5)
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                state=self.ch.request('devtools',op='status')
                if bool(state['open'])==desired:return 'F12 overlay open='+str(desired)
                time.sleep(.1)
            raise _StepFailure('F12 overlay did not change state')
        if raw.get('do')=='console_command':
            before=self.ch.request('devtools',op='status')
            if not before['open']:raise _StepFailure('console must be open for real keyboard submission')
            code=raw['code']
            subprocess.run(['xdotool','windowfocus','--sync',self.session.capture_window,'key','ctrl+a'],env=self.session.env,check=True,timeout=5)
            parts=code.split('\n')
            for i,part in enumerate(parts):
                if i:subprocess.run(['xdotool','key','ctrl+Return'],env=self.session.env,check=True,timeout=5)
                if part:subprocess.run(['xdotool','type','--clearmodifiers','--delay',str(int(raw.get('delay_ms',2))),'--',part],env=self.session.env,check=True,timeout=60)
            for key in raw.get('keys_before_submit',[]):
                subprocess.run(['xdotool','key',key],env=self.session.env,check=True,timeout=5)
            if raw.get('suffix'):
                subprocess.run(['xdotool','type','--clearmodifiers','--delay','5','--',raw['suffix']],env=self.session.env,check=True,timeout=15)
            subprocess.run(['xdotool','key','Return'],env=self.session.env,check=True,timeout=5)
            deadline=time.monotonic()+float(raw.get('timeout',30))
            expected=int(before['submitted'])+1
            while time.monotonic()<deadline:
                result=self.ch.request('devtools',op='output')
                if int(result['completed'])>=expected:
                    lines=[line for line in result['lines'] if int(line['request'])==expected]
                    (self.run_dir/f'console-command-{step.index}.json').write_text(json.dumps({'code':code,'input':'real owned-window keyboard','expected_request':expected,'result':result},indent=2))
                    if int(result['submitted'])!=expected:raise _StepFailure('unexpected duplicate/extra console submission')
                    text='\n'.join(str(line['text']) for line in lines)
                    for part in raw.get('contains',[]):
                        if part not in text:raise _StepFailure('console missing output '+repr(part)+': '+text)
                    if raw.get('kind') and not any(line['kind']==raw['kind'] for line in lines):raise _StepFailure('console missing output kind '+raw['kind'])
                    if not raw.get('allow_error',False) and any(line['kind']=='error' for line in lines):raise _StepFailure('unexpected console error: '+text)
                    return text
                time.sleep(.1)
            (self.run_dir/f'console-timeout-{step.index}.json').write_text(json.dumps({'expected_request':expected,'before':before,'last_result':result,'code':code,'step':raw},indent=2))
            raise _StepFailure('typed console command did not complete request '+str(expected))
        if raw.get('do')=='owned_input':
            # UI integration proof only: exact game window and owned DISPLAY.
            action=raw.get('action','key')
            allowed={'key','keydown','keyup','type','mousemove','click'}
            if action not in allowed: raise _StepFailure('unsupported owned input action')
            window=self.session.capture_window
            subprocess.run(['xdotool','windowfocus','--sync',window],env=self.session.env,check=True,timeout=5)
            if action=='type':
                text=raw.get('text','')
                if len(text)>16000: raise _StepFailure('owned input text too long')
                command=['xdotool','type','--clearmodifiers','--delay',str(int(raw.get('delay_ms',8))),'--',text]
            elif action=='mousemove':
                command=['xdotool','mousemove','--window',window,str(int(raw['x'])),str(int(raw['y']))]
            else:
                command=['xdotool',action,str(raw.get('key',raw.get('button','Return'))) ]
            subprocess.run(command,env=self.session.env,check=True,timeout=60)
            with (self.run_dir/'owned-input.jsonl').open('a') as file:
                file.write(json.dumps({'time':time.time(),'window':window,'step':step.index,'action':action,'text':raw.get('text'),'key':raw.get('key')})+'\n')
            return 'sent '+action+' to owned game window '+window
        if raw.get('do')=='capture_free_look':
            subprocess.run(['xdotool','windowfocus','--sync',self.session.capture_window,'key','Caps_Lock'],env=self.session.env,check=True,timeout=5)
            return 'Toggled native free-look on owned game display; visual confirmation required'
        if raw.get('do')=='advance_ticks':
            clock=raw.get('clock','server')
            if clock not in ('server','client'):raise _StepFailure('invalid clock')
            field=clock+'_tick'
            start=int(self.ch.state()[field]); target=start+int(raw['ticks'])
            deadline=time.monotonic()+float(raw.get('timeout',120))
            while True:
                state=self.ch.state()
                if int(state[field])>=target:return f"observed {clock} ticks {start} -> {state[field]}"
                verdict=self.watchdog.check(state)
                if verdict:raise _StepFailure(str(verdict),verdict=verdict,state=state)
                if time.monotonic()>=deadline:raise _StepFailure(clock+' tick interval did not elapse',state=state)
                time.sleep(.2)
        if raw.get('do')=='mark_log':
            if getattr(self.session,'capture_window',None):
                w,h=self.session.capture_geometry
                subprocess.run(['xdotool','mouseup','1','mouseup','2','mouseup','3','mousemove','--window',self.session.capture_window,str(w//2),str(h//2)],env=self.session.env,check=True,timeout=5)
            self.log_offset=(self.session.game_dir/'kotorphasor.log').stat().st_size
            return 'saved native log offset '+str(self.log_offset)
        if raw.get('do')=='await_log':
            deadline=time.monotonic()+float(raw.get('timeout',60))
            pattern=re.compile(raw['pattern'])
            minimum=int(raw.get('minimum',1)); maximum=raw.get('maximum')
            while True:
                with (self.session.game_dir/'kotorphasor.log').open('rb') as file:
                    file.seek(self.log_offset); text=file.read().decode('utf-8',errors='replace')
                lines=[line for line in text.splitlines() if pattern.search(line)]
                if len(lines)>=minimum and (maximum is None or len(lines)<=maximum):
                    (self.run_dir/f'log-gate-{step.index}.json').write_text(json.dumps({'pattern':raw['pattern'],'offset':self.log_offset,'lines':lines},indent=2))
                    return 'native log matched '+str(len(lines))+' lines'
                if maximum is not None and len(lines)>maximum:raise _StepFailure('too many matching native log lines: '+str(len(lines)))
                if time.monotonic()>=deadline:raise _StepFailure('native log predicate not reached: '+raw['pattern'])
                state=self.ch.state()
                verdict=self.watchdog.check(state)
                if verdict:raise _StepFailure(str(verdict),verdict=verdict,state=state)
                time.sleep(.2)
        return super()._do(step)

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--script',action='append',default=[])
    ap.add_argument('--console-script',action='append',default=[])
    ap.add_argument('--route',required=True)
    ap.add_argument('--build-dir',default='/home/brunner56/kp-validation-20260922-build')
    a=ap.parse_args()
    route=Path(a.route).resolve()
    quick=OUT/'quick-cursed'/route.name
    if route.parent.name=='cursed' and quick.exists():
        print('Using reviewed quick creative route:',quick,flush=True)
        route=quick
    if route.parent.name=='quick-cursed' and (OUT/'.pause-cursed').exists():
        print('Cursed queue paused for another owned creative check',flush=True)
        while (OUT/'.pause-cursed').exists():time.sleep(.5)
    scenario=Scenario.load(route)
    assert scenario.settings['game_speed']==1.0,'Live demonstration requires explicit 1x'
    os.environ['KOTOR1_DIR']='/home/brunner56/krayt/tmp/k1_harness'
    os.environ['KP_CHANNEL_TIMEOUT']='90'
    if pids_by_name('swkotor.exe'):raise SystemExit('Existing K1 process: refusing concurrent live run')
    available={k:int(v.split()[0]) for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())}
    if available['MemAvailable']<4*1024*1024 or available['SwapFree']<1024*1024:raise SystemExit('Insufficient free memory/swap for owned live run')
    with (Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp/harness-locks/live-game.lock')).open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        before=source_receipt()
        session=ExampleSession('k1',build_dir=a.build_dir,staged=str(OUT/'stage-k1'),wineprefix=str(OUT/'wineprefix-k1'),reset_saves=True,boot_timeout=120,screen=(1024,768),log=print)
        session.example_files=a.script
        session.console_files=a.console_script
        video=None;video_log=None;code=2;failure=None
        try:
            channel=session.boot()
            original_lua=channel.lua
            def traced_lua(code, *args, **kwargs):
                response=original_lua(code,*args,**kwargs)
                with (session.run_dir/'lua-requests.jsonl').open('a') as receipt:
                    receipt.write(json.dumps({'time':time.time(),'code_sha256':hashlib.sha256(code.encode()).hexdigest(),'code':code,'response':response},default=str)+'\n')
                return response
            channel.lua=traced_lua
            (session.run_dir/'source-before.json').write_text(json.dumps(before,indent=2))
            shutil.copy2(route,session.run_dir/'executed-route.toml')
            (session.run_dir/'route-source.json').write_text(json.dumps({'path':str(route),'sha256':hashlib.sha256(route.read_bytes()).hexdigest()},indent=2))
            tree=subprocess.check_output(['xwininfo','-root','-tree'],env=session.env,text=True)
            (session.run_dir/'capture-windows.txt').write_text(tree)
            candidates=re.findall(r'(0x[0-9a-fA-F]+) \"([^\"]*)\".*?(\d+)x(\d+)\+',tree)
            candidates=[r for r in candidates if int(r[2])>=800 and int(r[3])>=600 and r[1]]
            if not candidates:raise RuntimeError('No owned game window for GPU capture')
            window=max(candidates,key=lambda r:int(r[2])*int(r[3]))
            session.capture_window=window[0]
            session.capture_geometry=(int(window[2]),int(window[3]))
            print('Capturing owned game window '+str(window),flush=True)
            video_log=(session.run_dir/'ffmpeg.log').open('w')
            video=subprocess.Popen(['ffmpeg','-nostdin','-y','-f','x11grab','-framerate','60','-video_size',window[2]+'x'+window[3],'-window_id',window[0],'-i',f':{session.display}.0','-an','-c:v','libx264','-preset','ultrafast','-crf','20','-threads','2',str(session.run_dir/'continuous.mp4')],stdout=video_log,stderr=subprocess.STDOUT)
            checkpoints=Checkpoints(session.target,session.save_dir,root=OUT/'checkpoints')
            report=ValidationRunner(scenario,session,channel,checkpoints=checkpoints,log=print).run()
            code=0 if report.ok else 1
            print(json.dumps({'ok':report.ok,'run_dir':str(session.run_dir)}),flush=True)
        except Exception as error:
            failure=str(error)
            print(f'LIVE RUN FAILED: {error}',flush=True);traceback.print_exc()
        finally:
            if video:
                video.send_signal(signal.SIGINT)
                try:video.wait(timeout=15)
                except subprocess.TimeoutExpired:video.kill();video.wait()
            if video_log:video_log.close()
            artifact_dir=session.run_dir or OUT/'preflight-failures'/str(time.time_ns())
            artifact_dir.mkdir(parents=True,exist_ok=True)
            if session.game_dir is not None and session.run_dir is not None:
                for name in ['kotorphasor.log','kotorphasor-proxy.log']:
                    src=session.game_dir/name
                    if src.is_file():shutil.copy2(src,artifact_dir/name)
            if session.game_dir is not None or session.xvfb is not None or session.launcher is not None:
                session.teardown()
            after=source_receipt()
            (artifact_dir/'source-before.json').write_text(json.dumps(before,indent=2))
            (artifact_dir/'source-after.json').write_text(json.dumps(after,indent=2))
            if failure:
                (artifact_dir/'failure.json').write_text(json.dumps({'error':failure,'game_staged':session.game_dir is not None},indent=2))
            if before!=after:
                print('SOURCE RECEIPT MISMATCH',flush=True);code=3
            if code==0:
                try:
                    (session.run_dir/'showcase-review-pending.json').write_text(json.dumps({'status':'needs_visual_review','source':'continuous.mp4','reason':'Select actual native behavior and verify clarity before rendering showcase; old generic combat-marker rendering is not accepted.'},indent=2))
                    print('Continuous capture retained; explicit native-behavior visual review required before showcase export',flush=True)
                except Exception as error:
                    print('SUCCESS MEDIA FAILED: '+str(error),flush=True)
                    code=4
            (OUT/'latest-live-result.json').write_text(json.dumps({'code':code,'run_dir':str(artifact_dir),'source_unchanged':before==after,'error':failure},indent=2))
        raise SystemExit(code)
