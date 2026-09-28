import sys, hashlib, zipfile, shutil, json
from pathlib import Path
sys.dont_write_bytecode = True
W='/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W+'/tools'); sys.path.insert(0, W+'/scripts/harness')
import package_creative_harness_test as T
B = T.B
base = Path('/home/brunner56/kp-live-20260922/review-probes-packaging/race')
if base.exists(): shutil.rmtree(base)
src = T.fake_tree(base/'src')
target = 'scripts/examples/cursed/10_rancor.lua'
orig = (src/target).read_bytes()
real = B.clean_bytes
def swap(rel, data):
    out = real(rel, data)
    if rel == target:
        (src/target).write_bytes(orig)   # restore after staging read? no: stage got the tampered bytes
    return out
# overlay binds the ORIGINAL bytes; staged read sees tampered bytes; file restored before provenance re-read
prov = T.provenance_for(src, base/'prov.json')
(src/target).write_bytes(b'-- TAMPERED in window\n')
B.clean_bytes = swap
r = B.build(src, base/'out', provenance=prov)
shipped = zipfile.ZipFile(r['zip']).read('kotorphasor-creative-harness/'+target)
ov = json.loads((base/'prov.json').read_text())['overlay_sha256'][target]
print('build ok:', r['manifest_hashes'], '| shipped:', shipped, '| shipped sha == overlay:', hashlib.sha256(shipped).hexdigest()==ov)
