"""Serialized owned live route runner; deploy exact script bytes and retain receipts."""
from live_preflight import *
import argparse, signal, time, re
from kpharness.scenario import _StepFailure
from kpharness.checkpoints import Checkpoints

class ExampleSession(OwnedSession):
    example_files=[]
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
        if raw.get('do')=='advance_ticks':
            start=int(self.ch.state()['server_tick']); target=start+int(raw['ticks'])
            deadline=time.monotonic()+float(raw.get('timeout',120))
            while True:
                state=self.ch.state()
                if int(state['server_tick'])>=target:return f"observed server ticks {start} -> {state['server_tick']}"
                verdict=self.watchdog.check(state)
                if verdict:raise _StepFailure(str(verdict),verdict=verdict,state=state)
                if time.monotonic()>=deadline:raise _StepFailure('server tick interval did not elapse',state=state)
                time.sleep(.2)
        if raw.get('do')=='mark_log':
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
    ap.add_argument('--route',required=True)
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
        session=ExampleSession('k1',build_dir='/home/brunner56/kp-validation-20260922-build',staged=str(OUT/'stage-k1'),wineprefix=str(OUT/'wineprefix-k1'),reset_saves=True,boot_timeout=120,log=print)
        session.example_files=a.script
        video=None;video_log=None;code=2
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
            video_log=(session.run_dir/'ffmpeg.log').open('w')
            video=subprocess.Popen(['ffmpeg','-nostdin','-y','-f','x11grab','-framerate','12','-video_size','1024x768','-i',f':{session.display}.0','-an','-c:v','libx264','-preset','ultrafast','-crf','28',str(session.run_dir/'continuous.mp4')],stdout=video_log,stderr=subprocess.STDOUT)
            checkpoints=Checkpoints(session.target,session.save_dir,root=OUT/'checkpoints')
            report=ValidationRunner(scenario,session,channel,checkpoints=checkpoints,log=print).run()
            code=0 if report.ok else 1
            print(json.dumps({'ok':report.ok,'run_dir':str(session.run_dir)}),flush=True)
        except Exception as error:
            print(f'LIVE RUN FAILED: {error}',flush=True);traceback.print_exc()
        finally:
            if video:
                video.send_signal(signal.SIGINT)
                try:video.wait(timeout=15)
                except subprocess.TimeoutExpired:video.kill();video.wait()
            if video_log:video_log.close()
            for name in ['kotorphasor.log','kotorphasor-proxy.log']:
                src=session.game_dir/name
                if src.is_file():shutil.copy2(src,session.run_dir/name)
            session.teardown()
            after=source_receipt()
            (session.run_dir/'source-after.json').write_text(json.dumps(after,indent=2))
            if before!=after:
                print('SOURCE RECEIPT MISMATCH',flush=True);code=3
            if code==0:
                try:
                    from render_run import render
                    render(session.run_dir)
                    print('Created representative.mp4 and representative.gif',flush=True)
                except Exception as error:
                    print('SUCCESS MEDIA FAILED: '+str(error),flush=True)
                    code=4
            (OUT/'latest-live-result.json').write_text(json.dumps({'code':code,'run_dir':str(session.run_dir),'source_unchanged':before==after},indent=2))
        raise SystemExit(code)
