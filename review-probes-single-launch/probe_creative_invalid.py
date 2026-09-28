"""Invalid KP_MAX_BOOT_ATTEMPTS through run_creative with the real LinuxWineCreativeSession.
Lock path redirected to scratch (never the live-game lock); no game, no wine."""
import contextlib, json, os, sys, tempfile
from pathlib import Path
from unittest import mock
W = sys.argv[1]; sys.path.insert(0, W + "/scripts/harness")
from kpharness import creative as C, creative_wine as CW, session as S
root = Path(tempfile.mkdtemp(prefix="kp_creative_probe_"))
source = root/"source"; source.mkdir(); build = root/"build"; build.mkdir()
for n in ("kphasor.dll", "binkw32.dll"): (build/n).write_bytes(n.encode())
script = root/"demo.lua"; script.write_text("priority=1")
route = root/"route.toml"; route.write_text('name="t"\ntarget="k1"\n[settings]\ngame_speed=1.0\n[[step]]\ndo="lua"\ncode="return true"\n')
opts = C.parser().parse_args(["--backend","linux-wine-k1","--script",str(script),"--route",str(route),"--output",str(root/"output")])
events = []
real_lock = C.live_lock
@contextlib.contextmanager
def spy_lock(path):
    with real_lock(path) as s:
        events.append("live_lock ACQUIRED " + str(path)); yield s
    events.append("live_lock released")
class Rec:
    def __init__(self, run_dir, **k): events.append("recorder constructed")
adapter = lambda _: (CW.LinuxWineCreativeSession, Rec, CW.claim_directory, CW.disjoint, CW.source_receipt)
os.environ["KP_MAX_BOOT_ATTEMPTS"] = sys.argv[2]
with mock.patch.object(C.discover,"repo_root",return_value=root), mock.patch.object(C.discover,"data_dir",return_value=source), \
     mock.patch.object(C.discover,"build_dir",return_value=build), mock.patch.object(C,"shared_lock_path",return_value=root/"scratch-live.lock"), \
     mock.patch.object(C,"live_lock",spy_lock), mock.patch("kpharness.session.pids_by_name",return_value=[]), \
     mock.patch.object(C.shutil,"which",return_value="/usr/bin/fake"):
    try:
        C.run_creative(opts, adapter_factory=adapter); err = None
    except BaseException as e:
        err = f"{type(e).__name__}: {e}"
out = root/"output"
print(json.dumps({"raised": err, "events": events,
  "left_on_disk": sorted(str(p.relative_to(root)) for p in out.rglob("*") if p.parent in (out,) or p.parent.parent == out) if out.exists() else []}, indent=1))
