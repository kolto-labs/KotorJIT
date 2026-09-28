"""held_lock_descriptor on the canonical lock's own ext4 filesystem, using a PRIVATE flocked file
(never the canonical lock). Also: other open of same file refused, unlocked fd refused."""
import fcntl, os, sys, tempfile
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import gamescope_socket as G, capture_diagnostic as CD
d = tempfile.mkdtemp(prefix='r12c-lockfs-', dir='/run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp')
p = os.path.join(d, 'private.lock')
fd = os.open(p, os.O_RDWR | os.O_CREAT, 0o600); fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
print('fdinfo_lock_lines', [l for l in open(f'/proc/self/fdinfo/{fd}') if 'FLOCK' in l])
st = os.fstat(fd); print('stat_key', f'{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino}')
print('held', G.held_lock_descriptor(fd, p))
other = os.open(p, os.O_RDONLY)
for name, f in (('other_open', other),):
    try: print(name, G.held_lock_descriptor(f, p))
    except RuntimeError as e: print(name, 'refused:', e)
os.close(other); os.close(fd); os.unlink(p); os.rmdir(d)
print('trusted_root', G.trusted_repository_root(CD.__file__))
print('trusted_lock_path', CD.trusted_lock_path(), '== supervisor', CD.trusted_lock_path() == CD.canonical_lock_path())
