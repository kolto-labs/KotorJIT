"""Round-3 scanner probes. Crafted in memory; ZIPs written only under this scratch folder. Read-only on the worktree."""
import sys, io, os, zipfile, tarfile, struct, json, gzip, lzma, subprocess, shutil, zlib
from pathlib import Path
sys.dont_write_bytecode = True
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/tools')
import scan_release_zip as S
D = Path('/home/brunner56/kp-live-20260922/review-probes-scanner/zips'); shutil.rmtree(D, ignore_errors=True); D.mkdir()
MK = S.privacy_markers()
U = os.environ['USER']
print('markers', len(MK), 'identities', len(S.identity_markers(MK)), 'git identities', len(S.git_identities()))

def zbytes(entries, comment=b''):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, data, *extra in entries:
            zi = zipfile.ZipInfo(n, date_time=(1980, 1, 1, 0, 0, 0)); zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o100644 << 16
            for k, v in (extra[0] if extra else {}).items(): setattr(zi, k, v)
            z.writestr(zi, data)
        z.comment = comment
    return buf.getvalue()

def res(raw, allow=()):
    try:
        r = S.scan_bytes(raw, markers=MK, allow=allow)
    except Exception as e:
        return f'EXC {type(e).__name__}: {str(e)[:100]}'
    if r['ok']:
        return 'ok (NOT FLAGGED)'
    return 'FLAGGED ' + '; '.join(f"{f['kind']}:{f['detail'][:50]}" for f in r['findings'][:5])

def tarb(members, fmt=tarfile.PAX_FORMAT, mode='w', pax=None):
    b = io.BytesIO()
    with tarfile.open(fileobj=b, mode=mode, format=fmt, pax_headers=pax or {}) as t:
        for ti, data in members:
            ti.size = len(data); t.addfile(ti, io.BytesIO(data))
    return b.getvalue()

def ti(name, **kw):
    t = tarfile.TarInfo(name)
    for k, v in kw.items(): setattr(t, k, v)
    return t

