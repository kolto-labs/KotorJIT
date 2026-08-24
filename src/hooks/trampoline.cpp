#include "hooks/trampoline.hpp"

#include <cstdio>
#include <cstring>
#include <utility>
#include <vector>

#include "platform/platform.hpp"

namespace kp::hooks {
namespace {

// ---------------------------------------------------------------------------
// Opcode tables
//
// One flag word per opcode, covering "is there a ModRM byte" and "how many
// immediate bytes follow". Entries left at zero are unrecognised and cause a
// refusal, which is why the tables are written as explicit ranges rather than
// filled with a permissive default -- a default would turn "I have never seen
// this byte" into "assume it is one byte long", the exact failure the decoder
// exists to prevent.
// ---------------------------------------------------------------------------

enum : std::uint16_t {
    F_VALID = 0x0001,
    F_MODRM = 0x0002,
    F_IB    = 0x0004,  // one immediate byte
    F_IW    = 0x0008,  // two immediate bytes, fixed
    F_IZ    = 0x0010,  // four immediate bytes; two under a 0x66 prefix
    F_IA    = 0x0020,  // moffs: an absolute address, address-size wide
    F_PTR   = 0x0040,  // ptr16:32 -- offset plus selector
    F_REL8  = 0x0080,
    F_REL32 = 0x0100,  // relative displacement, iz-sized
    F_GRP3  = 0x0200,  // F6/F7: the immediate exists only for /0 and /1
};

struct OpTables {
    std::uint16_t one[256] = {};
    std::uint16_t two[256] = {};

