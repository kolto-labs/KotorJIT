// x86_64 instruction length decoding for the inline detour engine.
//
// Same job as the i386 decoder behind src/hooks/trampoline.hpp and the
// Thumb-2 allowlist in src/hooks/arm32/decode.hpp: before bytes are
// overwritten, the patcher must know where each instruction ends, and which
// ones depend on their own address.
//
// This is an allowlist of the opcodes seen in ordinary function prologues and
// their first few body instructions. Anything else refuses. Refusal is the
// cheap outcome; a mis-decoded length splits an instruction and the crash
// shows up later, somewhere unrelated.
//
// Position-dependent forms this decoder recognises and reports, so the
// trampoline can re-aim them:
//   * ModRM mod=00 rm=101 without SIB: RIP-relative disp32. REX.B does not
//     change this. (SIB base=101 with mod=00 is an absolute disp32, not RIP.)
//   * E8 call rel32, E9 jmp rel32, 0F 80..8F jcc rel32.
// Refused outright: address-size prefix 67, VEX/EVEX/XOP, short branches
// (EB, 70..7F, E0..E3), returns and traps (C2, C3, CA, CB, CC, CD, CF, F1,
// F4), I/O, moffs moves (A0..A3), far transfers, and any opcode not listed in
// decode.cpp.
#pragma once

#include <cstddef>
#include <cstdint>

namespace kp::hooks::x64 {

inline constexpr std::size_t kMaxInsnLen = 15;  // the architectural ceiling

enum class Rel : std::uint8_t {
    None,
    RipDisp32,   // memory operand [rip + disp32]
    Rel32,       // E8 / E9 / 0F 8x: branch target = end + rel32
};

struct Insn {
    std::uint8_t len = 0;         // 0 when refused
    Rel rel = Rel::None;
    std::uint8_t rel_offset = 0;  // byte offset of the disp32/rel32 field
    bool ends_flow = false;       // E9 / FF /4: no fall-through
    const char* refusal = nullptr;
    bool ok() const { return len != 0; }
};

// Decodes one instruction from at most `avail` bytes.
Insn decode(const std::uint8_t* code, std::size_t avail);

// The absolute address an instruction's disp32/rel32 names, given where the
// instruction sits. Only meaningful when rel != Rel::None.
std::uint64_t referent(const std::uint8_t* code, const Insn&, std::uint64_t at);

// Copies one instruction to `dst` (which will execute at `dst_at`), re-aiming
// its disp32/rel32 so it still names the same absolute address. Returns false,
// writing nothing, when the new displacement does not fit in a signed 32 bits.
bool relocate(const std::uint8_t* src, std::uint64_t src_at, const Insn&,
              std::uint8_t* dst, std::uint64_t dst_at);

}  // namespace kp::hooks::x64
