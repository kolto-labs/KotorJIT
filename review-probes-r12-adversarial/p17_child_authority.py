"""R12 --child authority attacks. Never opens the real canonical lock (stat only). Every lock here is private.
Each case stops right after verify_child_authority / held_lock_descriptor; nothing is launched."""
import fcntl, hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import capture_diagnostic as CD, gamescope_socket as GS
base = Path(tempfile.mkdtemp(prefix='kp-r12-p17-'))
real = GS.canonical_lock_path_for(GS.trusted_repository_root(CD.__file__))
print('checkout trusted lock path =', real, 'exists =', real.exists())

def private_lock(root):
    path = root / 'tmp/harness-locks/live-game.lock'; path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600); fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return path, fd

def forged_config(run_dir, lock_fd):
    run_dir.mkdir(parents=True, exist_ok=True)
    fd, sha = CD.create_child_token()
    (run_dir / 'commitments.json').write_text(json.dumps({'child_token_sha256': sha}))
    return CD.child_config(run_dir, ffmpeg='/x', ffprobe='/x', lock_fd=lock_fd, token_fd=fd, token_sha256=sha)

def attempt(label, fn):
    try:
        held = fn(); print(f'{label}: ADMITTED {held}')
    except Exception as error:
        print(f'{label}: refused: {error}')

# 1. checkout code, env redirected to a private root (R11-2 shape)
root1 = base / 'root1'; _, fd1 = private_lock(root1)
os.environ['KP_GAMESCOPE_REPO_ROOT'] = str(root1)
attempt('checkout_env_redirect', lambda: CD.verify_child_authority(forged_config(base / 'run1', fd1)))
del os.environ['KP_GAMESCOPE_REPO_ROOT']

# 2. second open file description of the (private stand-in) canonical lock, without the flock
root2 = base / 'root2'; path2, fd2 = private_lock(root2); other = os.open(path2, os.O_RDWR)
attempt('second_ofd_without_flock', lambda: GS.held_lock_descriptor(other, path2))
attempt('holder_ofd', lambda: GS.held_lock_descriptor(fd2, path2))
# 3. lock renamed away and replaced between the supervisor's flock and the child's check
os.rename(path2, path2.with_name('moved.lock')); path2.write_text('')
attempt('renamed_then_replaced', lambda: GS.held_lock_descriptor(fd2, path2))
os.unlink(path2)
attempt('renamed_no_replacement', lambda: GS.held_lock_descriptor(fd2, path2))

# 4. copied tree, byte-identical code, snapshot made by the REAL create_snapshot: manifest names the copy
fake = base / 'fakerepo'
for rel in ('scripts/harness', 'tools/kpdiscover.py', 'tools/tests/examples/manifest.json',
            'data/app_signatures.toml', 'data/addresses'):
    src, dst = Path(W) / rel, fake / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    (shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__')) if src.is_dir() else shutil.copyfile(src, dst))
_, fd4 = private_lock(fake)
snap = base / 'snap'
CD.create_snapshot(fake / 'scripts/harness', snap, entries=CD.SNAPSHOT_ENTRIES)
man = json.loads((snap / 'gamescope-harness-manifest.json').read_text())
same = all(hashlib.sha256((Path(W) / 'scripts/harness' / e['path']).read_bytes()).hexdigest() == e['sha256']
           for e in man['files'])
print('snapshot repository_root =', man['repository_root'], '| every module byte-identical to checkout =', same)
cfg = forged_config(base / 'run4', fd4)
code = ('import json,sys;sys.path.insert(0,%r);from kpharness import capture_diagnostic as CD;'
        'cfg=json.loads(open(%r).read());'
        'print("snapshot_copy_forged_lock: ADMITTED", CD.verify_child_authority(cfg))') % (str(snap / 'runtime'), str(base / 'cfg4.json'))
(base / 'cfg4.json').write_text(json.dumps(cfg))
r = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code], pass_fds=(fd4, cfg['token_fd']),
                   capture_output=True, text=True)
print((r.stdout + r.stderr).strip().splitlines()[-1])

# 5. bind mount in a private user+mount namespace: redirect a "canonical" path (private stand-in) to a
#    file the caller flocks. held_lock_descriptor uses only stat(path), so the real path behaves the same.
root5 = base / 'root5'; canon5 = root5 / 'tmp/harness-locks/live-game.lock'; canon5.parent.mkdir(parents=True)
canon5.write_text(''); mine = base / 'mine.lock'; mine.write_text('')
code5 = ('import fcntl,os,subprocess,sys;sys.path.insert(0,%r);from kpharness import gamescope_socket as GS;'
         'subprocess.run(["mount","--bind",%r,%r],check=True);'
         'fd=os.open(%r,os.O_RDWR);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);'
         'print("bind_mount_redirect: ADMITTED",GS.held_lock_descriptor(fd,%r))') % (
    W + '/scripts/harness', str(mine), str(canon5), str(mine), str(canon5))
r = subprocess.run(['unshare', '-rm', sys.executable, '-c', code5], capture_output=True, text=True)
print((r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout + r.stderr).strip() else f'rc={r.returncode}')
