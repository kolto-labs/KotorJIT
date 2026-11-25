#!/usr/bin/env python3
"""Offline tests for scripts/install_to_game.sh and its --method switch.

Runs the real script against throwaway game directories. Windows game folders
are stand-ins (the files only need the right names and sizes); the native
Linux cases use a real 32-bit executable and a stand-in libscriptforge.so whose
constructor prints a marker, so "the game loads ScriptForge" is checked by
running the game, not by reading the script.

What is pinned, per method:
  proxy    original binkw32.dll saved and restored byte-for-byte
  inject   binkw32.dll never touched; dll + launcher placed and removed
  linked   DT_NEEDED added (the game really loads the library); the
           executable restored byte-for-byte on uninstall
  preload  wrapper launches the game with the library preloaded
  auto     picks proxy for a Windows folder, linked for a native ELF one
and across methods: a second install is refused, a legacy kotorphasor/
folder keeps its scripts, and a pre-rename proxy (naming kphasor.dll) counts
as installed rather than being mistaken for the original Bink.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install_to_game.sh"

LIB_SRC = r"""
#include <stdio.h>
__attribute__((constructor)) static void sf_marker(void) { puts("SFLIB"); fflush(stdout); }
"""
MAIN_SRC = r"""
#include <stdio.h>
int main(void) { puts("MAIN"); return 0; }
"""


def have_m32() -> bool:
    if shutil.which("gcc") is None:
        return False
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "t.c"
        src.write_text("int main(void){return 0;}\n")
        if subprocess.run(["gcc", "-m32", str(src), "-o", str(Path(d) / "t")], capture_output=True).returncode:
            return False
        return subprocess.run([str(Path(d) / "t")]).returncode == 0


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="install_test."))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.game = self.tmp / "game"
        self.game.mkdir()
        self.build = self.tmp / "build"
        self.build.mkdir()

    def run_script(self, *args: str, ok: bool = True) -> subprocess.CompletedProcess:
        r = subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True)
        if ok:
            self.assertEqual(r.returncode, 0, f"{args}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}")
        return r

    def install(self, method: str | None = None, ok: bool = True) -> subprocess.CompletedProcess:
        m = ["--method", method] if method else []
        return self.run_script(*m, "install", str(self.game), str(self.build), ok=ok)

    def status(self) -> str:
        return self.run_script("status", str(self.game)).stdout

    def uninstall(self) -> None:
        self.run_script("uninstall", str(self.game))


class WindowsFolder(Base):
    def setUp(self) -> None:
        super().setUp()
        (self.game / "swkotor.exe").write_bytes(b"MZ" + b"\0" * 1024)
        self.bink = os.urandom(375808)                       # the real codec's size class
        (self.game / "binkw32.dll").write_bytes(self.bink)
        (self.build / "scriptforge.dll").write_bytes(b"MZ runtime")
        (self.build / "binkw32.dll").write_bytes(b"MZ proxy loads scriptforge.dll\0")
        (self.build / "scriptforge-launch.exe").write_bytes(b"MZ launcher")

    def test_proxy_saves_and_restores_the_original_bink(self) -> None:
        self.install("proxy")
        self.assertEqual((self.game / "binkw32_real.dll").read_bytes(), self.bink)
        self.assertEqual((self.game / "binkw32.dll").read_bytes(), (self.build / "binkw32.dll").read_bytes())
        self.assertTrue((self.game / "scriptforge.dll").is_file())
        self.assertTrue((self.game / "scriptforge" / "scripts").is_dir())
        self.assertIn("method: proxy", self.status())
        self.uninstall()
        self.assertEqual((self.game / "binkw32.dll").read_bytes(), self.bink)
        self.assertFalse((self.game / "binkw32_real.dll").exists())
        self.assertFalse((self.game / "scriptforge.dll").exists())
        self.assertIn("not installed", self.status())

    def test_inject_never_touches_bink(self) -> None:
        self.install("inject")
        self.assertEqual((self.game / "binkw32.dll").read_bytes(), self.bink)
        self.assertFalse((self.game / "binkw32_real.dll").exists())
        self.assertTrue((self.game / "scriptforge-launch.exe").is_file())
        self.assertTrue((self.game / "scriptforge.dll").is_file())
        self.assertIn("method: inject", self.status())
        self.uninstall()
        self.assertEqual((self.game / "binkw32.dll").read_bytes(), self.bink)
        self.assertFalse((self.game / "scriptforge-launch.exe").exists())
        self.assertFalse((self.game / "scriptforge.dll").exists())
        self.assertIn("not installed", self.status())

    def test_auto_picks_proxy_for_a_windows_folder(self) -> None:
        self.install()
        self.assertIn("method: proxy", self.status())

    def test_second_install_is_refused(self) -> None:
        for first, second in (("proxy", "inject"), ("inject", "proxy"), ("inject", "inject")):
            with self.subTest(f"{first} then {second}"):
                self.install(first)
                r = self.install(second, ok=False)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("already installed", r.stderr)
                self.uninstall()
                self.assertEqual((self.game / "binkw32.dll").read_bytes(), self.bink)

    def test_legacy_kotorphasor_folder_keeps_its_scripts(self) -> None:
        legacy = self.game / "kotorphasor" / "scripts"
        legacy.mkdir(parents=True)
        (legacy / "mine.lua").write_text("-- player script\n")
        self.install("inject")
        self.assertEqual((self.game / "scriptforge" / "scripts" / "mine.lua").read_text(), "-- player script\n")
        self.assertFalse((self.game / "kotorphasor").exists())

    def test_pre_rename_proxy_counts_as_installed_not_as_the_original(self) -> None:
        # An old install: our proxy (naming kphasor.dll) in place, original saved.
        (self.game / "binkw32_real.dll").write_bytes(self.bink)
        (self.game / "binkw32.dll").write_bytes(b"MZ old proxy loads kphasor.dll\0")
        self.assertIn("method: proxy", self.status())
        r = self.install("proxy", ok=False)
        self.assertIn("already installed", r.stderr)
        self.assertEqual((self.game / "binkw32_real.dll").read_bytes(), self.bink)   # never overwritten
        self.uninstall()
        self.assertEqual((self.game / "binkw32.dll").read_bytes(), self.bink)

    def test_unknown_method_is_rejected(self) -> None:
        r = self.install("sideload", ok=False)
        self.assertEqual(r.returncode, 2)


@unittest.skipUnless(have_m32(), "gcc -m32 (gcc-multilib) not available")
class LinuxFolder(Base):
    def setUp(self) -> None:
        super().setUp()
        (self.tmp / "main.c").write_text(MAIN_SRC)
        (self.tmp / "lib.c").write_text(LIB_SRC)
        for args in (["-no-pie", str(self.tmp / "main.c"), "-o", str(self.game / "KOTOR2")],
                     ["-shared", "-fPIC", str(self.tmp / "lib.c"), "-o", str(self.build / "libscriptforge.so")]):
            r = subprocess.run(["gcc", "-m32", *args], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
        self.exe_bytes = (self.game / "KOTOR2").read_bytes()

    def run_game(self, launcher: Path) -> list[str]:
        env = {k: v for k, v in os.environ.items() if k not in ("LD_PRELOAD", "LD_LIBRARY_PATH")}
        r = subprocess.run([str(launcher)], capture_output=True, text=True, cwd=str(self.tmp), env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.split()

    def test_linked_loads_the_library_and_uninstall_restores_the_binary(self) -> None:
        self.assertEqual(self.run_game(self.game / "KOTOR2"), ["MAIN"])
        self.install("linked")
        self.assertEqual(self.run_game(self.game / "KOTOR2"), ["SFLIB", "MAIN"])
        self.assertIn("method: linked", self.status())
        self.uninstall()
        self.assertEqual((self.game / "KOTOR2").read_bytes(), self.exe_bytes)
        self.assertTrue(os.access(self.game / "KOTOR2", os.X_OK))
        self.assertFalse((self.game / "libscriptforge.so").exists())
        self.assertEqual(self.run_game(self.game / "KOTOR2"), ["MAIN"])

    def test_preload_wrapper_loads_the_library(self) -> None:
        self.install("preload")
        self.assertEqual((self.game / "KOTOR2").read_bytes(), self.exe_bytes)   # binary untouched
        self.assertEqual(self.run_game(self.game / "run-scriptforge.sh"), ["SFLIB", "MAIN"])
        self.assertIn("method: preload", self.status())
        self.uninstall()
        self.assertFalse((self.game / "run-scriptforge.sh").exists())
        self.assertIn("not installed", self.status())

    def test_auto_picks_linked_for_a_native_elf_folder(self) -> None:
        self.install()
        self.assertIn("method: linked", self.status())
        self.assertEqual(self.run_game(self.game / "KOTOR2"), ["SFLIB", "MAIN"])


if __name__ == "__main__":
    unittest.main()
