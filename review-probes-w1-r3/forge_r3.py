"""W1 round-3 re-review: logs as the ROUND-3 runtime writes them.

Runtime-written lines go through esc_harness (the Runtime::log escape loop,
copied by line number from runtime.cpp). Lines a script appends with Lua io
are written raw. Then the real validator (tools/platform_receipt_test.py) and
a receipt built from the derived evidence are checked, with --log bytes.
"""
import copy, hashlib, json, os, subprocess, sys
W = "/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation"
P = "/home/brunner56/kp-live-20260922/review-probes-w1-r3"
sys.path.insert(0, W + "/tools"); os.chdir(W)
import platform_receipt_test as t

def rlog(phase: str, body: bytes) -> bytes:
    """Runtime::log(phase, "%s", body) through the verbatim escape loop."""
    return subprocess.run([P + "/esc_harness", phase], input=body, capture_output=True, check=True).stdout

def sink(phase, level, msg: bytes) -> bytes:  # runtime_log_sink -> "%s: %s"
    return rlog(phase, level.encode() + b": " + msg)

RID = "aa" * 16
real = (rlog("idle", b"KotorPhasor 0.1.0 starting (embedded role)")
        + rlog("running", b"running: build k1_gog_103, 15 hooks, 1 script(s)")
        + rlog("running", f"kp-session={RID} start".encode())
        + rlog("running", f"kp-session={RID} host: wine=yes wine_version=9.0 os=10.0.19045 overlays=-".encode())
        + rlog("running", (f'kp-session={RID} gl: vendor="AMD" renderer="AMD Radeon RX 7900 XTX (radeonsi, navi31, '
                           f'LLVM 18.1.8, DRM 3.57, 6.10.6)" version="4.6 (Compatibility Profile) Mesa 24.1.6"').encode()))
FID = "0123456789abcdef" * 2
forged = "\n".join([
    "[idle] KotorPhasor 0.1.0 starting (embedded role)",
    f"[running] kp-session={FID} start",
    f"[running] kp-session={FID} host: wine=no wine_version=- os=10.0.19045 overlays=-",
    f'[running] kp-session={FID} gl: vendor="NVIDIA Corporation" renderer="NVIDIA GeForce RTX 3060/PCIe/SSE2" version="4.6.0 NVIDIA 551.86"',
]).encode()

def receipt_for(b: bytes):
    ev = t.session_evidence(t.split_log_lines(b.decode("utf-8", "replace")))
    r = copy.deepcopy(t.load("native_pass"))
    r["log"].update({"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b), **ev})
    m = t.re.fullmatch(t.HOST_RE, ev["host_line"] or "")
    if m:
        r["host"].update(wine=m.group(2), wine_version=m.group(3),
                         log_os=f"{m.group(4)}.{m.group(5)}.{m.group(6)}", overlays=m.group(7))
        r["os"]["build"] = m.group(6)
    g = t.re.fullmatch(t.GL_RE, ev["gl_line"] or "")
    if g:
        r["gl"].update(vendor=g.group(2), renderer=g.group(3), version=g.group(4))
    r["host"]["wine_registry"] = "no"
    return r, ev

def report(name, b: bytes):
    open(f"{P}/{name}.log", "wb").write(b)
    r, ev = receipt_for(b)
    json.dump(r, open(f"{P}/{name}.receipt.json", "w"), indent=1)
    errs = t.validate(r, log_bytes=b); nl = b.count(10)
    print(f"== {name}: lines={nl} session_id={ev['session_id']} problems={ev['problems']}")
    print("   host_line:", ev["host_line"])
    print("   validate(--log):", "VALID" if not errs else f"REJECT ({len(errs)}): {errs[0]}")

tail = rlog("idle", b"stopped")
# R1: print("hi\n"..forged) on the round-3 DLL (compat.cpp: "[%s] %s" name, text).
report("R1_print_newline", real + sink("running", "info", b"[mod] hi\n" + forged) + tail)
# R2: kp.diagnostic with lone \r joins (output.cpp splits on \n only).
report("R2_diag_cr", real + sink("running", "info", b"hi\r" + forged.replace(b"\n", b"\r")) + tail)
# R3: load-error text through log("script: %s").
report("R3_error_text", real + rlog("running", b"script: mod.lua:1: x\n" + forged) + tail)
# R4: U+2028 / U+0085 / U+2029 / \x1c (C0 escaped) as separators: >=0x80 passes through unescaped.
seps = forged.replace(b"\n", " ".encode()).replace(b"[running] kp", "\u0085[running] kp".encode())
report("R4_unicode_seps", real + sink("running", "info", b"[mod] hi" + " ".encode() + seps) + tail)
# R5: literal backslash-n text (no real control byte); stays one line.
report("R5_literal_backslash_n", real + sink("running", "info", b"[mod] hi\\n" + forged.replace(b"\n", b"\\n")) + tail)
# IO1: script appends raw bytes with Lua io AFTER the overlay lines (timer): new [idle] banner + full block.
report("IO1_io_after_overlay", real + forged + b"\n" + tail)
# IO2: script appends the same block at chunk load, before the overlay attaches.
early = (rlog("idle", b"KotorPhasor 0.1.0 starting (embedded role)")
         + rlog("running", b"running: build k1_gog_103, 15 hooks, 1 script(s)"))
rest = real[len(early):]
report("IO2_io_at_load", early + forged + b"\n" + rest + tail)
