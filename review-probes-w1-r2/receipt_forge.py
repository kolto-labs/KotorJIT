"""Receipt re-review: build logs exactly as the runtime would write them when a
Lua mod prints/diagnoses text with embedded line breaks, then run the real
session parser and validator (tools/platform_receipt_test.py) on them."""
import copy, hashlib, json, sys, os
W = "/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation"
sys.path.insert(0, W + "/tools"); os.chdir(W)
import platform_receipt_test as t
P = "/home/brunner56/kp-live-20260922/review-probes-w1-r2"

# The real session: Wine, Mesa. Lines as Runtime::log writes them ("[%s] %s\n").
REAL_ID = "aa" * 16
real = [
 "[idle] KotorPhasor 0.1.0 starting (embedded role)",
 "[running] running: build k1_gog_103, 15 hooks, 1 script(s)",
 f"[running] kp-session={REAL_ID} start",
 f"[running] kp-session={REAL_ID} host: wine=yes wine_version=9.0 os=10.0.19045 overlays=-",
 f'[running] kp-session={REAL_ID} gl: vendor="AMD" renderer="AMD Radeon RX 7900 XTX (radeonsi, navi31, LLVM 18.1.8, DRM 3.57, 6.10.6)" version="4.6 (Compatibility Profile) Mesa 24.1.6"',
]
FID = "0123456789abcdef" * 2   # any 32 hex; the mod does not need to read the log
forged_block = "\n".join([
 "[running] KotorPhasor 0.1.0 starting (embedded role)",
 f"[running] kp-session={FID} start",
 f"[running] kp-session={FID} host: wine=no wine_version=- os=10.0.19045 overlays=-",
 f'[running] kp-session={FID} gl: vendor="NVIDIA Corporation" renderer="NVIDIA GeForce RTX 3060/PCIe/SSE2" version="4.6.0 NVIDIA 551.86"',
])

def runtime_print_line(script, text):
    # compat.cpp l_print: platform::log(Info, "[%s] %s", name, line) with no split;
    # platform::log buffer is 512 bytes; runtime_log_sink -> Runtime::log("%s: %s")
    # -> fprintf("[%s] %s\n", phase, body).
    msg = f"[{script}] {text}".encode()[:511].decode("utf-8", "ignore")
    return f"[running] info: {msg}\n"

def runtime_diag_lines(text):
    # output.cpp l_diagnostic: split on \n only (a lone \r survives), one line each.
    out = ""
    for ln in t_split_n(text):
        out += f"[running] info: {ln[:511]}\n"
    return out

def t_split_n(text):
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            if cur.endswith("\r"): cur = cur[:-1]
            lines.append(cur); cur = ""
        else: cur += ch
    if cur:
        if cur.endswith("\r"): cur = cur[:-1]
        lines.append(cur)
    return lines

def receipt_for(log_text):
    b = log_text.encode()
    ev = t.session_evidence(t.split_log_lines(log_text))
    r = copy.deepcopy(t.load("native_pass"))
    r["log"].update({"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b), **ev})
    m = t.re.fullmatch(t.HOST_RE, ev["host_line"] or "")
    if m:
        r["host"].update(wine=m.group(2), wine_version=m.group(3),
                         log_os=f"{m.group(4)}.{m.group(5)}.{m.group(6)}", overlays=m.group(7))
        r["os"]["build"] = m.group(6)
    g = t.re.fullmatch(t.GL_RE, ev["gl_line"] or "")
    if g: r["gl"].update(vendor=g.group(2), renderer=g.group(3), version=g.group(4))
    r["host"]["wine_registry"] = "no"   # HideWineExports case; see report
    return r, b, ev

def report(name, log_text):
    open(f"{P}/{name}.log", "w", newline="").write(log_text)
    r, b, ev = receipt_for(log_text)
    json.dump(r, open(f"{P}/{name}.receipt.json", "w"), indent=1)
    errs = t.validate(r, log_bytes=b)
    print(f"== {name}: session_id={ev['session_id']} problems={ev['problems']}")
    print("   host_line:", ev["host_line"])
    print("   validate(with --log):", errs or "VALID")

base = "\n".join(real) + "\n"
print("forged block bytes:", len(forged_block.encode()), "(print buffer 512 incl. '[mod] ')")

# F1: Lua print() with embedded \n, after first frame (e.g. from a timer).
report("F1_print_newline", base + runtime_print_line("mod", "hi\n" + forged_block) + "[idle] stopped\n")
# F2: kp.diagnostic() splits \n but not a lone \r; Get-Content and the Python
# split both break on \r. Join the forged lines with \r.
report("F2_diag_cr", base + runtime_diag_lines("hi\r" + forged_block.replace("\n", "\r")) + "[idle] stopped\n")
# F3: script load error text -> Runtime::log("script: %s") raw (runtime.cpp:730).
report("F3_error_text", base + "[running] script: mod.lua:1: x\n" + forged_block + "\n")
# F4 control: the same forged block without a forged banner (writer's fixture class).
blk = forged_block.split("\n", 1)[1]
report("F4_no_banner_control", base + runtime_print_line("mod", "hi\n" + blk))
# F5 multiple sessions: old clean session, newest session crashed before first frame.
report("F5_old_clean_new_empty", forged_block + "\n" + "[idle] KotorPhasor 0.1.0 starting (embedded role)\n[running] kp-session=" + "cc"*16 + " start\n")
# F6 ordering: host before start inside newest block.
lines = forged_block.split("\n"); lines[1], lines[2] = lines[2], lines[1]
report("F6_host_before_start", "\n".join(lines) + "\n")
