"""Crafted ZIPs against tools/scan_release_zip.py. Written only under scanner/. Read-only scan."""
import sys, io, os, zipfile, tarfile, struct, json, subprocess, shutil
from pathlib import Path
sys.dont_write_bytecode = True
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/tools')
import scan_release_zip as S
D = Path('/home/brunner56/kp-live-20260922/review-probes-scanner/prior/scanner')
shutil.rmtree(D, ignore_errors=True); D.mkdir()
MK = S.privacy_markers()
def mk(name, entries, comment=b'', prefix=b'', suffix=b''):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, data, *extra in entries:
            zi = zipfile.ZipInfo(n, date_time=(1980, 1, 1, 0, 0, 0)); zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = (0o100644) << 16
            if extra: 
                for k, v in extra[0].items(): setattr(zi, k, v)
            z.writestr(zi, data)
        z.comment = comment
    p = D / (name + '.zip'); p.write_bytes(prefix + buf.getvalue() + suffix); return p
def res(p):
    try:
        r = S.scan(p, markers=MK)
        return 'ok' if r['ok'] else 'FLAGGED ' + '; '.join(f"{f['kind']}:{f['detail'][:40]}" for f in r['findings'][:4])
    except Exception as e:
        return f'EXC {type(e).__name__}: {str(e)[:80]}'
cases = {
 'clean': mk('clean', [('pkg/a.lua', b'-- ok\n')]),
 'marker_in_entry_name_user': mk('n1', [('pkg/brunner56-notes.md', b'hi\n')]),
 'marker_in_entry_name_runid': mk('n2', [('pkg/20260927-102706-0523fa70/report.md', b'hi\n')]),
 'marker_in_entry_name_home': mk('n3', [('pkg/home/brunner56/x.md', b'hi\n')]),
 'kp_live_as_filename': mk('n4', [('pkg/kp-live-20260922.md', b'hi\n')]),
 'case_private_dir': mk('c1', [('pkg/.SuperPowers/sdd/x.md', b'hi\n'), ('pkg/TMP/x.md', b'hi\n'), ('pkg/Adjudication/x.json', b'{}')]),
 'case_marker_text': mk('c2', [('pkg/a.lua', b'-- c:\\users\\bob Brunner56 KP-LIVE /Volumes/x /media/bob\n')]),
 'zip_comment_marker': mk('m1', [('pkg/a.lua', b'-- ok\n')], comment=b'/home/brunner56/kp-live-20260922'),
 'entry_comment_marker': mk('m2', [('pkg/a.lua', b'-- ok\n', {'comment': b'/home/brunner56/secret'})]),
 'extra_field_marker': mk('m3', [('pkg/a.lua', b'-- ok\n', {'extra': struct.pack('<HH', 0xCAFE, 22) + b'/home/brunner56/secret'})]),
 'prepended_blob': mk('m4', [('pkg/a.lua', b'-- ok\n')], prefix=b'/home/brunner56/kp-live PRIVATE PREFIX\n'),
 'appended_blob_after_eocd': mk('m5', [('pkg/a.lua', b'-- ok\n')], suffix=b''),
 'nul_in_name': mk('x1', [('pkg/a.lua\x00../../../etc/evil', b'-- ok\n')]),
 'bidi_name': mk('x2', [('pkg/x\u202eaul.txt.lua', b'-- ok\n')]),
 'nfd_twins': mk('x3', [('pkg/caf\u00e9.lua', b'1'), ('pkg/cafe\u0301.lua', b'2')]),
 'case_twins': mk('x4', [('pkg/A.lua', b'1'), ('pkg/a.lua', b'2')]),
 'duplicate_names': mk('x5', [('pkg/a.lua', b'-- ok\n'), ('pkg/a.lua', b'-- /home/brunner56\n')]),
 'win_reserved': mk('x6', [('pkg/CON.lua', b'1'), ('pkg/a:b.lua', b'2'), ('pkg/t.lua.', b'3')]),
 'bom_magic': mk('p1', [('pkg/a.lua', b'\xef\xbb\xbfMZ fake\n')]),
 'pdf_ascii_polyglot': mk('p2', [('pkg/a.lua', b'-- x\n%PDF-1.4\n%%EOF\n')]),
 'utf16le_marker_in_dll': mk('p3', [('pkg/k.dll', b'MZ' + b'\0' * 30 + 'C:\\Users\\brunner56\\x.pdb'.encode('utf-16-le'))]),
 'ascii_marker_in_dll': mk('p4', [('pkg/k.dll', b'MZ' + b'\0' * 30 + b'/home/brunner56/build/x.pdb')]),
 'fp_run_id_like_date_in_doc': mk('f1', [('pkg/CHANGELOG.md', b'Built 20260927-102706 on CI\n')]),
 'fp_bioware_like_text': mk('f2', [('pkg/NOTES.md', b'TODO V2 plan\n')]),
 'fp_mz_text': mk('f3', [('pkg/mz.lua', b'MZ = 1\n')]),
 'fp_kb2_text': mk('f4', [('pkg/fix.md', b'KB2267602 is a Windows update\n')]),
 'fp_docs_research': mk('f5', [('pkg/docs/research/native-animation-sites.md', b'# public research\n')]),
 'fp_runs_folder': mk('f6', [('pkg/lib/runs/helper.lua', b'-- ok\n')]),
 'fp_linuxbrew_word': mk('f7', [('pkg/docs/install.md', b'Install with linuxbrew if you use it.\n')]),
}
# encrypted-like entry: set flag bit 0 so read() raises
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w') as z:
    z.writestr('pkg/a.lua', b'-- ok\n')
