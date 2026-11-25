// ARM32 (Thumb-2) inline detour: an 8-byte absolute branch at the target,
// the displaced instructions relocated into a trampoline that jumps back.
//
// Same shape of problem as src/hooks/trampoline.hpp's x86 engine, and this
// file is deliberately structured to match it -- Detour::install/uninstall/
// original() have the identical contract -- but the actual patch mechanics
// are new, not ported, because ARM and x86 disagree about the two things
// that matter most:
//
//   1. HOW FAR A BRANCH REACHES. x86's `E9 rel32` covers the entire 32-bit
//      address space in one 5-byte instruction. Thumb's widest PC-relative
//      branch (B.W) only reaches +/-16MB, which is not "everywhere" the way
//      x86's is. Rather than build near-allocation logic to keep a
//      trampoline inside that range, this engine uses the standard
//      ARM-detour absolute-jump idiom instead:
//
//          LDR.W PC, [PC, #0]     ; f8df f000
//          .word <target | 1>     ; the 1 is the interworking bit -- see below
//
//      8 bytes, unconditional, reaches any address, and -- because it loads
//      into PC rather than computing a PC-relative displacement -- carries
//      no range limit to reason about at all. That is 3 bytes more than
//      x86's kJmpRel32Size, which is why kPatchSize is 8, not 5.
//
//      One hazard this idiom carries that a plain branch would not: LDR
//      (literal)'s pseudocode computes its base as `Align(PC, 4)`, an
//      explicit round-DOWN to the nearest word boundary, not a no-op. If the
//      LDR.W itself lands at an address that is 2-mod-4 instead of 0-mod-4,
//      the processor reads the target word two bytes early -- the tail of
//      the LDR.W's own encoding stitched to the front half of the intended
//      target address -- and jumps to whatever garbage that produces. Every
//      site that writes this 8-byte pair (both the trampoline, at an offset
//      chosen by this file, and the target patch, at an address chosen by
//      the caller) has to either guarantee 4-byte alignment by construction
//      or refuse. See install()'s comments for how each site handles it.
//
//   2. INTERWORKING. x86 has no such thing -- code is code. Thumb and ARM
//      are two different instruction encodings for the same CPU, and
//      `LDR PC, [...]` uses bit 0 of the loaded value to choose which one
//      the processor switches into: 1 selects Thumb, 0 selects ARM. Every
//      function pointer this engine writes into that trampoline word --
//      the hook, and the "jump back to the original" target -- MUST have
//      bit 0 set, or the processor decodes the next instructions as ARM and
//      the result is immediate garbage. This file always operates in Thumb
//      mode and always sets that bit; it does not support hooking or being
//      hooked by ARM-mode code.
//
// RELOCATION, simplified relative to x86's version. decode.hpp's allowlist
// already refuses every PC-relative or otherwise positional instruction
// (literal loads, ADR, branches, POP/LDM into PC, MCR/MRC naming PC) rather
// than widen them, so there is no second relocation pass here the way x86's
// engine has for rel8->rel32: every instruction this engine agrees to steal
// is, by construction, safe to copy byte-for-byte to a different address.
// If a function's first few instructions are not made entirely of
// `relocatable == true` pieces, install() refuses rather than improvise --
// same discipline, simpler mechanism.
#pragma once

#include <stddef.h>
#include <stdint-gcc.h>

#include "hooks/arm32/decode.hpp"

