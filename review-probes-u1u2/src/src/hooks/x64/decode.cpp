// x86_64 length decoder. See decode.hpp for scope. The tables below are an
// allowlist: an opcode that is not handled explicitly refuses.
#include "hooks/x64/decode.hpp"

#include <cstring>

namespace kp::hooks::x64 {
namespace {

Insn refuse(const char* why) {
    Insn i;
    i.refusal = why;
    return i;
}

// Operand shapes for the one- and two-byte maps.
enum Shape : std::uint8_t {
    Bad,        // refuse
    None,       // opcode only
    M,          // ModRM
    MI8,        // ModRM + imm8
    MIz,        // ModRM + imm16/32 (66 selects 16)
    I8,         // imm8
    Iz,         // imm16/32
    Grp3b,      // F6: ModRM, imm8 only for /0 and /1
    Grp3v,      // F7: ModRM, immz only for /0 and /1
    MovImm,     // B8+r: immz, or imm64 with REX.W
    Rel32,      // E8/E9, 0F 80..8F
    Enter,      // C8: imm16 + imm8
};

Shape one_byte(std::uint8_t op) {
    if (op < 0x40) {
        switch (op & 7) {
            case 0: case 1: case 2: case 3: return M;
            case 4: return I8;
            case 5: return Iz;
            default: return Bad;  // push/pop seg, daa/das/aaa/aas (and prefixes, handled earlier)
        }
    }
    if (op >= 0x50 && op <= 0x5f) return None;         // push/pop r64
    if (op == 0x63) return M;                           // movsxd
    if (op == 0x68) return Iz;
    if (op == 0x69) return MIz;
    if (op == 0x6a) return I8;
    if (op == 0x6b) return MI8;
    if (op == 0x80 || op == 0x83 || op == 0xc0 || op == 0xc1) return MI8;
    if (op == 0x81) return MIz;
    if (op >= 0x84 && op <= 0x8b) return M;             // test/xchg/mov
    if (op == 0x8d) return M;                           // lea
    if (op == 0x8f) return M;                           // pop r/m (checked /0 below)
    if (op >= 0x90 && op <= 0x99) return None;          // nop/xchg/cwde/cdq
    if (op == 0x9c || op == 0x9d) return None;          // pushf/popf
    if (op == 0xa8) return I8;
    if (op == 0xa9) return Iz;
    if (op >= 0xb0 && op <= 0xb7) return I8;
    if (op >= 0xb8 && op <= 0xbf) return MovImm;
    if (op == 0xc6) return MI8;                         // checked /0 below
    if (op == 0xc7) return MIz;                         // checked /0 below
    if (op == 0xc8) return Enter;
    if (op == 0xc9) return None;                        // leave
    if (op >= 0xd0 && op <= 0xd3) return M;             // shifts
    if (op >= 0xd8 && op <= 0xdf) return M;             // x87
    if (op == 0xe8 || op == 0xe9) return Rel32;
    if (op == 0xf5 || (op >= 0xf8 && op <= 0xfd)) return None;  // cmc, flag ops
    if (op == 0xf6) return Grp3b;
    if (op == 0xf7) return Grp3v;
    if (op == 0xfe || op == 0xff) return M;             // checked reg field below
    return Bad;
}

Shape two_byte(std::uint8_t op) {
    if (op == 0x05) return None;                        // syscall
    if (op == 0x31 || op == 0xa2) return None;          // rdtsc, cpuid
    if (op >= 0x10 && op <= 0x17) return M;             // SSE moves
    if (op >= 0x18 && op <= 0x1f) return M;             // prefetch/hint nop/endbr
    if (op >= 0x28 && op <= 0x2f) return M;
    if (op == 0x38) return M;                           // 0F 38 xx: third byte handled by caller
    if (op == 0x3a) return MI8;                         // 0F 3A xx: third byte handled by caller
    if (op >= 0x40 && op <= 0x4f) return M;             // cmovcc
    if (op >= 0x50 && op <= 0x6f) return M;
    if (op >= 0x70 && op <= 0x73) return MI8;           // pshuf*, shift-by-imm groups
    if (op >= 0x74 && op <= 0x76) return M;
    if (op >= 0x7e && op <= 0x7f) return M;
    if (op >= 0x80 && op <= 0x8f) return Rel32;         // jcc rel32
    if (op >= 0x90 && op <= 0x9f) return M;             // setcc
    if (op == 0xa3 || op == 0xab || op == 0xb3 || op == 0xbb) return M;  // bt*
    if (op == 0xa4 || op == 0xac) return MI8;           // shld/shrd imm
    if (op == 0xa5 || op == 0xad || op == 0xaf) return M;
    if (op == 0xb0 || op == 0xb1) return M;             // cmpxchg
    if (op >= 0xb6 && op <= 0xb7) return M;             // movzx
    if (op == 0xba) return MI8;                         // bt* imm
    if (op >= 0xbc && op <= 0xbf) return M;             // bsf/bsr/movsx
    if (op == 0xc0 || op == 0xc1) return M;             // xadd
    if (op == 0xc2 || (op >= 0xc4 && op <= 0xc6)) return MI8;
    if (op >= 0xc8 && op <= 0xcf) return None;          // bswap
    if (op >= 0xd0 && op <= 0xfe) return M;             // SSE2 integer ops
    return Bad;
}

std::int32_t read_i32(const std::uint8_t* p) {
    std::int32_t v;
    std::memcpy(&v, p, 4);
    return v;
}

}  // namespace

Insn decode(const std::uint8_t* code, std::size_t avail) {
    if (!code) return refuse("null code pointer");
    const std::size_t limit = avail < kMaxInsnLen ? avail : kMaxInsnLen;
    std::size_t at = 0;
    bool opsize = false, rex_w = false;
    auto need = [&](std::size_t n) { return at + n <= limit; };

    // Legacy prefixes, any order.
    for (;;) {
        if (!need(1)) return refuse(avail >= kMaxInsnLen ? "instruction longer than 15 bytes" : "truncated");
        const auto b = code[at];
        if (b == 0x66) { opsize = true; ++at; continue; }
        if (b == 0xf2 || b == 0xf3 || b == 0xf0 || b == 0x2e || b == 0x36 ||
            b == 0x3e || b == 0x26 || b == 0x64 || b == 0x65) { ++at; continue; }
        if (b == 0x67) return refuse("address-size prefix 67");
        break;
    }
    // REX must immediately precede the opcode.
    if ((code[at] & 0xf0) == 0x40) {
        rex_w = (code[at] & 8) != 0;
        ++at;
        if (!need(1)) return refuse("truncated");
        const auto b = code[at];
        if ((b & 0xf0) == 0x40 || b == 0x66 || b == 0x67 || b == 0xf2 || b == 0xf3 || b == 0xf0 ||
            b == 0x2e || b == 0x36 || b == 0x3e || b == 0x26 || b == 0x64 || b == 0x65)
            return refuse("REX not immediately before the opcode");
    }
    if (!need(1)) return refuse("truncated");
    const auto op = code[at++];
    if (op == 0xc4 || op == 0xc5 || op == 0x62 || op == 0x8f) {
        // 8F is POP r/m unless it is an XOP escape; XOP's ModRM always has
        // reg != 0, which the POP /0 check below also refuses.
        if (op != 0x8f) return refuse("VEX/EVEX encoding");
    }

    Shape shape;
    bool two = false;
    std::uint8_t op2 = 0;
    if (op == 0x0f) {
        if (!need(1)) return refuse("truncated");
        op2 = code[at++];
        two = true;
        shape = two_byte(op2);
        if (op2 == 0x38 || op2 == 0x3a) {
            if (!need(1)) return refuse("truncated");
            ++at;  // third opcode byte; ModRM (and imm8 for 3A) follow
        }
    } else {
        shape = one_byte(op);
    }
    if (shape == Bad) {
        switch (op) {
            case 0xeb: case 0xe0: case 0xe1: case 0xe2: case 0xe3:
                return refuse("short branch (rel8)");
            case 0xc2: case 0xc3: case 0xca: case 0xcb: case 0xcf:
                return refuse("return");
            case 0xcc: case 0xcd: case 0xf1: case 0xf4:
                return refuse("trap or halt");
            default:
                if (op >= 0x70 && op <= 0x7f) return refuse("short branch (rel8)");
                return refuse(two ? "unsupported two-byte opcode" : "unsupported opcode");
        }
    }

    Insn insn;
    const std::size_t immz = opsize ? 2 : 4;
    std::size_t imm = 0;
    switch (shape) {
        case None: break;
        case I8: imm = 1; break;
        case Iz: imm = immz; break;
        case MovImm: imm = rex_w ? 8 : immz; break;
        case Enter: imm = 3; break;
        case Rel32:
            if (opsize) return refuse("operand-size prefix on a rel32 branch");
            insn.rel = Rel::Rel32;
            insn.rel_offset = std::uint8_t(at);
            imm = 4;
            if (!two && op == 0xe9) insn.ends_flow = true;
            break;
        default: {
            // ModRM forms.
            if (!need(1)) return refuse("truncated");
            const auto modrm = code[at++];
            const unsigned mod = modrm >> 6, reg = (modrm >> 3) & 7, rm = modrm & 7;
            if (!two) {
                if ((op == 0x8f || op == 0xc6 || op == 0xc7) && reg != 0)
                    return refuse(op == 0xc7 && modrm == 0xf8 ? "xbegin" : "unsupported group encoding");
                if (op == 0xfe && reg > 1) return refuse("unsupported group encoding");
                if (op == 0xff) {
                    if (reg == 3 || reg == 5 || reg == 7) return refuse("far transfer or invalid FF encoding");
                    if (reg == 4) insn.ends_flow = true;
                }
                if (op == 0x8d && mod == 3) return refuse("lea with register operand");
            }
            if (mod != 3) {
                if (rm == 4) {
                    if (!need(1)) return refuse("truncated");
                    const auto sib = code[at++];
                    if (mod == 0 && (sib & 7) == 5) {  // no base: absolute disp32
                        if (!need(4)) return refuse("truncated");
                        at += 4;
                    }
                } else if (mod == 0 && rm == 5) {      // RIP-relative
                    insn.rel = Rel::RipDisp32;
                    insn.rel_offset = std::uint8_t(at);
                    if (!need(4)) return refuse("truncated");
                    at += 4;
                }
                if (mod == 1) at += 1;
                if (mod == 2) at += 4;
                if (at > limit) return refuse("truncated");
            }
            if (shape == MI8) imm = 1;
            else if (shape == MIz) imm = immz;
            else if (shape == Grp3b) imm = reg <= 1 ? 1 : 0;
            else if (shape == Grp3v) imm = reg <= 1 ? immz : 0;
        }
    }
    if (!need(imm)) return refuse(avail >= kMaxInsnLen ? "instruction longer than 15 bytes" : "truncated");
    at += imm;
    insn.len = std::uint8_t(at);
    insn.refusal = nullptr;
    return insn;
}

std::uint64_t referent(const std::uint8_t* code, const Insn& insn, std::uint64_t at) {
    if (insn.rel == Rel::None) return 0;
    return at + insn.len + std::uint64_t(std::int64_t(read_i32(code + insn.rel_offset)));
}

bool relocate(const std::uint8_t* src, std::uint64_t src_at, const Insn& insn,
              std::uint8_t* dst, std::uint64_t dst_at) {
    if (!insn.ok()) return false;
    if (insn.rel == Rel::None) {
        std::memcpy(dst, src, insn.len);
        return true;
    }
    const std::uint64_t target = referent(src, insn, src_at);
    const std::int64_t disp = std::int64_t(target - (dst_at + insn.len));
    if (disp < INT32_MIN || disp > INT32_MAX) return false;
    const std::int32_t d32 = std::int32_t(disp);
    std::memcpy(dst, src, insn.len);
    std::memcpy(dst + insn.rel_offset, &d32, 4);
    return true;
}

}  // namespace kp::hooks::x64
