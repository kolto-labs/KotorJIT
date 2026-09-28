// Thumb-2 instruction length decoding, for the same reason
// src/hooks/trampoline.hpp's x86 decoder exists: the patcher has to know
// instruction boundaries before it overwrites bytes, or it splits an
// instruction and the corruption surfaces somewhere unrelated, later.
//
// Freestanding on purpose. This header (and decode.cpp) use no STL
// containers, no exceptions, no dynamic allocation -- the self-test tool
// that proves this code correct has to run under qemu-arm with no libc
// available (no ARM sysroot exists in the environment this was written in),
// so the code under test has to be buildable that way too. `tools/
// kp_hooktool_arm32.cpp` is the freestanding test driver; this pair of files
// is the only thing it links against besides the C runtime it writes itself.
//
// THUMB-2 IS NOT x86 -- READ THIS BEFORE TOUCHING THE TABLES BELOW
// ==================================================================
// x86's length rule needs a real opcode table because instruction length
// depends on which opcode it is. Thumb-2's length rule does not: ARM defines
// it structurally. Every Thumb-2 halfword's top 5 bits classify it:
//
//   bits[15:11] == 0b11101, 0b11110, or 0b11111   -> this is the FIRST half
//                                                     of a 32-bit instruction
//   anything else                                  -> a complete 16-bit
//                                                     instruction
//
// That rule is unconditional and total -- it holds for every Thumb-2
// instruction ever defined, including ones this file has never heard of.
// LENGTH is therefore not the hard problem here.
//
// RELOCATION is. An instruction that reads PC (r15) computes its result
// relative to WHERE IT SITS -- a literal-pool load, ADR, or any branch. Move
// it to a trampoline elsewhere in the address space and it silently
// computes the wrong answer unless the engine either re-aims it or refuses
// to move it at all. x86 solves this with an explicit opcode table (unknown
// opcode = refuse); this file uses the same discipline for the same reason:
// an ALLOWLIST of specific encodings verified safe to copy verbatim (no PC
// dependency), not a denylist of the ones known to be dangerous. Anything
// that does not match a table entry is refused, even if it would probably
// have been fine -- "probably" is exactly the word that turns into a
// three-in-the-morning crash report from a function nobody was even hooking
// on purpose.
//
// WHAT IS ALLOWLISTED (v1) -- verified against real bytes from
// K1__k1_android_ARMEABI and TSL__k2_android_libkotor2.so_armeabi-v7aandroid
// via objdump, not invented from the architecture reference alone:
//   16-bit: PUSH/POP (register list), ADD/SUB Rd,SP,#imm, MOV/MOVS (register
//     and 8-bit-immediate forms that do not name PC), CMP/CMN, basic ALU
//     group (AND/EOR/LSL/LSR/ASR/ADC/SBC/ROR/TST/RSB/ORR/MUL/BIC/MVN), NOP,
//     BX/BLX (register-indirect -- these read a register, not PC, to decide
//     where to go, so they carry no positional dependency themselves),
//     IT/ITT/ITE/... (the condition-code prefix; it does not touch PC).
//   32-bit: STMDB/LDMIA (register-list load/store, SP or a named base
//     register, never PC), the VFP/NEON coprocessor group (VPUSH, VLDR,
//     VMOV, VCMPE, VMRS and siblings -- these share the 32-bit prefix but
//     operate on FPU registers and a named base, not PC), MOVW/MOVT
//     (16-bit-immediate-into-register forms).
//
// WHAT IS DELIBERATELY REFUSED (v1), not solved -- naming these instead of
// silently mishandling them:
//   * LDR Rt, [PC, #imm] (16-bit and 32-bit literal-pool loads). The target
//     is a real absolute address, but the pool word lives at a fixed offset
//     from the ORIGINAL instruction; moving the LDR without moving or
//     re-deriving the pool entry needs a synthesized MOVW/MOVT+LDR sequence
//     this pass does not build.
//   * ADR (PC-relative address formation) -- same shape of problem as the
//     literal load.
//   * CBZ/CBNZ -- compare-and-branch-if-zero. Forward-only, +/-126 bytes.
//     Thumb has no long-range equivalent to widen into (unlike Bcc, which
//     has a documented .W wide form); ARM's own guidance is to rewrite the
//     surrounding code, which this engine will not do automatically. Same
//     refusal class as x86's LOOP/JECXZ, for the same reason: there is no
//     honest way to relocate it.
//   * B, BL, BLX(immediate), and conditional Bcc, in either width. All are
//     PC-relative branches. A future pass could widen the short forms and
//     re-aim the long ones (mirroring exactly what trampoline.cpp already
//     does for x86 rel8/rel32), but that fixup is not implemented yet, so
//     these refuse rather than pretend to be handled.
//   * Anything this table has not seen. The bytes still get a LENGTH (the
//     structural rule above is total), but claiming "safe to relocate" for
//     an unrecognised encoding is exactly the overclaim this file exists to
//     avoid, so `pc_relative_unhandled` is set and the caller must refuse.
#pragma once

#include <stddef.h>
#include <stdint-gcc.h>

namespace kp::hooks::arm32 {

// One decoded Thumb-2 instruction. Everything the patcher needs to know
// before it decides whether to copy this instruction into a trampoline.
struct Insn {
    bool          valid = false;      // false: could not even determine a length
    uint8_t  length = 0;         // 2 or 4
    bool          is_32bit = false;
    // True when this instruction is known, by the allowlist above, to be
    // safe to copy byte-for-byte to a different address. False covers BOTH
    // "known to be PC-relative" and "not recognised at all" -- the caller
    // must refuse relocating in either case, which is why there is one flag
    // rather than two: the distinction does not change what the patcher is
    // allowed to do with it.
    bool          relocatable = false;
    const char*   refusal = nullptr;  // set when valid == false, or as a
                                       // human-readable note when
                                       // relocatable == false but valid
    // 32-bit words, little-endian-decoded, exactly as read. 0 when
    // is_32bit is false. Kept for callers that want to log or re-verify
    // the classification independently of this decoder's own opinion.
    uint16_t half0 = 0;
    uint16_t half1 = 0;
};

// Decode one instruction starting at `code`. `avail` is how many bytes are
// left in the buffer -- a truncated halfword (avail < 2, or a 32-bit
// instruction with avail < 4) is a refusal, not a short read, exactly as
// trampoline.hpp's x86 decoder treats a truncated buffer.
Insn decode(const uint8_t* code, size_t avail);

}  // namespace kp::hooks::arm32
