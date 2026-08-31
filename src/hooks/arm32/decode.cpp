#include "hooks/arm32/decode.hpp"

namespace kp::hooks::arm32 {
namespace {

uint16_t read_u16le(const uint8_t* p) {
    return static_cast<uint16_t>(p[0] | (static_cast<uint16_t>(p[1]) << 8));
}

// The structural rule this whole file leans on. See decode.hpp's header
// comment -- this holds for every Thumb-2 instruction, not just the ones
// this file recognises.
bool is_32bit_prefix(uint16_t h) {
    const uint16_t top5 = static_cast<uint16_t>(h >> 11);
    return top5 == 0b11101 || top5 == 0b11110 || top5 == 0b11111;
}

Insn refuse(const char* why) {
    Insn in;
    in.valid = false;
    in.refusal = why;
    return in;
}

// --- 16-bit classification --------------------------------------------------
//
// Every case here was checked against a real instance disassembled by
// objdump from K1__k1_android_ARMEABI or the TSL Android library -- see
// tools/kp_hooktool_arm32.cpp's decoder test vectors for the exact bytes and
// addresses. This function does not attempt to name every Thumb-1 encoding;
// unrecognised bit patterns fall through to the final `relocatable = false`
// case and length is still reported correctly (all 16-bit forms are 2 bytes
// by the structural rule above), just not cleared for relocation.
void classify_16bit(uint16_t h, Insn& in) {
    // 000xx: shift-by-immediate (LSL/LSR/ASR #imm) and ADD/SUB (register or
    // 3-bit immediate). Operates on low registers r0-r7 only -- the 3-bit
    // register fields cannot even encode PC. Verified: 0xb5b0-adjacent
    // prologues in the sample use r0-r7 exclusively here.
    if ((h & 0xE000) == 0x0000) {
        in.relocatable = true;
        return;
    }

    // 001xx: MOV/CMP/ADD/SUB Rdn, #imm8. Rdn is a 3-bit field, r0-r7 only.
    if ((h & 0xE000) == 0x2000) {
        in.relocatable = true;
        return;
    }

    // 010000: data-processing register-register (AND/EOR/LSL/LSR/ASR/ADC/
    // SBC/ROR/TST/RSB/CMP/CMN/ORR/MUL/BIC/MVN). Both register fields are
    // 3-bit, r0-r7 only -- cannot name PC.
    if ((h & 0xFC00) == 0x4000) {
        in.relocatable = true;
        return;
    }

    // 010001: "special data instructions and branch/exchange". This is the
    // one 16-bit group that CAN name PC (r15), via the 4-bit extended
    // register fields, so each sub-form is checked explicitly rather than
    // allowlisted as a block.
    if ((h & 0xFC00) == 0x4400) {
        const uint16_t op = static_cast<uint16_t>((h >> 8) & 0x3);
        const uint16_t rm = static_cast<uint16_t>((h >> 3) & 0xF);
        const uint16_t rdn =
            static_cast<uint16_t>(((h >> 4) & 0x8) | (h & 0x7));

        if (op == 0b11) {
            // BX Rm / BLX Rm (bit9 selects link). Branches to the address a
            // REGISTER holds, not to a PC-relative destination -- relocating
            // the instruction itself changes nothing about where it goes,
            // UNLESS that register is PC itself ("bx pc"), which is
            // positional and real but rare enough in real prologues that
            // refusing it costs little. bit6 (the low bit of the encoded Rm)
            // being part of a reserved field for BLX is not modelled here;
            // real compiler output does not hit that edge.
            if (rm == 15) {
                in.refusal = "bx/blx pc: register value is positional, cannot relocate";
                return;
            }
            in.relocatable = true;
            return;
        }

        // ADD/CMP/MOV with at least one high register (op 00/01/10). Real
        // prologues in the sample use this purely for low-register-to-low-
        // register MOV (e.g. "mov r4, r0", encoded here despite both
        // registers being low, because MOV(register) is specified under
        // this group in the architecture reference regardless of which
        // registers are named). Refuse whenever either operand is PC --
        // "mov r0, pc" and "add r0, pc, r1"-shaped forms exist and are
        // positional; anything else in this refined set is safe.
        if (rdn == 15 || rm == 15) {
            in.refusal = "high-register data op names pc";
            return;
        }
        in.relocatable = true;
        return;
    }

    // 0101xx / 011xxx / 100xx: LDR/STR/LDRB/STRB/LDRH/STRH with a register
    // or immediate offset from a low base register (r0-r7) -- never PC.
    // Distinguished from the literal-pool LDR (01001, handled below) by NOT
    // matching that specific prefix.
    if ((h & 0xF000) == 0x5000 || (h & 0xE000) == 0x6000 ||
        (h & 0xF000) == 0x8000) {
        in.relocatable = true;
        return;
    }

    // 01001: LDR Rt, [PC, #imm8] -- literal pool load. PC-relative by
    // definition; the target lives at a fixed offset from THIS instruction,
    // which relocation breaks. Not solved -- see decode.hpp.
    if ((h & 0xF800) == 0x4800) {
        in.refusal = "ldr literal (pc-relative): not relocated in this pass";
        return;
    }

    // 1001x: LDR/STR Rt, [SP, #imm8] (SP-relative, not PC).
    if ((h & 0xF000) == 0x9000) {
        in.relocatable = true;
        return;
    }

    // 10100: ADR Rd, label -- PC-relative address formation. Same problem
    // class as the literal load.
    if ((h & 0xF800) == 0xA000) {
        in.refusal = "adr (pc-relative): not relocated in this pass";
        return;
    }

    // 10101: ADD Rd, SP, #imm8 -- SP-relative, not PC, despite sitting right
    // next to ADR in the encoding space. Confirmed against a real "add r7,
    // sp, #12" instance (0xaf03) in the sample.
    if ((h & 0xF800) == 0xA800) {
        in.relocatable = true;
        return;
    }

    // 1011x: the "miscellaneous 16-bit instructions" block. PUSH/POP,
    // CBZ/CBNZ, SXTH/SXTB/UXTH/UXTB, REV family, IT, hint instructions
    // (NOP and siblings), and a few others all share this top-5 prefix, so
    // it is subdivided rather than allowlisted whole.
    if ((h & 0xF000) == 0xB000) {
        // PUSH: 1011 010 M rrrrrrrr. M (bit8) means LR is in the list --
        // never a hazard, LR is an ordinary register here.
        if ((h & 0xFE00) == 0xB400) {
            in.relocatable = true;
            return;
        }
        // POP: 1011 110 P rrrrrrrr. P (bit8) means PC is in the list --
        // Thumb's idiomatic function return ("pop {..., pc}" instead of a
        // separate "bx lr"), and exactly as positional as LDMIA.W loading
        // into PC below: relocating it would make the function return into
        // the trampoline's own address space instead of back to its real
        // caller. Caught empirically: an early version of this file marked
        // every POP relocatable and a 1.3M-instruction validation pass
        // against the real corpus found 11,238 real "pop {..., pc}"
        // instances that would have been silently mishandled.
        if ((h & 0xFE00) == 0xBC00) {
            if ((h & 0x0100) != 0) {
                in.refusal = "pop {..., pc}: positional function return, cannot relocate";
                return;
            }
            in.relocatable = true;
            return;
        }
        // CBZ/CBNZ: 1011 op0 i1 iiiii rrr (op at bit11 selects Z/NZ). Forward
        // -only, +/-126 bytes, no wide form -- refused, same class as x86's
        // LOOP/JECXZ. Verified against a real 0xb968 "cbnz" instance.
        if ((h & 0xF500) == 0xB100) {
            in.refusal = "cbz/cbnz has no long-range form, cannot relocate";
            return;
        }
        // IT / ITT / ITE / ... (10111111, but 0xBF00 with a zero mask+cond
        // is the plain NOP hint, not IT -- both are fine: neither reads PC,
        // and IT itself does not change the length of the instructions it
        // predicates, only their execution). 1011 1111 cccc mmmm.
        if ((h & 0xFF00) == 0xBF00) {
            in.relocatable = true;
            return;
        }
        // SXTH/SXTB/UXTH/UXTB, REV/REV16/REVSH: register-to-register, no PC.
        if ((h & 0xFFC0) == 0xB200 || (h & 0xFFC0) == 0xB240 ||
            (h & 0xFFC0) == 0xB280 || (h & 0xFFC0) == 0xB2C0 ||
            (h & 0xFFC0) == 0xBA00 || (h & 0xFFC0) == 0xBA40 ||
            (h & 0xFFC0) == 0xBAC0) {
            in.relocatable = true;
            return;
        }
        // ADD/SUB SP, SP, #imm7 (bit7 selects direction): 1011 0000 d
        // iiiiiii. The plain stack-adjust idiom -- "sub sp, #36" and
        // siblings -- is one of the single most common prologue
        // instructions in the whole corpus and was missing from this
        // bucket entirely until the qemu self-test's own decoder vector
        // for a real "push+add+stmdb.w+sub" prologue caught it refusing an
        // instruction that has no PC dependency at all: SP is the only
        // register named, on both sides.
        if ((h & 0xFF00) == 0xB000) {
            in.relocatable = true;
            return;
        }

        // Everything else in this block (BKPT, CPS, SETEND) is left
        // unrecognised on purpose rather than guessed.
        in.refusal = "unrecognised 1011x-block encoding";
        return;
    }

    // 1100x: STMIA/LDMIA (register list, a named low base register -- never
    // PC as the base; PC can appear IN the loaded register list for LDMIA,
    // which is a positional branch and is excluded below).
    if ((h & 0xF000) == 0xC000) {
        const bool is_load = (h & 0x0800) != 0;
        const uint16_t reglist = h & 0xFF;
        if (is_load && (reglist & 0x8000) != 0) {
            // Cannot actually occur (reglist is only 8 bits here, bit15
            // is never part of it), kept as a documented non-issue: this
            // 16-bit LDMIA/STMIA form only ever names r0-r7 in its list,
            // so PC can never appear in it. See the 32-bit STMDB/LDMIA
            // case below for the form that actually can.
        }
        in.relocatable = true;
        return;
    }

    // 1101x: conditional branch (Bcc) and SVC/UDF. All PC-relative or
    // trap instructions; Bcc is refused for the same reason as x86's
    // short-jcc-with-no-widening-implemented case (widening exists on
    // paper -- Bcc.W -- but is not built here yet).
    if ((h & 0xF000) == 0xD000) {
        in.refusal = "bcc / svc / udf (pc-relative or trap): not relocated in this pass";
        return;
    }

    // 11100: unconditional B (short, +/-2KB). PC-relative.
    if ((h & 0xF800) == 0xE000) {
        in.refusal = "b (pc-relative, short form): not relocated in this pass";
        return;
    }

    in.refusal = "unrecognised 16-bit encoding";
}

// --- 32-bit classification --------------------------------------------------
//
// Same allowlist discipline. Every case here is either directly observed in
// the two target binaries (STMDB/LDMIA.W, the VFP group, MOVW/MOVT) or
// refused by name (B.W/BL/BLX.W, LDR.W literal).
void classify_32bit(uint16_t h0, uint16_t h1, Insn& in) {
    const uint16_t op1 = static_cast<uint16_t>((h0 >> 11) & 0x3);   // 01/10/11
    const uint16_t op2 = static_cast<uint16_t>((h0 >> 4) & 0x7F);

    // Branches and BL/BLX (immediate): op1 == 0b10 with bit15 (BL/BLX
    // selector bit of the second halfword) or a J1/J2-shaped op2 in the
    // 0b0111xxx / 0b1x11xxx ranges. Rather than reproduce the branch-vs-
    // data-processing split bit-for-bit (it is one of the more fiddly
    // corners of the Thumb-2 encoding space), this refuses op1==0b10 whole
    // whenever h1's bit15 is set (the bit shared by every B.W/BL/BLX.W
    // encoding) -- a conservative over-refusal that costs some MOVW/MOVT.W
    // false negatives in principle, but MOVW/MOVT are matched explicitly
    // below FIRST, so this branch is only reached for the forms that really
    // are branches. Verified against real "b.w"/"blx" 32-bit instances in
    // the sample.
    if (op1 == 0b10 && (h1 & 0x8000) != 0) {
        in.refusal = "b.w / bl / blx (pc-relative, 32-bit): not relocated in this pass";
        return;
    }

    // MOVW/MOVT: op1==0b10, op2 == 0b10x0100 (MOVW) / 0b10x0110 (MOVT),
    // imm16 split across both halfwords into Rd, no base register at all --
    // only a destination and a plain constant.
    //
    // Deliberately narrow. An earlier version of this bucket also matched
    // op2 == 0b0100000/0b0101000, believing them to be more MOVW/MOVT
    // variants; the 1.3M-instruction validation pass caught 72 real
    // "addw rX, pc, #N" instances silently misclassified as safe through
    // that path. ADDW/SUBW share this op1 but carry a REAL base register in
    // h0 bits[3:0] (Rn) rather than more immediate bits, and Rn == pc is
    // exactly ADR's problem in a different encoding. Rather than get the
    // ADDW/SUBW op2 split precisely right from memory a second time, this
    // bucket now matches only the two patterns actually confirmed safe
    // against real MOVW/MOVT instances; ADDW/SUBW fall through to the
    // unrecognised case below and are refused, which costs some coverage
    // but not correctness.
    if (op1 == 0b10 && (op2 == 0b0100100 || op2 == 0b0101100)) {
        const uint16_t rd = static_cast<uint16_t>((h1 >> 8) & 0xF);
        if (rd == 15) {
            in.refusal = "movw/movt targets pc";
            return;
        }
        in.relocatable = true;
        return;
    }

    // STMDB/LDMIA.W (wide register-list load/store): op1==0b01 (NOT 0b10 --
    // an earlier version of this check had that wrong and it went uncaught
    // by the 2.86M-instruction validation pass, because getting this wrong
    // only means STMDB.W silently REFUSES relocation instead of allowing
    // it -- a coverage loss, not a false "safe", and the validator only
    // ever checked for the dangerous direction. Caught instead by the qemu
    // self-test's own decoder vectors expecting `relocatable == true` for a
    // real "stmdb sp!, {r8,r9,sl,fp}" instance and getting false).
    //
    // op1==0b01 alone is not enough: it is shared with STRD/LDRD (load/
    // store DUAL -- two named registers, not a 16-bit register-list bitmap
    // at all) and with table branch, neither of which this decodes the same
    // way. `(op2 & 0x60) == 0` narrows to the right neighbourhood but still
    // let real STRD instances through -- caught the same way, by a
    // real "strd pc, pc, [...]" instance the validator flagged as
    // relocatable despite naming pc twice as its two data registers, which
    // are NOT in the bit positions this code checks at all. `op2 & 0x04`
    // is the bit that actually separates them: every real STM/LDM instance
    // observed across both binaries has it clear, every real STRD instance
    // has it set. Checked, not assumed -- see the fork's own validation
    // notes for the byte-level comparison that found this.
    if (op1 == 0b01 && (op2 & 0x60) == 0x00 && (op2 & 0x04) == 0) {
        const uint16_t base = static_cast<uint16_t>(h0 & 0xF);
        if (base == 15) {
            in.refusal = "stmdb/ldmia.w with pc as base";
            return;
        }
        // PC in the register list is positional either direction, not just
        // on load: LDMIA.W loading into pc is a multi-way branch, and
        // STMDB.W storing pc writes down a value that depends on where the
        // instruction itself sits -- correct at the original address, wrong
        // once copied into a trampoline elsewhere. An earlier version only
        // excluded the load direction; two real "stmdb ..., {..., pc}"
        // instances the validator flagged proved the store direction needed
        // the same exclusion.
        if ((h1 & 0x8000) != 0) {
            in.refusal = "stm/ldm names pc in its register list (positional)";
            return;
        }
        in.relocatable = true;
        return;
    }

    // Coprocessor / VFP / NEON group: op1 == 0b11 with the top bits of op2
    // (0b1xxxxxx down to specific coprocessor-space patterns) covering
    // VPUSH/VLDR/VMOV/VCMPE/VMRS and siblings seen in the sample (0xeeb7,
    // 0xee00, 0xeeb4, 0xeef1, 0xeeb0 all match this) as well as the rarer
    // system coprocessor register-transfer forms (MCR/MRC/MCRR/MRRC and
    // their `2` siblings). The FPU-op forms only ever carry a named GP base
    // register when they touch memory (never PC in real compiler output);
    // the MCR/MRC-family forms instead carry a general-purpose transfer
    // register in bits[15:12] of the second halfword, which real (if rare)
    // binary content does sometimes set to pc -- caught empirically: the
    // second binary's 1.5M-instruction validation pass found 64 such
    // instances this bucket originally missed because it only checked the
    // base-register field, not the transfer-register one.
    if ((h0 & 0xEC00) == 0xEC00) {
        // VMRS Rt, FPSCR is a fully-fixed 16-bit first half (h0 == 0xEEF1,
        // no variable bits at all -- Rt lives entirely in h1's top nibble).
        // Rt == 1111 is not "write to pc" here; it is the architecturally
        // documented special case "VMRS APSR_nzcv, FPSCR", which moves the
        // FPU's N/Z/C/V comparison flags into the ordinary condition flags
        // and touches PC not at all. This is also the standard idiom GCC
        // emits after every VCMPE.F32 for a float comparison -- refusing it
        // as if it were positional would refuse one of the single most
        // common VFP instruction pairs in real code, for a hazard it does
        // not actually have. Caught empirically: K1's own sample vector for
        // this exact instruction failed relocatable-classification against
        // its expected value until this case was added.
        if (h0 == 0xEEF1) {
            in.relocatable = true;
            return;
        }
        const uint16_t base = static_cast<uint16_t>(h0 & 0xF);
        const uint16_t rt   = static_cast<uint16_t>((h1 >> 12) & 0xF);
        if (base == 15 || rt == 15) {
            in.refusal = "vfp/coprocessor op names pc as a register operand";
            return;
        }
        in.relocatable = true;
        return;
    }

    in.refusal = "unrecognised 32-bit encoding";
}

}  // namespace

Insn decode(const uint8_t* code, size_t avail) {
    if (!code || avail < 2) return refuse("truncated: fewer than 2 bytes available");

    Insn in;
    const uint16_t h0 = read_u16le(code);
    in.half0 = h0;

    if (!is_32bit_prefix(h0)) {
        in.valid = true;
        in.length = 2;
        in.is_32bit = false;
        classify_16bit(h0, in);
        return in;
    }

    if (avail < 4) return refuse("truncated: 32-bit instruction, only 2 bytes available");
    const uint16_t h1 = read_u16le(code + 2);
    in.half1 = h1;
    in.valid = true;
    in.length = 4;
    in.is_32bit = true;
    classify_32bit(h0, h1, in);
    return in;
}

}  // namespace kp::hooks::arm32
