"""Signature synthesis: unique masked patterns, thunk xref locators, field offsets, unification."""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import capstone
from capstone import x86

from .binary_view import BinaryView
from .masker import MaskedInstruction, MaskedSignature, mask_instructions


@dataclass(frozen=True)
class SignatureResult:
    kind: str                 # "pattern" | "xref_thunk" | "unresolved"
    pattern: str = ""         # lowercase hex bytes
    mask: str = ""            # lowercase hex 0xFF/0x00 mask
    concrete_bytes: int = 0
    total_bytes: int = 0
    hit_count: int = 0
    target_pattern: str = ""  # xref_thunk only
    target_mask: str = ""     # xref_thunk only
    thunk_prefix: str = ""    # bytes before opcode (E8/E9)
    thunk_suffix: str = ""    # optional bytes after rel32
    thunk_opcode: str = "e9"  # "e9" (jmp rel32) or "e8" (call rel32)
    reason: str = ""          # non-empty if unresolved or note


@dataclass(frozen=True)
class FieldExtraction:
    offset: int
    size: int
    base_reg: str
    insn_va: int
    mnemonic: str
    op_str: str


def _valid_for_scanner(val: bytes, mask: bytes) -> bool:
    if not val or len(val) != len(mask) or mask[0] != 0xFF:
        return False
    concrete = sum(1 for m in mask if m == 0xFF)
    return concrete * 2 >= len(val)


def _join_instructions(insns: Sequence[MaskedInstruction]) -> tuple[bytes, bytes]:
    val = b"".join(i.raw for i in insns)
    msk = b"".join(i.mask for i in insns)
    return val, msk


