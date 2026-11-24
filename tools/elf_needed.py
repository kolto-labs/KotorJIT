#!/usr/bin/env python3
"""Address-preserving ELF32 DT_NEEDED manager for ScriptForge (KPM-style LinkedDependency).

Adds a shared-library dependency (e.g. $ORIGIN/libscriptforge.so) to an ELF32
little-endian executable (such as native Linux KOTOR 2) without changing e_phoff,
any existing PT_LOAD segment, or any .text virtual address or byte.

Mechanism (mirrors KotOR Patch Manager's ElfDependencies):
  1. Repurpose the last PT_NOTE program header into a new PT_LOAD (PF_R | PF_W).
  2. Append a copy of .dynstr + "<soname>\\0" and a relocated .dynamic table
     with the new DT_NEEDED entry inserted before DT_NULL (and updated
     DT_STRTAB / DT_STRSZ) into that new segment at a page-aligned file offset
     and virtual address above all existing PT_LOAD segments.
  3. Point PT_DYNAMIC (and matching SHT_DYNAMIC / .dynstr SHT_STRTAB section
     headers when present) to the new locations.

Subcommands:
  elf_needed.py list  <elf>
  elf_needed.py check <elf> <soname>
  elf_needed.py add   <elf> <soname> [--output <path>] [--backup <path>]
"""
from __future__ import annotations

import argparse
import os
import shutil
import struct
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

EHDR_FMT = "<16sHHIIIIIHHHHHH"
PHDR_FMT = "<IIIIIIII"
SHDR_FMT = "<IIIIIIIIII"
DYN_FMT = "<iI"

EHDR_SIZE = struct.calcsize(EHDR_FMT)
PHDR_SIZE = struct.calcsize(PHDR_FMT)
SHDR_SIZE = struct.calcsize(SHDR_FMT)
DYN_SIZE = struct.calcsize(DYN_FMT)

ET_EXEC = 2
ET_DYN = 3

PT_LOAD = 1
PT_DYNAMIC = 2
PT_NOTE = 4

PF_W = 0x2
PF_R = 0x4

SHT_STRTAB = 3
SHT_DYNAMIC = 6

DT_NULL = 0
DT_NEEDED = 1
DT_STRTAB = 5
DT_STRSZ = 10

PAGE_SIZE = 0x1000


class ElfError(RuntimeError):
    pass


def align_up(value: int, align: int) -> int:
    if align <= 1:
        return value
    return (value + align - 1) // align * align


@dataclass
class ElfHeader:
    e_ident: bytes
    e_type: int
    e_machine: int
    e_version: int
    e_entry: int
    e_phoff: int
    e_shoff: int
    e_flags: int
    e_ehsize: int
    e_phentsize: int
    e_phnum: int
    e_shentsize: int
    e_shnum: int
    e_shstrndx: int


@dataclass
class Phdr:
    p_type: int
    p_offset: int
    p_vaddr: int
    p_paddr: int
    p_filesz: int
    p_memsz: int
    p_flags: int
    p_align: int

    def pack(self) -> bytes:
        return struct.pack(
            PHDR_FMT,
            self.p_type,
            self.p_offset,
            self.p_vaddr,
            self.p_paddr,
            self.p_filesz,
            self.p_memsz,
            self.p_flags,
            self.p_align,
        )


def parse_elf32(data: bytes) -> tuple[ElfHeader, list[Phdr]]:
    if len(data) < EHDR_SIZE:
        raise ElfError("file is smaller than an ELF32 header")
    eh = ElfHeader(*struct.unpack_from(EHDR_FMT, data, 0))
    if eh.e_ident[:6] != b"\x7fELF\x01\x01":
        raise ElfError("not a 32-bit little-endian ELF image")
    if eh.e_type not in (ET_EXEC, ET_DYN):
        raise ElfError(f"unsupported ELF e_type={eh.e_type} (expected ET_EXEC or ET_DYN)")
    if eh.e_phentsize != PHDR_SIZE or eh.e_phnum == 0:
        raise ElfError(f"invalid ELF32 program header table (phentsize={eh.e_phentsize}, phnum={eh.e_phnum})")
    ph_end = eh.e_phoff + eh.e_phnum * PHDR_SIZE
    if ph_end > len(data):
        raise ElfError("program header table extends past end of file")
    phdrs = [
        Phdr(*struct.unpack_from(PHDR_FMT, data, eh.e_phoff + i * PHDR_SIZE))
        for i in range(eh.e_phnum)
    ]
    return eh, phdrs


