"""Real snapshot (production create_snapshot of the worktree closure), then the production code IMPORTED FROM
THE SNAPSHOT RUNTIME (same -I -S -B bootstrap shape as supervise) computes trusted_lock_path with
KP_GAMESCOPE_REPO_ROOT redirected, and verify_child_authority-style check with a private flocked fd.
The canonical lock is only stat()ed by held_lock_descriptor; never opened."""
import json, os, subprocess, sys, tempfile, fcntl
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import gamescope_snapshot as S, capture_diagnostic as CD
t = Path(tempfile.mkdtemp(prefix='r12c-snap-'))
snap = S.create_snapshot(Path(W) / 'scripts/harness', t / 'snap', entries=CD.SNAPSHOT_ENTRIES)
runtime = snap / 'runtime'
fake = t / 'fake'; (fake / 'tmp/harness-locks').mkdir(parents=True); (fake / '.git').mkdir()
lock = os.open(fake / 'tmp/harness-locks/live-game.lock', os.O_RDWR | os.O_CREAT, 0o600); fcntl.flock(lock, fcntl.LOCK_EX)
code = ('import sys;sys.dont_write_bytecode=True;sys.path.insert(0,%r);' % str(runtime) +
        'import kpharness.capture_diagnostic as C, kpharness.gamescope_socket as G, json;'
        'print(json.dumps({"module": C.__file__, "trusted_lock": str(C.trusted_lock_path()),'
        '"root": str(G.trusted_repository_root(C.__file__))}));'
        'import os\ntry:\n  G.held_lock_descriptor(%d, C.trusted_lock_path()); print("ADMITTED")\n'
        'except RuntimeError as e: print("refused:", e)' % lock)
env = dict(os.environ, KP_GAMESCOPE_REPO_ROOT=str(fake)); env.pop('PYTHONPATH', None)
p = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code], env=env, pass_fds=(lock,), capture_output=True, text=True, cwd=snap)
print(p.stdout, p.stderr[-800:])
print('supervisor canonical_lock_path', CD.canonical_lock_path())
