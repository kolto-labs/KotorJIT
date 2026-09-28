"""Drive real GameSession.boot -> _launch_and_connect -> launch -> connect -> teardown.
Only process spawning, locks, staging and Xvfb are faked. No wine, no game, no lock files."""
import json, os, subprocess, sys, tempfile, time
from pathlib import Path
from unittest import mock
W = sys.argv[1]; mode = sys.argv[2]; env_val = sys.argv[3]
sys.path.insert(0, W + "/scripts/harness")
from kpharness import session as S
spawned = []; real_popen = subprocess.Popen
def fake_popen(cmd, *a, **k):
    spawned.append(list(cmd))
    k.pop("cwd", None)
    return real_popen(["sleep", "0" if mode == "crash" else "30"], *a, **k)
def fake_run(cmd, *a, **k):
    spawned.append(["RUN"] + list(cmd))
    return subprocess.CompletedProcess(cmd, 0, b"", b"")
tmp = Path(tempfile.mkdtemp(prefix="kp_probe_"))
os.environ["KP_MAX_BOOT_ATTEMPTS"] = env_val
S.BOOT_RETRY_SETTLE = 0.0
with mock.patch.object(S.subprocess, "Popen", fake_popen), \
     mock.patch.object(S.subprocess, "run", fake_run), \
     mock.patch.object(S, "pids_by_name", lambda name: []), \
     mock.patch.object(S, "preflight_tmp_write", lambda: None), \
     mock.patch.object(S, "write_runtime_ini", lambda *a, **k: None):
    s = S.GameSession("k1", staged=str(tmp / "stage"), wineprefix=str(tmp / "pfx"), boot_timeout=3.0, log=lambda m: None)
    s.acquire_lock = lambda: None; s.release_lock = lambda: None
    s.release_stage_lock = lambda: None; s.start_xvfb = lambda: None
    def stage(res=None):
        s.run_dir.mkdir(parents=True, exist_ok=True)
        s.game_dir = tmp / "game"; s.game_dir.mkdir(exist_ok=True)
        s._wineprefix.mkdir(parents=True, exist_ok=True); (s._wineprefix / "system.reg").write_text("x")
    s.stage = stage
    s._choose_display = lambda: 999
    t0 = time.time()
    try:
        s.boot(); out = {"raised": None}
    except BaseException as e:
        out = {"raised": type(e).__name__, "reason": getattr(e, "reason", None),
               "launch_count": getattr(e, "launch_count", None),
               "max_boot_attempts": getattr(e, "max_boot_attempts", None),
               "evidence_path": getattr(e, "evidence_path", None)}
    game_launches = [c for c in spawned if c and c[0] != "RUN" and "swkotor.exe" in " ".join(c)]
    ev = Path(s.run_dir) / "boot-attempts.json"
    out.update(mode=mode, env=env_val, elapsed=round(time.time() - t0, 1),
               game_launch_popens=len(game_launches),
               wineserver_k_calls=sum(1 for c in spawned if c[0] == "RUN" and "-k" in c),
               evidence_exists_after_teardown=ev.is_file(),
               session_json_exists=S.GameSession.session_info_path(s.staged).exists(),
               evidence=json.loads(ev.read_text()) if ev.is_file() else None)
    print(json.dumps(out, indent=1, default=str))
