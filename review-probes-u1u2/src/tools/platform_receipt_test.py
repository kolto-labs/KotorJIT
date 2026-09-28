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
"""
from __future__ import annotations

import json
import re
import sys
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
    "host": ["wine", "wine_version", "log_os", "overlays"],
    "game": ["exe_name", "exe_sha256", "container_sha256", "slice_sha256"],
    "runtime": ["kphasor_dll_sha256", "proxy_binkw32_sha256", "real_binkw32_sha256"],
    "gl": ["vendor", "renderer", "version"],
    "log": ["sha256", "bytes", "host_line", "gl_line"],
    "f12": ["result", "method", "attested_by"],
}
SHA_FIELDS = [("game", "exe_sha256"), ("game", "container_sha256"), ("game", "slice_sha256"),
              ("runtime", "kphasor_dll_sha256"), ("runtime", "proxy_binkw32_sha256"),
              ("runtime", "real_binkw32_sha256"), ("log", "sha256")]
# The runtime's own line (platform_win32.cpp format_host_identity).
HOST_RE = r"host: wine=(yes|no) wine_version=(\S+) os=(\d+)\.(\d+)\.(\d+) overlays=(\S+)"
GL_RE = r'gl: vendor="([^"]*)" renderer="([^"]*)" version="([^"]*)"'
# A VM without GPU passthrough is not acceptance (plan section 3).
SOFTWARE_RENDERERS = ("llvmpipe", "softpipe", "microsoft basic render driver",
                      "gdi generic", "swiftshader")


def build_record_shas() -> dict[str, str]:
    text = (ROOT / "src/generated/builds.inc").read_text()
    body = text.split("static const BuildRecord kBuilds[] = {", 1)[1]
    return {sha: alias for alias, sha in
            re.findall(r'\{\s*"(\w+)",\s*"([0-9a-f]{64})",', body)}


def validate(r: dict, records: dict[str, str] | None = None) -> list[str]:
    """Reasons this is not a valid native-Windows receipt; empty when valid."""
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

    # Wine: the top-level field and the runtime's own line must both say no.
    line = r["log"]["host_line"]
    m = re.search(HOST_RE, line) if isinstance(line, str) else None
    if m is None:
        errs.append("log.host_line missing or unparsable; runtime never reported its host")
    else:
        if m.group(1) != "no":
            errs.append("runtime log says wine=yes: a Wine run never closes a native cell")
        if r["host"]["wine"] != m.group(1):
            errs.append(f"host.wine={r['host']['wine']!r} disagrees with log line wine={m.group(1)}")
        log_build = m.group(5)
        if str(r["os"]["build"]) != log_build:
            errs.append(f"os.build {r['os']['build']} disagrees with RtlGetVersion build {log_build} in log")
    if r["host"]["wine"] != "no":
        errs.append(f"host.wine is {r['host']['wine']!r}, a native receipt needs 'no'")

    g = r["game"]
    if g["exe_sha256"] not in records:
        errs.append(f"game.exe_sha256 {g['exe_sha256']} is not a BuildRecord")
    elif g.get("build") not in (None, records[g["exe_sha256"]]):
        errs.append(f"game.build {g['build']!r} disagrees with BuildRecord {records[g['exe_sha256']]!r}")
    # A PE is one image: container and slice are the exe.
    if not (g["container_sha256"] == g["slice_sha256"] == g["exe_sha256"]):
        errs.append("PE container/slice sha must equal exe sha")

    renderer = str(r["gl"]["renderer"] or "").lower()
    if not renderer:
        errs.append("gl.renderer empty; the overlay never initialised")
    elif any(s in renderer for s in SOFTWARE_RENDERERS):
        errs.append(f"software renderer {r['gl']['renderer']!r}: not a real GPU run")

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
    def assertRejected(self, name: str, needle: str):
        errs = validate(load(name))
        self.assertTrue(any(needle in e for e in errs), f"{name}: {needle!r} not in {errs}")

    def test_native_pass_is_valid_and_closes(self):
        r = load("native_pass")
        self.assertEqual(validate(r), [])
        self.assertTrue(closes_cell(r))

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
        # Red check: with the log-line wine rule removed, wine_disagrees_with_log
        # would pass. That is what the rule is for.
        r = load("wine_disagrees_with_log")
        r["log"]["host_line"] = r["log"]["host_line"].replace("wine=yes", "wine=no")
        self.assertEqual(validate(r), [])

    def test_missing_host_line_rejected(self):
        self.assertRejected("no_host_line", "never reported its host")

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

    def test_bom_prefixed_receipt_validates(self):
        # Windows PowerShell 5.1 writes UTF-8 with a BOM; the CLI must accept it.
        import subprocess, tempfile
        with tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False) as f:
            f.write(b"\xef\xbb\xbf" + (FIXTURES / "native_pass.json").read_bytes())
        try:
            out = subprocess.run([sys.executable, __file__, "--validate", f.name],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        finally:
            Path(f.name).unlink()

    def test_fixtures_carry_no_unknown_shas(self):
        # Exe shas in fixtures are public BuildRecord identities or obvious filler.
        records = build_record_shas()
        for p in FIXTURES.glob("*.json"):
            for m in re.findall(r'"([0-9a-f]{64})"', p.read_text()):
                filler = len(set(m)) == 1
                known_bink = m == "2d0ae23a6175dc7b635c402a5e7e9542e923c0d1c376a8c5ef876ca0d5959d23"
                self.assertTrue(m in records or filler or known_bink, f"{p.name}: {m}")


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
        host = re.search(r"\$HostPattern = '([^']+)'", self.receipt).group(1)
        gl = re.search(r"\$GlPattern = '([^']+)'", self.receipt).group(1)
        self.assertEqual(host, HOST_RE)
        self.assertEqual(gl, GL_RE)

    def test_cpp_host_line_matches_regex(self):
        src = (ROOT / "src/platform/platform_win32.cpp").read_text()
        fmt = re.search(r'"(host: [^"]+)"', src).group(1)
        for wine, ver in (("no", "-"), ("yes", "9.0")):
            line = "[info] " + fmt % (wine, ver, 10, 0, 22631, "galaxy64.dll,gameoverlayrenderer.dll")
            m = re.search(HOST_RE, line)
            self.assertIsNotNone(m, line)
            self.assertEqual(m.group(1), wine)
            self.assertEqual(m.group(5), "22631")

    def test_cpp_gl_line_matches_regex(self):
        src = (ROOT / "src/devtools/overlay.cpp").read_text()
        fmt = re.search(r'"(gl: vendor=(?:[^"\\]|\\.)*)"', src).group(1).replace('\\"', '"')
        line = fmt % ("NVIDIA Corporation", "NVIDIA GeForce RTX 3060/PCIe/SSE2", "4.6.0 NVIDIA 560.94")
        m = re.search(GL_RE, line)
        self.assertIsNotNone(m, line)
        self.assertEqual(m.group(2), "NVIDIA GeForce RTX 3060/PCIe/SSE2")

    def test_overlay_logs_once_at_imgui_init(self):
        src = (ROOT / "src/devtools/overlay.cpp").read_text()
        self.assertEqual(src.count("log_host_and_gl();"), 1)
        init = src.index("ImGui_ImplOpenGL2_Init();")
        self.assertLess(init, src.index("log_host_and_gl();"))
        self.assertLess(src.index("if (!context) {"), init)

    def test_host_identity_detects_wine_by_export(self):
        src = (ROOT / "src/platform/platform_win32.cpp").read_text()
        self.assertIn('"wine_get_version"', src)
        self.assertIn('"RtlGetVersion"', src)
        for pat in ('"galaxy"', '"overlay"', '"nvspcap"'):
            self.assertIn(pat, src)

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
                       "is not a supported build"):
            self.assertIn(needle, self.install)
        # Never moves the original Bink; copies it.
        self.assertNotRegex(self.install, r"Move-Item[^\n]*\$Proxy")

    def test_scripts_avoid_powershell7_only_syntax(self):
        for name, text in (("install", self.install), ("receipt", self.receipt)):
            code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
            for bad in ("??", "?.", " && ", " || ", "-AsHashtable", "-Parallel"):
                self.assertNotIn(bad, code, f"{name}: {bad}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--validate":
        # utf-8-sig: Windows PowerShell 5.1 Set-Content -Encoding UTF8 writes a BOM.
        errs = validate(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8-sig")))
        for e in errs:
            print("REJECT", e)
        print("VALID native receipt" if not errs else f"{len(errs)} problem(s)")
        sys.exit(1 if errs else 0)
    unittest.main()
