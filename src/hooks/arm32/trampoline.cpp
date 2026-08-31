#include "hooks/arm32/trampoline.hpp"

// Not <string.h>/<cstring>: neither exists for the freestanding ARM target
// this file's only build proof (tools/kp_hooktool_arm32.cpp) compiles
// against (no libc sysroot at all -- see that file's header comment). These
// three declarations match the standard library's exactly and are
// satisfied there by that file's own freestanding definitions; a normal
// (non-freestanding) build satisfies them from libc as usual, since a
// libc-provided memcpy/memcmp has the identical signature and calling
// convention.
extern "C" void* memcpy(void* dst, const void* src, size_t n);
extern "C" int   memcmp(const void* a, const void* b, size_t n);

// Uses kp::platform::* exactly as src/hooks/trampoline.cpp does, not because
// this file has been wired into the real runtime (it has not -- see
// trampoline.hpp's header note), but so that it already speaks the one
// memory-management interface the rest of this codebase uses. The
// freestanding qemu self-test in tools/kp_hooktool_arm32.cpp supplies its
// own implementation of these same five functions (raw Linux syscalls, no
// libc), which is what proves this file's logic independently of whether a
// real platform_linux.cpp happens to be linked in.

namespace kp::hooks::arm32 {

const char* to_string(HookStatus s) {
    switch (s) {
        case HookStatus::Ok:               return "ok";
        case HookStatus::BadArgs:          return "bad arguments";
        case HookStatus::AlreadyInstalled: return "already installed";
        case HookStatus::NotInstalled:     return "not installed";
        case HookStatus::Unreadable:       return "target address is not mapped";
        case HookStatus::ByteMismatch:     return "original bytes did not match";
        case HookStatus::DecodeFailed:     return "could not decode/relocate displaced instructions";
        case HookStatus::AllocFailed:      return "executable allocation failed";
        case HookStatus::ProtectFailed:    return "page protection change failed";
    }
    return "?";
}

Detour::~Detour() {
    if (installed_) uninstall();
    release();
}

Detour::Detour(Detour&& other) noexcept { *this = static_cast<Detour&&>(other); }

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
    memcpy(original_, other.original_, sizeof(original_));

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

namespace {

void write_u32le(uint8_t* p, uint32_t v) { memcpy(p, &v, 4); }

// f8df f000 = LDR.W PC, [PC, #0]. Byte order matters here in a way it does
// not for a plain data word: Thumb-2 instructions are two little-endian
// HALFWORDS stored in their own encoded order, not one little-endian
// 32-bit word, so this is {0xdf, 0xf8, 0x00, 0xf0} on the wire, not a
// straight byte-reverse of 0xf8dff000.
void write_ldr_pc_pc0(uint8_t* p) {
    p[0] = 0xDF; p[1] = 0xF8; p[2] = 0x00; p[3] = 0xF0;
}

}  // namespace

HookStatus Detour::install(void* target, void* detour,
                           const uint8_t* expect, size_t expect_len,
                           const char** detail) {
    auto explain = [&](const char* text) { if (detail) *detail = text; };

    if (!target || !detour) {
        explain("target or detour is null");
        return HookStatus::BadArgs;
    }
    if (installed_) {
        explain("this Detour already holds an installed hook");
        return HookStatus::AlreadyInstalled;
    }

    // Callers pass plain Thumb code addresses, bit 0 clear -- exactly like a
    // C function pointer to a Thumb function looks once you strip the
    // interworking convention back out. This engine clears it defensively
    // (in case a caller got it from somewhere that already set it) and adds
    // it back exactly once, at the one place it is actually needed: writing
    // an address into the LDR.W PC target word.
    const auto target_addr =
        reinterpret_cast<uintptr_t>(target) & ~uintptr_t(1);
    const auto* code = reinterpret_cast<const uint8_t*>(target_addr);

    if (!platform::is_readable(code, kMaxStolen)) {
        explain("target address is not mapped");
        return HookStatus::Unreadable;
    }

    if (expect && expect_len) {
        if (expect_len > kMaxStolen || memcmp(code, expect, expect_len) != 0) {
            explain("expected bytes did not match the target");
            return HookStatus::ByteMismatch;
        }
    }

    // --- decode far enough to cover the 8-byte patch --------------------
    //
    // No relocation-with-fixup pass, unlike x86: decode.hpp's allowlist
    // already refuses anything positional, so every accepted instruction is
    // safe to memcpy verbatim. The only thing this loop computes is how
    // many whole instructions it takes to reach or exceed kPatchSize.
    size_t stolen = 0;
    while (stolen < kPatchSize) {
        const Insn in = decode(code + stolen, kMaxStolen - stolen);
        if (!in.valid || !in.relocatable) {
            explain(in.refusal ? in.refusal : "decode failed");
            return HookStatus::DecodeFailed;
        }
        stolen += in.length;
    }

    // --- trampoline: stolen bytes, verbatim, then jump back -------------

    const size_t tramp_size = stolen + kPatchSize;
    auto* tramp = static_cast<uint8_t*>(platform::alloc_exec(tramp_size));
    if (!tramp) {
        explain("could not allocate executable memory for the trampoline");
        return HookStatus::AllocFailed;
    }

    memcpy(tramp, code, stolen);
    write_ldr_pc_pc0(tramp + stolen);
    write_u32le(tramp + stolen + 4,
               static_cast<uint32_t>((target_addr + stolen) | 1u));

    if (!platform::commit_exec(tramp, tramp_size)) {
        platform::free_exec(tramp, tramp_size);
        explain("could not make the trampoline executable");
        return HookStatus::ProtectFailed;
    }
    platform::flush_instruction_cache(tramp, tramp_size);

    // --- patch the target -------------------------------------------------

    memcpy(original_, code, stolen);

    if (!platform::set_protection(const_cast<uint8_t*>(code), stolen,
                                  platform::Protect::ReadWrite)) {
        platform::free_exec(tramp, tramp_size);
        explain("could not make the target writable");
        return HookStatus::ProtectFailed;
    }

    auto* patch = const_cast<uint8_t*>(code);
    write_ldr_pc_pc0(patch);
    write_u32le(patch + 4,
               static_cast<uint32_t>(reinterpret_cast<uintptr_t>(detour) | 1u));
    // Nothing pads the remainder the way x86's NOP fill does: kPatchSize
    // (8) is a whole-instruction boundary by construction (the loop above
    // only stops once `stolen` has consumed complete instructions), so
    // there is no partial-instruction tail left dangling here at all.

    if (!platform::set_protection(patch, stolen, platform::Protect::ReadExec)) {
        platform::log(platform::LogLevel::Warn,
                      "arm32 detour at %p installed, but the page could not be "
                      "returned to R+X",
                      patch);
    }
    platform::flush_instruction_cache(patch, stolen);

    target_          = target_addr;
    detour_          = detour;
    trampoline_      = tramp;
    trampoline_size_ = tramp_size;
    stolen_len_      = stolen;
    installed_       = true;
    return HookStatus::Ok;
}

HookStatus Detour::uninstall() {
    if (!installed_) return HookStatus::NotInstalled;

    auto* patch = reinterpret_cast<uint8_t*>(target_);
    if (!platform::set_protection(patch, stolen_len_, platform::Protect::ReadWrite)) {
        return HookStatus::ProtectFailed;
    }
    memcpy(patch, original_, stolen_len_);
    if (!platform::set_protection(patch, stolen_len_, platform::Protect::ReadExec)) {
        platform::log(platform::LogLevel::Warn,
                      "arm32 detour at %p uninstalled, but the page could not "
                      "be returned to R+X",
                      patch);
    }
    platform::flush_instruction_cache(patch, stolen_len_);

    installed_ = false;
    release();
    return HookStatus::Ok;
}

}  // namespace kp::hooks::arm32
