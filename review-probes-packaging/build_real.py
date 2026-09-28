import sys, json, hashlib
sys.dont_write_bytecode = True
W='/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W+'/tools')
import package_creative_harness as pch
P='/home/brunner56/kp-live-20260922/review-probes-packaging'
# 1) unpatched non-dry build must refuse (path hit / provenance)
sel = pch.select_files(W)['selected']
overlay = {r: hashlib.sha256(open(W+'/'+r,'rb').read()).hexdigest() for r in sel}
json.dump({'base_commit': None, 'overlay_sha256': overlay}, open(P+'/prov.json','w'))
try:
    pch.build(W, P+'/out-unpatched', provenance=P+'/prov.json'); print('UNPATCHED BUILT (unexpected)')
except ValueError as e:
    print('unpatched refused:', e)
# 2) bypass only the path-scan refusal so a real ZIP exists to scan independently
real_scan = pch.path_scan
hits=[]
def rec(rel, data):
    h = real_scan(rel, data); hits.extend(h); return []
pch.path_scan = rec
print(json.dumps(pch.build(W, P+'/out-real', provenance=P+'/prov.json'), indent=1))
print('bypassed hits', hits)
