// x86_64 inline detour: a 14-byte absolute jump at the target, the displaced
// instructions relocated into a trampoline that jumps back.
//
// Same contract as the i386 Detour in src/hooks/trampoline.hpp and the Thumb
// one in src/hooks/arm32/trampoline.hpp -- install/uninstall/original() mean
// the same thing -- but self-contained. It includes neither of those headers
// nor src/platform/platform.hpp, because kp_hooks is built -m32 and this
// engine is 64-bit only.
//
// PATCH. `FF 25 00000000` followed by the 8-byte destination: jmp [rip+0].
// It reaches any address, so the detour can live anywhere. The price is 14
// stolen bytes where i386 needs 5.
//
// TRAMPOLINE. Stolen instructions are copied and re-aimed (decode.hpp's
// relocate). A RIP-relative operand or rel32 branch keeps pointing at the
// same absolute address only if the trampoline sits within +/-2GiB of that
// address, so the trampoline page is mapped near the target with
// MAP_FIXED_NOREPLACE hints. The jump back uses the same 14-byte form. A
// relocated displacement that does not fit refuses; nothing is written.
//
// W^X. No page is ever writable and executable at once. The target page goes
// RX -> RW -> RX around the write, and the trampoline page is filled RW and
// then sealed RX. Because the target page is briefly not executable, no code
// that runs during install/uninstall may share it: install refuses when the
// patcher's own code is on that page, and callers must not hook a function
// that shares a page with the caller or with anything another thread may be
// executing. If the kernel refuses the RX restore (SELinux execmod, for
// example) the call reports ProtectFailed; it never falls back to RWX.
//
// Linux only. Not thread-safe: install/uninstall assume nothing else is
// executing the patched bytes.
#pragma once

#include <cstddef>
#include <cstdint>

#include "hooks/x64/decode.hpp"

namespace kp::hooks::x64 {

inline constexpr std::size_t kPatchSize = 14;
inline constexpr std::size_t kMaxStolen = kPatchSize + kMaxInsnLen - 1;

enum class HookStatus {
    Ok,
    BadArgs,
    AlreadyInstalled,
    NotInstalled,
    ByteMismatch,     // caller's expected bytes differ from the target
    DecodeFailed,     // an instruction in the stolen range refused
    BranchIntoPatch,  // a stolen instruction names an address inside the stolen range
    FlowEnds,         // ret/jmp before kPatchSize bytes: the next bytes may not be code
    OutOfRange,       // a relocated disp32/rel32 does not fit
    AllocFailed,
    ProtectFailed,
    UnsafePage,       // the patcher's own code shares the target page
    PatchClobbered,   // uninstall found something other than our patch
};

const char* to_string(HookStatus);

// Plans the stolen range without touching memory: how many bytes, and whether
// any instruction needs relocation. Exposed so tests can run it on synthetic
// prologues at any address.
struct Plan {
    std::size_t stolen = 0;
    bool needs_near = false;  // some instruction is RIP-relative or rel32
    HookStatus status = HookStatus::Ok;
    const char* detail = nullptr;
};
Plan plan(const std::uint8_t* code, std::size_t avail, std::uint64_t at);

class Detour {
public:
    Detour() = default;
    ~Detour();
    Detour(const Detour&) = delete;
    Detour& operator=(const Detour&) = delete;
    Detour(Detour&&) noexcept;
    Detour& operator=(Detour&&) noexcept;

    // Patch `target` to jump to `detour`. If `expect` is given, the target's
    // first expect_len bytes must match it or nothing is written.
    HookStatus install(void* target, void* detour,
                       const std::uint8_t* expect = nullptr,
                       std::size_t expect_len = 0,
                       const char** detail = nullptr);

    // Restores the original bytes after checking our patch is still there.
    HookStatus uninstall();

    // Calls the unmodified function. Do not cache it across uninstall.
    void* original() const { return trampoline_; }
    bool installed() const { return installed_; }
    std::size_t stolen_bytes() const { return stolen_; }
    void* trampoline_page() const { return page_; }

private:
    void release();

    std::uint8_t* target_ = nullptr;
    void* trampoline_ = nullptr;
    void* page_ = nullptr;
    std::size_t page_size_ = 0;
    std::uint8_t original_[kMaxStolen] = {};
    std::uint8_t patch_[kPatchSize] = {};
    std::size_t stolen_ = 0;
    bool installed_ = false;
};

}  // namespace kp::hooks::x64