// A narrow, freestanding-safe restatement of the five kp::platform::
// functions trampoline.cpp needs (src/platform/platform.hpp's real
// declarations, same names, same signatures) rather than an #include of
// that header directly. platform.hpp pulls in the normal libstdc++ chain,
// which this subsystem cannot assume: the qemu self-test that is this
// code's only proof of correctness right now links with -nostdlib against
// a target that has no libstdc++ installed at all (see tools/
// kp_hooktool_arm32.cpp's header comment).
//
// This is a real seam, named rather than hidden: these declarations and
// platform.hpp's are kept text-identical by hand, but nothing enforces
// that, and no translation unit in this repo includes both headers today
// (this subsystem is standalone -- see the file-header note above). A
// future integration that links this against the real
// src/platform/platform_linux.cpp would hit a redefinition error the
// moment both headers landed in the same TU, and would need this file
// changed to include the real platform.hpp instead of restating it. That
// is deliberately left as follow-up work, not solved speculatively here.
namespace kp::platform {
enum class Protect { ReadExec, ReadWrite, ReadWriteExec };
bool set_protection(void* addr, size_t len, Protect);
void* alloc_exec(size_t len);
bool  commit_exec(void* addr, size_t len);
void  free_exec(void* addr, size_t len);
bool is_readable(const void* addr, size_t len);
void flush_instruction_cache(void* addr, size_t len);
enum class LogLevel { Debug, Info, Warn, Error };
void log(LogLevel, const char* fmt, ...);
}  // namespace kp::platform

namespace kp::hooks::arm32 {

inline constexpr size_t kPatchSize = 8;   // LDR.W PC,[PC,#0] + .word
inline constexpr size_t kMaxInsnLen = 4;  // Thumb-2's own hard ceiling
// Worst case: 7 bytes already stolen (just short of kPatchSize), then one
// more maximum-length instruction.
inline constexpr size_t kMaxStolen = kPatchSize + kMaxInsnLen - 1;

enum class HookStatus {
    Ok,
    BadArgs,
    AlreadyInstalled,
    NotInstalled,
    Unreadable,
    ByteMismatch,
    DecodeFailed,       // an instruction in the displaced range refused
                        // relocation (unrecognised, or a known-positional
                        // form -- decode.hpp's Insn::refusal names which)
    AllocFailed,
    ProtectFailed,
    Unaligned,          // target is not 4-byte aligned: writing the
                        // LDR.W PC,[PC,#0]+.word patch there would hit the
                        // Align(PC,4) hazard documented above the class
};

const char* to_string(HookStatus);

using TrampolineFn = void (*)(void* original, void* user);

// One installed detour. Same move-only ownership shape as the x86 Detour.
class Detour {
public:
    Detour() = default;
    ~Detour();

    Detour(const Detour&) = delete;
    Detour& operator=(const Detour&) = delete;
    Detour(Detour&&) noexcept;
    Detour& operator=(Detour&&) noexcept;

    // Install an absolute branch to `detour` at `target`. Both pointers are
    // Thumb function addresses -- do NOT pre-set bit 0 on them; install()
    // does that itself, uniformly, exactly once per address, so a caller
    // that already set it would silently double it away to bit 1 clear.
    //
    // `expect`/`expect_len` behave exactly as the x86 engine's install()
    // documents: supplied and mismatching means refuse, not patch-and-warn.
    HookStatus install(void* target, void* detour,
                       const uint8_t* expect = nullptr,
                       size_t expect_len = 0,
                       const char** detail = nullptr,
                       TrampolineFn on_trampoline = nullptr,
                       void* trampoline_user = nullptr);

    HookStatus uninstall();

    // Reaches the unmodified function. Callers must treat this exactly as
    // the x86 engine's original() is treated: call it, never the target
    // address, and never cache it across an uninstall.
    void* original() const { return trampoline_; }

    bool        installed() const { return installed_; }
    size_t stolen_bytes() const { return stolen_len_; }
    void*       target() const { return reinterpret_cast<void*>(target_ & ~uintptr_t(1)); }

private:
    void release();

    uintptr_t target_ = 0;   // Thumb bit already cleared for our own bookkeeping
    void*          detour_ = nullptr;
    void*          trampoline_ = nullptr;
    size_t    trampoline_size_ = 0;
    uint8_t   original_[kMaxStolen] = {};
    size_t    stolen_len_ = 0;
    bool           installed_ = false;
};

}  // namespace kp::hooks::arm32
