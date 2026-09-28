// x86_64 inline detour. See trampoline.hpp for the patch shape and W^X rules.
#include "hooks/x64/trampoline.hpp"

#include <sys/mman.h>
#include <unistd.h>

#include <cerrno>
#include <cstring>
#include <utility>

namespace kp::hooks::x64 {
namespace {

// jmp [rip+0] ; .quad destination
void write_abs_jmp(std::uint8_t* at, std::uint64_t destination) {
    at[0] = 0xff;
    at[1] = 0x25;
    std::memset(at + 2, 0, 4);
    std::memcpy(at + 6, &destination, 8);
}

std::size_t page_size() {
    static const std::size_t size = std::size_t(sysconf(_SC_PAGESIZE));
    return size;
}

std::uintptr_t page_down(std::uintptr_t a) { return a & ~(std::uintptr_t(page_size()) - 1); }

// Makes [addr, addr+len) writable (not executable), copies, and seals it
// read+execute again. Never RWX.
HookStatus write_code(std::uint8_t* addr, const std::uint8_t* bytes, std::size_t len, const char** detail) {
    const auto lo = page_down(reinterpret_cast<std::uintptr_t>(addr));
    const auto hi = page_down(reinterpret_cast<std::uintptr_t>(addr) + len - 1) + page_size();
    auto* base = reinterpret_cast<void*>(lo);
    if (mprotect(base, hi - lo, PROT_READ | PROT_WRITE) != 0) {
        if (detail) *detail = "mprotect RW refused";
        return HookStatus::ProtectFailed;
    }
    std::memcpy(addr, bytes, len);
    if (mprotect(base, hi - lo, PROT_READ | PROT_EXEC) != 0) {
        if (detail) *detail = errno == EACCES ? "mprotect RX refused (EACCES: SELinux execmod?)"
                                              : "mprotect RX refused";
        return HookStatus::ProtectFailed;
    }
    __builtin___clear_cache(reinterpret_cast<char*>(addr), reinterpret_cast<char*>(addr + len));
    return HookStatus::Ok;
}

// True when any of the engine's own code shares a page with [addr, addr+len).
// That page is briefly not executable while it is patched.
bool shares_engine_page(const std::uint8_t* addr, std::size_t len) {
    const std::uintptr_t engine[] = {
        reinterpret_cast<std::uintptr_t>(&write_code),
        reinterpret_cast<std::uintptr_t>(&write_abs_jmp),
        reinterpret_cast<std::uintptr_t>(&plan),
        reinterpret_cast<std::uintptr_t>(&decode),
        reinterpret_cast<std::uintptr_t>(&relocate),
    };
    const auto lo = page_down(reinterpret_cast<std::uintptr_t>(addr));
    const auto hi = page_down(reinterpret_cast<std::uintptr_t>(addr) + len - 1) + page_size();
    for (auto e : engine)
        if (e >= lo && e < hi) return true;
    // Detour::install itself, via the return address of this call. One
    // address per function is a sanity guard, not a proof.
    const auto self = reinterpret_cast<std::uintptr_t>(__builtin_return_address(0));
    return self >= lo && self < hi;
}

// Maps one RW page within +/-2GiB of `near`, trying hints outward in 1MiB
// steps. Returns nullptr if none is free.
void* map_near(std::uintptr_t near, std::size_t size) {
    const std::uintptr_t step = 1u << 20, reach = 0x7ff00000u;
    const std::uintptr_t origin = near & ~(step - 1);
    for (std::uintptr_t d = 0; d < reach; d += step) {
        for (int sign = 0; sign < 2; ++sign) {
            if (d == 0 && sign) continue;
            std::uintptr_t hint;
            if (sign == 0) {
                if (origin > UINTPTR_MAX - d) continue;
                hint = origin + d;
            } else {
                if (origin < d + step) continue;
                hint = origin - d;
            }
            if (hint >= 0x0000800000000000ull) continue;  // user half only
            void* p = mmap(reinterpret_cast<void*>(hint), size, PROT_READ | PROT_WRITE,
                           MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
            if (p == MAP_FAILED) continue;
            if (reinterpret_cast<std::uintptr_t>(p) != hint) {  // kernel without FIXED_NOREPLACE
                munmap(p, size);
                continue;
            }
            return p;
        }
    }
    return nullptr;
}

}  // namespace

const char* to_string(HookStatus s) {
    switch (s) {
        case HookStatus::Ok: return "Ok";
        case HookStatus::BadArgs: return "BadArgs";
        case HookStatus::AlreadyInstalled: return "AlreadyInstalled";
        case HookStatus::NotInstalled: return "NotInstalled";
        case HookStatus::ByteMismatch: return "ByteMismatch";
        case HookStatus::DecodeFailed: return "DecodeFailed";
        case HookStatus::BranchIntoPatch: return "BranchIntoPatch";
        case HookStatus::FlowEnds: return "FlowEnds";
        case HookStatus::OutOfRange: return "OutOfRange";
        case HookStatus::AllocFailed: return "AllocFailed";
        case HookStatus::ProtectFailed: return "ProtectFailed";
        case HookStatus::UnsafePage: return "UnsafePage";
        case HookStatus::PatchClobbered: return "PatchClobbered";
    }
    return "?";
}

Plan plan(const std::uint8_t* code, std::size_t avail, std::uint64_t at) {
    Plan p;
    if (!code) { p.status = HookStatus::BadArgs; return p; }
    std::size_t off = 0;
    while (off < kPatchSize) {
        const auto insn = decode(code + off, avail - off);
        if (!insn.ok()) {
            p.status = HookStatus::DecodeFailed;
            p.detail = insn.refusal;
            return p;
        }
        if (insn.rel != Rel::None) p.needs_near = true;
        off += insn.len;
        if (insn.ends_flow && off < kPatchSize) {
            p.status = HookStatus::FlowEnds;
            p.detail = "unconditional jump before the patch window is filled";
            return p;
        }
    }
    // Second pass, now the stolen length is known: anything that names an
    // address inside the replaced bytes would land in the middle of the patch.
    for (std::size_t o = 0; o < off;) {
        const auto insn = decode(code + o, avail - o);
        if (insn.rel != Rel::None) {
            const auto r = referent(code + o, insn, at + o);
            if (r > at && r < at + off) {
                p.status = HookStatus::BranchIntoPatch;
                p.detail = "a stolen instruction names an address inside the stolen range";
                return p;
            }
        }
        o += insn.len;
    }
    p.stolen = off;
    return p;
}

Detour::~Detour() {
    if (installed_) uninstall();
    release();
}

Detour::Detour(Detour&& o) noexcept { *this = std::move(o); }

Detour& Detour::operator=(Detour&& o) noexcept {
    if (this == &o) return *this;
    if (installed_) uninstall();
    release();
    target_ = o.target_;
    trampoline_ = o.trampoline_;
    page_ = o.page_;
    page_size_ = o.page_size_;
    std::memcpy(original_, o.original_, sizeof original_);
    std::memcpy(patch_, o.patch_, sizeof patch_);
    stolen_ = o.stolen_;
    installed_ = o.installed_;
    o.target_ = nullptr;
    o.trampoline_ = o.page_ = nullptr;
    o.page_size_ = o.stolen_ = 0;
    o.installed_ = false;
    return *this;
}

void Detour::release() {
    if (page_) munmap(page_, page_size_);
    page_ = trampoline_ = nullptr;
    page_size_ = 0;
}

HookStatus Detour::install(void* target, void* detour, const std::uint8_t* expect,
                           std::size_t expect_len, const char** detail) {
    if (detail) *detail = nullptr;
    if (installed_) return HookStatus::AlreadyInstalled;
    if (!target || !detour || (expect_len && !expect) || expect_len > kMaxStolen) return HookStatus::BadArgs;
    auto* code = static_cast<std::uint8_t*>(target);
    const auto at = reinterpret_cast<std::uint64_t>(target);

    if (shares_engine_page(code, kMaxStolen)) {
        if (detail) *detail = "the detour engine's own code is on the target page";
        return HookStatus::UnsafePage;
    }
    if (expect && std::memcmp(code, expect, expect_len) != 0) {
        if (detail) *detail = "target bytes differ from the expected prologue";
        return HookStatus::ByteMismatch;
    }
    const auto pl = plan(code, kMaxStolen, at);
    if (pl.status != HookStatus::Ok) {
        if (detail) *detail = pl.detail;
        return pl.status;
    }

    // Trampoline: relocated instructions, then jmp back. Near the target when
    // anything needs re-aiming; anywhere otherwise.
    const std::size_t size = page_size();
    void* page = pl.needs_near ? map_near(reinterpret_cast<std::uintptr_t>(target), size)
                               : mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (!page || page == MAP_FAILED) {
        if (detail) *detail = "no free page within +/-2GiB of the target";
        return HookStatus::AllocFailed;
    }
    auto* tramp = static_cast<std::uint8_t*>(page);
    const auto tramp_at = reinterpret_cast<std::uint64_t>(tramp);
    std::size_t out = 0;
    for (std::size_t o = 0; o < pl.stolen;) {
        const auto insn = decode(code + o, pl.stolen - o);
        if (!insn.ok() || !relocate(code + o, at + o, insn, tramp + out, tramp_at + out)) {
            munmap(page, size);
            if (detail) *detail = insn.ok() ? "relocated displacement does not fit in 32 bits" : insn.refusal;
            return insn.ok() ? HookStatus::OutOfRange : HookStatus::DecodeFailed;
        }
        o += insn.len;
        out += insn.len;
    }
    write_abs_jmp(tramp + out, at + pl.stolen);
    if (mprotect(page, size, PROT_READ | PROT_EXEC) != 0) {
        munmap(page, size);
        if (detail) *detail = "mprotect RX on the trampoline refused";
        return HookStatus::ProtectFailed;
    }
    __builtin___clear_cache(reinterpret_cast<char*>(tramp), reinterpret_cast<char*>(tramp + out + kPatchSize));

    // Patch: jmp [rip+0] to the detour, the rest of the stolen range int3.
    std::uint8_t patch[kMaxStolen];
    std::memset(patch, 0xcc, sizeof patch);
    write_abs_jmp(patch, reinterpret_cast<std::uint64_t>(detour));
    std::memcpy(original_, code, pl.stolen);
    const auto st = write_code(code, patch, pl.stolen, detail);
    if (st != HookStatus::Ok) {
        munmap(page, size);
        return st;
    }
    std::memcpy(patch_, patch, kPatchSize);
    target_ = code;
    trampoline_ = page_ = page;
    page_size_ = size;
    stolen_ = pl.stolen;
    installed_ = true;
    return HookStatus::Ok;
}

HookStatus Detour::uninstall() {
    if (!installed_) return HookStatus::NotInstalled;
    if (std::memcmp(target_, patch_, kPatchSize) != 0) return HookStatus::PatchClobbered;
    const auto st = write_code(target_, original_, stolen_, nullptr);
    if (st != HookStatus::Ok) return st;
    installed_ = false;
    release();
    target_ = nullptr;
    stolen_ = 0;
    return HookStatus::Ok;
}

}  // namespace kp::hooks::x64
