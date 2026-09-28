import sys, io, os, zipfile, tarfile, gzip, struct
sys.dont_write_bytecode = True
sys.path.insert(0, '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/tools')
import scan_release_zip as S
exec(open('probes.py').read().split("C = {}")[0].split("MK = S.privacy_markers()")[1].replace("shutil.rmtree(D, ignore_errors=True); D.mkdir()", ""), globals()) if False else None
MK = S.privacy_markers(); U = os.environ['USER']
def zb(entries):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, d in entries: z.writestr(n, d)
    return b.getvalue()
def tb(members):
    b = io.BytesIO()
    with tarfile.open(fileobj=b, mode='w', format=tarfile.PAX_FORMAT) as t:
        for ti, d in members: ti.size = len(d); t.addfile(ti, io.BytesIO(d))
    return b.getvalue()
def r(raw, allow=()):
    x = S.scan_bytes(raw, markers=MK, allow=allow)
    return ('ok' if x['ok'] else 'FLAGGED') + ' ' + str([(f['kind'], f['detail'][:40]) for f in x['findings']][:4]) + ' expected=' + str([f['kind'] for f in x['expected']])
t = tarfile.TarInfo('a.lua'); t.uname = U
inner = tb([(t, b'-- ok\n')]); mid = tb([(tarfile.TarInfo('inner.tar'), inner)])
print('nested tar in tar.gz owner  ', r(zb([('p/s.tar.gz', gzip.compress(mid, mtime=0))])))
print('nested tar in tar.gz as .gz ', r(zb([('p/s.gz', gzip.compress(mid, mtime=0))])))
pe = b'MZ' + b'\0' * 62 + f'C:\\Users\\{U}\\x.pdb'.encode('utf-16-le')
print('small PE wide marker allow  ', r(zb([('p/k.dll', pe)]), ('*.dll',)))
pe2 = pe + b'\xff'
print('same + one 0xff byte allow  ', r(zb([('p/k.dll', pe2)]), ('*.dll',)))