def synthesize_unique(
    bv: BinaryView,
    entry_va: int,
    *,
    min_bytes: int = 12,
    max_bytes: int = 256,
    func_size: int | None = None,
    allow_thunk_xref: bool = True,
    _depth: int = 0,
) -> SignatureResult:
    """Synthesize the shortest strictly-unique (count == 1) signature starting at `entry_va`."""
    func_end = (entry_va + func_size) if (func_size and func_size > 0) else None
    insns = mask_instructions(bv, entry_va, max_bytes=max_bytes, func_end_va=func_end)
    if not insns:
        return SignatureResult(kind="unresolved", reason="unreadable_or_unparseable_code")

    # Detect tail-jmp or short call-forwarder candidates before true function exit.
    # Track the furthest forward branch target so an early guard return
    # (`test eax, eax; jg cont; xor eax, eax; ret; cont: ...`) does NOT
    # prematurely truncate signature growth or xref_thunk collection.
    thunk_candidates: list[tuple[int, bytes, int, int, bytes]] = []  # (opcode, prefix, call_off, target_va, ins_idx)
    acc_bytes = bytearray()
    acc_mask = bytearray()
    terminated = False
    max_fwd_target = entry_va
    bit_mask = (1 << bv.bits) - 1

    for idx, ins in enumerate(insns):
        if ins.mnemonic.startswith("j") and ins.mnemonic != "jmp" and ins.branch_target is not None:
            if entry_va < ins.branch_target < entry_va + max_bytes:
                if ins.branch_target > max_fwd_target:
                    max_fwd_target = ins.branch_target

        if ins.is_jmp_rel32 and ins.jmp_target is not None and idx <= 8:
            thunk_candidates.append((0xE9, bytes(acc_bytes), len(acc_bytes), ins.jmp_target, idx))
        elif (
            ins.mnemonic == "call"
            and len(ins.raw) == 5
            and ins.raw[0] == 0xE8
            and idx <= 16
        ):
            target_val = ins.va + 5 + struct.unpack_from("<i", ins.raw, 1)[0]
            thunk_candidates.append((0xE8, bytes(acc_bytes), len(acc_bytes), target_val & bit_mask, idx))

        # Stop before inter-function padding once past every known branch target.
        if ins.va >= max_fwd_target and ins.mnemonic in ("int3", "nop") and idx > 0 and insns[idx - 1].mnemonic in ("ret", "jmp", "int3", "nop"):
            terminated = True
            break

        acc_bytes.extend(ins.raw)
        acc_mask.extend(ins.mask)
        is_exit = ins.mnemonic == "ret" or (ins.mnemonic == "jmp" and len(acc_bytes) <= (func_size or 64))
        if is_exit and (ins.va >= max_fwd_target):
            terminated = True

        total = len(acc_bytes)
        if total >= min_bytes and _valid_for_scanner(acc_bytes, acc_mask):
            val_b = bytes(acc_bytes)
            msk_b = bytes(acc_mask)
            hits = bv.scan_masked(val_b, msk_b, max_hits=2)
            if len(hits) == 1 and hits[0] == entry_va:
                return SignatureResult(
                    kind="pattern",
                    pattern=val_b.hex(),
                    mask=msk_b.hex(),
                    concrete_bytes=sum(1 for m in msk_b if m == 0xFF),
                    total_bytes=total,
                    hit_count=1,
                )
        if terminated:
            break

    # Even if function is shorter than min_bytes (no tail jmp), check exact unique bytes if valid
    if acc_bytes and _valid_for_scanner(acc_bytes, acc_mask):
        val_b = bytes(acc_bytes)
        msk_b = bytes(acc_mask)
        hits = bv.scan_masked(val_b, msk_b, max_hits=2)
        if len(hits) == 1 and hits[0] == entry_va and len(val_b) >= 5:
            return SignatureResult(
                kind="pattern",
                pattern=val_b.hex(),
                mask=msk_b.hex(),
                concrete_bytes=sum(1 for m in msk_b if m == 0xFF),
                total_bytes=len(val_b),
                hit_count=1,
            )

    # Try E9 tail-jump or E8 call-forwarder xref resolution (prefer tail-jmp or last unique E8 callee)
    if allow_thunk_xref and _depth == 0 and thunk_candidates:
        ordered = sorted(thunk_candidates, key=lambda c: (0 if c[0] == 0xE9 else 1, -c[2]))
        for opcode, prefix_b, _call_off, t_va, ins_idx in ordered:
            if not bv.contains_va(t_va) or t_va == entry_va:
                continue
            target_sig = synthesize_unique(
                bv, t_va, min_bytes=min_bytes, max_bytes=max_bytes,
                allow_thunk_xref=False, _depth=1,
            )
            if target_sig.kind != "pattern":
                continue
            suffix_b = b""
            if opcode == 0xE8 and ins_idx + 1 < len(insns):
                # Short deterministic epilogue suffix (up to 8 bytes or until ret)
                suf = bytearray()
                for s_ins in insns[ins_idx + 1:]:
                    if s_ins.mask != b"\xFF" * len(s_ins.raw):
                        break
                    suf.extend(s_ins.raw)
                    if s_ins.mnemonic == "ret" or len(suf) >= 8:
                        break
                suffix_b = bytes(suf)
            matched = _find_unique_thunk_to(bv, opcode, prefix_b, suffix_b, t_va)
            if matched != entry_va and suffix_b:
                matched = _find_unique_thunk_to(bv, opcode, prefix_b, b"", t_va)
                suffix_b = b""
            if matched == entry_va:
                return SignatureResult(
                    kind="xref_thunk",
                    target_pattern=target_sig.pattern,
                    target_mask=target_sig.mask,
                    thunk_prefix=prefix_b.hex(),
                    thunk_suffix=suffix_b.hex(),
                    thunk_opcode=f"{opcode:02x}",
                    concrete_bytes=len(prefix_b) + 1 + len(suffix_b) + target_sig.concrete_bytes,
                    total_bytes=len(prefix_b) + 5 + len(suffix_b),
                    hit_count=1,
                    reason="tail_jmp_thunk" if opcode == 0xE9 else "call_forwarder_xref",
                )

    hit_count = bv.count_masked(bytes(acc_bytes), bytes(acc_mask)) if _valid_for_scanner(acc_bytes, acc_mask) else 0
    why = "ambiguous_pattern" if hit_count > 1 else ("short_stub_non_unique" if terminated else "no_unique_pattern_within_budget")
    return SignatureResult(
        kind="unresolved",
        concrete_bytes=sum(1 for m in acc_mask if m == 0xFF),
        total_bytes=len(acc_bytes),
        hit_count=hit_count,
        reason=why,
    )


