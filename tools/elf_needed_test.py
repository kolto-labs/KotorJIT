#!/usr/bin/env python3
"""Offline tests for tools/elf_needed.py (KPM-style DT_NEEDED linked dependency).

Builds a real 32-bit executable and a shared library whose constructor prints a
marker, patches the executable with elf_needed.py, and runs it. The checks are
on behaviour (the dynamic loader really loads the library) and on the promises
the tool makes: no existing code byte or loadable segment moves, adding twice
is a no-op, and a binary with no PT_NOTE to repurpose is refused.

Needs gcc with -m32 support (gcc-multilib); skips otherwise.
"""
from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import elf_needed  # noqa: E402

LIB_SRC = r"""
#include <stdio.h>
__attribute__((constructor)) static void sf_marker(void) { puts("SFLIB"); fflush(stdout); }
"""
MAIN_SRC = r"""
#include <stdio.h>
int main(void) { puts("MAIN"); return 0; }
"""
LIBNAME = "libsfneeded.so"


def have_m32() -> bool:
    if shutil.which("gcc") is None:
        return False
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "t.c"
        src.write_text("int main(void){return 0;}\n")
        r = subprocess.run(["gcc", "-m32", str(src), "-o", str(Path(d) / "t")], capture_output=True)
        if r.returncode != 0:
            return False
        return subprocess.run([str(Path(d) / "t")]).returncode == 0


def phdrs(data: bytes) -> list[tuple]:
    e_phoff = struct.unpack_from("<I", data, 28)[0]
    e_phentsize, e_phnum = struct.unpack_from("<HH", data, 42)
    return [struct.unpack_from("<IIIIIIII", data, e_phoff + i * e_phentsize) for i in range(e_phnum)]


def section(data: bytes, name: str) -> tuple[int, int]:
    shoff = struct.unpack_from("<I", data, 32)[0]
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", data, 46)
    str_off = struct.unpack_from("<IIIIII", data, shoff + shstrndx * shentsize)[4]
    for i in range(shnum):
        sh = struct.unpack_from("<IIIIII", data, shoff + i * shentsize)
        nm = data[str_off + sh[0]:data.index(b"\0", str_off + sh[0])].decode()
        if nm == name:
            return sh[4], sh[5]
    raise KeyError(name)


