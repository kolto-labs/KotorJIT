#!/usr/bin/env python3
"""Offline tests for scripts/package_kpatch.py (KotorJIT as a KPM DLL-only patch).

Checks the archive against what KPM's loader expects (manifest.toml and a
*hooks.toml at the root, modules under binaries/<platform>_<arch><ext>, no
[[hooks]] so KotorPatcher treats it as DLL-only), and that every build the
manifest advertises is one the runtime itself recognises: a hash the runtime's
build table does not know would let KPM install a patch that then refuses to
start.
"""
from __future__ import annotations

import importlib.util
import re
import shutil
import sys
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package_kpatch", ROOT / "scripts" / "package_kpatch.py")
package_kpatch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package_kpatch)

# KPM's version ids for the builds KotorJIT's tables are keyed by alias.
KPM_ID_FOR_ALIAS = {
    "k1_gog_103": "kotor1_gog_103",
    "k1_steam_103": "kotor1_steam_103",
    "k2_gog_aspyr": "kotor2_gog_aspyr",
    "k2_steam_aspyr": "kotor2_steam_aspyr",
    "k1_mac_steam_x64": "kotor1_steam_aspyr_macos",
    "k2_mac_steam_x64": "kotor2_steam_aspyr_macos",
}


def runtime_build_hashes() -> dict[str, set[str]]:
    """alias -> file SHA-256s the runtime's generated build tables recognise."""
    out: dict[str, set[str]] = {}
    for inc in ("builds.inc", "builds_macho.inc"):
        text = (ROOT / "src" / "generated" / inc).read_text()
        for alias, digest in re.findall(r'\{\s*"([a-z0-9_]+)",\s*"([0-9a-f]{64})"', text):
            out.setdefault(alias, set()).add(digest.upper())
    return out


class Manifest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = tomllib.loads((ROOT / "kpatch" / "manifest.toml").read_text())["patch"]

    def test_shipped_inputs_validate(self) -> None:
        package_kpatch.validate_kpatch_inputs(ROOT / "kpatch" / "manifest.toml", ROOT / "kpatch" / "hooks.toml")

    def test_every_advertised_build_is_one_the_runtime_recognises(self) -> None:
        known = runtime_build_hashes()
        alias_for_kpm = {v: k for k, v in KPM_ID_FOR_ALIAS.items()}
        for kpm_id, digest in self.manifest["supported_versions"].items():
            with self.subTest(kpm_id):
                self.assertIn(kpm_id, alias_for_kpm, f"no KotorJIT build mapped to KPM id {kpm_id}")
                self.assertIn(digest, known.get(alias_for_kpm[kpm_id], set()),
                              f"{kpm_id} hash is not in the runtime's build table")

    def test_version_matches_the_repository(self) -> None:
        self.assertEqual(self.manifest["version"], (ROOT / "VERSION").read_text().strip())


class Validation(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="kpatch_test."))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.hooks = self.tmp / "hooks.toml"
        self.hooks.write_text("# DLL-only\n")

    def manifest(self, body: str) -> Path:
        p = self.tmp / "manifest.toml"
        p.write_text(body)
        return p

    GOOD = ('[patch]\nid="x"\nname="X"\nversion="1"\nauthor="a"\ndescription="desc"\n'
            '[patch.supported_versions]\nkotor1_gog_103="' + "A" * 64 + '"\n')

    def test_good_manifest_passes(self) -> None:
        self.assertEqual(package_kpatch.validate_kpatch_inputs(self.manifest(self.GOOD), self.hooks), {"windows"})

    def test_declared_hooks_are_rejected(self) -> None:
        self.hooks.write_text('[[hooks]]\naddress=0x401000\ntype="simple"\n')
        with self.assertRaises(ValueError):
            package_kpatch.validate_kpatch_inputs(self.manifest(self.GOOD), self.hooks)

    def test_lowercase_or_short_hashes_are_rejected(self) -> None:
        for bad in ("a" * 64, "A" * 63):
            with self.subTest(bad), self.assertRaises(ValueError):
                package_kpatch.validate_kpatch_inputs(
                    self.manifest(self.GOOD.replace("A" * 64, bad)), self.hooks)

    def test_missing_fields_are_rejected(self) -> None:
        for field in ('id="x"\n', 'author="a"\n', 'description="desc"\n', "[patch.supported_versions]\n"):
            with self.subTest(field), self.assertRaises(ValueError):
                package_kpatch.validate_kpatch_inputs(self.manifest(self.GOOD.replace(field, "")), self.hooks)


class Archive(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="kpatch_test."))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.build = self.tmp / "build"
        self.build.mkdir()

    def package(self, *extra: str) -> tuple[int, Path]:
        out = self.tmp / "dist" / "kotorjit.kpatch"
        rc = package_kpatch.main([str(self.build), "--output", str(out),
                                  "--mac-build-dir", str(self.tmp / "no-mac"), *extra])
        return rc, out

    def test_archive_layout_matches_kpm(self) -> None:
        (self.build / "kotorjit.dll").write_bytes(b"MZ windows")
        (self.build / "libkotorjit.so").write_bytes(b"\x7fELF linux")
        rc, out = self.package()
        self.assertEqual(rc, 0)
        with zipfile.ZipFile(out) as z:
            self.assertEqual(sorted(z.namelist()), ["binaries/windows_x86.dll",
                                                    "hooks.toml", "manifest.toml"])
            self.assertEqual(z.read("binaries/windows_x86.dll"), b"MZ windows")
            self.assertEqual(z.read("manifest.toml"), (ROOT / "kpatch" / "manifest.toml").read_bytes())
            self.assertFalse(tomllib.loads(z.read("hooks.toml").decode()).get("hooks"))

    def test_include_linux_adds_linux_binary(self) -> None:
        (self.build / "kotorjit.dll").write_bytes(b"MZ windows")
        (self.build / "libkotorjit.so").write_bytes(b"\x7fELF linux")
        rc, out = self.package("--include-linux")
        self.assertEqual(rc, 0)
        with zipfile.ZipFile(out) as z:
            self.assertEqual(sorted(z.namelist()), ["binaries/linux_x86.so", "binaries/windows_x86.dll",
                                                    "hooks.toml", "manifest.toml"])
            self.assertEqual(z.read("binaries/linux_x86.so"), b"\x7fELF linux")

    def test_missing_declared_platform_binary_fails(self) -> None:
        (self.build / "libkotorjit.so").write_bytes(b"\x7fELF linux")
        rc, out = self.package()
        self.assertNotEqual(rc, 0)
        self.assertFalse(out.exists())

    def test_no_built_runtime_fails_without_writing_an_archive(self) -> None:
        rc, out = self.package()
        self.assertNotEqual(rc, 0)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
