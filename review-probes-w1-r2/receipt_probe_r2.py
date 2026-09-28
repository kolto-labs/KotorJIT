"""Prior R1-R6 re-run against the new validator (anchored kp-session lines)."""
import copy, sys, os
W = "/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation"
sys.path.insert(0, W + "/tools"); os.chdir(W)
import platform_receipt_test as t
base = t.load("native_pass"); sid = base["log"]["session_id"]
def v(name, r): e = t.validate(r); print(f"{name}: {'VALID' if not e else 'REJECT ' + ' | '.join(e[:3])}")
r = copy.deepcopy(base); r["log"]["gl_line"] = f'[running] kp-session={sid} gl: vendor="Mesa" renderer="llvmpipe (LLVM 17.0.6, 256 bits)" version="2.1 Mesa 24.1.0"'; v("R1 gl_line llvmpipe, gl.* says GPU", r)
r = copy.deepcopy(base); r["host"]["log_os"] = "6.1.7601"; r["host"]["overlays"] = "galaxy.dll"; v("R2 host.log_os/overlays disagree", r)
r = copy.deepcopy(base)
r["gl"] = {"vendor":"AMD","renderer":"AMD Radeon RX 7900 XTX (radeonsi, navi31, LLVM 18.1.8, DRM 3.57, 6.10.6)","version":"4.6 (Compatibility Profile) Mesa 24.1.6"}
r["log"]["gl_line"] = f'[running] kp-session={sid} gl: vendor="AMD" renderer="{r["gl"]["renderer"]}" version="{r["gl"]["version"]}"'
v("R3 hidden wine_get_version + Mesa radeonsi", r)
r3b = copy.deepcopy(r); r3b["gl"] = {"vendor":"AMD","renderer":"AMD Radeon RX 7900 XTX","version":"4.6 (Compatibility Profile) Mesa 24.1.6"}
r3b["log"]["gl_line"] = f'[running] kp-session={sid} gl: vendor="AMD" renderer="AMD Radeon RX 7900 XTX" version="4.6 (Compatibility Profile) Mesa 24.1.6"'
v("R3b Mesa only in GL version string (renderer clean)", r3b)
r = copy.deepcopy(base); r["log"]["host_line"] = base["log"]["host_line"] + " [lua] host: wine=yes wine_version=9.0 os=10.0.22631 overlays=-"; v("R4 two host: tokens on one line", r)
r = copy.deepcopy(base); r["game"]["build"] = None; v("R5 build null", r)
r = copy.deepcopy(base); r["runtime"]["install_manifest_sha256"] = None; v("R6 manifest sha null", r)
print("synthetic.log (prior lastmatch input) ->", t.session_evidence(t.split_log_lines(open("/home/brunner56/kp-live-20260922/review-probes-w0w1/synthetic.log").read()))["problems"])
