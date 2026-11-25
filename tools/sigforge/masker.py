"""Instruction-aware relocation/branch masking via Capstone."""
from __future__ import annotations

from dataclasses import dataclass
import capstone
from capstone import x86

from .binary_view import BinaryView


@dataclass(frozen=True)
class MaskedInstruction:
    va: int
    raw: bytes
    mask: bytes
    mnemonic: str
    op_str: str
    is_jmp_rel32: bool = False
    jmp_target: int | None = None
    branch_target: int | None = None


@dataclass(frozen=True)
class MaskedSignature:
    value: bytes
    mask: bytes
    instructions: int

    @property
    def concrete_count(self) -> int:
        return sum(1 for m in self.mask if m == 0xFF)

    @property
    def pattern_hex(self) -> str:
        return self.value.hex()

    @property
    def mask_hex(self) -> str:
        return self.mask.hex()

    @property
    def ida_pattern(self) -> str:
        return " ".join(
            f"{b:02X}" if m == 0xFF else "?"
            for b, m in zip(self.value, self.mask)
        )


def _cs_for(bv: BinaryView) -> capstone.Cs:
    if bv.arch == "x86":
        cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    elif bv.arch == "x86_64":
        cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    elif bv.arch == "arm":
        cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
    elif bv.arch == "arm64":
        cs = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    else:
        raise ValueError(f"Unsupported arch {bv.arch!r}")
    cs.detail = True
    return cs


def _zero_span(mask: bytearray, offset: int, size: int) -> None:
    if offset <= 0 or size <= 0 or offset >= len(mask):
        return
    end = min(len(mask), offset + size)
    for i in range(offset, end):
        mask[i] = 0x00


def _looks_like_address(bv: BinaryView, value: int) -> bool:
    if value <= 0x10000:
        return False
    uval = value & ((1 << bv.bits) - 1)
    if bv.contains_va(uval):
        return True
    # Also treat addresses close to image_base (within 128 MB) as relocatable constants
    return bv.image_base > 0 and bv.image_base <= uval < bv.image_base + 0x08000000


def mask_instructions(
    bv: BinaryView,
    entry_va: int,
    *,
    max_bytes: int = 96,
    func_end_va: int | None = None,
) -> list[MaskedInstruction]:
    """Disassemble up to `max_bytes` from `entry_va` and compute relocation masks."""
    code = bv.read_va(entry_va, max_bytes)
    if not code:
        return []
    cs = _cs_for(bv)
    out: list[MaskedInstruction] = []
    func_end = func_end_va if func_end_va and func_end_va > entry_va else entry_va + 0x400

    for ins in cs.disasm(code, entry_va):
        raw = bytes(ins.bytes)
        mask = bytearray([0xFF] * len(raw))
        is_jmp_rel32 = False
        jmp_target: int | None = None

        if bv.arch in ("x86", "x86_64"):
            is_branch = (
                x86.X86_GRP_CALL in ins.groups
                or x86.X86_GRP_JUMP in ins.groups
                or ins.mnemonic.startswith(("call", "j"))
            )
            branch_target: int | None = None
            if ins.mnemonic == "jmp" and len(raw) == 5 and raw[0] == 0xE9 and ins.operands:
                if ins.operands[0].type == x86.X86_OP_IMM:
                    is_jmp_rel32 = True
                    jmp_target = int(ins.operands[0].imm)

            # Relative/immediate branches and image-based constants
            if getattr(ins, "imm_size", 0) > 0 and getattr(ins, "imm_offset", 0) > 0:
                imm_sz = ins.imm_size
                imm_off = ins.imm_offset
                for op in ins.operands:
                    if op.type == x86.X86_OP_IMM:
                        imm_val = int(op.imm)
                        if is_branch:
                            branch_target = imm_val
                            if imm_sz >= 4 or not (entry_va <= imm_val < func_end):
                                _zero_span(mask, imm_off, imm_sz)
                        elif imm_sz >= 4 and _looks_like_address(bv, imm_val):
                            _zero_span(mask, imm_off, imm_sz)

            # Memory displacements: RIP-relative (x64), absolute [addr], or image-base table [reg*N + addr]
            if getattr(ins, "disp_size", 0) == 4 and getattr(ins, "disp_offset", 0) > 0:
                disp_off = ins.disp_offset
                disp_sz = ins.disp_size
                for op in ins.operands:
                    if op.type == x86.X86_OP_MEM:
                        if op.mem.base == x86.X86_REG_RIP:
                            _zero_span(mask, disp_off, disp_sz)
                        elif op.mem.base == 0 and op.mem.index == 0:
                            # Absolute memory ref (globals, IAT thunks, etc.)
                            _zero_span(mask, disp_off, disp_sz)
                        elif _looks_like_address(bv, int(op.mem.disp)):
                            _zero_span(mask, disp_off, disp_sz)
        elif bv.arch in ("arm", "arm64"):
            branch_target = None
            # Mask 32-bit PC-relative branches if target leaves function
            if len(raw) == 4 and ins.mnemonic.startswith(("b", "bl")):
                if bv.bits == 32:
                    mask[0] = 0xFF
                    mask[1] = 0x00
                    mask[2] = 0x00
                else:
                    # Keep opcode byte 3 (top bits of ARM64 encoding) intact at byte 0?
                    # Little endian: opcode bits are in byte 3, so skip byte 0 requirement only if arch != x86.
                    pass
        else:
            branch_target = None

        out.append(MaskedInstruction(
            va=ins.address,
            raw=raw,
            mask=bytes(mask),
            mnemonic=ins.mnemonic,
            op_str=ins.op_str,
            is_jmp_rel32=is_jmp_rel32,
            jmp_target=jmp_target,
            branch_target=branch_target,
        ))
        # Stop linear disassembly once we hit an unconditional return/jmp past entry if func_end reached
        if func_end_va and ins.address + len(raw) >= func_end_va:
            break
    return out
