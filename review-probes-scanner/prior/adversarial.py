"""Round-2 adversarial probes. Fake trees only, under this scratch dir. Nothing published."""
import sys, os, json, hashlib, zipfile, shutil, stat, traceback
from pathlib import Path
sys.dont_write_bytecode = True
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/tools'); sys.path.insert(0, W + '/scripts/harness')
import package_creative_harness_test as T
B = T.B
P = Path('/home/brunner56/kp-live-20260922/review-probes-scanner/prior/adv')


def rm(path):
    """Cleanup that always finishes: restore write bits, unlink symlinks, ignore races."""
    if not os.path.lexists(path):
        return
    if os.path.islink(path) or not os.path.isdir(path):
        os.unlink(path); return
    for cur, dirs, files in os.walk(path, followlinks=False):
        for d in dirs:
            try: os.chmod(os.path.join(cur, d), 0o755, follow_symlinks=False)
            except (OSError, NotImplementedError): pass
    shutil.rmtree(path, ignore_errors=True)


rm(P); P.mkdir(parents=True)
PNG = b'\x89PNG\r\n\x1a\n' + b'\0' * 20 + b'/home/secretuser/kp-live/ ' + b'\xff\xfe'
RESULTS = {}


def run(name, mutate):
    base = P / name; src = T.fake_tree(base / 'src'); outside = base / 'outside'; outside.mkdir()
    note = mutate(src, outside)
    try:
        prov = T.provenance_for(src, base / 'prov.json')
        r = B.build(src, base / 'out', provenance=prov)
        z = zipfile.ZipFile(r['zip']); names = z.namelist()
        leaked = [n for n in names if any(k in n for k in note.get('look', []))]
        blob = b''.join(z.read(n) for n in names)
        content = [m for m in note.get('bytes', []) if m in blob]
        receipt = z.read(B.TOP + '/packaging-receipt.json')
        rleak = [m for m in note.get('receipt', []) if m in receipt]
        msg = f'BUILT; leaked entries={leaked}; leaked bytes={content}; receipt names={rleak}'
    except Exception as e:
        msg = f'REFUSED {type(e).__name__}: {e}'
    RESULTS[name] = msg
    print(f'{name}: {msg}', flush=True)


# ---- prior 11 ----
def parent_symlink_fixed(src, out):
    (out / 'user').mkdir(); (out / 'user' / 'creative-harness.md').write_text('# Secret outside doc\n')
    shutil.rmtree(src / 'docs/user'); os.symlink(out / 'user', src / 'docs/user')
    return {'look': ['creative-harness.md'], 'bytes': [b'Secret outside doc']}
def parent_symlink_walked(src, out):
    shutil.move(str(src / 'scripts/examples'), str(out / 'examples'))
    (out / 'examples' / 'cursed' / 'outside_secret.lua').write_text('-- outside tree\n')
    os.symlink(out / 'examples', src / 'scripts/examples')
    return {'look': ['outside_secret'], 'bytes': [b'outside tree']}
def hardlink(src, out):
    (out / 'private.txt').write_text('-- PRIVATE hardlinked bytes\n')
    os.link(out / 'private.txt', src / 'scripts/examples/cursed/hl.lua')
    return {'look': ['hl.lua'], 'bytes': [b'PRIVATE hardlinked']}
def case_variants(src, out):
    for n in ('A.SAV', 'b.GIF', 'c.Mp4', 'd.TPC', 'e.Bik', 'f.2DA'):
        (src / 'scripts/examples/cursed' / n).write_bytes(b'x')
    return {'look': ['A.SAV', 'b.GIF', 'c.Mp4', 'd.TPC', 'e.Bik', 'f.2DA']}
def binary_lua(src, out):
    (src / 'scripts/examples/cursed/evil.lua').write_bytes(PNG)
    return {'look': ['evil.lua'], 'bytes': [b'\x89PNG', b'/home/secretuser']}
def utf16_lua(src, out):
    (src / 'scripts/examples/cursed/u16.lua').write_bytes('-- /home/secretuser/x\n'.encode('utf-16'))
    return {'look': ['u16.lua'], 'bytes': ['/home/'.encode('utf-16-le')]}
def markers(src, out):
    (src / 'scripts/examples/cursed/m.lua').write_text('-- brunner56 ~/kp-live-20260922 .superpowers/sdd\n')
    return {'look': ['m.lua'], 'bytes': [b'brunner56', b'kp-live', b'.superpowers']}
