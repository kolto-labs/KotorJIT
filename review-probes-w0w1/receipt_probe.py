import copy, json, sys
sys.path.insert(0, "tools")
import platform_receipt_test as t
base = t.load("native_pass")
def v(name, r): print(f"{name}: {t.validate(r) or 'VALID'}")
r = copy.deepcopy(base); r["log"]["gl_line"] = '[info] gl: vendor="Mesa" renderer="llvmpipe (LLVM 17.0.6, 256 bits)" version="2.1 Mesa 24.1.0"'; v("R1 gl_line llvmpipe, gl.renderer says GPU", r)
r = copy.deepcopy(base); r["host"]["log_os"] = "6.1.7601"; r["host"]["overlays"]="galaxy.dll"; v("R2 host.log_os/overlays disagree with host_line", r)
r = copy.deepcopy(base)
r["gl"] = {"vendor":"AMD","renderer":"AMD Radeon RX 7900 XTX (radeonsi, navi31, LLVM 18.1.8, DRM 3.57, 6.10.6)","version":"4.6 (Compatibility Profile) Mesa 24.1.6"}
r["log"]["gl_line"] = '[info] gl: vendor="AMD" renderer="%s" version="%s"' % (r["gl"]["renderer"], r["gl"]["version"])
r["os"]["build"]="19045"; r["log"]["host_line"]="[info] host: wine=no wine_version=- os=10.0.19045 overlays=-"; r["host"]["log_os"]="10.0.19045"
v("R3 Wine w/ hidden wine_get_version (Mesa radeonsi GL, Wine default 10.0.19045)", r)
r = copy.deepcopy(base); r["log"]["host_line"] = "[info] host: wine=no wine_version=- os=10.0.22631 overlays=- [lua] host: wine=yes wine_version=9.0 os=10.0.22631 overlays=-"; v("R4 two host: tokens on one line", r)
r = copy.deepcopy(base); r["game"]["build"] = None; v("R5 build null (no manifest)", r)
r = copy.deepcopy(base); r["runtime"]["install_manifest_sha256"] = None; del r["os"]["ubr"]; v("R6 manifest sha null", r)