def _find_unique_thunk_to(
    bv: BinaryView,
    opcode: int,
    prefix: bytes,
    suffix: bytes,
    target_va: int,
) -> int | None:
    """Return unique VA where bytes equal `prefix + opcode + rel32(target_va) + suffix`, else None."""
    hits: list[int] = []
    plen = len(prefix)
    slen = len(suffix)
    for base_va, buf in bv.exec_chunks():
        pos = 0
        limit = len(buf) - (plen + 5 + slen)
        while pos <= limit:
            if plen > 0:
                idx = buf.find(prefix, pos, limit + 1)
            else:
                idx = buf.find(opcode, pos, limit + 1)
            if idx < 0:
                break
            op_off = idx + plen
            if buf[op_off] == opcode:
                if slen == 0 or buf[op_off + 5 : op_off + 5 + slen] == suffix:
                    rel32 = struct.unpack_from("<i", buf, op_off + 1)[0]
                    insn_va = base_va + op_off
                    dst = (insn_va + 5 + rel32) & ((1 << bv.bits) - 1)
                    if dst == target_va:
                        hits.append(base_va + idx)
                        if len(hits) > 1:
                            return None
            pos = idx + 1
    return hits[0] if len(hits) == 1 else None


def extract_field_offset(
    bv: BinaryView,
    accessor_va: int,
    *,
    max_bytes: int = 96,
    base_reg: str | None = None,
    min_disp: int = 1,
    max_disp: int = 0x4000,
    occurrence: int = 0,
) -> FieldExtraction | None:
    """Extract a struct displacement operand from a uniquely verified accessor function."""
    code = bv.read_va(accessor_va, max_bytes)
    if not code:
        return None
    mode = capstone.CS_MODE_64 if bv.bits == 64 else capstone.CS_MODE_32
    cs = capstone.Cs(capstone.CS_ARCH_X86, mode)
    cs.detail = True
    seen = 0
    for ins in cs.disasm(code, accessor_va):
        for op in ins.operands:
            if op.type == x86.X86_OP_MEM and op.mem.base != 0:
                reg = ins.reg_name(op.mem.base)
                if reg in ("esp", "rsp", "ebp", "rbp"):
                    continue
                if base_reg is not None and reg != base_reg:
                    continue
                disp = int(op.mem.disp)
                if min_disp <= disp <= max_disp:
                    if seen == occurrence:
                        size = int(op.size) or (8 if bv.bits == 64 else 4)
                        return FieldExtraction(
                            offset=disp,
                            size=size,
                            base_reg=reg,
                            insn_va=ins.address,
                            mnemonic=ins.mnemonic,
                            op_str=ins.op_str,
                        )
                    seen += 1
    return None


def unify_signatures(specs: Sequence[tuple[str, BinaryView, int]]) -> dict:
    """Attempt a single cross-build masked signature across all `(build_id, bv, va)` targets."""
    if not specs:
        return {"unified": False, "reason": "empty_specs"}
    per_build: list[tuple[str, BinaryView, int, list[MaskedInstruction]]] = []
    for bid, bv, va in specs:
        insns = mask_instructions(bv, va, max_bytes=96)
        if not insns:
            return {"unified": False, "reason": f"unreadable:{bid}"}
        per_build.append((bid, bv, va, insns))

    # Align prefix bytes across all builds and mask any byte that differs between builds
    min_len = min(sum(len(i.raw) for i in insns) for _, _, _, insns in per_build)
    raws = [b"".join(i.raw for i in insns)[:min_len] for _, _, _, insns in per_build]
    masks = [b"".join(i.mask for i in insns)[:min_len] for _, _, _, insns in per_build]

    unified_val = bytearray(raws[0])
    unified_mask = bytearray(masks[0])
    for idx in range(min_len):
        if any(m[idx] != 0xFF for m in masks) or any(r[idx] != unified_val[idx] for r in raws):
            unified_mask[idx] = 0x00

    if not unified_mask or unified_mask[0] != 0xFF:
        return {"unified": False, "reason": "divergent_entry_bytes"}

    # Pick shortest length >= 12 where all builds get unique == 1 match
    for length in range(12, min_len + 1):
        v = bytes(unified_val[:length])
        m = bytes(unified_mask[:length])
        if not _valid_for_scanner(v, m):
            continue
        ok = True
        for _, bv, va, _ in per_build:
            hits = bv.scan_masked(v, m, max_hits=2)
            if hits != [va]:
                ok = False
                break
        if ok:
            return {
                "unified": True,
                "pattern": v.hex(),
                "mask": m.hex(),
                "concrete_bytes": sum(1 for b in m if b == 0xFF),
                "total_bytes": length,
                "builds": [bid for bid, _, _, _ in per_build],
            }
    return {"unified": False, "reason": "no_shared_unique_prefix"}