def nested_private(src, out):
    for d in ('.superpowers/sdd', 'data/adjudication', 'tmp', 'Saves'):
        (src / 'scripts/examples/cursed' / d).mkdir(parents=True)
        (src / 'scripts/examples/cursed' / d / 'n.lua').write_text('-- nested private\n')
    return {'look': ['.superpowers', 'adjudication', 'tmp/', 'Saves'],
            'receipt': [b'.superpowers', b'adjudication', b'/tmp/', b'Saves']}
def backslash_name(src, out):
    (src / 'scripts/examples/cursed' / '..\\..\\..\\..\\evil.lua').write_text('-- slip\n')
    return {'look': ['\\']}
def symlink_leaf(src, out):
    (out / 'x.lua').write_text('--x\n'); os.symlink(out / 'x.lua', src / 'scripts/examples/cursed/ln.lua')
    return {'look': ['ln.lua']}
def users_in_readme(src, out):
    (src / 'scripts/examples/cursed/README.md').write_text('see /Users/bob and file:///home/x\n')
    return {'bytes': [b'/Users/bob']}


# ---- new: case-variant private names ----
def case_private_nested_examples(src, out):
    for d in ('.SuperPowers', 'TMP', 'Adjudication', 'SAVES', 'KP-LIVE-x', 'Research'):
        (src / 'scripts/examples/cursed' / d).mkdir(parents=True)
        (src / 'scripts/examples/cursed' / d / 'n.lua').write_text('-- case private\n')
    return {'look': ['SuperPowers', 'TMP', 'Adjudication', 'SAVES', 'KP-LIVE', 'Research'],
            'receipt': [b'SuperPowers', b'TMP', b'Adjudication', b'SAVES', b'KP-LIVE', b'Research']}
def case_private_in_closure(src, out):
    # A closure subpackage under a case-variant private name: only route where selection reaches depth.
    for d in ('Tmp', 'Research'):
        T.write(src, f'scripts/harness/kpharness/{d}/__init__.py', '')
        T.write(src, f'scripts/harness/kpharness/{d}/leak.py', 'SECRET_CLOSURE = 1\n')
    T.write(src, 'scripts/harness/kpharness/shared.py',
            'from .Tmp import leak\nfrom .Research import leak as l2\ndef helper():\n    return 1\n')
    return {'look': ['/Tmp/', '/Research/'], 'bytes': [b'SECRET_CLOSURE']}
def lower_private_in_closure(src, out):
    T.write(src, 'scripts/harness/kpharness/tmp/__init__.py', '')
    T.write(src, 'scripts/harness/kpharness/tmp/leak.py', 'SECRET_CLOSURE = 1\n')
    T.write(src, 'scripts/harness/kpharness/shared.py', 'from .tmp import leak\ndef helper():\n    return 1\n')
    return {'look': ['/tmp/'], 'bytes': [b'SECRET_CLOSURE']}
def case_markers(src, out):
    (src / 'scripts/examples/cursed/cm.lua').write_text(
        '-- Brunner56 KP-LIVE-20260922 .SUPERPOWERS mybook c:\\users\\bob C:/USERS/bob /Volumes/Ext /media/bob\n')
    return {'look': ['cm.lua'], 'bytes': [b'Brunner56', b'KP-LIVE', b'c:\\users', b'/Volumes/', b'/media/bob']}
def marker_name_file(src, out):
    (src / 'scripts/examples/cursed/20260927-102706-0523fa70.lua').write_text('-- run id named file\n')
    return {'look': ['20260927-102706']}

# ---- new: UTF-8 BOM / overlong / encoding tricks ----
def bom_home(src, out):
    (src / 'scripts/examples/cursed/bom.lua').write_bytes(b'\xef\xbb\xbf-- /home/secretuser/x\n')
    return {'look': ['bom.lua'], 'bytes': [b'/home/secretuser']}
def bom_then_png(src, out):
    (src / 'scripts/examples/cursed/bompng.lua').write_bytes(b'\xef\xbb\xbf' + PNG)
    return {'look': ['bompng.lua'], 'bytes': [b'\x89PNG']}
def overlong_slash(src, out):
    # '/home/' with overlong-encoded '/' (C0 AF): invalid under strict UTF-8
    (src / 'scripts/examples/cursed/ovl.lua').write_bytes(b'-- \xc0\xafhome\xc0\xafsecretuser\n')
    return {'look': ['ovl.lua'], 'bytes': [b'secretuser']}
def cesu_surrogate(src, out):
    (src / 'scripts/examples/cursed/sur.lua').write_bytes(b'-- \xed\xa0\x80 /home/x\n')
    return {'look': ['sur.lua']}
