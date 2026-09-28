import sys, os, shutil, hashlib
sys.dont_write_bytecode = True
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/tools'); sys.path.insert(0, W + '/scripts/harness')
import package_creative_harness_test as T
from pathlib import Path
B = T.B
base = Path('/home/brunner56/kp-live-20260922/review-probes-packaging-r2/twice'); shutil.rmtree(base, ignore_errors=True)
src = T.fake_tree(base / 'src'); prov = T.provenance_for(src, base / 'prov.json')
r = B.build(src, base / 'out', provenance=prov)
snap = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (base / 'out').rglob('*') if p.is_file()}
try:
    B.build(src, base / 'out', provenance=prov); print('second build BUILT (unexpected)')
except ValueError as e:
    print('second build refused:', e)
after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (base / 'out').rglob('*') if p.is_file()}
print('out unchanged:', snap == after, 'files', len(after))
os.symlink(base / 'elsewhere', base / 'dangling')
try:
    B.build(src, base / 'dangling', provenance=prov); print('dangling-symlink out BUILT (unexpected)')
except ValueError as e:
    print('dangling symlink out refused:', e, '| target created:', (base / 'elsewhere').exists())
shutil.rmtree(base); print('cleanup done:', not base.exists())