@unittest.skipUnless(have_m32(), "gcc -m32 (gcc-multilib) not available")
class ElfNeeded(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="elf_needed_test."))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "lib.c").write_text(LIB_SRC)
        (self.tmp / "main.c").write_text(MAIN_SRC)
        self.cc(["-shared", "-fPIC", str(self.tmp / "lib.c"), "-o", str(self.tmp / LIBNAME)])

    def cc(self, args: list[str]) -> None:
        r = subprocess.run(["gcc", "-m32", "-O1", *args], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def build_exe(self, name: str, *flags: str) -> Path:
        out = self.tmp / name
        self.cc([*flags, str(self.tmp / "main.c"), "-o", str(out)])
        return out

    def run_exe(self, exe: Path, cwd: Path | None = None, libdir: Path | None = None) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env.pop("LD_LIBRARY_PATH", None)
        if libdir is not None:
            env["LD_LIBRARY_PATH"] = str(libdir)
        return subprocess.run([str(exe)], capture_output=True, text=True, cwd=str(cwd or self.tmp), env=env)

    def patch(self, exe: Path, soname: str) -> bytes:
        out, changed = elf_needed.add_needed(exe.read_bytes(), soname)
        self.assertTrue(changed)
        exe.write_bytes(out)
        return out

    # --- behaviour -------------------------------------------------------

    def test_patched_executable_loads_the_library_before_main(self) -> None:
        exe = self.build_exe("app", "-no-pie")
        self.assertEqual(self.run_exe(exe, libdir=self.tmp).stdout.split(), ["MAIN"])
        self.patch(exe, LIBNAME)
        r = self.run_exe(exe, libdir=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), ["SFLIB", "MAIN"])

    def test_origin_soname_resolves_next_to_the_executable_from_any_cwd(self) -> None:
        exe = self.build_exe("app", "-no-pie")
        self.patch(exe, "$ORIGIN/" + LIBNAME)
        elsewhere = Path(tempfile.mkdtemp(prefix="elf_needed_cwd."))
        self.addCleanup(shutil.rmtree, elsewhere, True)
        r = self.run_exe(exe, cwd=elsewhere)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), ["SFLIB", "MAIN"])

    def test_position_independent_executable_also_works(self) -> None:
        exe = self.build_exe("app_pie", "-pie", "-fPIE")
        self.patch(exe, LIBNAME)
        r = self.run_exe(exe, libdir=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), ["SFLIB", "MAIN"])

    # --- promises ----------------------------------------------------------

    def test_no_code_byte_or_existing_load_segment_moves(self) -> None:
        exe = self.build_exe("app", "-no-pie")
        before = exe.read_bytes()
        after = self.patch(exe, LIBNAME)
        t_off, t_size = section(before, ".text")
        self.assertEqual(before[t_off:t_off + t_size], after[t_off:t_off + t_size])
        self.assertEqual(struct.unpack_from("<I", before, 28), struct.unpack_from("<I", after, 28))  # e_phoff
        old_loads = [p for p in phdrs(before) if p[0] == elf_needed.PT_LOAD]
        new_loads = [p for p in phdrs(after) if p[0] == elf_needed.PT_LOAD]
        self.assertEqual(new_loads[:len(old_loads)], old_loads)
        self.assertEqual(len(new_loads), len(old_loads) + 1)

    def test_load_segments_stay_in_ascending_vaddr_order(self) -> None:
        # ELF spec: "Loadable segment entries in the program header table appear
        # in ascending order, sorted on the p_vaddr member."
        exe = self.build_exe("app", "-no-pie")
        after = self.patch(exe, LIBNAME)
        vaddrs = [p[2] for p in phdrs(after) if p[0] == elf_needed.PT_LOAD]
        self.assertEqual(vaddrs, sorted(vaddrs))

    def test_order_holds_when_the_note_comes_before_the_load_segments(self) -> None:
        # The repurposed PT_NOTE may sit anywhere in the table. If it precedes
        # an existing PT_LOAD, leaving the new PT_LOAD in its slot breaks the
        # ascending order the kernel relies on (total_mapping_size takes the
        # first and last PT_LOAD to size a PIE's reservation).
        for name, flags in (("app_exec", ("-no-pie",)), ("app_pie", ("-pie", "-fPIE"))):
            with self.subTest(name):
                exe = self.build_exe(name, *flags)
                data = bytearray(exe.read_bytes())
                e_phoff = struct.unpack_from("<I", data, 28)[0]
                e_phentsize, e_phnum = struct.unpack_from("<HH", data, 42)
                entries = [bytes(data[e_phoff + i * e_phentsize:e_phoff + (i + 1) * e_phentsize])
                           for i in range(e_phnum)]
                types = [struct.unpack_from("<I", e)[0] for e in entries]
                note = max(i for i, t in enumerate(types) if t == elf_needed.PT_NOTE)
                first_load = types.index(elf_needed.PT_LOAD)
                entries.insert(first_load, entries.pop(note))   # NOTE now precedes every PT_LOAD
                data[e_phoff:e_phoff + e_phnum * e_phentsize] = b"".join(entries)
                exe.write_bytes(bytes(data))
                self.assertEqual(self.run_exe(exe, libdir=self.tmp).stdout.split(), ["MAIN"])

                after = self.patch(exe, LIBNAME)
                vaddrs = [p[2] for p in phdrs(after) if p[0] == elf_needed.PT_LOAD]
                self.assertEqual(vaddrs, sorted(vaddrs))
                r = self.run_exe(exe, libdir=self.tmp)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stdout.split(), ["SFLIB", "MAIN"])

    def test_adding_twice_is_a_no_op(self) -> None:
        exe = self.build_exe("app", "-no-pie")
        once = self.patch(exe, LIBNAME)
        twice, changed = elf_needed.add_needed(once, LIBNAME)
        self.assertFalse(changed)
        self.assertEqual(once, twice)
        self.assertEqual(elf_needed.list_needed(once).count(LIBNAME), 1)

    def test_existing_dependencies_are_kept(self) -> None:
        exe = self.build_exe("app", "-no-pie")
        original = elf_needed.list_needed(exe.read_bytes())
        self.assertIn("libc.so.6", original)
        after = self.patch(exe, LIBNAME)
        self.assertEqual(elf_needed.list_needed(after), original + [LIBNAME])

    def test_binary_without_pt_note_is_refused(self) -> None:
        exe = self.build_exe("app", "-no-pie")
        data = bytearray(exe.read_bytes())
        e_phoff = struct.unpack_from("<I", data, 28)[0]
        e_phentsize, e_phnum = struct.unpack_from("<HH", data, 42)
        for i in range(e_phnum):
            off = e_phoff + i * e_phentsize
            if struct.unpack_from("<I", data, off)[0] == elf_needed.PT_NOTE:
                struct.pack_into("<I", data, off, 0x6474E551)  # PT_GNU_STACK: harmless, not a NOTE
        with self.assertRaises(elf_needed.ElfError):
            elf_needed.add_needed(bytes(data), LIBNAME)

    # --- command line ------------------------------------------------------

    def test_cli_add_check_list_and_backup(self) -> None:
        exe = self.build_exe("app", "-no-pie")
        original = exe.read_bytes()
        tool = [sys.executable, str(ROOT / "tools" / "elf_needed.py")]
        backup = self.tmp / "app.orig"
        self.assertNotEqual(subprocess.run([*tool, "check", str(exe), LIBNAME]).returncode, 0)
        r = subprocess.run([*tool, "add", str(exe), LIBNAME, "--backup", str(backup)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(backup.read_bytes(), original)
        self.assertEqual(subprocess.run([*tool, "check", str(exe), LIBNAME]).returncode, 0)
        listed = subprocess.run([*tool, "list", str(exe)], capture_output=True, text=True).stdout
        self.assertIn(LIBNAME, listed)
        self.assertTrue(os.access(exe, os.X_OK))
        self.assertEqual(self.run_exe(exe, libdir=self.tmp).stdout.split(), ["SFLIB", "MAIN"])


if __name__ == "__main__":
    unittest.main()
