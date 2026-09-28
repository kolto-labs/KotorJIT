from gpu_display import GPUDisplay
from pathlib import Path
import os,subprocess,time
class Display(GPUDisplay):
    screen=(1280,720)
    run_dir=Path('/home/brunner56/kp-live-20260922/gpu-capture-probe')
    log=staticmethod(print)
d=Display();d.run_dir.mkdir(exist_ok=True)
(d.run_dir/'gpu-display.json').unlink(missing_ok=True)
gears=None
try:
    d.start_xvfb();env=dict(os.environ);env.update(d.gpu_env)
    gears=subprocess.Popen(['glxgears','-geometry','1280x720'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    time.sleep(1)
    wid=subprocess.check_output(['xdotool','search','--name','glxgears'],env=env,text=True).splitlines()[0]
    print('Capturing owned window',wid)
    result=subprocess.run(['ffmpeg','-nostdin','-y','-f','x11grab','-framerate','60','-video_size','1280x720','-window_id',wid,'-i',d.gpu_env['DISPLAY'],'-t','4','-an','-c:v','libx264','-preset','ultrafast','-crf','20','-threads','2',str(d.run_dir/'capture.mp4')],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=15)
    (d.run_dir/'ffmpeg.log').write_bytes(result.stderr)
    print('capture exit',result.returncode)
finally:
    if gears:
        gears.terminate();gears.wait(timeout=5)
    if getattr(d,'xvfb',None):
        d.xvfb.terminate();d.xvfb.wait(timeout=10)
