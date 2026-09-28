"""Owned GPU display prototype; no borrowing the desktop display."""
import json, os, subprocess, time
from pathlib import Path

class GPUDisplay:
    def start_xvfb(self):
        w,h=self.screen
        ready=self.run_dir/'gpu-display.json'
        child=Path('/home/brunner56/kp-live-20260922/gpu_display_child.py')
        env=dict(os.environ)
        for key in ('LIBGL_ALWAYS_SOFTWARE','GALLIUM_DRIVER','LP_NUM_THREADS'):
            env.pop(key,None)
        log=(self.run_dir/'gamescope.log').open('wb')
        self.xvfb=subprocess.Popen(['gamescope','--backend','headless','-w',str(w),'-h',str(h),'-W',str(w),'-H',str(h),'-r','60','--','/usr/bin/python3',str(child),str(ready)],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        log.close()
        deadline=time.monotonic()+20
        while not ready.is_file():
            if self.xvfb.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Owned GPU display failed to start')
            time.sleep(.1)
        self.gpu_env=json.loads(ready.read_text())
        self.display=int(self.gpu_env['DISPLAY'].split(':')[1].split('.')[0])
        env.update(self.gpu_env)
        check=subprocess.run(['glxinfo','-B'],env=env,text=True,capture_output=True,timeout=10)
        (self.run_dir/'renderer.txt').write_text(check.stdout+check.stderr)
        if check.returncode or 'Accelerated: yes' not in check.stdout:raise RuntimeError('GPU acceleration not established')
        self.log('Owned GPU display ready '+self.gpu_env['DISPLAY'])
    def _build_env(self):
        env=super()._build_env()
        for key in ('LIBGL_ALWAYS_SOFTWARE','GALLIUM_DRIVER','LP_NUM_THREADS'):
            env.pop(key,None)
        env.update(self.gpu_env)
        return env
