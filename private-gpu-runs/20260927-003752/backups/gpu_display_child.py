import json,os,signal,sys
from pathlib import Path
p=Path(sys.argv[1]);tmp=p.with_suffix('.tmp')
tmp.write_text(json.dumps({k:os.environ[k] for k in ('DISPLAY','XAUTHORITY','WAYLAND_DISPLAY') if k in os.environ}))
tmp.replace(p)
signal.pause()
