"""--child authority: no token, forged token, replay, and a forged start that also redirects the
lock check through KP_GAMESCOPE_REPO_ROOT to a private lock file. Only verify_child_authority()
and main(['--child', ...]) up to the authority check are exercised; the canonical lock is never opened.
The main() call for the forged case runs in a subprocess whose run_child is replaced by a stub."""
import fcntl, hashlib, json, os, secrets, subprocess, sys, tempfile
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import capture_diagnostic as CD

def pipe_with(token: str) -> int:
    r, w = os.pipe(); os.write(w, token.encode()); os.close(w); return r

tmp = Path(tempfile.mkdtemp(prefix='kp-r11-p12-'))
run = tmp / 'run'; run.mkdir()

def attempt(label, config, **kw):
    try:
        CD.verify_child_authority(config, **kw); print(f'{label}: ADMITTED')
    except CD.DiagnosticRefused as e:
        print(f'{label}: refused: {e}')

# 1. no token
attempt('no_token', CD.child_config(run, ffmpeg='x', ffprobe='y', lock_fd=5))
# 2. forged token without commitments
token = secrets.token_hex(32); sha = hashlib.sha256(token.encode()).hexdigest()
attempt('forged_token_no_commitments', CD.child_config(run, ffmpeg='x', ffprobe='y', lock_fd=5,
        token_fd=pipe_with(token), token_sha256=sha))
# 3. replay: commitments of a "real" run exist, token plaintext is not recoverable; guess a new one
(run / 'commitments.json').write_text(json.dumps({'child_token_sha256': sha}))
attempt('replay_config_new_pipe_other_token', CD.child_config(run, ffmpeg='x', ffprobe='y', lock_fd=5,
        token_fd=pipe_with(secrets.token_hex(32)), token_sha256=sha))
# 4. replay with a regular file carrying the right token (not a FIFO)
f = tmp / 'tok'; f.write_text(token); fd = os.open(f, os.O_RDONLY)
attempt('regular_file_token', CD.child_config(run, ffmpeg='x', ffprobe='y', lock_fd=5, token_fd=fd, token_sha256=sha))
# 5. forged: own pipe + own commitments, lock guard via the real canonical_lock_guard, no lock held
attempt('forged_pipe_and_commitments_no_lock', CD.child_config(run, ffmpeg='x', ffprobe='y', lock_fd=5,
        token_fd=pipe_with(token), token_sha256=sha))
# 6. forged + KP_GAMESCOPE_REPO_ROOT pointing at a private root whose lock this process holds
fake_root = tmp / 'fake-repo'; (fake_root / 'tmp/harness-locks').mkdir(parents=True); (fake_root / '.git').mkdir()
lock = os.open(fake_root / 'tmp/harness-locks/live-game.lock', os.O_RDWR | os.O_CREAT, 0o600)
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
os.environ['KP_GAMESCOPE_REPO_ROOT'] = str(fake_root)
attempt('forged_pipe_commitments_env_redirected_lock', CD.child_config(run, ffmpeg='x', ffprobe='y', lock_fd=lock,
        token_fd=pipe_with(token), token_sha256=sha))
real_lock = Path(W).parents[1] / 'tmp/harness-locks/live-game.lock'
print('canonical_lock_path_would_be=', CD.canonical_lock_path(), 'exists=', CD.canonical_lock_path().exists())
