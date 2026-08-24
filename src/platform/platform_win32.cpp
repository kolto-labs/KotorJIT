// Win32/PE implementation. Target: swkotor.exe, running natively or under Wine.
//
// Wine matters to the details here. VirtualProtect and VirtualAlloc are fully
// implemented by Wine, so nothing in this file behaves differently there. The
// parts of the runtime that do care about Wine are elsewhere: the binkw32 proxy
// (which only works because Wine ships no builtin binkw32) and the wait for the
// DRM stub to decipher .text.

#include "platform/platform.hpp"

#include <cstring>

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

namespace kp::platform {
namespace {

DWORD to_prot(Protect p) {
    switch (p) {
        case Protect::ReadExec:      return PAGE_EXECUTE_READ;
        case Protect::ReadWrite:     return PAGE_READWRITE;
        case Protect::ReadWriteExec: return PAGE_EXECUTE_READWRITE;
    }
    return PAGE_READONLY;
}

}  // namespace

bool set_protection(void* addr, std::size_t len, Protect p) {
    if (!addr || len == 0) return false;
    // VirtualProtect already spans pages for us, unlike mprotect, so no manual
    // alignment is needed here. The out-parameter is mandatory even when the
    // caller does not want it, hence the throwaway local.
    DWORD previous = 0;
    if (!::VirtualProtect(addr, len, to_prot(p), &previous)) {
        log(LogLevel::Error, "VirtualProtect(%p, %zu) failed: %lu",
            addr, len, ::GetLastError());
        return false;
    }
    return true;
}

void* alloc_exec(std::size_t len) {
    if (len == 0) return nullptr;
    // Writable first, executable later -- see the header. On Windows this also
    // keeps us clear of anti-cheat and EMET-style policies that flag a fresh
    // PAGE_EXECUTE_READWRITE allocation as shellcode staging.
    void* p = ::VirtualAlloc(nullptr, len, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!p) {
        log(LogLevel::Error, "VirtualAlloc(%zu) failed: %lu", len, ::GetLastError());
    }
    return p;
}

bool commit_exec(void* addr, std::size_t len) {
    return set_protection(addr, len, Protect::ReadExec);
}

void free_exec(void* addr, std::size_t /*len*/) {
    // MEM_RELEASE requires a zero size and the exact base returned by
    // VirtualAlloc, which is why the length is ignored rather than forwarded.
    if (addr) ::VirtualFree(addr, 0, MEM_RELEASE);
}

bool is_readable(const void* addr, std::size_t len) {
    if (!addr || len == 0) return false;
    // VirtualQuery rather than the deprecated IsBadReadPtr: IsBadReadPtr probes
    // by touching the page, which trips guard pages and turns a stack-growth
    // guard into a spurious failure. VirtualQuery just asks the memory manager.
    auto cursor = reinterpret_cast<const std::uint8_t*>(addr);
    const auto* end = cursor + len;
    while (cursor < end) {
        MEMORY_BASIC_INFORMATION info{};
        if (::VirtualQuery(cursor, &info, sizeof(info)) == 0) return false;
        if (info.State != MEM_COMMIT) return false;
        const DWORD prot = info.Protect;
        if (prot & (PAGE_NOACCESS | PAGE_GUARD)) return false;
        // A range can span several regions, so step to the next one rather than
        // assuming the first answer covers the whole request.
        cursor = reinterpret_cast<const std::uint8_t*>(info.BaseAddress) + info.RegionSize;
    }
    return true;
}

void flush_instruction_cache(void* addr, std::size_t len) {
    ::FlushInstructionCache(::GetCurrentProcess(), addr, len);
}

std::uintptr_t module_base(const char* name) {
    // A PE module handle IS its load base -- that is the documented contract,
    // not a coincidence to be defended against.
    HMODULE h = ::GetModuleHandleA((name && *name) ? name : nullptr);
    return reinterpret_cast<std::uintptr_t>(h);
}

}  // namespace kp::platform
