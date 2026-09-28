import sys, os, json, hashlib, tempfile, zipfile, shutil
from pathlib import Path
sys.dont_write_bytecode = True
W='/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W+'/tools'); sys.path.insert(0, W+'/scripts/harness')
import package_creative_harness_test as T
B = T.B
P = Path('/home/brunner56/kp-live-20260922/review-probes-packaging/fixround/adv')
if P.exists(): shutil.rmtree(P)
P.mkdir()
PNG = b'\x89PNG\r\n\x1a\n' + b'\0'*20 + b'/home/secretuser/kp-live/ ' + b'\xff\xfe'
def run(name, mutate):
    base = P/name; src = T.fake_tree(base/'src'); outside = base/'outside'; outside.mkdir()
    note = mutate(src, outside)
    try:
        prov = T.provenance_for(src, base/'prov.json')
        r = B.build(src, base/'out', provenance=prov)
        names = zipfile.ZipFile(r['zip']).namelist()
        leaked = [n for n in names if any(k in n for k in note['look'])]
        blob = b''.join(zipfile.ZipFile(r['zip']).read(n) for n in names)
        content = [m for m in note.get('bytes', []) if m in blob]
        print(f'{name}: BUILT; leaked entries={leaked}; leaked bytes={content}')
    except Exception as e:
        print(f'{name}: REFUSED {type(e).__name__}: {e}')

def parent_symlink_fixed(src, out):
    (out/'user').mkdir(); (out/'user'/'creative-harness.md').write_text('# Secret outside doc brunner56\n')
    shutil.rmtree(src/'docs/user'); os.symlink(out/'user', src/'docs/user')
    return {'look': ['creative-harness.md'], 'bytes': [b'Secret outside doc']}
def parent_symlink_walked(src, out):
    shutil.move(str(src/'scripts/examples'), str(out/'examples'))
    (out/'examples'/'cursed'/'outside_secret.lua').write_text('-- outside tree brunner56\n')
    os.symlink(out/'examples', src/'scripts/examples')
    return {'look': ['outside_secret'], 'bytes': [b'outside tree']}
def hardlink(src, out):
    (out/'private.txt').write_text('-- PRIVATE hardlinked bytes\n')
    os.link(out/'private.txt', src/'scripts/examples/cursed/hl.lua')
    return {'look': ['hl.lua'], 'bytes': [b'PRIVATE hardlinked']}
def case_variants(src, out):
    for n in ('A.SAV','b.GIF','c.Mp4','d.TPC','e.Bik','f.2DA'):
        (src/'scripts/examples/cursed'/n).write_bytes(b'x')
    return {'look': ['A.SAV','b.GIF','c.Mp4','d.TPC','e.Bik','f.2DA']}
def binary_lua(src, out):
    (src/'scripts/examples/cursed/evil.lua').write_bytes(PNG)
    return {'look': ['evil.lua'], 'bytes': [b'\x89PNG', b'/home/secretuser']}
def utf16_lua(src, out):
    (src/'scripts/examples/cursed/u16.lua').write_bytes('-- /home/secretuser/x\n'.encode('utf-16'))
    return {'look': ['u16.lua'], 'bytes': ['/home/'.encode('utf-16-le')]}
def markers(src, out):
    (src/'scripts/examples/cursed/m.lua').write_text('-- brunner56 ~/kp-live-20260922 /mnt/x /tmp/kp /root/x C:\\\\Users\\\\bob .superpowers/sdd\n')
    return {'look': ['m.lua'], 'bytes': [b'brunner56', b'kp-live', b'.superpowers']}
def nested_private(src, out):
    for d in ('.superpowers/sdd', 'data/adjudication', 'tmp', 'Saves'):
        (src/'scripts/examples/cursed'/d).mkdir(parents=True)
        (src/'scripts/examples/cursed'/d/'n.lua').write_text('-- nested private\n')
    return {'look': ['.superpowers', 'adjudication', 'tmp/', 'Saves']}
def backslash_name(src, out):
    (src/'scripts/examples/cursed'/'..\\..\\..\\..\\evil.lua').write_text('-- slip\n')
    return {'look': ['\\']}
def symlink_leaf(src, out):
    (out/'x.lua').write_text('--x\n'); os.symlink(out/'x.lua', src/'scripts/examples/cursed/ln.lua')
    return {'look': ['ln.lua']}
def pem_in_readme(src, out):
    (src/'scripts/examples/cursed/README.md').write_text('see /Users/bob and file:///home/x\n')
    return {'look': []}
for f in (parent_symlink_fixed, parent_symlink_walked, hardlink, case_variants, binary_lua, utf16_lua,
          markers, nested_private, backslash_name, symlink_leaf, pem_in_readme):
    run(f.__name__, f)
