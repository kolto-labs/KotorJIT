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
// MAP_FIXED_NOREPLACE hints. The search is centred on the target, not on the
// referents; a referent that is near the target's reach limit can refuse
// (OutOfRange) even when some other page would have fitted. The jump back
// uses the same 14-byte form. A relocated displacement that does not fit
// refuses; nothing is written.
//
// PLAN LIMITS. The walk stops at ret, traps, E9 and FF /4 (refused when they
// end before 14 bytes). A call (E8, FF /2) followed by NOP padding inside the
// window also refuses (FlowEnds): that is the tail of a noreturn wrapper and
// the bytes after the padding belong to the next function. int3 padding
// already refuses. Not detected: a noreturn call followed directly by the
// next function with no padding, and jumps from elsewhere into bytes 1..13.
//
// W^X. The engine never makes a page writable and executable at once. The
// protection the target page(s) had at install is read from /proc/self/maps
// and recorded; the page goes <recorded> -> RW -> <recorded> around each
// write, at install and at uninstall. A page that was already W+X (a JIT
// arena, say) is put back as it was found; the engine does not create one.
// The trampoline page is filled RW and then sealed RX.
//
// install refuses (NotExecutable) when a target page is not executable
// now: it is not code, or an earlier failed write left it RW (see FAILED
// RESTORE). Recording that protection would keep the target dead. It
// refuses (Unreadable) when a page it would read is unmapped or PROT_NONE.
// Both checks come from /proc/self/maps before any target byte is read:
// the expected-bytes compare and the plan only see the bytes on readable,
// executable pages (up to kMaxStolen). A function whose stolen bytes end
// before a guard page still installs.
//
// Because the target page is briefly not executable, no code that runs
// during the write may share it. install refuses (UnsafePage) when the
// target page holds the engine's write path, libc's mprotect or
// __errno_location, the mprotect test hook, or the caller of install. That
// is a sanity guard, not a proof: callers must not hook a function that
// shares a page with anything another thread may be executing.
//
// LAZY BINDING. Code in the RW window makes no PLT calls: mprotect is a
// bare syscall and errno is never read (the test seam excepted). A first
// call through a lazily bound PLT slot would run ld.so's resolver there,
// and the guard above does not cover ld.so's pages. Code outside the window
// (fopen of /proc/self/maps, mmap) may still bind lazily; the target is
// executable then.
//
// FAILED RESTORE. If the kernel refuses to restore the protection after the
// write (SELinux execmod, for example), the engine makes the page RW again,
// writes back the bytes that were there before, and retries the restore.
// It never falls back to RWX. Outcomes, all reported as ProtectFailed with a
// detail string:
//   * rolled back and resealed: memory is as it was before the call;
//   * rolled back, reseal refused again: the old bytes are in place but the
//     page stays RW, not executable. Real execmod denials land here, since
//     the page is already a modified private copy. Treat that page as dead;
//   * rollback refused too: the new bytes stay, and the target page(s) can
//     be left RW, not executable (a half-applied rollback flip can undo a
//     page the restore did reach). Calling the target then faults.
//     For install the patch is in place, so install returns ProtectFailed
//     with installed() true and keeps the trampoline; the target stays
//     uncallable until uninstall() succeeds, which puts back the original
//     bytes and the recorded protection. For uninstall the original bytes
//     are back, so the Detour is uninstalled and its trampoline released,
//     but nothing will make that page executable again: treat it as dead.
//     A later install on it refuses (NotExecutable).
//
// LIFETIME. If the destructor or move-assignment finds the hook still
// installed and uninstall() fails (PatchClobbered: another hook was chained
// on top; ProtectFailed), the trampoline page is leaked on purpose. Code
// that still reaches our detour, directly or through the other hook, calls
// original(); unmapping it would crash that call. leaked_trampoline_pages()
// counts these.
//
// Linux only. Not thread-safe: install/uninstall assume nothing else is
// executing the patched bytes. That assumption also covers the mapping
// itself: install reads /proc/self/maps and only then reads and writes the
// target bytes it described; uninstall never reads maps again, it writes to
// the mapping recorded at install. Another thread unmapping (or remapping)
// the target in between -- after install's read, or at any point before
// uninstall -- is a TOCTOU race this engine does not guard against: it is
// out of contract, not a checked refusal, and can fault instead of
// returning Unreadable.
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
    AllocFailed,      // no trampoline page (none free within +/-2GiB when relocation needs one)
    ProtectFailed,    // see FAILED RESTORE: installed() may still be true after install
    UnsafePage,       // the patcher's own code shares the target page
    PatchClobbered,   // uninstall found something other than our patch
    NotExecutable,    // a target page is not executable now (not code, or left dead by a failed write)
    Unreadable,       // a target page is unmapped or not readable (PROT_NONE)
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

    // Restores the original bytes and the recorded protection after checking
    // our patch is still there. On failure, installed() says whether the
    // patch is still in place (see FAILED RESTORE).
    HookStatus uninstall(const char** detail = nullptr);

    // Calls the unmodified function. Do not cache it across uninstall.
    void* original() const { return trampoline_; }
    bool installed() const { return installed_; }
    std::size_t stolen_bytes() const { return stolen_; }
    void* trampoline_page() const { return page_; }

private:
    void release();
    void abandon();  // uninstall if needed; leak the trampoline if that fails

    std::uint8_t* target_ = nullptr;
    void* trampoline_ = nullptr;
    void* page_ = nullptr;
    std::size_t page_size_ = 0;
    std::uint8_t original_[kMaxStolen] = {};
    std::uint8_t patch_[kPatchSize] = {};
    std::size_t stolen_ = 0;
    int prot_[2] = {};  // protection of the first and last target page at install
    bool installed_ = false;
};

// Trampoline pages this process has deliberately not unmapped. See ~Detour.
std::size_t leaked_trampoline_pages();

namespace testing {
// Replaces mprotect inside the engine. nullptr restores the real one. Test
// use only: lets the self-test make the kernel "refuse" a protection change.
using ProtectFn = int (*)(void*, std::size_t, int);
void set_protect_hook(ProtectFn);
}  // namespace testing

}  // namespace kp::hooks::x64
