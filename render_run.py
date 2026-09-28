"""Create a representative gameplay clip/GIF from a completed creative route."""
from pathlib import Path
import hashlib,json,subprocess,sys

def render(run):
    run=Path(run); report=json.loads((run/'report.json').read_text())
    if report.get('ok') is not True:raise ValueError('Cannot publish success media for failed route')
    video=run/'continuous.mp4'
    duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(video)],text=True).strip())
    elapsed=0.;start=None
    for step in report['steps']:
        description=step.get('description',step.get('label',''))
        # Actual report uses desc; support only known rendered labels as fallback.
        description+=' '+step.get('desc','')+' '+step.get('step','')
        if 'arena:' in description or 'fight the room' in description:
            start=max(0,elapsed-1);break
        elapsed+=float(step.get('seconds',0))
    if start is None:start=max(0,min(duration-12,elapsed*.6))
    start=min(start,max(0,duration-10));length=min(10,duration-start)
    common=['ffmpeg','-nostdin','-y','-v','error','-threads','2','-ss',str(start),'-t',str(length),'-i',str(video)]
    subprocess.run(common+['-an','-vf','scale=640:-2','-c:v','libx264','-preset','fast','-crf','24','-threads','2',str(run/'representative.mp4')],check=True)
    subprocess.run(common+['-filter_complex_threads','1','-filter_complex','fps=8,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3','-threads','2',str(run/'representative.gif')],check=True)
    receipt={'source_video':str(video),'source_sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'route_ok':True,'start_seconds':start,'duration_seconds':length,'selection':'automatic arena/combat route marker; requires visual review for defining effects','artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [run/'representative.mp4',run/'representative.gif']}}
    (run/'media.json').write_text(json.dumps(receipt,indent=2));return receipt
if __name__=='__main__':print(json.dumps(render(sys.argv[1]),indent=2))
