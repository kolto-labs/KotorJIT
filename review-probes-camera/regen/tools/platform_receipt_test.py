#!/usr/bin/env python3
"""Schema and contract test for native-Windows KotorPhasor receipts.

A receipt is what closes a native platform cell (plan: fan-out F section 3):
OS/build, CPU/translation, container+slice sha, DLL/proxy sha, log hash and
the physical F12 result. Wine never closes a native cell, so a receipt whose
runtime log line says wine=yes is rejected as a native receipt, whatever its
top-level fields claim.

Everything here is offline and synthetic: fixtures in
tools/fixtures/platform-receipts/ carry no retail bytes (exe shas are the
public BuildRecord identities; DLL and log shas are filler).

Since CI has no Windows PowerShell, the test also pins the text contracts the
PowerShell scripts depend on: the receipt script emits every key the validator
requires, its log regexes match the lines the C++ actually formats, and the
installer's exe allowlist names only BuildRecord shas.

    python3 tools/platform_receipt_test.py                  # run tests
    python3 tools/platform_receipt_test.py --validate r.json   # check one receipt
    python3 tools/platform_receipt_test.py --validate r.json --log kotorphasor.log

The installer and parser-parity tests run the real PowerShell under pwsh and
skip without it. From a container, set KP_PWSH="host-cmd pwsh"; KP_SCRATCH
picks where their synthetic game folders go.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tools/fixtures/platform-receipts"
RECEIPT_PS1 = ROOT / "scripts/receipts/windows-native-receipt.ps1"
INSTALL_PS1 = ROOT / "scripts/install/windows/Install-KotorPhasor.ps1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

SCHEMA = "kotorphasor.native-receipt/v1"
REQUIRED = {
    "os": ["family", "product", "version", "build"],
    "cpu": ["arch", "translation"],
    "host": ["wine", "wine_version", "log_os", "overlays", "wine_registry"],
    "game": ["exe_name", "exe_sha256", "container_sha256", "slice_sha256"],
    "runtime": ["kphasor_dll_sha256", "proxy_binkw32_sha256", "real_binkw32_sha256"],
    "gl": ["vendor", "renderer", "version"],
    "log": ["sha256", "bytes", "session_start_line", "session_id", "host_line", "gl_line",
            "session_marker_lines", "host_like_lines", "gl_like_lines", "problems"],
    "f12": ["result", "method", "attested_by"],
}
SHA_FIELDS = [("game", "exe_sha256"), ("game", "container_sha256"), ("game", "slice_sha256"),
              ("runtime", "kphasor_dll_sha256"), ("runtime", "proxy_binkw32_sha256"),
              ("runtime", "real_binkw32_sha256"), ("log", "sha256")]

# kotorphasor.log line shapes. Every line is "[<phase>] <body>" (Runtime::log).
# Lines that come through the platform sink, which is everything a Lua script
# can log (print, kp.diagnostic), read "[<phase>] <level>: <body>". The
# kp-session lines are written by overlay.cpp straight to Runtime::log, so they
# have no level token. The patterns match a whole line (fullmatch here,
# ^...$ with -cmatch in the PS1); test_receipt_regexes_match_python pins them.
BANNER_RE = r"\[[a-z-]+\] KotorPhasor \S+ starting \([a-z-]+ role\)"
SESSION_RE = r"\[[a-z-]+\] kp-session=([0-9a-f]{32}) start"
HOST_RE = (r"\[[a-z-]+\] kp-session=([0-9a-f]{32}) host: wine=(yes|no) wine_version=(\S+)"
           r" os=(\d+)\.(\d+)\.(\d+) overlays=(\S+)")
GL_RE = r'\[[a-z-]+\] kp-session=([0-9a-f]{32}) gl: vendor="([^"]*)" renderer="([^"]*)" version="([^"]*)"'
# Substrings that make a line count as a claim of each kind, anchored or not.
# A script that prints "host: wine=no" adds a second host-like line to the
# session, and a session with more than one is refused.
MARKER, HOST_LIKE, GL_LIKE = "kp-session=", "host: wine=", "gl: vendor="
# A VM without GPU passthrough is not acceptance (plan section 3).
SOFTWARE_RENDERERS = ("llvmpipe", "softpipe", "lavapipe", "microsoft basic render driver",
                      "gdi generic", "swiftshader")
# GL vendor/renderer text that native Windows drivers do not report: Mesa and
# its Linux drivers (what Wine passes through on Linux), Wine itself, macOS
# GL, and VM adapters. The version string is not checked: Microsoft's OpenGL
# compatibility layer on ARM64 Windows is Mesa-based and says so there.
NON_NATIVE_GL = ("mesa", "radeonsi", "r600", "zink", "virgl", "nouveau", "crocus", "gallium",
                 "panfrost", "freedreno", "asahi", "svga3d", "vmware", "virtualbox", "wine",
                 "opengl engine", "apple")
LINUX_DRM = re.compile(r"\bdrm \d")    # "(..., DRM 3.57, 6.10.6)" in Mesa renderers


def split_log_lines(text: str) -> list[str]:
    """Lines as PowerShell Get-Content yields them: split on CRLF, CR or LF."""
    lines = re.split(r"\r\n|\r|\n", text)
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def session_evidence(lines: list[str]) -> dict:
    """What windows-native-receipt.ps1 Get-SessionEvidence records under log.

    The current session is everything after the last runtime start banner.
    Inside it there must be exactly one kp-session start line, one host-like
    line and one gl-like line; every kp-session line must be one of the three
    anchored shapes and carry the start line's id; start comes first. A line
    is only reported when those rules hold, so a spoofed, doubled or stale
    line leaves host_line or gl_line null.
    """
    ev = {"session_start_line": None, "session_id": None, "host_line": None, "gl_line": None,
          "session_marker_lines": 0, "host_like_lines": 0, "gl_like_lines": 0, "problems": []}
    problems = ev["problems"]
    start = None
    for i, line in enumerate(lines):
        if re.fullmatch(BANNER_RE, line):
            start = i
    if start is None:
        problems.append("no KotorPhasor start banner in the log")
        return ev
    ev["session_start_line"] = lines[start]
    session = lines[start + 1:]
    starts, hosts, gls, ids = [], [], [], set()
    for i, line in enumerate(session):
        if MARKER in line:
            ev["session_marker_lines"] += 1
            m = (re.fullmatch(SESSION_RE, line) or re.fullmatch(HOST_RE, line)
                 or re.fullmatch(GL_RE, line))
            if m is None:
                problems.append(f"session line {i + 1} mentions kp-session= but is not a runtime line")
            else:
                ids.add(m.group(1))
            if re.fullmatch(SESSION_RE, line):
                starts.append((i, line))
        if HOST_LIKE in line:
            ev["host_like_lines"] += 1
            hosts.append((i, line))
        if GL_LIKE in line:
            ev["gl_like_lines"] += 1
            gls.append((i, line))
    if len(starts) != 1:
        problems.append(f"{len(starts)} kp-session start lines in the current session, want 1")
    if len(ids) > 1:
        problems.append(f"{len(ids)} different session ids in the current session")
    if len(hosts) != 1:
        problems.append(f"{len(hosts)} host lines in the current session, want 1")
    if len(gls) != 1:
        problems.append(f"{len(gls)} gl lines in the current session, want 1")
    if problems:
        return ev
    (s_i, s_line), (h_i, h_line), (g_i, g_line) = starts[0], hosts[0], gls[0]
    if not re.fullmatch(HOST_RE, h_line):
        problems.append("the host line is not in the runtime's anchored format")
    if not re.fullmatch(GL_RE, g_line):
        problems.append("the gl line is not in the runtime's anchored format")
    if not (s_i < h_i and s_i < g_i):
        problems.append("host or gl line comes before the session start line")
    if problems:
        return ev
    ev["session_id"] = re.fullmatch(SESSION_RE, s_line).group(1)
    ev["host_line"], ev["gl_line"] = h_line, g_line
    return ev


def build_record_shas() -> dict[str, str]:
    text = (ROOT / "src/generated/builds.inc").read_text()
    body = text.split("static const BuildRecord kBuilds[] = {", 1)[1]
    return {sha: alias for alias, sha in
            re.findall(r'\{\s*"(\w+)",\s*"([0-9a-f]{64})",', body)}


def validate(r: dict, records: dict[str, str] | None = None, log_bytes: bytes | None = None) -> list[str]:
    """Reasons this is not a valid native-Windows receipt; empty when valid.

    With log_bytes (the kotorphasor.log the receipt names), the log section is
    re-derived from the log itself and must match; without it the validator
    can only check the receipt against the lines it quotes.
    """
    records = build_record_shas() if records is None else records
    errs: list[str] = []
    if r.get("schema") != SCHEMA:
        errs.append(f"schema is {r.get('schema')!r}, want {SCHEMA!r}")
    if r.get("kind") != "windows-native":
        errs.append(f"kind is {r.get('kind')!r}, want 'windows-native'")
    for section, keys in REQUIRED.items():
        sec = r.get(section)
        if not isinstance(sec, dict):
            errs.append(f"missing section {section}")
            continue
        for k in keys:
            if k not in sec:
                errs.append(f"missing {section}.{k}")
    if errs:
        return errs

    for section, k in SHA_FIELDS:
        v = r[section][k]
        if not isinstance(v, str) or not HEX64.match(v):
            errs.append(f"{section}.{k} is not a lowercase sha256: {v!r}")

    if r["os"]["family"] != "windows":
        errs.append(f"os.family is {r['os']['family']!r}")

    log, host, gl = r["log"], r["host"], r["gl"]
    if log_bytes is not None:
        if hashlib.sha256(log_bytes).hexdigest() != log["sha256"]:
            errs.append("log.sha256 does not match the log given")
        if len(log_bytes) != log["bytes"]:
            errs.append(f"log.bytes {log['bytes']} does not match the log given ({len(log_bytes)})")
        derived = session_evidence(split_log_lines(log_bytes.decode("utf-8", "replace")))
        for k, v in derived.items():
            if log.get(k) != v:
                errs.append(f"log.{k} {log.get(k)!r} does not match the log, which gives {v!r}")

    # The current session: one start, one host, one gl line, one id.
    if log["problems"]:
        for p in log["problems"]:
            errs.append(f"log: {p}")
    for k, want in (("session_marker_lines", 3), ("host_like_lines", 1), ("gl_like_lines", 1)):
        if log[k] != want:
            errs.append(f"log.{k} is {log[k]!r}, want {want}: a line was added, doubled or lost")
    sid = log["session_id"]
    if not (isinstance(sid, str) and re.fullmatch(r"[0-9a-f]{32}", sid)):
        errs.append(f"log.session_id {sid!r} is not a 32-hex runtime session id")
    if not (isinstance(log["session_start_line"], str) and re.fullmatch(BANNER_RE, log["session_start_line"])):
        errs.append("log.session_start_line is not the runtime start banner")

    # Wine: every derived field must equal the anchored runtime line it came from.
    line = log["host_line"]
    m = re.fullmatch(HOST_RE, line) if isinstance(line, str) else None
    if m is None:
        errs.append("log.host_line missing or not in the runtime's anchored format; runtime never reported its host")
    else:
        if m.group(1) != sid:
            errs.append(f"log.host_line session {m.group(1)} is not log.session_id")
        if m.group(2) != "no":
            errs.append("runtime log says wine=yes: a Wine run never closes a native cell")
        if host["wine"] != m.group(2):
            errs.append(f"host.wine={host['wine']!r} disagrees with log line wine={m.group(2)}")
        if host["wine_version"] != m.group(3):
            errs.append(f"host.wine_version {host['wine_version']!r} disagrees with log line {m.group(3)!r}")
        log_os = f"{m.group(4)}.{m.group(5)}.{m.group(6)}"
        if host["log_os"] != log_os:
            errs.append(f"host.log_os {host['log_os']!r} disagrees with log line os={log_os}")
        if host["overlays"] != m.group(7):
            errs.append(f"host.overlays {host['overlays']!r} disagrees with log line overlays={m.group(7)}")
        if str(r["os"]["build"]) != m.group(6):
            errs.append(f"os.build {r['os']['build']} disagrees with RtlGetVersion build {m.group(6)} in log")
        if m.group(2) == "no" and m.group(3) != "-":
            errs.append(f"log line says wine=no but wine_version={m.group(3)}")
        if m.group(7).startswith("snapshot-failed"):
            errs.append(f"overlay scan failed ({m.group(7)}); the module list is unknown, run again")
    if host["wine"] != "no":
        errs.append(f"host.wine is {host['wine']!r}, a native receipt needs 'no'")
    if host["wine_registry"] == "yes":
        errs.append("HKLM\\Software\\Wine exists: the receipt ran inside a Wine prefix")

    g = r["game"]
    if g["exe_sha256"] not in records:
        errs.append(f"game.exe_sha256 {g['exe_sha256']} is not a BuildRecord")
    elif g.get("build") not in (None, records[g["exe_sha256"]]):
        errs.append(f"game.build {g['build']!r} disagrees with BuildRecord {records[g['exe_sha256']]!r}")
    # A PE is one image: container and slice are the exe.
    if not (g["container_sha256"] == g["slice_sha256"] == g["exe_sha256"]):
        errs.append("PE container/slice sha must equal exe sha")

    # GL: the fields must equal the anchored line, and the line must look native.
    gm = re.fullmatch(GL_RE, log["gl_line"]) if isinstance(log["gl_line"], str) else None
    if gm is None:
        errs.append("log.gl_line missing or not in the runtime's anchored format; the overlay never initialised")
    else:
        if gm.group(1) != sid:
            errs.append(f"log.gl_line session {gm.group(1)} is not log.session_id")
        for i, k in enumerate(("vendor", "renderer", "version"), start=2):
            if gl[k] != gm.group(i):
                errs.append(f"gl.{k} {gl[k]!r} disagrees with log line {gm.group(i)!r}")
        vendor, renderer = gm.group(2).lower(), gm.group(3).lower()
        if not renderer:
            errs.append("gl renderer empty; the overlay never initialised")
        elif any(s in renderer for s in SOFTWARE_RENDERERS):
            errs.append(f"software renderer {gm.group(3)!r}: not a real GPU run")
        for field, text in (("vendor", vendor), ("renderer", renderer)):
            hit = next((s for s in NON_NATIVE_GL if s in text), None)
            if hit is None and LINUX_DRM.search(text):
                hit = "DRM <version>"
            if hit:
                errs.append(f"gl {field} {text!r} names {hit!r}: Mesa, Wine, macOS or VM "
                            "graphics, not native Windows evidence")

    f = r["f12"]
    if f["result"] not in ("pass", "fail"):
        errs.append(f"f12.result is {f['result']!r}; a receipt records a physical F12 attempt")
    if f["method"] != "physical-keyboard":
        errs.append(f"f12.method is {f['method']!r}, want 'physical-keyboard'")
    if f["attested_by"] != "user":
        errs.append(f"f12.attested_by is {f['attested_by']!r}, want 'user'")
    return errs


def closes_cell(r: dict) -> bool:
    return not validate(r) and r["f12"]["result"] == "pass"


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8-sig"))


# --------------------------------------------------------------------------


class Receipts(unittest.TestCase):
    def assertRejected(self, name: str, needle: str, log: str | None = None):
        raw = (FIXTURES / "logs" / f"{log}.log").read_bytes() if log else None
        errs = validate(load(name), log_bytes=raw)
        self.assertTrue(any(needle in e for e in errs), f"{name}: {needle!r} not in {errs}")

    def test_native_pass_is_valid_and_closes(self):
        r = load("native_pass")
        self.assertEqual(validate(r), [])
        self.assertTrue(closes_cell(r))

    def test_native_pass_matches_its_log(self):
        # The fixture is what the receipt script writes for logs/native_pass.log,
        # whose earlier Wine session must be ignored.
        raw = (FIXTURES / "logs/native_pass.log").read_bytes()
        self.assertIn(b"wine=yes", raw)
        self.assertEqual(validate(load("native_pass"), log_bytes=raw), [])

    def test_native_fail_is_valid_but_does_not_close(self):
        r = load("native_f12_fail")
        self.assertEqual(validate(r), [])
        self.assertFalse(closes_cell(r))

    def test_arm64_emulation_is_valid_and_says_so(self):
        r = load("native_arm64_emulated")
        self.assertEqual(validate(r), [])
        self.assertEqual(r["cpu"]["translation"], "x86-on-arm64-emulation")

    def test_wine_yes_rejected_as_native(self):
        self.assertRejected("wine_yes", "wine=yes")
        self.assertFalse(closes_cell(load("wine_yes")))

    def test_top_level_no_cannot_override_log_yes(self):
        r = load("wine_disagrees_with_log")
        self.assertEqual(r["host"]["wine"], "no")
        self.assertRejected("wine_disagrees_with_log", "wine=yes")
        self.assertRejected("wine_disagrees_with_log", "disagrees with log line")

    def test_wine_rule_is_load_bearing(self):
        # Red check: with the log line turned to wine=no, the disagreeing
        # fixture passes. The log-line rule is what rejects it.
        r = load("wine_disagrees_with_log")
        r["log"]["host_line"] = r["log"]["host_line"].replace("wine=yes wine_version=9.0",
                                                              "wine=no wine_version=-")
        self.assertEqual(validate(r), [])

    def test_wine_registry_rejected(self):
        self.assertRejected("wine_registry_yes", "HKLM\\Software\\Wine")

    def test_missing_host_line_rejected(self):
        self.assertRejected("no_host_line", "runtime never reported its host")

    def test_missing_field_rejected(self):
        self.assertRejected("missing_field", "missing runtime.kphasor_dll_sha256")

    def test_bad_sha_rejected(self):
        self.assertRejected("bad_sha", "log.sha256 is not a lowercase sha256")

    def test_unknown_exe_rejected(self):
        self.assertRejected("unknown_exe", "is not a BuildRecord")

    def test_f12_not_run_rejected(self):
        self.assertRejected("f12_not_run", "physical F12 attempt")

    def test_software_renderer_rejected(self):
        self.assertRejected("software_renderer", "software renderer")

    def test_os_build_must_match_runtime(self):
        self.assertRejected("os_build_disagrees", "RtlGetVersion build")

    # ---- review I1: spoofed, doubled and stale lines -----------------------

    def test_spoofed_later_host_line_rejected(self):
        r = load("spoofed_later_host_line")
        self.assertIsNone(r["log"]["host_line"])
        self.assertEqual(r["log"]["host_like_lines"], 3)
        self.assertRejected("spoofed_later_host_line", "3 host lines in the current session")
        self.assertRejected("spoofed_later_host_line", "not a runtime line")

    def test_spoofed_log_never_yields_a_wine_no_line(self):
        ev = session_evidence(split_log_lines((FIXTURES / "logs/spoofed_later_host.log").read_text()))
        self.assertIsNone(ev["host_line"])
        self.assertIsNone(ev["gl_line"])

    def test_forged_receipt_caught_against_its_log(self):
        # A receipt edited to look clean passes on its own quoted lines (the
        # validator cannot see a log it is not given) and fails with --log.
        self.assertEqual(validate(load("forged_for_spoofed_log")), [])
        self.assertRejected("forged_for_spoofed_log", "does not match the log", log="spoofed_later_host")

    def test_stale_prior_session_rejected(self):
        # A complete wine=no session earlier in the file is not this run.
        raw = (FIXTURES / "logs/stale_prior_session.log").read_text()
        self.assertIn("host: wine=no", raw)
        r = load("stale_prior_session")
        self.assertIsNone(r["log"]["host_line"])
        self.assertRejected("stale_prior_session", "0 host lines in the current session")

    def test_session_id_mismatch_rejected(self):
        self.assertRejected("session_id_mismatch", "2 different session ids")

    def test_cr_injected_line_counts_twice(self):
        ev = session_evidence(split_log_lines((FIXTURES / "logs/cr_split_host.log").read_text()))
        self.assertEqual(ev["host_like_lines"], 2)
        self.assertIsNone(ev["host_line"])

    def test_log_without_banner_rejected(self):
        ev = session_evidence(split_log_lines((FIXTURES / "logs/no_banner.log").read_text()))
        self.assertEqual(ev["problems"], ["no KotorPhasor start banner in the log"])

    def test_two_host_tokens_on_one_line_rejected(self):
        self.assertRejected("two_host_tokens", "anchored format")

    def test_unanchored_script_line_is_not_a_host_line(self):
        sid = "0" * 32
        for line in (f"[running] info: kp-session={sid} host: wine=no wine_version=- os=10.0.1 overlays=-",
                     f"[running] info: [x] host: wine=no wine_version=- os=10.0.1 overlays=-",
                     f"[running] kp-session={sid} host: wine=no wine_version=- os=10.0.1 overlays=- ",
                     f"x[running] kp-session={sid} host: wine=no wine_version=- os=10.0.1 overlays=-"):
            self.assertIsNone(re.fullmatch(HOST_RE, line), line)

    # ---- review I2: every derived field against its source line -----------

    def test_gl_fields_must_equal_gl_line(self):
        self.assertRejected("gl_line_disagrees", "gl.renderer 'SYNTHETIC GPU' disagrees with log line")

    def test_host_fields_must_equal_host_line(self):
        self.assertRejected("host_fields_disagree", "host.log_os '6.1.7601' disagrees")
        self.assertRejected("host_fields_disagree", "host.overlays 'galaxy.dll' disagrees")

    def test_mesa_renderer_rejected_as_native(self):
        # Review R3: wine=no (hidden export), Mesa radeonsi GL.
        r = load("mesa_renderer")
        self.assertEqual(r["host"]["wine"], "no")
        self.assertRejected("mesa_renderer", "names 'radeonsi'")

    def test_non_native_gl_names(self):
        base = load("native_pass")
        sid = base["log"]["session_id"]
        for vendor, renderer, hit in (
                ("Intel", "Mesa Intel(R) UHD Graphics 620 (KBL GT2)", "mesa"),
                ("AMD", "AMD CAICOS (DRM 2.50.0 / 6.1.0, LLVM 15.0.7)", "DRM <version>"),
                ("Mesa", "zink Vulkan 1.3(NVIDIA GeForce RTX 3060 (NVIDIA_PROPRIETARY))", "mesa"),
                ("Wine", "SYNTHETIC GPU", "wine"),
                ("Apple", "Apple M1", "apple"),
                ("VMware, Inc.", "SVGA3D; build: RELEASE; LLVM;", "svga3d")):
            r = json.loads(json.dumps(base))
            r["log"]["gl_line"] = (f'[running] kp-session={sid} gl: vendor="{vendor}" '
                                   f'renderer="{renderer}" version="4.6"')
            r["gl"] = {"vendor": vendor, "renderer": renderer, "version": "4.6"}
            errs = validate(r)
            self.assertTrue(any(f"names {hit!r}" in e for e in errs), (renderer, errs))

    def test_native_gpu_names_pass(self):
        base = load("native_pass")
        sid = base["log"]["session_id"]
        for vendor, renderer, version in (
                ("NVIDIA Corporation", "NVIDIA GeForce RTX 3060/PCIe/SSE2", "4.6.0 NVIDIA 560.94"),
                ("ATI Technologies Inc.", "AMD Radeon RX 7900 XTX", "4.6.0 Compatibility Profile Context 24.9.1"),
                ("Intel", "Intel(R) Iris(R) Xe Graphics", "4.6.0 - Build 31.0.101.5186")):
            r = json.loads(json.dumps(base))
            r["log"]["gl_line"] = (f'[running] kp-session={sid} gl: vendor="{vendor}" '
                                   f'renderer="{renderer}" version="{version}"')
            r["gl"] = {"vendor": vendor, "renderer": renderer, "version": version}
            self.assertEqual(validate(r), [], renderer)

    def test_overlay_snapshot_failure_rejected(self):
        self.assertRejected("overlay_snapshot_failed", "overlay scan failed")

    def test_bom_prefixed_receipt_validates(self):
        # Windows PowerShell 5.1 writes UTF-8 with a BOM; the CLI must accept it.
        with tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False) as f:
            f.write(b"\xef\xbb\xbf" + (FIXTURES / "native_pass.json").read_bytes())
        try:
            out = subprocess.run([sys.executable, __file__, "--validate", f.name],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        finally:
            Path(f.name).unlink()

    def test_cli_log_option(self):
        ok = subprocess.run([sys.executable, __file__, "--validate", str(FIXTURES / "native_pass.json"),
                             "--log", str(FIXTURES / "logs/native_pass.log")], capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        bad = subprocess.run([sys.executable, __file__, "--validate",
                              str(FIXTURES / "forged_for_spoofed_log.json"),
                              "--log", str(FIXTURES / "logs/spoofed_later_host.log")],
                             capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1, bad.stdout)
        self.assertIn("does not match the log", bad.stdout)

    def test_fixtures_carry_no_unknown_shas(self):
        # Exe shas are public BuildRecord identities; the rest are filler or
        # the shas of the synthetic logs next to them.
        records = build_record_shas()
        logs = {hashlib.sha256(p.read_bytes()).hexdigest() for p in (FIXTURES / "logs").glob("*.log")}
        for p in FIXTURES.glob("*.json"):
            for m in re.findall(r'"([0-9a-f]{64})"', p.read_text()):
                filler = len(set(m)) == 1
                known_bink = m == "2d0ae23a6175dc7b635c402a5e7e9542e923c0d1c376a8c5ef876ca0d5959d23"
                self.assertTrue(m in records or filler or known_bink or m in logs, f"{p.name}: {m}")


class ScriptContracts(unittest.TestCase):
    """What the PowerShell scripts promise, checked as text (no pwsh here)."""

    def setUp(self):
        self.receipt = RECEIPT_PS1.read_text()
        self.install = INSTALL_PS1.read_text()

    def test_receipt_script_emits_every_required_key(self):
        for section, keys in REQUIRED.items():
            self.assertRegex(self.receipt, rf"\b{section}\s*=", f"section {section}")
            for k in keys:
                self.assertRegex(self.receipt, rf"\b{k}\s*=", f"{section}.{k}")
        self.assertIn(f"'{SCHEMA}'", self.receipt)
        self.assertIn("'windows-native'", self.receipt)
        self.assertIn("'physical-keyboard'", self.receipt)

    def test_receipt_regexes_match_python(self):
        for var, py in (("BannerPattern", BANNER_RE), ("SessionPattern", SESSION_RE),
                        ("HostPattern", HOST_RE), ("GlPattern", GL_RE)):
            ps = re.search(rf"\${var} = '([^']+)'", self.receipt).group(1)
            self.assertEqual(ps, "^" + py + "$", var)
        self.assertNotRegex(self.receipt, r"\$(Host|Gl|Session|Banner)Pattern\b[^\n]*[^c]-match\b")
        self.assertIn("-cmatch $HostPattern", self.receipt)

    def _runtime_line(self, body: str) -> str:
        # Runtime::log writes "[<phase>] <body>\n"; pin that wrapper too.
        rt = (ROOT / "src/runtime/runtime.cpp").read_text()
        self.assertIn('std::fprintf(f, "[%s] %s\\n", to_string(phase_), body);', rt)
        return "[%s] %s" % ("running", body)

    def test_cpp_session_host_gl_lines_match_anchored_regexes(self):
        ov = (ROOT / "src/devtools/overlay.cpp").read_text()
        win = (ROOT / "src/platform/platform_win32.cpp").read_text()
        sid = "0123456789abcdef0123456789abcdef"
        start_fmt = re.search(r'log\("(kp-session=%s start)"', ov).group(1)
        host_fmt = re.search(r'log\("(kp-session=%s %s)", session_id\(\), host\)', ov).group(1)
        gl_fmt = re.search(r'"(kp-session=%s gl: vendor=(?:[^"\\]|\\.)*)"', ov).group(1).replace('\\"', '"')
        host_body = re.search(r'"(host: [^"]+)"', win).group(1)
        self.assertIsNotNone(re.fullmatch(SESSION_RE, self._runtime_line(start_fmt % sid)))
        for wine, ver, ov_list in (("no", "-", "-"), ("yes", "9.0", "galaxy64.dll,+3_more"),
                                   ("no", "-", "snapshot-failed:24")):
            line = self._runtime_line(host_fmt % (sid, host_body % (wine, ver, 10, 0, 22631, ov_list)))
            m = re.fullmatch(HOST_RE, line)
            self.assertIsNotNone(m, line)
            self.assertEqual((m.group(1), m.group(2), m.group(6), m.group(7)), (sid, wine, "22631", ov_list))
        line = self._runtime_line(gl_fmt % (sid, "NVIDIA Corporation", "NVIDIA GeForce RTX 3060/PCIe/SSE2",
                                            "4.6.0 NVIDIA 560.94"))
        m = re.fullmatch(GL_RE, line)
        self.assertIsNotNone(m, line)
        self.assertEqual(m.group(3), "NVIDIA GeForce RTX 3060/PCIe/SSE2")

    def test_session_lines_bypass_the_script_log_sink(self):
        # platform::log goes through the sink that adds "<level>: " to every
        # script-visible line; the evidence lines must not.
        ov = (ROOT / "src/devtools/overlay.cpp").read_text()
        body = ov[ov.index("void log_session_start()"):ov.index("BOOL WINAPI swap(HDC dc)")]
        self.assertNotIn("platform::log(", body)
        self.assertEqual(body.count("runtime::Runtime::instance().log("), 3)
        for needle in ("kp-session=", "host: wine=", "gl: vendor="):
            emitters = [p for p in (ROOT / "src").rglob("*.cpp") if needle in p.read_text()]
            want = {"kp-session=": "overlay.cpp", "host: wine=": "platform_win32.cpp",
                    "gl: vendor=": "overlay.cpp"}[needle]
            self.assertEqual([p.name for p in emitters], [want], needle)

    def test_overlay_logs_once_at_imgui_init(self):
        src = (ROOT / "src/devtools/overlay.cpp").read_text()
        self.assertEqual(src.count("log_host_and_gl();"), 1)
        init = src.index("ImGui_ImplOpenGL2_Init();")
        self.assertLess(init, src.index("log_host_and_gl();"))
        self.assertLess(src.index("if (!context) {"), init)
        # The start line: once, when the overlay attaches, before swap is hooked.
        tick = src[src.index("void overlay_tick() {"):]
        self.assertEqual(src.count("log_session_start();"), 1)
        self.assertLess(tick.index("attempted = true;"), tick.index("log_session_start();"))
        self.assertLess(tick.index("log_session_start();"), tick.index('"SwapBuffers"'))

    def test_host_identity_detects_wine_by_export(self):
        src = (ROOT / "src/platform/platform_win32.cpp").read_text()
        self.assertIn('"wine_get_version"', src)
        self.assertIn('"RtlGetVersion"', src)
        for pat in ('"galaxy"', '"overlay"', '"nvspcap"', '"discordhook"', '"rtsshooks"'):
            self.assertIn(pat, src)

    def test_overlay_list_failure_and_overflow_are_explicit(self):
        src = (ROOT / "src/platform/platform_win32.cpp").read_text()
        self.assertIn('"snapshot-failed:%lu"', src)
        self.assertIn("ERROR_BAD_LENGTH", src)
        self.assertIn('"%s+%u_more"', src)

    def test_installer_exe_allowlist_is_build_records(self):
        records = build_record_shas()
        block = re.search(r"\$ExeAllowlist = @\{(.*?)\n\}", self.install, re.S).group(1)
        pairs = re.findall(r"'([0-9a-f]{64})' = '(\w+)'", block)
        self.assertTrue(pairs)
        for sha, alias in pairs:
            self.assertEqual(records.get(sha), alias, sha)
        aliases = {a for _, a in pairs}
        self.assertNotIn("k1_steam_103_unpacked", aliases)

    def test_installer_bink_allowlist_is_hex(self):
        block = re.search(r"\$BinkAllowlist = @\{(.*?)\n\}", self.install, re.S).group(1)
        shas = re.findall(r"'([0-9a-f]+)' =", block)
        self.assertTrue(shas)
        for s in shas:
            self.assertRegex(s, HEX64)

    def test_installer_is_transactional_and_owned_only(self):
        for needle in ("install-manifest.json", "original_sha256", "[array]::Reverse",
                       "rolled back", "left in place", "binkw32_real.dll sha256",
                       "is not a supported build", "Resolve-Owned", "Assert-Manifest"):
            self.assertIn(needle, self.install)
        # Never moves the original Bink; copies it.
        self.assertNotRegex(self.install, r"Move-Item[^\n]*\$Proxy")
        # Every delete goes through a resolved, checked path.
        self.assertNotIn("Join-Path $GameDir $m.backup_dir", self.install)
        self.assertNotIn("Join-Path $GameDir $f.path", self.install)

    def test_installer_registers_proxy_undo_before_copy(self):
        undo = self.install.index("[void]$undo.Add({ Copy-Item -LiteralPath (Join-Path $GameDir $backupFile)")
        copy = self.install.index("Copy-Item -LiteralPath $srcProxy -Destination $Proxy -Force")
        self.assertLess(undo, copy)

    def test_scripts_explain_execution_policy(self):
        for text in (self.install, self.receipt):
            self.assertIn("Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass", text)
            self.assertIn("Unblock-File", text)
        self.assertTrue((ROOT / "docs/user/windows-native-install.md").exists())

    def test_receipt_default_output_is_not_the_game_folder(self):
        self.assertIn("$env:LOCALAPPDATA", self.receipt)
        self.assertNotRegex(self.receipt, r"\$OutFile = Join-Path \$GameDir")

    def test_scripts_avoid_powershell7_only_syntax(self):
        for name, text in (("install", self.install), ("receipt", self.receipt)):
            code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
            for bad in ("??", "?.", " && ", " || ", "-AsHashtable", "-Parallel"):
                self.assertNotIn(bad, code, f"{name}: {bad}")
            self.assertTrue(text.isascii(), f"{name} is not pure ASCII")


class ReceiptParserParity(unittest.TestCase):
    """The PS1 session parser and session_evidence() agree on every fixture log."""

    def test_ps1_parser_matches_python(self):
        pwsh = _pwsh()
        if not pwsh:
            self.skipTest("no pwsh on PATH and KP_PWSH unset")
        text = RECEIPT_PS1.read_text()
        block = text[text.index("# --- BEGIN session parser"):text.index("# --- END session parser")]
        root = Path(tempfile.mkdtemp(prefix="kp-parity-", dir=os.environ.get("KP_SCRATCH")))
        self.addCleanup(shutil.rmtree, root, True)
        (root / "parser.ps1").write_text(block)
        (root / "run.ps1").write_text(
            "param([string]$Parser, [string]$Log)\n"
            "Set-StrictMode -Version 2.0\n$ErrorActionPreference = 'Stop'\n"
            ". $Parser\n"
            "Get-SessionEvidence (Get-Content -LiteralPath $Log) | ConvertTo-Json -Depth 4 -Compress\n")
        logs = sorted((FIXTURES / "logs").glob("*.log"))
        self.assertGreaterEqual(len(logs), 6)
        for log in logs:
            with self.subTest(log.name):
                out = subprocess.run(pwsh + ["-NoProfile", "-NonInteractive", "-File", str(root / "run.ps1"),
                                             "-Parser", str(root / "parser.ps1"), "-Log", str(log)],
                                     capture_output=True, text=True, timeout=120)
                self.assertEqual(out.returncode, 0, out.stderr)
                ps = json.loads(out.stdout)
                py = session_evidence(split_log_lines(log.read_bytes().decode()))
                self.assertEqual(ps, py)


# --------------------------------------------------------------------------
# Installer behaviour: the real script under pwsh, on synthetic game folders.


def _pwsh() -> list[str] | None:
    """KP_PWSH (e.g. "host-cmd pwsh" from a container), else pwsh on PATH."""
    env = os.environ.get("KP_PWSH")
    if env:
        return shlex.split(env)
    found = shutil.which("pwsh")
    return [found] if found else None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class InstallerBehaviour(unittest.TestCase):
    """Uninstall must never delete outside what it installed (review C1).

    Each case installs into <scratch>/games/nest/game, tampers with the
    manifest, and asserts that uninstall refuses and that no file anywhere
    under the scratch root changed. The fake exe and Bink bytes are made here;
    their shas are added to the allowlists of a temp copy of the installer.
    Scratch lives under KP_SCRATCH (default: the system temp dir).
    """

    EXE = b"synthetic swkotor.exe for installer tests\n"
    BINK = b"synthetic original binkw32.dll for installer tests\n"
    DLL = b"synthetic kphasor.dll\n"
    PROXY = b"synthetic proxy that loads kphasor.dll\n"

    def setUp(self):
        self.pwsh = _pwsh()
        if not self.pwsh:
            self.skipTest("no pwsh on PATH and KP_PWSH unset")
        self.root = Path(tempfile.mkdtemp(prefix="kp-install-", dir=os.environ.get("KP_SCRATCH")))
        self.addCleanup(shutil.rmtree, self.root, True)
        src = Path(os.environ.get("KP_INSTALL_PS1", INSTALL_PS1)).read_text()
        src = src.replace("$ExeAllowlist = @{\n",
                          "$ExeAllowlist = @{\n    '%s' = 'k1_gog_103'\n" % _sha(self.EXE), 1)
        src = src.replace("$BinkAllowlist = @{\n",
                          "$BinkAllowlist = @{\n    '%s' = 'test bink'\n" % _sha(self.BINK), 1)
        self.script = self.root / "Install.ps1"
        self.script.write_text(src)
        self.src = self.root / "src"
        self.src.mkdir()
        (self.src / "kphasor.dll").write_bytes(self.DLL)
        (self.src / "binkw32.dll").write_bytes(self.PROXY)
        self.addr = self.root / "addr"
        self.addr.mkdir()
        (self.addr / "k1_gog_103.json").write_text('{"build": "k1_gog_103"}\n')
        (self.addr / "k2_steam_aspyr.json").write_text('{"build": "k2_steam_aspyr"}\n')
        self.fresh()

    def fresh(self):
        games = self.root / "games"
        shutil.rmtree(games, ignore_errors=True)
        self.game = games / "nest" / "game"
        self.game.mkdir(parents=True)
        (self.game / "swkotor.exe").write_bytes(self.EXE)
        (self.game / "binkw32.dll").write_bytes(self.BINK)
        (self.game / "chitin.key").write_bytes(b"data\n")
        (games / "nest" / "sibling-data.txt").write_bytes(b"sibling\n")
        (games / "victim.txt").write_bytes(b"victim\n")
        (games / "victim.dll").write_bytes(b"victim dll\n")

    def run_ps(self, *args: str) -> tuple[int, str]:
        cmd = self.pwsh + ["-NoProfile", "-NonInteractive", "-File", str(self.script),
                           "-GameDir", str(self.game), *args]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return out.returncode, out.stdout + out.stderr

    def install(self):
        rc, out = self.run_ps("-SourceDir", str(self.src), "-AddressDir", str(self.addr))
        self.assertEqual(rc, 0, out)

    def manifest_path(self) -> Path:
        return self.game / "kotorphasor" / "install-manifest.json"

    def edit(self, fn):
        p = self.manifest_path()
        m = json.loads(p.read_text(encoding="utf-8-sig"))
        fn(m)
        p.write_text(json.dumps(m))

    def snapshot(self) -> dict[str, str]:
        games = self.root / "games"
        return {str(p.relative_to(games)): ("dir" if p.is_dir() else _sha(p.read_bytes()))
                for p in sorted(games.rglob("*"))}

    def assert_refused_untouched(self, label: str, mutate):
        self.fresh()
        self.install()
        self.edit(mutate)
        before = self.snapshot()
        rc, out = self.run_ps("-Action", "Uninstall")
        after = self.snapshot()
        self.assertNotEqual(rc, 0, f"{label}: uninstall did not refuse\n{out}")
        self.assertEqual(before, after, f"{label}: files changed\n{out}")

    # ---- review C1: T1, T9 and friends -----------------------------------

    def test_backup_dir_tampering_refused_nothing_deleted(self):
        victim = str(self.root / "games" / "victim.txt")
        cases = {
            "dot (T1)": ".", "dotdot (T9)": "..", "null": None, "empty": "",
            "rooted absolute": str(self.root / "games"), "rooted drive": "C:\\",
            "rooted backslash": "\\kotorphasor\\backup\\20260101T000000Z",
            "../victim": "../victim.txt", "..\\victim": "..\\victim.txt",
            "traversal inside prefix": "kotorphasor/backup/20260101T000000Z/../../..",
            "own dir, no stamp": "kotorphasor/backup", "absolute victim": victim,
            "scripts dir": "kotorphasor/scripts", "stream": "kotorphasor/backup/20260101T000000Z:x",
        }
        for label, value in cases.items():
            with self.subTest(label):
                self.assert_refused_untouched(label, lambda m, v=value: m.__setitem__("backup_dir", v))

    def test_file_path_tampering_refused_nothing_deleted(self):
        games = self.root / "games"
        vsha = _sha((games / "victim.txt").read_bytes())
        cases = {
            "../victim (T2)": "../victim.txt", "..\\victim": "..\\victim.txt",
            "absolute victim": str(games / "victim.txt"), "dot": ".", "empty": "", "null": None,
            "nested traversal": "kotorphasor/../../victim.txt",
        }
        for label, value in cases.items():
            with self.subTest(label):
                self.assert_refused_untouched(label, lambda m, v=value: m["files"].insert(
                    0, {"path": v, "action": "created", "sha256": vsha}))

    def test_backup_file_tampering_refused_nothing_deleted(self):
        cases = {"../victim.dll": "../victim.dll", "..\\victim.dll": "..\\victim.dll",
                 "other folder": "kotorphasor/scripts/binkw32.dll", "null": None}
        for label, value in cases.items():
            with self.subTest(label):
                def mutate(m, v=value):
                    for f in m["files"]:
                        if f["action"] == "replaced":
                            f["backup"] = v
                self.assert_refused_untouched(label, mutate)

    # ---- happy path and the binkw32_real.dll fallback ---------------------

    def test_install_status_uninstall_round_trip(self):
        before = self.snapshot()
        self.install()
        m = json.loads(self.manifest_path().read_text(encoding="utf-8-sig"))
        self.assertRegex(m["backup_dir"], r"^kotorphasor[\\/]backup[\\/]\d{8}T\d{6}Z$")
        tables = sorted(p.name for p in (self.game / "kotorphasor" / "addresses").iterdir())
        self.assertEqual(tables, ["k1_gog_103.json"], "only the detected build's table")
        rc, out = self.run_ps("-Action", "Status")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("changed", out)
        self.assertRegex(out, r"since \d{4}-\d\d-\d\dT")   # a string, not a localized DateTime
        rc, out = self.run_ps("-Action", "Uninstall")
        self.assertEqual(rc, 0, out)
        after = self.snapshot()
        self.assertEqual(after.pop("nest/game/kotorphasor"), "dir")
        self.assertEqual(after.pop("nest/game/kotorphasor/scripts"), "dir")
        self.assertEqual(before, after)

    def test_missing_backup_falls_back_to_verified_real_dll(self):
        # Review T3: the backup folder is gone but binkw32_real.dll is the
        # hash-verified original.
        self.install()
        shutil.rmtree(self.game / "kotorphasor" / "backup")
        rc, out = self.run_ps("-Action", "Uninstall")
        self.assertEqual(rc, 0, out)
        self.assertEqual(_sha((self.game / "binkw32.dll").read_bytes()), _sha(self.BINK))
        self.assertFalse((self.game / "binkw32_real.dll").exists())
        self.assertFalse((self.game / "kphasor.dll").exists())
        self.assertFalse(self.manifest_path().exists())

    def test_missing_backup_and_changed_real_dll_refused(self):
        self.install()
        shutil.rmtree(self.game / "kotorphasor" / "backup")
        (self.game / "binkw32_real.dll").write_bytes(b"not the original\n")
        before = self.snapshot()
        rc, out = self.run_ps("-Action", "Uninstall")
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(before, self.snapshot())

    def test_status_refuses_tampered_manifest(self):
        self.install()
        self.edit(lambda m: m.__setitem__("backup_dir", ".."))
        rc, out = self.run_ps("-Action", "Status")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("backup_dir", out)


if __name__ == "__main__":
    if len(sys.argv) in (3, 5) and sys.argv[1] == "--validate":
        # utf-8-sig: Windows PowerShell 5.1 Set-Content -Encoding UTF8 writes a BOM.
        log_bytes = None
        if len(sys.argv) == 5:
            if sys.argv[3] != "--log":
                sys.exit("usage: --validate receipt.json [--log kotorphasor.log]")
            log_bytes = Path(sys.argv[4]).read_bytes()
        errs = validate(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8-sig")), log_bytes=log_bytes)
        for e in errs:
            print("REJECT", e)
        print("VALID native receipt" if not errs else f"{len(errs)} problem(s)")
        sys.exit(1 if errs else 0)
    unittest.main()