C = {}
OK = b'-- ok\n'
SECRET = f'-- /home/{U}/secret\n'.encode()
# ---- tar owners
C['tar_uname_user'] = zbytes([('p/s.tar', tarb([(ti('a.lua', uname=U), OK)]))])
C['tar_uname_user_uppercase'] = zbytes([('p/s.tar', tarb([(ti('a.lua', uname=U.upper()), OK)]))])
C['tar_gname_git_email_local'] = zbytes([('p/s.tar', tarb([(ti('a.lua', gname='halomastar'), OK)]))])
C['tar_numeric_only_uid1000'] = zbytes([('p/s.tar', tarb([(ti('a.lua', uid=1000, gid=1000), OK)]))])
C['tar_root_0_0 (clean control)'] = zbytes([('p/s.tar', tarb([(ti('a.lua', uname='root', gname='root'), OK)]))])
C['tar_blank_0_0 (clean control)'] = zbytes([('p/s.tar', tarb([(ti('a.lua'), OK)]))])
C['tar_other_account_bob'] = zbytes([('p/s.tar', tarb([(ti('a.lua', uname='bob'), OK)]))])
C['tar_ustar_huge_uid_base256'] = zbytes([('p/s.tar', tarb([(ti('a.lua', uid=2**40), OK)], fmt=tarfile.GNU_FORMAT))])
C['tar_pax_member_uname_override'] = zbytes([('p/s.tar', tarb([(ti('a.lua', pax_headers={'uname': U}), OK)]))])
C['tar_pax_member_uid_override'] = zbytes([('p/s.tar', tarb([(ti('a.lua', pax_headers={'uid': '1000'}), OK)]))])
C['tar_pax_xattr_marker'] = zbytes([('p/s.tar', tarb([(ti('a.lua', pax_headers={'SCHILY.xattr.user.origin': f'/home/{U}/x'}), OK)]))])
C['tar_pax_comment_identity'] = zbytes([('p/s.tar', tarb([(ti('a.lua', pax_headers={'comment': 'built by arrenkaetris'}), OK)]))])
C['tar_pax_GLOBAL_comment_marker'] = zbytes([('p/s.tar', tarb([(ti('a.lua'), OK)], pax={'comment': f'/home/{U}/kp-live-x'}))])
C['tar_pax_GLOBAL_uname'] = zbytes([('p/s.tar', tarb([(ti('a.lua'), OK)], pax={'uname': U}))])
longdir = 'd' * 120 + '/'
C['tar_gnu_longname_marker'] = zbytes([('p/s.tar', tarb([(ti(longdir + f'kp-live-x/{U}.lua'), OK)], fmt=tarfile.GNU_FORMAT))])
C['tar_ustar_prefix_marker'] = zbytes([('p/s.tar', tarb([(ti('a' * 100 + f'/{U}/b.lua'), OK)], fmt=tarfile.USTAR_FORMAT))])
C['tar_gnu_longlink_symlink_target'] = zbytes([('p/s.tar', tarb([(ti('l', type=tarfile.SYMTYPE, linkname='x' * 120 + f'/home/{U}'), b'')], fmt=tarfile.GNU_FORMAT))])
# nested tarball in tarball in zip
inner = tarb([(ti('a.lua', uname=U), OK)])
mid = tarb([(ti('inner.tar'), inner)])
gz = io.BytesIO(); gzip.GzipFile(fileobj=gz, mode='wb', mtime=0).write(mid)
C['tar_nested_tar_in_targz_owner'] = zbytes([('p/s.tar.gz', gz.getvalue())])
C['tar_in_xz_owner'] = zbytes([('p/s.tar.xz', lzma.compress(inner))])
deep = zbytes([('d/s.tar', inner)])
for _ in range(3): deep = zbytes([('d/n.zip', deep)])
C['nested_4_deep (depth limit)'] = zbytes([('p/n.zip', deep)])
# data after tar end-of-archive / after an invalid header: GNU tar skips to next header; Python tarfile stops
m1 = tarb([(ti('a.lua'), OK)], fmt=tarfile.USTAR_FORMAT)
hidden = tarb([(ti('b.lua'), SECRET)], fmt=tarfile.USTAR_FORMAT)
end_idx = len(m1) - 1024 * ((len(m1) - 1024 - 512 - 512) // 1024)  # conservative; compute exactly below
# exact: header(512)+data padded(512) then EOF blocks
body = m1[:1024]
C['tar_member_after_EOF_zeros'] = zbytes([('p/s.tar', body + b'\0' * 1024 + hidden)])
bad = bytearray(512); bad[:10] = b'garbage!!!'
C['tar_member_after_invalid_header'] = zbytes([('p/s.tar', body + bytes(bad) + hidden)])
Path(D / 'tar_after_invalid.tar').write_bytes(body + bytes(bad) + hidden)
Path(D / 'tar_after_eof.tar').write_bytes(body + b'\0' * 1024 + hidden)
# ---- ZIP containers
z = zbytes([('p/a.lua', OK), ('p/b.lua', OK)])
cd = z.rfind(b'PK\x01\x02', 0, z.find(b'PK\x05\x06')); first_cd = z.find(b'PK\x01\x02')
# gap between last local entry and central directory; fix offsets
gap = f'/home/{U}/GAP-SECRET'.encode()
eocd = z.find(b'PK\x05\x06')
cd_off = struct.unpack_from('<I', z, eocd + 16)[0]
zz = bytearray(z[:cd_off] + gap + z[cd_off:])
struct.pack_into('<I', zz, eocd + len(gap) + 16, cd_off + len(gap))
C['zip_gap_before_central_dir'] = bytes(zz)
C['zip_trailing_after_eocd'] = z + f'\n/home/{U}/TRAIL'.encode()
# deflate stream with hidden bytes appended inside the compressed region of an entry
co = zlib.compressobj(9, zlib.DEFLATED, -15); comp = co.compress(OK) + co.flush()
comp_h = comp + f'/home/{U}/INSIDE'.encode()
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as zf: zf.writestr('p/a.lua', OK)
# hand-build a deflated entry with slack
name = b'p/a.lua'; crc = zlib.crc32(OK)
lh = struct.pack('<4sHHHHHIIIHH', b'PK\x03\x04', 20, 0, 8, 0, 0x21, crc, len(comp_h), len(OK), len(name), 0) + name
ch = struct.pack('<4sHHHHHHIIIHHHHHII', b'PK\x01\x02', 20, 20, 0, 8, 0, 0x21, crc, len(comp_h), len(OK), len(name), 0, 0, 0, 0, 0o100644 << 16, 0) + name
body2 = lh + comp_h
eo = struct.pack('<4sHHHHIIH', b'PK\x05\x06', 0, 0, 1, 1, len(ch), len(body2), 0)
C['zip_deflate_slack_bytes'] = body2 + ch + eo
# NUL in central name hides the tail from zipfile
C['zip_nul_in_name_tail_marker'] = zbytes([(f'p/a.lua\x00/home/{U}/x', OK)])
# 0x5855 old Info-ZIP unix field with uid/gid 1000
C['zip_extra_5855_uid'] = zbytes([('p/a.lua', OK, {'extra': struct.pack('<HHIIHH', 0x5855, 12, 0, 0, 1000, 1000)})])
C['zip_extra_7875_uid'] = zbytes([('p/a.lua', OK, {'extra': struct.pack('<HHBBIBI', 0x7875, 11, 1, 4, 1000, 4, 1000)})])
C['zip_extra_000d_pkware_unix'] = zbytes([('p/a.lua', OK, {'extra': struct.pack('<HHIIHH', 0x000d, 12, 0, 0, 1000, 1000)})])
C['zip_exact_duplicate_names'] = zbytes([('p/a.lua', OK), ('p/a.lua', OK)])
C['zip_file_vs_implicit_folder_case'] = zbytes([('p/A', OK), ('p/a/x.lua', OK)])
C['zip_file_vs_folder_same'] = zbytes([('p/x', OK), ('p/x/y.lua', OK)])
# ---- --allow cannot hide
enc = bytearray(zbytes([('p/a.dll', OK)])); enc[enc.find(b'PK\x03\x04') + 6] |= 1; enc[enc.find(b'PK\x01\x02') + 8] |= 1
C['allow_star_vs_encrypted'] = (bytes(enc), ('*',))
C['allow_star_vs_7z'] = (zbytes([('p/a.7z', b'7z\xbc\xaf\x27\x1c' + b'\0' * 40)]), ('*',))
C['allow_star_vs_zst_suffix'] = (zbytes([('p/a.bin.zst', b'hello')]), ('*',))
C['allow_star_vs_zstd_magic_as_dll'] = (zbytes([('p/a.dll', b'\x28\xb5\x2f\xfd' + b'\0' * 20)]), ('*',))
C['allow_star_vs_unreadable_gz'] = (zbytes([('p/a.gz', b'\x1f\x8b\x08' + b'broken')]), ('*',))
C['allow_star_vs_zip_as_dll_with_marker'] = (zbytes([('p/a.dll', zbytes([('x.txt', SECRET)]))]), ('*',))
C['allow_star_hides_png_media (by design)'] = (zbytes([('p/a.png', b'\x89PNG\r\n\x1a\n' + b'\0' * 20)]), ('*',))
C['allow_star_vs_heldback_codecaves'] = (zbytes([('p/data/codecaves.toml', OK)]), ('*',))
# ---- BOM and encodings
C['bom_elf_bin'] = zbytes([('p/a.bin', b'\xef\xbb\xbf\x7fELF' + b'\x01' * 20)])
C['double_bom_elf_bin'] = zbytes([('p/a.bin', b'\xef\xbb\xbf\xef\xbb\xbf\x7fELF' + b'\x01' * 20)])
C['bom_png_in_lua'] = zbytes([('p/a.lua', b'\xef\xbb\xbf\x89PNG\r\n\x1a\n')])
C['utf16le_nobom_log_marker'] = zbytes([('p/build.log', f'C:\\Users\\{U}\\x.pdb\r\n'.encode('utf-16-le'))])
C['utf16le_bom_log_marker'] = zbytes([('p/build.log', '\ufeff'.encode('utf-16-le') + f'/home/{U}/x\n'.encode('utf-16-le'))])
C['utf16le_nobom_dat_identity'] = zbytes([('p/cfg.dat', 'owner=arrenkaetris\n'.encode('utf-16-le'))])
C['utf16be_nobom_dat_marker'] = zbytes([('p/cfg.dat', f'/home/{U}/x\n'.encode('utf-16-be'))])
C['pe_small_all_utf8_valid_wide_marker'] = zbytes([('p/k.dll', b'MZ' + b'\0' * 62 + f'C:\\Users\\{U}\\x.pdb'.encode('utf-16-le'))])
C['utf32_marker_bin'] = zbytes([('p/a.bin', f'/home/{U}/x'.encode('utf-32-le'))])
# ---- markers and case
C['upper_HOME_other_user'] = zbytes([('p/a.md', b'see /HOME/bob/x\n')])
C['upper_HOME_build_user'] = zbytes([('p/a.md', f'see /HOME/{U.upper()}/x\n'.encode())])
C['Users_lower_mac'] = zbytes([('p/a.md', b'see /users/bob/x\n')])
C['D_drive_users'] = zbytes([('p/a.md', b'see D:\\Users\\bob\\x\n')])
C['imgui_PageDown/Home/End (fp control)'] = zbytes([('p/a.cpp', b'// PageDown/Home/End keys\n')])
C['run_id_runs_shape'] = zbytes([('p/a.md', b'tmp/k1_harness/runs/20260915-071620\n')])
C['run_id_8hex_upper'] = zbytes([('p/a.md', b'20260927-102706-0523FA70\n')])
C['run_id_bare_stamp (fp control)'] = zbytes([('p/a.md', b'20260910-095338\n')])
C['run_id_runs_windows_sep'] = zbytes([('p/a.md', b'runs\\20260915-071620\n')])
C['identity_email_full'] = zbytes([('p/a.md', b'mail halomastar@gmail.com\n')])
C['identity_git_name'] = zbytes([('p/a.md', b'by ArrenKaetris\n')])
C['identity_underscore'] = zbytes([('p/a.md', f'x_{U}_y\n'.encode())])
C['data_research_nested (docs ok?)'] = zbytes([('p/docs/research/a.md', OK)])
C['data_research'] = zbytes([('p/data/research/a.json', b'{}')])
C['nested_tmp_not_root'] = zbytes([('p/lib/tmp/a.lua', OK)])
C['root_tmp'] = zbytes([('p/tmp/a.lua', OK)])
C['root_tmp_no_topfolder'] = zbytes([('tmp/a.lua', OK), ('b.lua', OK)])
C['heldback_events_draft_case'] = zbytes([('p/Data/Events.Draft.toml', OK)])
C['heldback_in_nested_targz'] = zbytes([('p/s.tar', tarb([(ti('source/data/codecaves.toml'), OK)]))])

out = {}
for k, v in C.items():
    raw, allow = v if isinstance(v, tuple) else (v, ())
    out[k] = res(raw, allow)
    print(f'{k:42} {out[k]}')
json.dump(out, open(D.parent / 'probes.json', 'w'), indent=1)