def vaddr_to_offset(phdrs: list[Phdr], vaddr: int, size: int = 1) -> int:
    for p in phdrs:
        if p.p_type != PT_LOAD or p.p_filesz == 0:
            continue
        if p.p_vaddr <= vaddr and vaddr + size <= p.p_vaddr + p.p_filesz:
            return p.p_offset + (vaddr - p.p_vaddr)
    raise ElfError(f"virtual address 0x{vaddr:08x} (+{size}) is not covered by any PT_LOAD filesz")


def read_dynamic_info(
    data: bytes, phdrs: list[Phdr]
) -> tuple[int, Phdr, list[tuple[int, int]], int, int, bytes]:
    dyn_idx = next((i for i, p in enumerate(phdrs) if p.p_type == PT_DYNAMIC), None)
    if dyn_idx is None:
        raise ElfError("ELF image has no PT_DYNAMIC segment")
    dyn_phdr = phdrs[dyn_idx]
    if dyn_phdr.p_filesz < DYN_SIZE or dyn_phdr.p_offset + dyn_phdr.p_filesz > len(data):
        raise ElfError("PT_DYNAMIC segment is truncated")

    entries: list[tuple[int, int]] = []
    strtab_va = None
    strsz = None
    count = dyn_phdr.p_filesz // DYN_SIZE
    for i in range(count):
        tag, val = struct.unpack_from(DYN_FMT, data, dyn_phdr.p_offset + i * DYN_SIZE)
        entries.append((tag, val))
        if tag == DT_NULL:
            break
        if tag == DT_STRTAB:
            strtab_va = val
        elif tag == DT_STRSZ:
            strsz = val

    if strtab_va is None or strsz is None or strsz == 0:
        raise ElfError("dynamic table lacks DT_STRTAB or DT_STRSZ")
    strtab_off = vaddr_to_offset(phdrs, strtab_va, strsz)
    dynstr = data[strtab_off : strtab_off + strsz]
    return dyn_idx, dyn_phdr, entries, strtab_va, strsz, dynstr


def read_cstr(buf: bytes, offset: int) -> str:
    if offset >= len(buf):
        raise ElfError(f"dynstr offset {offset} out of bounds ({len(buf)})")
    end = buf.find(b"\x00", offset)
    if end == -1:
        end = len(buf)
    return buf[offset:end].decode("utf-8", errors="replace")


def list_needed(data: bytes) -> list[str]:
    _, phdrs = parse_elf32(data)
    _, _, entries, _, _, dynstr = read_dynamic_info(data, phdrs)
    return [read_cstr(dynstr, val) for tag, val in entries if tag == DT_NEEDED]


