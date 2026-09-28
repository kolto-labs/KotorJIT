"""Owned live preflight; never run until offline/review gates pass."""
import fcntl, hashlib, json, os, shutil, subprocess, sys, traceback
from pathlib import Path
ROOT=Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation')
OUT=Path('/home/brunner56/kp-live-20260922')
sys.path.insert(0,str(ROOT/'scripts/harness'))
from kpharness.session import GameSession, pids_by_name
from kpharness.scenario import Scenario, ScenarioRunner

class OwnedSession(GameSession):
    def game_pids(self):
        owned=[]
        for pid in pids_by_name(self.target.process_name):
            proc=Path('/proc')/str(pid)
            try:
                env=(proc/'environ').read_bytes().split(b'\0')
                prefix=f'WINEPREFIX={self.wineprefix}'.encode()
                if prefix in env or (proc/'cwd').resolve()==self.staged:
                    owned.append(pid)
            except OSError:
                pass
        return owned
    def process_alive(self):
        return bool(self.game_pids()) or (self.launcher is not None and self.launcher.poll() is None)
    def stage(self, resources=None):
        super().stage(resources)
        scripts=self.game_dir/'kotorphasor/scripts'
        if scripts.is_symlink(): scripts.unlink()
        elif scripts.exists(): shutil.rmtree(scripts)
        scripts.mkdir(parents=True)
        manifest={}
        for relative in ['probe/00_probe.lua','probe/10_position_trace.lua']:
            source=ROOT/'scripts/examples'/relative
            target=scripts/source.name
            shutil.copy2(source,target)
            manifest[relative]=hashlib.sha256(target.read_bytes()).hexdigest()
        (self.run_dir/'deployed-scripts.json').write_text(json.dumps(manifest,indent=2))
        # A private reflink copy avoids all writes through the source Override.
        override=self.game_dir/'Override'
        if override.is_symlink():
            source=override.resolve();override.unlink()
            subprocess.run(['cp','-a','--reflink=always',str(source),str(override)],check=True)
        if not override.exists():override.mkdir()

def source_receipt():
    source=Path('/home/brunner56/krayt/tmp/k1_harness')
    names=['swkotor.ini','kotorphasor.ini','kphasor.dll','binkw32.dll','binkw32_real.dll','steam_appid.txt','kotorphasor.log','kotorphasor-proxy.log']
    files=[source/n for n in names]+sorted((source/'Saves').rglob('*'))
    return {str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None for p in files if not p.is_dir()}

if __name__=='__main__':
    os.environ['KOTOR1_DIR']='/home/brunner56/krayt/tmp/k1_harness'
    if pids_by_name('swkotor.exe'):
        raise SystemExit('Existing K1 process: live preflight not started')
    lock=Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp/harness-locks/live-game.lock')
    lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        before=source_receipt()
        (OUT/'source-before.json').write_text(json.dumps(before,indent=2))
        session=OwnedSession('k1',build_dir='/home/brunner56/kp-validation-20260922-build',
            staged=str(OUT/'stage-k1'),wineprefix=str(OUT/'wineprefix-k1'),
            reset_saves=True,boot_timeout=120,log=print)
        try:
            channel=session.boot()
            report=ScenarioRunner(Scenario.load(OUT/'dantooine_smoke.toml'),session,channel,log=print).run()
            print(json.dumps({'ok':report.ok,'run_dir':str(session.run_dir)},indent=2),flush=True)
            exit_code=0 if report.ok else 1
        except Exception as error:
            print(f'PREFLIGHT FAILED: {error}',flush=True)
            traceback.print_exc()
            exit_code=2
        finally:
            session.teardown()
            after=source_receipt()
            (OUT/'source-after.json').write_text(json.dumps(after,indent=2))
            if before!=after:
                print('SOURCE RECEIPT MISMATCH',flush=True)
                exit_code=3
        raise SystemExit(exit_code)