    OpTables() {
        auto set = [](std::uint16_t* t, int lo, int hi, std::uint16_t f) {
            for (int i = lo; i <= hi; ++i) t[i] = static_cast<std::uint16_t>(f | F_VALID);
        };

        // --- one-byte opcodes ---------------------------------------------

        // ADD/OR/ADC/SBB/AND/SUB/XOR/CMP all share one shape: four ModRM forms,
        // then AL,imm8 and eAX,imm32.
        for (int base = 0x00; base <= 0x38; base += 8) {
            set(one, base + 0, base + 3, F_MODRM);
            set(one, base + 4, base + 4, F_IB);
            set(one, base + 5, base + 5, F_IZ);
        }
        set(one, 0x06, 0x07, 0);            // push/pop es
        set(one, 0x0E, 0x0E, 0);            // push cs  (0x0F is the escape byte)
        set(one, 0x16, 0x17, 0);            // push/pop ss
        set(one, 0x1E, 0x1F, 0);            // push/pop ds
        set(one, 0x26, 0x27, 0);            // es prefix, daa
        set(one, 0x2E, 0x2F, 0);            // cs prefix, das
        set(one, 0x36, 0x37, 0);            // ss prefix, aaa
        set(one, 0x3E, 0x3F, 0);            // ds prefix, aas
        set(one, 0x40, 0x5F, 0);            // inc/dec/push/pop r32
        set(one, 0x60, 0x61, 0);            // pushad/popad
        set(one, 0x62, 0x63, F_MODRM);      // bound, arpl
        set(one, 0x64, 0x67, 0);            // fs/gs/opsize/addrsize prefixes
        set(one, 0x68, 0x68, F_IZ);         // push imm32
        set(one, 0x69, 0x69, F_MODRM | F_IZ);
        set(one, 0x6A, 0x6A, F_IB);         // push imm8
        set(one, 0x6B, 0x6B, F_MODRM | F_IB);
        set(one, 0x6C, 0x6F, 0);            // ins/outs
        set(one, 0x70, 0x7F, F_REL8);       // jcc short
        set(one, 0x80, 0x80, F_MODRM | F_IB);
        set(one, 0x81, 0x81, F_MODRM | F_IZ);
        set(one, 0x82, 0x83, F_MODRM | F_IB);
        set(one, 0x84, 0x8F, F_MODRM);      // test/xchg/mov/lea/pop
        set(one, 0x90, 0x99, 0);            // nop, xchg eax, cwde, cdq
        set(one, 0x9A, 0x9A, F_PTR);        // call far
        set(one, 0x9B, 0x9F, 0);
        set(one, 0xA0, 0xA3, F_IA);         // mov to/from moffs -- NO ModRM
        set(one, 0xA4, 0xA7, 0);            // movs/cmps
        set(one, 0xA8, 0xA8, F_IB);
        set(one, 0xA9, 0xA9, F_IZ);
        set(one, 0xAA, 0xAF, 0);            // stos/lods/scas
        set(one, 0xB0, 0xB7, F_IB);         // mov r8, imm8
        set(one, 0xB8, 0xBF, F_IZ);         // mov r32, imm32
        set(one, 0xC0, 0xC1, F_MODRM | F_IB);
        set(one, 0xC2, 0xC2, F_IW);         // ret imm16
        set(one, 0xC3, 0xC3, 0);
        set(one, 0xC4, 0xC5, F_MODRM);      // les/lds
        set(one, 0xC6, 0xC6, F_MODRM | F_IB);
        set(one, 0xC7, 0xC7, F_MODRM | F_IZ);
        set(one, 0xC8, 0xC8, F_IW | F_IB);  // enter imm16, imm8
        set(one, 0xC9, 0xC9, 0);
        set(one, 0xCA, 0xCA, F_IW);         // retf imm16
        set(one, 0xCB, 0xCC, 0);
        set(one, 0xCD, 0xCD, F_IB);         // int imm8
        set(one, 0xCE, 0xCF, 0);
        set(one, 0xD0, 0xD3, F_MODRM);      // shift group
        set(one, 0xD4, 0xD5, F_IB);         // aam/aad
        set(one, 0xD6, 0xD7, 0);
        set(one, 0xD8, 0xDF, F_MODRM);      // x87 -- length is ModRM-determined
        set(one, 0xE0, 0xE3, F_REL8);       // loop/loopz/loopnz/jecxz
        set(one, 0xE4, 0xE7, F_IB);         // in/out imm8
        set(one, 0xE8, 0xE9, F_REL32);      // call/jmp near
        set(one, 0xEA, 0xEA, F_PTR);        // jmp far
        set(one, 0xEB, 0xEB, F_REL8);       // jmp short
        set(one, 0xEC, 0xEF, 0);            // in/out dx
        set(one, 0xF0, 0xF5, 0);            // lock, int1, rep prefixes, hlt, cmc
        set(one, 0xF6, 0xF6, F_MODRM | F_GRP3 | F_IB);
        set(one, 0xF7, 0xF7, F_MODRM | F_GRP3 | F_IZ);
        set(one, 0xF8, 0xFD, 0);            // flag ops
        set(one, 0xFE, 0xFF, F_MODRM);      // inc/dec, call/jmp/push indirect

        // --- 0F-escaped opcodes -------------------------------------------

        set(two, 0x00, 0x03, F_MODRM);
        set(two, 0x06, 0x06, 0);            // clts
        set(two, 0x08, 0x09, 0);            // invd/wbinvd
        set(two, 0x0B, 0x0B, 0);            // ud2
        set(two, 0x0D, 0x0D, F_MODRM);      // prefetch
        // 0F 18..1F covers the multi-byte NOPs and endbr32 (F3 0F 1E FB). The
        // generic ModRM path gets endbr32's length right without special-casing.
        set(two, 0x10, 0x2F, F_MODRM);
        set(two, 0x30, 0x35, 0);            // wrmsr/rdtsc/rdmsr/rdpmc/sysenter/sysexit
        set(two, 0x37, 0x37, 0);            // getsec
        // 0F 38 and 0F 3A are three-byte escapes and 0F 78/79 change length
        // under a 66 prefix. Left unrecognised on purpose -- MSVC 7.1 emits
        // none of them, and refusing beats a wrong length.
        set(two, 0x40, 0x77, F_MODRM);
        set(two, 0x70, 0x73, F_MODRM | F_IB);
        set(two, 0x77, 0x77, 0);            // emms
        two[0x78] = 0;
        two[0x79] = 0;
        set(two, 0x7C, 0x7F, F_MODRM);
        set(two, 0x80, 0x8F, F_REL32);      // jcc near
        set(two, 0x90, 0x9F, F_MODRM);      // setcc
        set(two, 0xA0, 0xA2, 0);            // push fs, pop fs, cpuid
        set(two, 0xA3, 0xA3, F_MODRM);      // bt
        set(two, 0xA4, 0xA4, F_MODRM | F_IB);
        set(two, 0xA5, 0xA5, F_MODRM);
        set(two, 0xA8, 0xAA, 0);            // push gs, pop gs, rsm
        set(two, 0xAB, 0xAB, F_MODRM);      // bts
        set(two, 0xAC, 0xAC, F_MODRM | F_IB);
        set(two, 0xAD, 0xAF, F_MODRM);
        set(two, 0xB0, 0xC1, F_MODRM);
        // 0F BA is Group 8 -- bt/bts/btr/btc r/m32, imm8 -- so it carries an
        // immediate that the rest of this range does not. Without F_IB it
        // decodes one byte short, which is worse than refusing: a wrong length
        // splits the following instruction and the game dies somewhere
        // unrelated, much later.
        //
        // MSVC never emits it, so KOTOR 1 contains none and a sweep over that
        // binary alone cannot find this. GCC does emit it, and the TSL Linux
        // build has two.
        set(two, 0xBA, 0xBA, F_MODRM | F_IB);
        set(two, 0xC2, 0xC2, F_MODRM | F_IB);
        set(two, 0xC3, 0xC3, F_MODRM);
        set(two, 0xC4, 0xC6, F_MODRM | F_IB);
        set(two, 0xC7, 0xC7, F_MODRM);
        set(two, 0xC8, 0xCF, 0);            // bswap
        set(two, 0xD0, 0xFF, F_MODRM);
    }
};

const OpTables& tables() {
    // Function-local so the tables are built on first use. A namespace-scope
    // object would be exposed to static-initialisation order if anything ever
    // decodes during startup.
    static const OpTables t;
    return t;
}

bool is_prefix(std::uint8_t b) {
    switch (b) {
        case 0xF0:                          // lock
        case 0xF2: case 0xF3:               // rep / repne (also SSE selectors)
        case 0x2E: case 0x36: case 0x3E: case 0x26: case 0x64: case 0x65:
        case 0x66:                          // operand size
        case 0x67:                          // address size -- recognised, then refused
            return true;
        default:
            return false;
    }
}

Insn refuse(const char* why) {
    Insn in;
    in.valid = false;
    in.refusal = why;
    return in;
}

std::int32_t read_i32(const std::uint8_t* p) {
    std::int32_t v = 0;
    std::memcpy(&v, p, 4);
    return v;
}

void write_i32(std::uint8_t* p, std::int32_t v) {
    std::memcpy(p, &v, 4);
}

}  // namespace

// ---------------------------------------------------------------------------
// Length decoding
// ---------------------------------------------------------------------------

Insn decode(const std::uint8_t* code, std::size_t avail) {
    if (!code || avail == 0) return refuse("no bytes to decode");

    Insn in;
    std::size_t i = 0;
    int prefix_count = 0;

    while (i < avail && is_prefix(code[i])) {
        if (code[i] == 0x67) {
            // A 0x67 switches to 16-bit addressing, which changes ModRM/SIB
            // decoding wholesale. Rather than carry a second addressing mode
            // for something 32-bit compilers never emit, refuse.
            return refuse("address-size prefix 0x67 (16-bit addressing not decoded)");
        }
        if (code[i] == 0x66) in.operand_size_16 = true;
        ++i;
        if (++prefix_count > 4) return refuse("more than four prefix bytes");
    }
    if (i >= avail) return refuse("truncated: prefixes with no opcode");
    in.prefix_len = static_cast<std::uint8_t>(i);

    std::uint16_t flags;
    if (code[i] == 0x0F) {
        ++i;
        if (i >= avail) return refuse("truncated: 0F escape with no opcode");
        in.two_byte = true;
        in.opcode = code[i];
        flags = tables().two[in.opcode];
    } else {
        in.opcode = code[i];
        flags = tables().one[in.opcode];
    }
    ++i;

    if (!(flags & F_VALID)) {
        return refuse(in.two_byte ? "unrecognised 0F-escaped opcode"
                                  : "unrecognised opcode");
    }
    if ((flags & F_REL32) && in.operand_size_16) {
        // 66 E9 is jmp rel16 -- legal, but it truncates EIP to 16 bits and no
        // compiler emits it. Refusing avoids a relocation special case.
        return refuse("operand-size prefix on a near branch");
    }

    // ModRM, and the SIB / displacement it may drag along.
    std::uint8_t modrm_reg = 0;
    if (flags & F_MODRM) {
        if (i >= avail) return refuse("truncated: missing ModRM");
        const std::uint8_t modrm = code[i++];
        const std::uint8_t mod = static_cast<std::uint8_t>((modrm >> 6) & 3);
        const std::uint8_t rm  = static_cast<std::uint8_t>(modrm & 7);
        modrm_reg = static_cast<std::uint8_t>((modrm >> 3) & 7);

        if (mod != 3) {
            std::size_t disp = 0;
            if (rm == 4) {
                // rm == 100b is the escape to a SIB byte, not register ESP.
                if (i >= avail) return refuse("truncated: missing SIB");
                const std::uint8_t sib = code[i++];
                // mod == 00 with base == 101b means "no base register, disp32".
                if (mod == 0 && (sib & 7) == 5) disp = 4;
            }
            if (mod == 0 && rm == 5) {
                // The case decoders get wrong: mod == 00 normally means "no
                // displacement", but rm == 101b is the absolute-address form and
                // carries a full disp32. `64 89 25 00 00 00 00` is exactly this.
                disp = 4;
            } else if (mod == 1) {
                disp = 1;
            } else if (mod == 2) {
                disp = 4;
            }
            i += disp;
        }
    }

    // Immediates.
    std::size_t imm = 0;
    const std::size_t iz = in.operand_size_16 ? 2u : 4u;
    if (flags & F_GRP3) {
        // F6/F7 are a group where only /0 and /1 (TEST) take an immediate. Every
        // other member -- NOT, NEG, MUL, IMUL, DIV, IDIV -- takes none.
        if (modrm_reg <= 1) imm += (flags & F_IZ) ? iz : 1u;
    } else {
        if (flags & F_IB)  imm += 1;
        if (flags & F_IW)  imm += 2;
        if (flags & F_IZ)  imm += iz;
        if (flags & F_IA)  imm += 4;  // 0x67 already refused, so always 4
        if (flags & F_PTR) imm += in.operand_size_16 ? 4u : 6u;
    }

    if (flags & F_REL8) {
        in.rel = RelKind::Rel8;
        in.rel_offset = static_cast<std::uint8_t>(i);
        imm += 1;
    } else if (flags & F_REL32) {
        in.rel = RelKind::Rel32;
        in.rel_offset = static_cast<std::uint8_t>(i);
        imm += iz;
    }

    i += imm;
    if (i > avail) return refuse("truncated: instruction runs past the buffer");
    if (i > kMaxInsnLen) return refuse("instruction longer than 15 bytes");

    in.valid = true;
    in.length = static_cast<std::uint8_t>(i);
    return in;
}

std::uintptr_t branch_target(const std::uint8_t* code, const Insn& in, std::uintptr_t ip) {
    const std::intptr_t disp =
        (in.rel == RelKind::Rel8)
            ? static_cast<std::intptr_t>(static_cast<std::int8_t>(code[in.rel_offset]))
            : static_cast<std::intptr_t>(read_i32(code + in.rel_offset));
    // Relative displacements are measured from the END of the instruction.
    return static_cast<std::uintptr_t>(ip + in.length + disp);
}

std::string hex_bytes(const std::uint8_t* data, std::size_t len) {
    std::string out;
    out.reserve(len * 3);
    char buf[4];
    for (std::size_t i = 0; i < len; ++i) {
        std::snprintf(buf, sizeof(buf), "%02X", data[i]);
        if (i) out.push_back(' ');
        out += buf;
    }
    return out;
}

const char* to_string(HookStatus s) {
    switch (s) {
        case HookStatus::Ok:                  return "ok";
        case HookStatus::BadArgs:             return "bad arguments";
        case HookStatus::AlreadyInstalled:    return "already installed";
        case HookStatus::NotInstalled:        return "not installed";
        case HookStatus::Unreadable:          return "target address is not mapped";
        case HookStatus::ByteMismatch:        return "original bytes did not match";
        case HookStatus::DecodeFailed:        return "could not decode displaced instructions";
        case HookStatus::Unrelocatable:       return "displaced instruction cannot be relocated";
        case HookStatus::BranchIntoPatchArea: return "displaced branch targets the patch area";
        case HookStatus::AllocFailed:         return "executable allocation failed";
        case HookStatus::ProtectFailed:       return "page protection change failed";
    }
    return "?";
}

// ---------------------------------------------------------------------------
// Installation
// ---------------------------------------------------------------------------

namespace {

// One displaced instruction, with where it came from and where it is going.
struct Piece {
    Insn           insn;
    std::size_t    src_off = 0;
    std::size_t    dst_off = 0;
    std::uint8_t   dst_len = 0;
    std::uintptr_t abs_target = 0;  // for relative branches
};

}  // namespace

Detour::~Detour() {
    if (installed_) uninstall();
    release();
}

Detour::Detour(Detour&& other) noexcept {
    *this = std::move(other);
}

Detour& Detour::operator=(Detour&& other) noexcept {
    if (this == &other) return *this;
    if (installed_) uninstall();
    release();

    target_          = other.target_;
    detour_          = other.detour_;
    trampoline_      = other.trampoline_;
    trampoline_size_ = other.trampoline_size_;
    stolen_len_      = other.stolen_len_;
    installed_       = other.installed_;
    std::memcpy(original_, other.original_, sizeof(original_));

    other.trampoline_ = nullptr;
    other.trampoline_size_ = 0;
    other.installed_ = false;
    other.stolen_len_ = 0;
    return *this;
}

void Detour::release() {
    if (trampoline_) {
        platform::free_exec(trampoline_, trampoline_size_);
        trampoline_ = nullptr;
        trampoline_size_ = 0;
    }
}

HookStatus Detour::install(void* target, void* detour,
                           const std::uint8_t* expect, std::size_t expect_len,
                           std::string* detail) {
    auto explain = [&](const std::string& text) {
        if (detail) *detail = text;
    };

    if (!target || !detour) {
        explain("target or detour is null");
        return HookStatus::BadArgs;
    }
    if (installed_) {
        explain("this Detour already holds an installed hook");
        return HookStatus::AlreadyInstalled;
    }

    const auto target_addr = reinterpret_cast<std::uintptr_t>(target);
    const auto* code = static_cast<const std::uint8_t*>(target);

    // Before anything dereferences the address, establish that it is an address.
    // Everything downstream -- byte verification, decoding, patching -- reads
    // this memory, so a wrong table entry would fault inside the very check that
    // exists to catch a wrong table entry.
    if (!platform::is_readable(target, kMaxStolen)) {
        char addr_text[16];
        std::snprintf(addr_text, sizeof(addr_text), "0x%08X",
                      static_cast<unsigned>(target_addr));
        explain(std::string("address ") + addr_text + " is not mapped");
        return HookStatus::Unreadable;
    }

    // Verification comes first, before decoding and long before any write. If
    // the image does not hold the bytes the address table promised, every
    // conclusion drawn from that address is void.
    if (expect && expect_len) {
        if (expect_len > kMaxStolen) {
            explain("expected-byte pattern is longer than the engine can displace");
            return HookStatus::BadArgs;
        }
        if (std::memcmp(code, expect, expect_len) != 0) {
            char addr_text[16];
            std::snprintf(addr_text, sizeof(addr_text), "0x%08X",
                          static_cast<unsigned>(target_addr));
            explain("expected [" + hex_bytes(expect, expect_len) + "] at " + addr_text +
                    ", found [" + hex_bytes(code, expect_len) + "]");
            return HookStatus::ByteMismatch;
        }
    }

    // --- pass 1: decode far enough to cover the JMP, and lay out the copy ---

    std::vector<Piece> pieces;
    std::size_t stolen = 0;
    std::size_t dst = 0;

    while (stolen < kJmpRel32Size) {
        Piece p;
        p.src_off = stolen;
        p.insn = decode(code + stolen, kMaxStolen - stolen);
        if (!p.insn.valid) {
            explain(std::string("at +") + std::to_string(stolen) + ": " +
                    (p.insn.refusal ? p.insn.refusal : "decode failed") +
                    " [" + hex_bytes(code + stolen, 8) + "]");
            return HookStatus::DecodeFailed;
        }

        p.dst_off = dst;
        p.dst_len = p.insn.length;

        if (p.insn.rel != RelKind::None) {
            p.abs_target = branch_target(code + stolen, p.insn, target_addr + stolen);

            if (p.insn.rel == RelKind::Rel8) {
                if (p.insn.prefix_len != 0) {
                    explain("prefixed short branch cannot be widened");
                    return HookStatus::Unrelocatable;
                }
                if (p.insn.opcode == 0xEB) {
                    p.dst_len = 5;   // -> E9 rel32
                } else if (p.insn.opcode >= 0x70 && p.insn.opcode <= 0x7F) {
                    p.dst_len = 6;   // -> 0F 8x rel32
                } else {
                    // LOOP/LOOPE/LOOPNE/JECXZ. No rel32 form exists.
                    explain("LOOP/JECXZ has no long form and cannot be relocated");
                    return HookStatus::Unrelocatable;
                }
            }
        }

        dst += p.dst_len;
        stolen += p.insn.length;
        pieces.push_back(p);
    }

    // A branch that lands inside the bytes we are about to overwrite would,
    // after relocation, jump straight into our own JMP and detour again --
    // unbounded recursion. Checked here, before the first write, so a refusal
    // leaves the target untouched.
    for (const Piece& p : pieces) {
        if (p.insn.rel == RelKind::None) continue;
        if (p.abs_target >= target_addr && p.abs_target < target_addr + stolen) {
            explain("displaced branch at +" + std::to_string(p.src_off) +
                    " targets +" + std::to_string(p.abs_target - target_addr) +
                    ", inside the " + std::to_string(stolen) + "-byte patch area");
            return HookStatus::BranchIntoPatchArea;
        }
    }

    const std::size_t tramp_size = dst + kJmpRel32Size;

    // --- pass 2: emit the trampoline -------------------------------------

    auto* tramp = static_cast<std::uint8_t*>(platform::alloc_exec(tramp_size));
    if (!tramp) {
        explain("could not allocate " + std::to_string(tramp_size) +
                " bytes of executable memory");
        return HookStatus::AllocFailed;
    }
    const auto tramp_addr = reinterpret_cast<std::uintptr_t>(tramp);

    for (const Piece& p : pieces) {
        const std::uint8_t* src = code + p.src_off;
        std::uint8_t* out = tramp + p.dst_off;
        const std::uintptr_t out_addr = tramp_addr + p.dst_off;

        if (p.insn.rel == RelKind::Rel32) {
            // Same encoding, new displacement: re-aim at the original absolute
            // target from the trampoline's position.
            std::memcpy(out, src, p.insn.length);
            write_i32(out + p.insn.rel_offset,
                      static_cast<std::int32_t>(p.abs_target - (out_addr + p.dst_len)));
        } else if (p.insn.rel == RelKind::Rel8) {
            // Widen. A signed byte cannot reach from the trampoline back to the
            // function, so the short form is rewritten as its long equivalent.
            if (p.insn.opcode == 0xEB) {
                out[0] = 0xE9;
                write_i32(out + 1,
                          static_cast<std::int32_t>(p.abs_target - (out_addr + 5)));
            } else {
                out[0] = 0x0F;
                out[1] = static_cast<std::uint8_t>(p.insn.opcode + 0x10);  // 7x -> 0F 8x
                write_i32(out + 2,
                          static_cast<std::int32_t>(p.abs_target - (out_addr + 6)));
            }
        } else {
            std::memcpy(out, src, p.insn.length);
        }
    }

    // Jump back to the first byte the patch did not cover.
    std::uint8_t* tail = tramp + dst;
    tail[0] = 0xE9;
    write_i32(tail + 1, static_cast<std::int32_t>(
                            (target_addr + stolen) -
                            (tramp_addr + dst + kJmpRel32Size)));

    if (!platform::commit_exec(tramp, tramp_size)) {
        platform::free_exec(tramp, tramp_size);
        explain("could not make the trampoline executable");
        return HookStatus::ProtectFailed;
    }
    platform::flush_instruction_cache(tramp, tramp_size);

    // --- pass 3: patch the target ----------------------------------------

    std::memcpy(original_, code, stolen);

    if (!platform::set_protection(target, stolen, platform::Protect::ReadWrite)) {
        platform::free_exec(tramp, tramp_size);
        explain("could not make the target writable");
        return HookStatus::ProtectFailed;
    }

    auto* patch = static_cast<std::uint8_t*>(target);
    patch[0] = 0xE9;
    write_i32(patch + 1,
              static_cast<std::int32_t>(reinterpret_cast<std::uintptr_t>(detour) -
                                        (target_addr + kJmpRel32Size)));
    // Pad the remainder of the displaced range. The bytes are unreachable --
    // control never falls into them -- but leaving instruction fragments there
    // makes any later disassembly of the function nonsense, including our own.
    for (std::size_t i = kJmpRel32Size; i < stolen; ++i) patch[i] = 0x90;

    if (!platform::set_protection(target, stolen, platform::Protect::ReadExec)) {
        // The patch is live and correct; only the protection restore failed.
        // Warn rather than roll back -- undoing a live patch is riskier than a
        // page that stayed writable.
        platform::log(platform::LogLevel::Warn,
                      "detour at %p installed, but the page could not be returned to R+X",
                      target);
    }
    platform::flush_instruction_cache(target, stolen);

    target_          = target_addr;
    detour_          = detour;
    trampoline_      = tramp;
    trampoline_size_ = tramp_size;
    stolen_len_      = stolen;
    installed_       = true;

    platform::log(platform::LogLevel::Debug,
                  "detour %p -> %p, %zu bytes displaced, trampoline %p (%zu bytes)",
                  target, detour, stolen, tramp, tramp_size);
    return HookStatus::Ok;
}

HookStatus Detour::uninstall() {
    if (!installed_) return HookStatus::NotInstalled;

    auto* patch = reinterpret_cast<std::uint8_t*>(target_);
    if (!platform::set_protection(patch, stolen_len_, platform::Protect::ReadWrite)) {
        return HookStatus::ProtectFailed;
    }
    std::memcpy(patch, original_, stolen_len_);
    platform::set_protection(patch, stolen_len_, platform::Protect::ReadExec);
    platform::flush_instruction_cache(patch, stolen_len_);

    installed_ = false;
    release();
    return HookStatus::Ok;
}

}  // namespace kp::hooks
