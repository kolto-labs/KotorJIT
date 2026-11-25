"""Uniform binary loader (PE, ELF, Mach-O) with VA translation and fast masked search."""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

IMAGE_SCN_MEM_EXECUTE = 0x20000000
PF_X = 0x1
S_ATTR_SOME_INSTRUCTIONS = 0x00000400
S_ATTR_PURE_INSTRUCTIONS = 0x80000000


@dataclass(frozen=True)
class SectionView:
    name: str
    va: int
    vsize: int
    file_offset: int
    file_size: int
    executable: bool


class BinaryView:
    """In-memory view of a binary executable or shared library."""

    def __init__(
        self,
        raw: bytes,
        *,
        format_kind: str,
        arch: str,
        bits: int,
        image_base: int,
        sections: Sequence[SectionView],
        path: str = "",
    ) -> None:
        self.raw = raw
        self.format_kind = format_kind  # "pe", "pe64", "elf", "elf64", "macho", "macho64"
        self.arch = arch                # "x86", "x86_64", "arm", "arm64"
        self.bits = bits
        self.image_base = image_base
        self.sections = tuple(sorted(sections, key=lambda s: s.va))
        self.path = path
        self.min_va = min((s.va for s in self.sections if s.vsize > 0), default=image_base)
        self.max_va = max((s.va + s.vsize for s in self.sections if s.vsize > 0), default=image_base)
        self._exec_chunks = tuple(
            (s.va, self.raw[s.file_offset : s.file_offset + min(s.file_size, s.vsize)])
            for s in self.sections
            if s.executable and s.file_size > 0 and s.vsize > 0
        )

    @classmethod
    def from_file(cls, path: str | Path, arch_prefer: str = "x86_64") -> "BinaryView":
        p = Path(path)
        raw = p.read_bytes()
        return cls.from_bytes(raw, path=str(p), arch_prefer=arch_prefer)

    @classmethod
    def from_bytes(cls, raw: bytes, *, path: str = "", arch_prefer: str = "x86_64") -> "BinaryView":
        if raw[:2] == b"MZ":
            return cls._load_pe(raw, path=path)
        if raw[:4] == b"\x7fELF":
            return cls._load_elf(raw, path=path)
        if raw[:4] in (b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
                       b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe"):
            return cls._load_macho(raw, path=path, arch_prefer=arch_prefer)
        raise ValueError(f"Unsupported binary format in {path or '<bytes>'}")

    @classmethod
    def _load_pe(cls, raw: bytes, *, path: str) -> "BinaryView":
        import pefile
        pe = pefile.PE(data=raw, fast_load=True)
        is_64 = pe.FILE_HEADER.Machine == 0x8664 or pe.OPTIONAL_HEADER.Magic == 0x20B
        image_base = int(pe.OPTIONAL_HEADER.ImageBase)
        secs: list[SectionView] = []
        for s in pe.sections:
            name = s.Name.rstrip(b"\x00").decode("utf-8", errors="replace")
            va = image_base + int(s.VirtualAddress)
            vsize = int(s.Misc_VirtualSize) or int(s.SizeOfRawData)
            foff = int(s.PointerToRawData)
            fsize = int(s.SizeOfRawData)
            exec_flag = bool(s.Characteristics & IMAGE_SCN_MEM_EXECUTE) or name.lower().startswith(".text")
            secs.append(SectionView(name, va, vsize, foff, fsize, exec_flag))
        return cls(
            raw,
            format_kind="pe64" if is_64 else "pe",
            arch="x86_64" if is_64 else "x86",
            bits=64 if is_64 else 32,
            image_base=image_base,
            sections=secs,
            path=path,
        )

    @classmethod
    def _load_elf(cls, raw: bytes, *, path: str) -> "BinaryView":
        import io
        from elftools.elf.elffile import ELFFile
        ef = ELFFile(io.BytesIO(raw))
        bits = 64 if ef.elfclass == 64 else 32
        mach = ef["e_machine"]
        arch_map = {
            "EM_386": "x86",
            "EM_X86_64": "x86_64",
            "EM_ARM": "arm",
            "EM_AARCH64": "arm64",
        }
        arch = arch_map.get(mach, "x86_64" if bits == 64 else "x86")
        loads = [seg for seg in ef.iter_segments() if seg["p_type"] == "PT_LOAD"]
        image_base = min((int(seg["p_vaddr"]) for seg in loads), default=0)
        secs: list[SectionView] = []
        for sec in ef.iter_sections():
            sh_addr = int(sec["sh_addr"])
            sh_size = int(sec["sh_size"])
            sh_off = int(sec["sh_offset"])
            sh_flags = int(sec["sh_flags"])
            if sh_addr == 0 or sh_size == 0:
                continue
            exec_flag = bool(sh_flags & 0x4)  # SHF_EXECINSTR
            fsize = 0 if sec["sh_type"] == "SHT_NOBITS" else min(sh_size, max(0, len(raw) - sh_off))
            secs.append(SectionView(sec.name, sh_addr, sh_size, sh_off, fsize, exec_flag))
        return cls(
            raw,
            format_kind="elf64" if bits == 64 else "elf",
            arch=arch,
            bits=bits,
            image_base=image_base,
            sections=secs,
            path=path,
        )

    @classmethod
    def _load_macho(cls, raw: bytes, *, path: str, arch_prefer: str) -> "BinaryView":
        slice_off = 0
        slice_len = len(raw)
        magic_be = struct.unpack_from(">I", raw, 0)[0]
        if magic_be == 0xCAFEBABE:
            nfat = struct.unpack_from(">I", raw, 4)[0]
            want_cputype = 0x01000007 if arch_prefer == "x86_64" else (0x0100000C if arch_prefer == "arm64" else 7)
            chosen = None
            first = None
            for i in range(nfat):
                cputype, _cpusub, offset, size, _align = struct.unpack_from(">IIIII", raw, 8 + i * 20)
                if first is None:
                    first = (offset, size)
                if cputype == want_cputype:
                    chosen = (offset, size)
                    break
            slice_off, slice_len = chosen or first
        data = raw[slice_off : slice_off + slice_len]
        mh_magic = struct.unpack_from("<I", data, 0)[0]
        is_64 = mh_magic == 0xFEEDFACF
        cputype = struct.unpack_from("<I", data, 4)[0]
        ncmds, sizeofcmds = struct.unpack_from("<II", data, 16)
        hdr_size = 32 if is_64 else 28
        arch = "x86_64" if cputype == 0x01000007 else ("arm64" if cputype == 0x0100000C else ("arm" if cputype == 12 else "x86"))
        secs: list[SectionView] = []
        image_base = 0
        pos = hdr_size
        end = min(len(data), hdr_size + sizeofcmds)
        for _ in range(ncmds):
            if pos + 8 > end:
                break
            cmd, cmdsize = struct.unpack_from("<II", data, pos)
            if cmdsize < 8 or pos + cmdsize > end:
                break
            if cmd == 0x19 and cmdsize >= 72:  # LC_SEGMENT_64
                segname = data[pos + 8 : pos + 24].split(b"\x00", 1)[0].decode("ascii", "replace")
                vmaddr, vmsize, fileoff, filesize, _maxp, _initp, nsects, _flags = struct.unpack_from("<QQQQIIII", data, pos + 24)
                if segname == "__TEXT":
                    image_base = vmaddr
                sp = pos + 72
                for _s in range(nsects):
                    if sp + 80 > pos + cmdsize:
                        break
                    sname = data[sp : sp + 16].split(b"\x00", 1)[0].decode("ascii", "replace")
                    s_addr, s_size, s_off, _al, _ro, _nr, s_flags = struct.unpack_from("<QQIIIII", data, sp + 32)
                    exec_flag = bool(s_flags & (S_ATTR_PURE_INSTRUCTIONS | S_ATTR_SOME_INSTRUCTIONS))
                    secs.append(SectionView(sname, s_addr, s_size, slice_off + s_off, min(s_size, max(0, slice_len - s_off)), exec_flag))
                    sp += 80
            elif cmd == 0x01 and cmdsize >= 56:  # LC_SEGMENT
                segname = data[pos + 8 : pos + 24].split(b"\x00", 1)[0].decode("ascii", "replace")
                vmaddr, vmsize, fileoff, filesize, _maxp, _initp, nsects, _flags = struct.unpack_from("<IIIIIIII", data, pos + 24)
                if segname == "__TEXT":
                    image_base = vmaddr
                sp = pos + 56
                for _s in range(nsects):
                    if sp + 68 > pos + cmdsize:
                        break
                    sname = data[sp : sp + 16].split(b"\x00", 1)[0].decode("ascii", "replace")
                    s_addr, s_size, s_off, _al, _ro, _nr, s_flags = struct.unpack_from("<IIIIIII", data, sp + 32)
                    exec_flag = bool(s_flags & (S_ATTR_PURE_INSTRUCTIONS | S_ATTR_SOME_INSTRUCTIONS))
                    secs.append(SectionView(sname, s_addr, s_size, slice_off + s_off, min(s_size, max(0, slice_len - s_off)), exec_flag))
                    sp += 68
            pos += cmdsize
        return cls(
            raw,
            format_kind="macho64" if is_64 else "macho",
            arch=arch,
            bits=64 if is_64 else 32,
            image_base=image_base,
            sections=secs,
            path=path,
        )

    def contains_va(self, va: int) -> bool:
        for s in self.sections:
            if s.va <= va < s.va + s.vsize:
                return True
        return False

    def va_to_offset(self, va: int) -> int | None:
        for s in self.sections:
            if s.va <= va < s.va + s.file_size:
                return s.file_offset + (va - s.va)
        return None

    def read_va(self, va: int, size: int) -> bytes:
        off = self.va_to_offset(va)
        if off is None:
            return b""
        return self.raw[off : off + size]

    def exec_chunks(self) -> tuple[tuple[int, bytes], ...]:
        return self._exec_chunks

    def scan_exact(self, needle: bytes, max_hits: int = 2) -> list[int]:
        if not needle:
            return []
        hits: list[int] = []
        for base_va, buf in self._exec_chunks:
            start = 0
            while True:
                idx = buf.find(needle, start)
                if idx < 0:
                    break
                hits.append(base_va + idx)
                if len(hits) >= max_hits:
                    return hits
                start = idx + 1
        return hits

    def scan_masked(self, value: bytes, mask: bytes, max_hits: int = 2) -> list[int]:
        n = len(value)
        if n == 0 or len(mask) != n or mask[0] != 0xFF:
            return []
        first_byte = value[0]
        checks = tuple((i, value[i], mask[i]) for i in range(1, n) if mask[i] != 0)
        hits: list[int] = []
        for base_va, buf in self._exec_chunks:
            limit = len(buf) - n
            if limit < 0:
                continue
            pos = 0
            while pos <= limit:
                idx = buf.find(first_byte, pos, limit + 1)
                if idx < 0:
                    break
                matched = True
                for i, v, m in checks:
                    if (buf[idx + i] & m) != (v & m):
                        matched = False
                        break
                if matched:
                    hits.append(base_va + idx)
                    if len(hits) >= max_hits:
                        return hits
                pos = idx + 1
        return hits

    def count_masked(self, value: bytes, mask: bytes) -> int:
        return len(self.scan_masked(value, mask, max_hits=2))
