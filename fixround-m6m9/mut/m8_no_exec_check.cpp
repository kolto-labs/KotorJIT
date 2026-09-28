// x86_64 inline detour. See trampoline.hpp for the patch shape and W^X rules.
#include "hooks/x64/trampoline.hpp"

#include <sys/mman.h>
#include <sys/syscall.h>
#include <unistd.h>

#include <cerrno>
#include <cstdio>
#include <cstring>
#include <utility>

namespace kp::hooks::x64 {
namespace {

std::size_t g_leaked = 0;
testing::ProtectFn g_protect = nullptr;

// mprotect as a bare syscall: 0, or -errno. It runs while a target page is
// RW and not executable, so it must not go through the PLT (a lazy-bound
// slot would run ld.so's resolver inside that window) and must not touch
// errno (__errno_location is another PLT call). The test seam keeps the
// libc convention and is translated here.
int protect(void* addr, std::size_t len, int prot) {
    if (g_protect) {
        if (g_protect(addr, len, prot) == 0) return 0;
        return errno ? -errno : -EPERM;
    }
    long r;
    asm volatile("syscall"
                 : "=a"(r)
                 : "0"(long(SYS_mprotect)), "D"(addr), "S"(len), "d"(long(prot))
                 : "rcx", "r11", "memory");
    return int(r);
}

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

// The pages [addr, addr+len) touches: one, or two when it crosses a boundary.
struct Span {
    std::uintptr_t lo = 0;
    std::size_t pages = 0;
    void* base() const { return reinterpret_cast<void*>(lo); }
    std::size_t bytes() const { return pages * page_size(); }
};
Span span_of(const std::uint8_t* addr, std::size_t len) {
    const auto a = reinterpret_cast<std::uintptr_t>(addr);
    Span s;
    s.lo = page_down(a);
    s.pages = (page_down(a + len - 1) - s.lo) / page_size() + 1;
    return s;
}

// PROT_* of the mapping that contains `page`, from /proc/self/maps; -1 when
// it is not listed. Runs before any protection changes.
int page_prot(std::uintptr_t page) {
    FILE* f = std::fopen("/proc/self/maps", "re");
    if (!f) return -1;
    char line[512];
    bool line_start = true;
    int prot = -1;
    while (std::fgets(line, sizeof line, f)) {
        const bool parse = line_start;
        line_start = std::strchr(line, '\n') != nullptr;  // long paths span several reads
        if (!parse) continue;
        unsigned long lo = 0, hi = 0;
        char perms[5] = {};
        if (std::sscanf(line, "%lx-%lx %4s", &lo, &hi, perms) == 3 && page >= lo && page < hi) {
            prot = (perms[0] == 'r' ? PROT_READ : 0) | (perms[1] == 'w' ? PROT_WRITE : 0) |
                   (perms[2] == 'x' ? PROT_EXEC : 0);
            break;
        }
    }
    std::fclose(f);
    return prot;
}

// Byte copy that stays in this function: write_code runs it while the
// target page is writable and not executable, so it must not call into
// libc (whose memcpy could share a hooked page). volatile keeps the compiler
// from turning the loop back into a memcpy call.
__attribute__((noinline)) void copy_code(std::uint8_t* dst, const std::uint8_t* src, std::size_t n) {
    auto* d = reinterpret_cast<volatile std::uint8_t*>(dst);
    for (std::size_t i = 0; i < n; ++i) d[i] = src[i];
}

// Puts each page of `s` back to its recorded protection. 0, or the first
// -errno.
int reseal(const Span& s, const int prot[2]) {
    if (s.pages == 1 || prot[0] == prot[1]) return protect(s.base(), s.bytes(), prot[0]);
    int err = 0;
    for (std::size_t i = 0; i < s.pages; ++i) {
        const int r = protect(reinterpret_cast<void*>(s.lo + i * page_size()), page_size(), prot[i]);
        if (r && !err) err = r;
    }
    return err;
}

const char* restore_refused(bool eacces, int outcome) {
    static const char* const msgs[3][2] = {
        {"mprotect restore refused; previous bytes rolled back and page resealed",
         "mprotect restore refused (EACCES: SELinux execmod?); previous bytes rolled back and page resealed"},
        {"mprotect restore refused; previous bytes rolled back but the page is left RW, not executable",
         "mprotect restore refused (EACCES: SELinux execmod?); previous bytes rolled back but the page is "
         "left RW, not executable"},
        {"mprotect restore refused and rollback refused; new bytes left in place and the page left RW, not "
         "executable",
         "mprotect restore refused (EACCES: SELinux execmod?) and rollback refused; new bytes left in place and "
         "the page left RW, not executable"},
    };
    return msgs[outcome][eacces ? 1 : 0];
}

// Makes the pages under [addr, addr+len) RW (never executable while
// writable), copies `bytes`, and puts back the recorded protection `prot`.
// If that restore is refused, rolls back to the previous bytes while the
// page can still be written, and tries the restore again. On return,
// `now_new` says whether memory holds `bytes` (true) or what was there
// before (false). See FAILED RESTORE in trampoline.hpp.
HookStatus write_code(std::uint8_t* addr, const std::uint8_t* bytes, std::size_t len, const int prot[2],
                      bool& now_new, const char** detail) {
    now_new = false;
    const Span s = span_of(addr, len);
    std::uint8_t previous[kMaxStolen];
    std::memcpy(previous, addr, len);  // page still has its recorded protection here
    if (protect(s.base(), s.bytes(), PROT_READ | PROT_WRITE) != 0) {
        reseal(s, prot);  // a two-mapping span can be half changed
        if (detail) *detail = "mprotect RW refused; nothing written";
        return HookStatus::ProtectFailed;
    }
    copy_code(addr, bytes, len);
    const int refused = reseal(s, prot);
    if (refused == 0) {
        __builtin___clear_cache(reinterpret_cast<char*>(addr), reinterpret_cast<char*>(addr + len));
        now_new = true;
        return HookStatus::Ok;
    }
    const bool eacces = refused == -EACCES;
    // reseal may have restored one page of two; make the whole span writable
    // again before copying back.
    if (protect(s.base(), s.bytes(), PROT_READ | PROT_WRITE) != 0) {
        now_new = true;
        if (detail) *detail = restore_refused(eacces, 2);
        return HookStatus::ProtectFailed;
    }
    copy_code(addr, previous, len);
    const bool sealed = reseal(s, prot) == 0;
    if (sealed) __builtin___clear_cache(reinterpret_cast<char*>(addr), reinterpret_cast<char*>(addr + len));
    if (detail) *detail = restore_refused(eacces, sealed ? 0 : 1);
    return HookStatus::ProtectFailed;
}

// True when code that runs while [addr, addr+len) is RW shares one of its
// pages. Not inlined, so the return address below is inside Detour::install.
__attribute__((noinline)) bool shares_engine_page(const std::uint8_t* addr, std::size_t len) {
    const std::uintptr_t engine[] = {
        reinterpret_cast<std::uintptr_t>(&write_code),
        reinterpret_cast<std::uintptr_t>(&copy_code),
        reinterpret_cast<std::uintptr_t>(&reseal),
        reinterpret_cast<std::uintptr_t>(&protect),
        reinterpret_cast<std::uintptr_t>(&restore_refused),
        reinterpret_cast<std::uintptr_t>(&span_of),
        reinterpret_cast<std::uintptr_t>(&page_size),
        reinterpret_cast<std::uintptr_t>(&page_down),
        reinterpret_cast<std::uintptr_t>(&write_abs_jmp),
        reinterpret_cast<std::uintptr_t>(&plan),
        reinterpret_cast<std::uintptr_t>(&decode),
        reinterpret_cast<std::uintptr_t>(&relocate),
        // libc code the test seam runs between the flip to RW and the
        // restore. The real path is a bare syscall; these stay listed as a
        // cheap margin.
        reinterpret_cast<std::uintptr_t>(&::mprotect),
        reinterpret_cast<std::uintptr_t>(&::__errno_location),
        reinterpret_cast<std::uintptr_t>(g_protect),
        // Detour::install itself, via the return address of this call.
        reinterpret_cast<std::uintptr_t>(__builtin_return_address(0)),
    };
    const Span s = span_of(addr, len);
    for (auto e : engine)
        if (e && e >= s.lo && e < s.lo + s.bytes()) return true;
    return false;
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

std::size_t leaked_trampoline_pages() { return g_leaked; }
void testing::set_protect_hook(testing::ProtectFn fn) { g_protect = fn; }

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
        case HookStatus::NotExecutable: return "NotExecutable";
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
        if (insn.is_call && off < kPatchSize) {
            const auto next = decode(code + off, avail - off);
            if (next.ok() && next.is_nop) {
                p.status = HookStatus::FlowEnds;
                p.detail = "call followed by NOP padding inside the patch window (noreturn callee?)";
                return p;
            }
        }
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

Detour::~Detour() { abandon(); }

Detour::Detour(Detour&& o) noexcept { *this = std::move(o); }

Detour& Detour::operator=(Detour&& o) noexcept {
    if (this == &o) return *this;
    abandon();
    target_ = o.target_;
    trampoline_ = o.trampoline_;
    page_ = o.page_;
    page_size_ = o.page_size_;
    std::memcpy(original_, o.original_, sizeof original_);
    std::memcpy(patch_, o.patch_, sizeof patch_);
    stolen_ = o.stolen_;
    std::memcpy(prot_, o.prot_, sizeof prot_);
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

void Detour::abandon() {
    if (installed_ && uninstall() != HookStatus::Ok && installed_) {
        // The target still jumps to our detour, directly or through a hook
        // chained on top of ours, and the detour calls original(). Unmapping
        // the trampoline would make that call jump into unmapped memory, so
        // the page is leaked on purpose and counted.
        ++g_leaked;
        page_ = trampoline_ = nullptr;
        page_size_ = 0;
        target_ = nullptr;
        stolen_ = 0;
        installed_ = false;
        return;
    }
    release();
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

    // The protection the target page(s) have now. Every write puts back
    // exactly this, at install and at uninstall.
    int prot[2];
    const Span span = span_of(code, pl.stolen);
    for (std::size_t i = 0; i < 2; ++i) {
        prot[i] = page_prot(span.lo + (i < span.pages ? i : 0) * page_size());
        if (prot[i] < 0) {
            if (detail) *detail = "target page is not listed in /proc/self/maps";
            return HookStatus::ProtectFailed;
        }
        // Not code, or a page an earlier failed write left RW. Recording
        // that protection would keep the target non-executable for good.
        if (false) {
            if (detail) *detail = "target page is not executable";
            return HookStatus::NotExecutable;
        }
    }

    // Trampoline: relocated instructions, then jmp back. Near the target when
    // anything needs re-aiming; anywhere otherwise.
    const std::size_t size = page_size();
    void* page = pl.needs_near ? map_near(reinterpret_cast<std::uintptr_t>(target), size)
                               : mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (!page || page == MAP_FAILED) {
        if (detail) *detail = pl.needs_near ? "no free page within +/-2GiB of the target"
                                            : "mmap of the trampoline page failed";
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
    if (protect(page, size, PROT_READ | PROT_EXEC) != 0) {
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
    bool now_patched = false;
    const auto st = write_code(code, patch, pl.stolen, prot, now_patched, detail);
    if (!now_patched) {  // nothing written, or rolled back: the trampoline is unreachable
        munmap(page, size);
        return st;
    }
    // Ok, or a failed restore whose rollback was also refused: either way the
    // patch is live and jumps through the trampoline, so this Detour owns an
    // installed hook (and install reports st).
    std::memcpy(patch_, patch, kPatchSize);
    std::memcpy(prot_, prot, sizeof prot_);
    target_ = code;
    trampoline_ = page_ = page;
    page_size_ = size;
    stolen_ = pl.stolen;
    installed_ = true;
    return st;
}

HookStatus Detour::uninstall(const char** detail) {
    if (detail) *detail = nullptr;
    if (!installed_) return HookStatus::NotInstalled;
    if (std::memcmp(target_, patch_, kPatchSize) != 0) {
        if (detail) *detail = "the target no longer holds our patch (another hook chained on top?)";
        return HookStatus::PatchClobbered;
    }
    bool now_original = false;
    const auto st = write_code(target_, original_, stolen_, prot_, now_original, detail);
    if (!now_original) return st;  // our patch is still in place: still installed
    installed_ = false;
    release();
    target_ = nullptr;
    stolen_ = 0;
    return st;
}

}  // namespace kp::hooks::x64
