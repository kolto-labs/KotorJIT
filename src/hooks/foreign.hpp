// Living with other people's hooks.
//
// Hyperstim is not the only thing that patches the game. K1SE detours
// CSWVirtualMachineCommands::ExecuteCommand with MinHook; KPM patches the
// dispatcher's bound; overlays, injectors and future mods detour whatever they
// need. Every one of them starts the same way: it overwrites a function's
// first instructions with a jump to its own code and copies the bytes it
// displaced into a trampoline that jumps back. Before this module, a site
// whose first bytes were not byte-for-byte what the address table recorded
// refused -- correct for a wrong build, but it turned "another mod got there
// first" into "Hyperstim does not start".
//
// What this module decides, and what it never does
// ------------------------------------------------
// It answers one question with evidence: is this site the function we expect,
// with its head replaced by somebody's detour? Pure byte logic plus a memory
// search; it writes nothing and chooses no address on its own.
//
//   Evidence, strongest first (resolve_from_signatures records which one won):
//
//   A  exact        the recorded bytes, untouched. Not this module.
//   B  stub+tail    a recognised detour stub at the head, the original bytes
//                   after the displaced instructions intact, at least kMinTail
//                   of them. Usable with or without a recorded address.
//   C  relocated    a recognised stub at the head, AND the displaced original
//                   instructions found elsewhere in executable memory followed
//                   by a jump back to exactly where they were displaced from.
//                   That is the footprint every trampoline-based hooking
//                   library leaves (MinHook, Microsoft Detours, PolyHook,
//                   funchook, subhook), and it also hands back the original
//                   bytes so prologue-derived facts (the dispatcher bound) can
//                   still be read.
//   D  build-bound  a recognised stub at the recorded address of an address
//                   table that was selected by the executable's own sha256.
//                   The weakest, and only ever consulted with a recorded VA.
//
// What Hyperstim then does with a foreign-patched site (registry.cpp):
//   * reference / call sites (vm.execute_command): use the patched entry as-is.
//     Calls go through the other mod's detour, which is what keeps its own
//     features (K1SE's extra routines) working -- bypassing it would break them.
//   * detour sites: chain. Our engine displaces the other mod's jump into our
//     trampoline (rel32 jumps are relocated; it already does this), so the game
//     runs ours, then theirs, then the original. Order of load stops mattering.
//
// Policy: Chain (default) or Refuse (the old strict behaviour, for debugging a
// suspected conflict). Set by `foreign_patches = chain|refuse` in hyperstim.ini
// or HYPERSTIM_FOREIGN_PATCHES.
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace kp::hooks::foreign {

enum class StubKind : std::uint8_t {
    None,
    JmpRel32,        // E9 rel32                         5 bytes (MinHook, Detours on x86)
    JmpRel8,         // EB rel8                          2 bytes (hot-patch short jump)
    JmpMemAbs32,     // FF 25 [disp32]                   6 bytes, i386 absolute indirect
    JmpMemRip,       // FF 25 [rip+disp32]               6 bytes, x86-64 indirect
    JmpAbs64,        // FF 25 00000000 <imm64>           14 bytes (MinHook/Detours x64, ours)
    PushRet,         // 68 imm32 C3                      6 bytes
    MovRegJmpReg,    // B8+r imm32 ; FF E0+r             7 bytes, i386
    MovAbsRegJmpReg, // 48/49 B8+r imm64 ; [41] FF E0+r  12-13 bytes, x86-64
};

const char* to_string(StubKind);

struct Stub {
    StubKind       kind = StubKind::None;
    std::size_t    length = 0;
    // Where the stub sends execution. 0 when it is an indirect jump through
    // memory that is not readable right now -- still a stub, destination unknown.
    std::uintptr_t destination = 0;
};

// Decode a detour stub at `code`, which executes at address `at`. Pure: reads
// only `code[0..avail)` (plus, for the indirect forms, the pointer it names
// when that is readable). False for anything that is not one of the forms
// above -- including an ordinary jump that merely happens to be a function's
// first instruction, which callers rule out by checking the original bytes
// were not a jump.
bool decode_stub(const std::uint8_t* code, std::size_t avail, std::uintptr_t at, Stub& out,
                 bool x64);

// End of the original instruction that a stub of `stub_len` bytes would
// finish inside, measured on `original[0..n)` with this build's length
// decoder. 0 when the instructions cannot be decoded or run past n.
std::size_t boundary_after(const std::uint8_t* original, std::size_t n, std::size_t stub_len);

// Original bytes after the displaced head must match for at least this many
// bytes before stub+tail (evidence B) counts on its own.
inline constexpr std::size_t kMinTail = 6;

struct TolerantMatch {
    bool        ok = false;
    Stub        stub;
    // First byte of `expected` checked strictly: the end of the original
    // instruction the stub's last byte falls in. Bytes in [stub.length,
    // boundary) may be original or filler (CC / 90): MinHook leaves them,
    // Detours fills them with int3.
    std::size_t boundary = 0;
    std::size_t tail = 0;           // expected.size() - boundary
    const char* refusal = nullptr;  // why not, when !ok
};

// Does `live` look like `expected` with its head replaced by a detour stub?
// Never true when `expected` itself starts with a jump (that would be the
// original code, and the exact compare already handles it).
//
// `require_tail` false skips the kMinTail rule; the caller must then supply
// evidence C or D before acting on the result.
TolerantMatch match_tolerant(const std::uint8_t* live, const std::uint8_t* expected, std::size_t n,
                             std::uintptr_t at, bool x64, bool require_tail = true);

// Evidence C. Search the process's private executable memory (where hooking
// libraries allocate trampolines; platform::executable_regions) for
// `head[0..head_len)` immediately followed by a jump (any StubKind form) whose
// destination is `resume`. Returns the address of the relocated copy, or 0.
// Only exact copies are found: a displaced prologue that contained a relative
// branch would have been re-aimed by the hooking library, and is reported as
// not found rather than guessed at.
std::uintptr_t find_relocated_prologue(const std::uint8_t* head, std::size_t head_len,
                                       std::uintptr_t resume, bool x64);

// Same search over caller-supplied spans; what the function above delegates to,
// and what the offline test drives directly.
struct Span { std::uintptr_t va = 0; std::size_t size = 0; };
std::uintptr_t find_relocated_prologue_in(const std::vector<Span>& spans, const std::uint8_t* head,
                                          std::size_t head_len, std::uintptr_t resume, bool x64);

enum class Policy : std::uint8_t { Chain, Refuse };
void        set_policy(Policy);
Policy      policy();
bool        parse_policy(std::string_view text, Policy& out);
const char* to_string(Policy);

// "jmp rel32 -> 0x10002345 (k1se.dll)" -- one line for the log.
std::string describe(const Stub&);

}  // namespace kp::hooks::foreign