raw = bytearray(buf.getvalue())
i = raw.find(b'PK\x03\x04'); raw[i+6] |= 1
j = raw.find(b'PK\x01\x02'); raw[j+8] |= 1
(D / 'enc.zip').write_bytes(bytes(raw)); cases['encrypted_flag'] = D / 'enc.zip'
# tar.gz nested with marker inside
tb = io.BytesIO()
with tarfile.open(fileobj=tb, mode='w:gz') as t:
    data = b'-- /home/brunner56/x\n'; ti = tarfile.TarInfo('inner/a.lua'); ti.size = len(data); t.addfile(ti, io.BytesIO(data))
cases['nested_targz_marker'] = mk('t1', [('pkg/src.tar.gz', tb.getvalue())])
tb2 = io.BytesIO()
with tarfile.open(fileobj=tb2, mode='w:xz') as t:
    ti = tarfile.TarInfo('inner/a.lua'); ti.size = len(data); t.addfile(ti, io.BytesIO(data))
cases['nested_tarxz_allowed'] = mk('t2', [('pkg/src.tar.xz', tb2.getvalue())])
out = {}
for k, p in cases.items():
    out[k] = res(p); print(f'{k:32} {out[k]}')
# allow-list interplay: nested .tar.xz under --allow '*.xz'
r = S.scan(cases['nested_tarxz_allowed'], markers=MK, allow=('*.xz',))
print('nested_tarxz_with_allow_*.xz    ', 'ok' if r['ok'] else 'FLAGGED', [f['kind'] for f in r['findings']], 'expected', [f['kind'] for f in r['expected']])
r = S.scan(cases['ascii_marker_in_dll'], markers=MK, allow=('*.dll',))
print('ascii_marker_in_dll_with_allow  ', 'ok' if r['ok'] else 'FLAGGED', [f['kind'] for f in r['findings']])
# CLI behaviour on the encrypted case (uncaught exception?)
cp = subprocess.run([sys.executable, W + '/tools/scan_release_zip.py', str(D / 'enc.zip')], capture_output=True, text=True)
print('CLI encrypted rc', cp.returncode, 'stderr tail', cp.stderr.strip().splitlines()[-1:] if cp.stderr else '', 'stdout', cp.stdout[:80].replace('\n', ' '))
json.dump(out, open(D.parent / 'scanner_probes.json', 'w'), indent=1)
