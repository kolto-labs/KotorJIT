import sys, json, hashlib
from pathlib import Path
root=Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation')
sys.path[:0]=[str(root/'scripts/harness'),str(root/'tools')]
from kpharness import display_backends as D
import kpharness_gamescope_backend_test as B

def make(source, *, level_source=None, bottom_source=None, indexed=True, count=None):
    count = len(source) if count is None else count
    base=B.fixture_content_probe(None,None)
    base=(base*((count+len(base)-1)//len(base)))[:count]
    if indexed:
        rows=B.with_index_fields([{k:v for k,v in row.items() if k not in ('index_top','index_bottom')} for row in base], source)
    else:
        rows=[{k:v for k,v in row.items() if k not in ('index_top','index_bottom')} for row in base]
    lev=source if level_source is None else level_source
    rows=[{**row,'yavg':B.pattern_yavg(lev[i]),'ydif':(20.0 if i else 0.0),'udif':0.0,'vdif':0.0} for i,row in enumerate(rows)]
    if indexed and bottom_source is not None:
        br=B.with_index_fields([{k:v for k,v in row.items() if k not in ('index_top','index_bottom')} for row in base], bottom_source)
        rows=[{**row,'index_bottom':br[i]['index_bottom']} for i,row in enumerate(rows)]
    pts=[i/60 for i in range(count)]
    return rows,pts

def run(name, rows, pts, policy, end=7.0):
    try:
        r=D.evaluate_content(rows,pts,1.0,end,policy)
    except Exception as exc:
        print(json.dumps({'case':name,'exception':type(exc).__name__,'message':str(exc)},sort_keys=True)); return
    idx=r.get('index_sequence')
    print(json.dumps({'case':name,'status':r['status'],'level':r.get('level_sequence',{}).get('status'),'index':None if idx is None else idx['status'],'kinds':[] if idx is None else sorted({v['kind'] for v in idx['violations']}),'drop_ratio':None if idx is None else idx['source_drop_ratio'],'max_gap':None if idx is None else idx['maximum_source_gap_seconds'],'failures':r['failures']},sort_keys=True))

p=dict(D.CONTENT_POLICIES['animated-diagnostic-v2'])
# isolated one-frame source drop: shared policy tolerance allows it only when total drop ratio remains <= .5%.
s=list(range(361)); s[61:]=[x+1 for x in s[61:]]
rows,pts=make(s); run('isolated_drop',rows,pts,p)
# accumulated drops: every output advances by two source frames.
s=list(range(0,720,2)); rows,pts=make(s); run('accumulated_drop',rows,pts,p)
# one large gap: total ratio is small but the max source gap is over 50ms.
s=list(range(2001)); s[601:]=[x+7 for x in s[601:]]; rows,pts=make(s); run('excessive_maxgap',rows,pts,p,end=30.0)
# periodic loop/replay controls.
for n in (7,14):
 s=[i%n for i in range(361)]; rows,pts=make(s); run(f'loop{n}',rows,pts,p)
# stale brightness with a valid-looking but repeating index.
s=[i%2 for i in range(361)]; rows,pts=make(s,level_source=[i%2 for i in range(361)]); run('stale_replay',rows,pts,p)
# reorder one frame in an otherwise increasing source.
s=list(range(361)); s[120],s[121]=s[121],s[120]; rows,pts=make(s); run('reorder',rows,pts,p)
# bottom half freezes while top continues.
top=list(range(361)); bottom=list(range(361)); bottom[180:]=[179 for _ in bottom[180:]]
rows,pts=make(top,bottom_source=bottom); run('halfregion_bottom_freeze',rows,pts,p)
# game/non-index policy must remain evaluable without barcode fields.
g=dict(D.CONTENT_POLICIES['game-capture-v1']); s=list(range(361)); rows,pts=make(s,indexed=False); run('non_index_game_policy',rows,pts,g)