def add_needed(data: bytes, soname: str) -> tuple[bytes, bool]:
    eh, phdrs = parse_elf32(data)
    dyn_idx, dyn_phdr, entries, strtab_va, strsz, dynstr = read_dynamic_info(data, phdrs)

    existing = [read_cstr(dynstr, val) for tag, val in entries if tag == DT_NEEDED]
    if soname in existing:
        return data, False

    try:
        soname_bytes = soname.encode("ascii") + b"\x00"
    except UnicodeEncodeError as exc:
        raise ElfError(f"soname must be ASCII: {soname!r}") from exc
    if b"\x00" in soname_bytes[:-1]:
        raise ElfError("soname contains NUL byte")

    note_indices = [i for i, p in enumerate(phdrs) if p.p_type == PT_NOTE]
    if not note_indices:
        raise ElfError("no PT_NOTE program header available to repurpose (use --method preload instead)")
    note_idx = note_indices[-1]

    load_ends = [p.p_vaddr + p.p_memsz for p in phdrs if p.p_type == PT_LOAD]
    if not load_ends:
        raise ElfError("no PT_LOAD segments found")

    new_seg_off = align_up(len(data), PAGE_SIZE)
    new_seg_vaddr = align_up(max(load_ends), PAGE_SIZE)

    # Keep all original .dynstr offsets intact so existing DT_NEEDED, .dynsym, and version entries remain valid.
    new_dynstr = bytearray(dynstr)
    if not new_dynstr.endswith(b"\x00"):
        new_dynstr.append(0)
    soname_off = len(new_dynstr)
    new_dynstr.extend(soname_bytes)
    new_strsz = len(new_dynstr)

    dyn_rel_off = align_up(new_strsz, 8)
    new_dyn_off = new_seg_off + dyn_rel_off
    new_dyn_vaddr = new_seg_vaddr + dyn_rel_off

    rebuilt_entries: list[tuple[int, int]] = []
    for tag, val in entries:
        if tag == DT_NULL:
            continue
        if tag == DT_STRTAB:
            rebuilt_entries.append((DT_STRTAB, new_seg_vaddr))
        elif tag == DT_STRSZ:
            rebuilt_entries.append((DT_STRSZ, new_strsz))
        else:
            rebuilt_entries.append((tag, val))
    rebuilt_entries.append((DT_NEEDED, soname_off))
    rebuilt_entries.append((DT_NULL, 0))

    new_dynamic = b"".join(struct.pack(DYN_FMT, tag, val) for tag, val in rebuilt_entries)
    new_seg_size = dyn_rel_off + len(new_dynamic)

    out = bytearray(data)
    if len(out) < new_seg_off:
        out.extend(b"\x00" * (new_seg_off - len(out)))
    out.extend(new_dynstr)
    if dyn_rel_off > new_strsz:
        out.extend(b"\x00" * (dyn_rel_off - new_strsz))
    out.extend(new_dynamic)

    # Update repurposed PT_NOTE -> RW PT_LOAD.
    phdrs[note_idx] = Phdr(
        p_type=PT_LOAD,
        p_offset=new_seg_off,
        p_vaddr=new_seg_vaddr,
        p_paddr=new_seg_vaddr,
        p_filesz=new_seg_size,
        p_memsz=new_seg_size,
        p_flags=PF_R | PF_W,
        p_align=PAGE_SIZE,
    )
    # Point PT_DYNAMIC at the relocated .dynamic.
    phdrs[dyn_idx] = Phdr(
        p_type=PT_DYNAMIC,
        p_offset=new_dyn_off,
        p_vaddr=new_dyn_vaddr,
        p_paddr=new_dyn_vaddr,
        p_filesz=len(new_dynamic),
        p_memsz=len(new_dynamic),
        p_flags=dyn_phdr.p_flags,
        p_align=dyn_phdr.p_align,
    )

    for i, ph in enumerate(phdrs):
        struct.pack_into(PHDR_FMT, out, eh.e_phoff + i * PHDR_SIZE, *struct.unpack(PHDR_FMT, ph.pack()))

    # Keep section headers in sync for readelf -S / -d when present.
    if eh.e_shoff != 0 and eh.e_shentsize >= SHDR_SIZE and eh.e_shnum > 0:
        sh_end = eh.e_shoff + eh.e_shentsize * eh.e_shnum
        if sh_end <= len(data):
            for i in range(eh.e_shnum):
                sh_pos = eh.e_shoff + i * eh.e_shentsize
                sh = list(struct.unpack_from(SHDR_FMT, out, sh_pos))
                sh_type, sh_addr, sh_off = sh[1], sh[3], sh[4]
                if sh_type == SHT_DYNAMIC and (sh_addr == dyn_phdr.p_vaddr or sh_off == dyn_phdr.p_offset):
                    sh[3] = new_dyn_vaddr
                    sh[4] = new_dyn_off
                    sh[5] = len(new_dynamic)
                    struct.pack_into(SHDR_FMT, out, sh_pos, *sh)
                elif sh_type == SHT_STRTAB and sh_addr == strtab_va:
                    sh[3] = new_seg_vaddr
                    sh[4] = new_seg_off
                    sh[5] = new_strsz
                    struct.pack_into(SHDR_FMT, out, sh_pos, *sh)

    return bytes(out), True


def write_atomic(target: Path, payload: bytes, mode: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.tmp.", dir=str(target.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="list DT_NEEDED dependencies")
    p_list.add_argument("elf", type=Path)

    p_check = sub.add_parser("check", help="exit 0 if soname is already in DT_NEEDED")
    p_check.add_argument("elf", type=Path)
    p_check.add_argument("soname")

    p_add = sub.add_parser("add", help="add DT_NEEDED soname preserving all .text VAs")
    p_add.add_argument("elf", type=Path)
    p_add.add_argument("soname")
    p_add.add_argument("--output", type=Path, default=None, help="write patched binary here instead of in-place")
    p_add.add_argument("--backup", type=Path, default=None, help="save original file here first if missing")

    args = ap.parse_args(argv)
    try:
        src = args.elf
        if not src.is_file():
            raise ElfError(f"not a file: {src}")
        raw = src.read_bytes()

        if args.cmd == "list":
            for dep in list_needed(raw):
                print(dep)
            return 0

        if args.cmd == "check":
            deps = list_needed(raw)
            return 0 if args.soname in deps else 1

        if args.cmd == "add":
            patched, changed = add_needed(raw, args.soname)
            dst = args.output if args.output is not None else src
            mode = src.stat().st_mode & 0o7777
            if args.backup is not None and changed and not args.backup.exists():
                args.backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, args.backup)
            if changed or dst != src:
                write_atomic(dst, patched, mode)
            if changed:
                print(f"added DT_NEEDED {args.soname} -> {dst}")
            else:
                print(f"already present: {args.soname} in {dst}")
            return 0
    except ElfError as exc:
        print(f"elf_needed: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
