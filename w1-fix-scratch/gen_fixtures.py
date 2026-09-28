"""One-off: regenerate tools/fixtures/platform-receipts/*.json in the new schema."""
import copy, hashlib, json, sys
from pathlib import Path
sys.path.insert(0, "tools")
import platform_receipt_test as t
F = t.FIXTURES
LOGS = F / "logs"

def from_log(name):
    raw = (LOGS / f"{name}.log").read_bytes()
    ev = t.session_evidence(t.split_log_lines(raw.decode()))
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), **ev}

def derive(r):
    """host and gl fields exactly as the PS1 derives them from the lines."""
    import re
    m = re.fullmatch(t.HOST_RE, r["log"]["host_line"] or "")
    r["host"].update(wine=m and m.group(2), wine_version=m and m.group(3),
                     log_os=m and f"{m.group(4)}.{m.group(5)}.{m.group(6)}", overlays=m and m.group(7))
    g = re.fullmatch(t.GL_RE, r["log"]["gl_line"] or "")
    r["gl"] = {"vendor": g and g.group(2), "renderer": g and g.group(3), "version": g and g.group(4)}
    return r

base = {
  "schema": t.SCHEMA, "kind": "windows-native", "generated_at": "2026-09-27T00:00:00.0000000Z",
  "os": {"family": "windows", "product": "Windows 10 Pro", "display_version": "23H2",
         "version": "10.0", "build": "22631", "ubr": "4317"},
  "cpu": {"arch": "AMD64", "name": "SYNTHETIC CPU", "translation": "none", "detected_by": "IsWow64Process2"},
  "host": {"wine": None, "wine_version": None, "log_os": None, "overlays": None, "wine_registry": "no"},
  "game": {"exe_name": "swkotor.exe",
           "exe_sha256": "9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435",
           "container_sha256": "9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435",
           "slice_sha256": "9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435",
           "build": "k1_gog_103"},
  "runtime": {"kphasor_dll_sha256": "a" * 64, "proxy_binkw32_sha256": "b" * 64,
              "real_binkw32_sha256": "2d0ae23a6175dc7b635c402a5e7e9542e923c0d1c376a8c5ef876ca0d5959d23",
              "install_manifest_sha256": "c" * 64},
  "gl": {}, "log": from_log("native_pass"),
  "f12": {"result": "pass", "method": "physical-keyboard", "attested_by": "user"},
}
derive(base)
out = {}
out["native_pass"] = base
r = copy.deepcopy(base); r["f12"]["result"] = "fail"; out["native_f12_fail"] = r
r = copy.deepcopy(base); r["cpu"].update(arch="ARM64", translation="x86-on-arm64-emulation"); out["native_arm64_emulated"] = r
r = copy.deepcopy(base); r["f12"]["result"] = "not-run"; out["f12_not_run"] = r
r = copy.deepcopy(base); del r["runtime"]["kphasor_dll_sha256"]; out["missing_field"] = r
r = copy.deepcopy(base); r["log"]["sha256"] = "D" * 64; out["bad_sha"] = r
r = copy.deepcopy(base)
for k in ("exe_sha256", "container_sha256", "slice_sha256"): r["game"][k] = "e" * 64
r["game"]["build"] = None; out["unknown_exe"] = r
r = copy.deepcopy(base); r["os"]["build"] = "19045"; out["os_build_disagrees"] = r
r = copy.deepcopy(base); r["host"]["wine_registry"] = "yes"; out["wine_registry_yes"] = r

def with_line(r, kind, line):
    r["log"][kind] = line
    r["log"]["sha256"] = "d" * 64
    return derive(r)
sid = base["log"]["session_id"]
# Runtime line says wine=yes; everything consistent with it.
out["wine_yes"] = with_line(copy.deepcopy(base), "host_line",
    f"[running] kp-session={sid} host: wine=yes wine_version=9.0 os=10.0.22631 overlays=-")
# Top-level fields hand-edited to say no, the line still says yes.
r = copy.deepcopy(out["wine_yes"]); r["host"]["wine"] = "no"; r["host"]["wine_version"] = "-"
out["wine_disagrees_with_log"] = r
out["software_renderer"] = with_line(copy.deepcopy(base), "gl_line",
    f'[running] kp-session={sid} gl: vendor="VMware, Inc." renderer="llvmpipe (LLVM 17.0.6, 256 bits)" version="4.5 (Compatibility Profile) Mesa 24.1.0"')
# R3: Wine with wine_get_version hidden, Mesa radeonsi GL, all fields consistent.
out["mesa_renderer"] = with_line(copy.deepcopy(base), "gl_line",
    f'[running] kp-session={sid} gl: vendor="AMD" renderer="AMD Radeon RX 7900 XTX (radeonsi, navi31, LLVM 18.1.8, DRM 3.57, 6.10.6)" version="4.6 (Compatibility Profile) Mesa 24.1.6"')
# R1: gl_line says llvmpipe, gl.* claims the GPU.
r = copy.deepcopy(out["software_renderer"]); r["gl"] = dict(base["gl"]); out["gl_line_disagrees"] = r
# R2: log_os and overlays hand-edited.
r = copy.deepcopy(base); r["host"]["log_os"] = "6.1.7601"; r["host"]["overlays"] = "galaxy.dll"; out["host_fields_disagree"] = r
out["overlay_snapshot_failed"] = with_line(copy.deepcopy(base), "host_line",
    f"[running] kp-session={sid} host: wine=no wine_version=- os=10.0.22631 overlays=snapshot-failed:24")
# What the receipt script writes for each problem log.
for name in ("spoofed_later_host", "stale_prior_session", "session_id_mismatch"):
    r = copy.deepcopy(base); r["log"] = from_log(name); derive(r)
    out[{"spoofed_later_host": "spoofed_later_host_line"}.get(name, name)] = r
# Hand-forged receipt for the spoofed log: claims a clean anchored wine=no
# line and counts of 1. Only --log (re-deriving from the log) catches it.
r = copy.deepcopy(base)
r["log"]["sha256"] = from_log("spoofed_later_host")["sha256"]
r["log"]["bytes"] = from_log("spoofed_later_host")["bytes"]
out["forged_for_spoofed_log"] = r
# R4: two host tokens on one line.
out["two_host_tokens"] = with_line(copy.deepcopy(base), "host_line",
    f"[running] kp-session={sid} host: wine=no wine_version=- os=10.0.22631 overlays=- [lua] host: wine=yes wine_version=9.0 os=10.0.22631 overlays=-")
# no_host_line: the game never drew a frame in this session.
r = copy.deepcopy(out["stale_prior_session"]); out["no_host_line"] = r

keep = set(out)
for p in F.glob("*.json"):
    if p.stem not in keep: p.unlink(); print("removed", p.name)
for name, r in out.items():
    (F / f"{name}.json").write_text(json.dumps(r, indent=2) + "\n")
print(len(out), "fixtures")
for name, r in sorted(out.items()):
    errs = t.validate(r)
    print(f"{name:28s} {'VALID' if not errs else errs[0][:110]}")
