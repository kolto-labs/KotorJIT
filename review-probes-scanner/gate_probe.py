"""Does the packager's final gate scan the exact bytes written, before any write? Temp trees only."""
import sys, os, hashlib, tempfile, json
from pathlib import Path
from unittest import mock
sys.dont_write_bytecode = True
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/tools')
import package_creative_harness_test as T
B = T.B
with tempfile.TemporaryDirectory() as d:
    tmp = Path(d); src = T.fake_tree(tmp / 'src'); prov = T.provenance_for(src, tmp / 'p.json')
    seen = {}
    real = B._scanner.scan_bytes
    def spy(raw, **kw):
        seen['sha'] = hashlib.sha256(raw).hexdigest(); seen['out_exists'] = (tmp / 'out').exists()
        seen['allow'] = kw.get('allow', ()); seen['markers'] = len(kw.get('markers') or ())
        return real(raw, **kw)
    with mock.patch.object(B._scanner, 'scan_bytes', side_effect=spy):
        r = B.build(src, tmp / 'out', provenance=prov)
    disk = hashlib.sha256(Path(r['zip']).read_bytes()).hexdigest()
    print('1 gate sha == disk sha:', seen['sha'] == disk, '| out existed at gate time:', seen['out_exists'],
          '| allow:', seen['allow'], '| markers passed:', seen['markers'])
    # 2: disable the builder's own earlier path scans; the gate alone must refuse a planted home path
    T.write(src, 'scripts/examples/cursed/10_rancor.lua', '-- /home/' + os.environ['USER'] + '/x\n')
    prov2 = T.provenance_for(src, tmp / 'p2.json')
    with mock.patch.object(B, 'path_scan', return_value=[]):
        try:
            B.build(src, tmp / 'out2', provenance=prov2); print('2 BUILT (gate missed)')
        except ValueError as e:
            print('2 REFUSED:', str(e)[:160].replace(os.environ['USER'], '<user>'), '| out2 exists:', (tmp / 'out2').exists())
    # 3: gate raising an exception must also leave nothing
    with mock.patch.object(B._scanner, 'scan_bytes', side_effect=RuntimeError('boom')):
        try:
            B.build(T.fake_tree(tmp / 'src3'), tmp / 'out3', provenance=T.provenance_for(tmp / 'src3', tmp / 'p3.json'))
            print('3 BUILT')
        except Exception as e:
            print('3 raised', type(e).__name__, '| out3 exists:', (tmp / 'out3').exists())