def zero_width_marker(src, out):
    # Visible to a human as /home/brunner56 but split by U+200B; user name still whole-word.
    (src / 'scripts/examples/cursed/zw.lua').write_text('-- /ho\u200bme/secretuser brun\u200bner56\n')
    return {'look': ['zw.lua'], 'bytes': ['secretuser'.encode()]}
def fullwidth_marker(src, out):
    (src / 'scripts/examples/cursed/fw.lua').write_text('-- \uff0fhome\uff0fsecretuser\n')
    return {'look': ['fw.lua'], 'bytes': ['secretuser'.encode()]}
def bom_gzip_ascii(src, out):
    (src / 'scripts/examples/cursed/bomgz.lua').write_bytes(b'\xef\xbb\xbfMZ fake header\n')
    return {'look': ['bomgz.lua']}

# ---- new: polyglots (valid UTF-8, no leading magic) ----
def pdf_ascii_after_comment(src, out):
    (src / 'scripts/examples/cursed/poly.lua').write_bytes(b'-- x\n%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n')
    return {'look': ['poly.lua'], 'bytes': [b'%PDF-1.4']}
def zip_appended_in_utf8(src, out):
    # ZIP with a STORED ASCII member appended after Lua text: still valid UTF-8? only if all bytes < 0x80.
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as z:
        zi = zipfile.ZipInfo('secret.txt', date_time=(1980, 1, 1, 0, 0, 0)); z.writestr(zi, 'SECRETPAYLOAD')
    data = b'-- innocent\n' + buf.getvalue()
    (src / 'scripts/examples/cursed/zpoly.lua').write_bytes(data)
    return {'look': ['zpoly.lua'], 'bytes': [b'SECRETPAYLOAD', b'PK\x03\x04']}
def base64_png_in_lua(src, out):
    import base64
    (src / 'scripts/examples/cursed/b64.lua').write_text('local img = "' + base64.b64encode(PNG).decode() + '"\n')
    return {'look': ['b64.lua'], 'bytes': [b'iVBORw0K']}
def gff_after_newline(src, out):
    (src / 'scripts/examples/cursed/gffp.lua').write_bytes(b'\nGFF V3.2 fake\n')
    return {'look': ['gffp.lua']}

# ---- new: ZIP entry name normalization ----
def nfc_nfd_twins(src, out):
    (src / 'scripts/examples/cursed' / 'caf\u00e9.lua').write_text('-- nfc\n')
    (src / 'scripts/examples/cursed' / 'cafe\u0301.lua').write_text('-- nfd\n')
    return {'look': ['caf']}
def case_twins(src, out):
    (src / 'scripts/examples/cursed/Twin.lua').write_text('-- upper\n')
    (src / 'scripts/examples/cursed/twin.lua').write_text('-- lower\n')
    return {'look': ['win.lua']}
def windows_reserved(src, out):
    for n in ('CON.lua', 'aux.lua', 'trail.lua.', 'sp.lua ', 'a:b.lua', 'q?.lua', 'st*r.lua'):
        (src / 'scripts/examples/cursed' / n).write_text('-- w\n')
    return {'look': ['CON.lua', 'aux.lua', 'trail.lua.', 'sp.lua ', 'a:b.lua', 'q?.lua', 'st*r.lua']}
def bidi_name(src, out):
    (src / 'scripts/examples/cursed' / 'x\u202eaul.txt.lua').write_text('-- bidi\n')
    return {'look': ['\u202e']}
def dotdot_like(src, out):
    (src / 'scripts/examples/cursed' / '..lua').write_text('-- dots\n')
    (src / 'scripts/examples/cursed' / '...lua').write_text('-- dots\n')
    return {'look': ['..lua']}


ALL = [parent_symlink_fixed, parent_symlink_walked, hardlink, case_variants, binary_lua, utf16_lua,
       markers, nested_private, backslash_name, symlink_leaf, users_in_readme,
       case_private_nested_examples, case_private_in_closure, lower_private_in_closure, case_markers,
       marker_name_file, bom_home, bom_then_png, overlong_slash, cesu_surrogate, zero_width_marker,
       fullwidth_marker, bom_gzip_ascii, pdf_ascii_after_comment, zip_appended_in_utf8, base64_png_in_lua,
       gff_after_newline, nfc_nfd_twins, case_twins, windows_reserved, bidi_name, dotdot_like]
only = set(sys.argv[1:])
for f in ALL:
    if only and f.__name__ not in only:
        continue
    try:
        run(f.__name__, f)
    except Exception:
        print(f.__name__, 'PROBE ERROR', traceback.format_exc(limit=2), flush=True)
json.dump(RESULTS, open(P.parent / 'adversarial.json', 'w'), indent=1)
rm(P)  # cleanup always finishes
print('cleanup done:', not P.exists())
