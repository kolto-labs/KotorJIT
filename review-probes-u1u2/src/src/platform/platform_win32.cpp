// Win32/PE implementation. Target: swkotor.exe, running natively or under Wine.
//
// Wine matters to the details here. VirtualProtect and VirtualAlloc are fully
// implemented by Wine, so nothing in this file behaves differently there. The
// parts of the runtime that do care about Wine are elsewhere: the binkw32 proxy
// (which only works because Wine ships no builtin binkw32) and the wait for the
// DRM stub to decipher .text.

#include "platform/platform.hpp"

#include <cctype>
#include <cstdio>
#include <cstring>

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <tlhelp32.h>

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

// GetProcAddress hands back FARPROC; copy the bits into the real signature
// rather than casting between function types (-Wcast-function-type).
template <class Function>
Function proc(HMODULE module, const char* name) {
    FARPROC address = module ? ::GetProcAddress(module, name) : nullptr;
    Function result = nullptr;
    static_assert(sizeof(result) == sizeof(address));
    std::memcpy(&result, &address, sizeof(result));
    return result;
}

// Lowercase ASCII base name of a wide module name. Non-ASCII becomes '?':
// the match patterns are ASCII and the log line should stay ASCII too.
void base_name(const wchar_t* in, char* out, std::size_t len) {
    std::size_t n = 0;
    for (; *in && n + 1 < len; ++in) {
        const wchar_t c = *in;
        char ch = c < 128 ? static_cast<char>(std::tolower(static_cast<int>(c))) : '?';
        // Space-delimited log line, comma-separated list: keep each name one token.
        if (ch == ' ' || ch == '\t' || ch == ',') ch = '_';
        out[n++] = ch;
    }
    out[n] = '\0';
}

bool is_overlay(const char* name) {
    return std::strncmp(name, "galaxy", 6) == 0 ||
           std::strstr(name, "overlay") != nullptr ||
           std::strncmp(name, "nvspcap", 7) == 0;
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

HostIdentity host_identity() {
    HostIdentity id;
    HMODULE ntdll = ::GetModuleHandleA("ntdll.dll");

    using WineVersion = const char*(__cdecl*)();
    if (auto wine = proc<WineVersion>(ntdll, "wine_get_version")) {
        id.wine = true;
        const char* v = wine();
        std::snprintf(id.wine_version, sizeof id.wine_version, "%s", v ? v : "?");
        // The log line is space-delimited; keep this one token.
        for (char* c = id.wine_version; *c; ++c)
            if (*c == ' ' || *c == '\t' || *c == ',') *c = '_';
    }

    // LONG, not NTSTATUS: the latter is not declared under WIN32_LEAN_AND_MEAN.
    using RtlGetVersion = LONG(WINAPI*)(OSVERSIONINFOW*);
    if (auto get = proc<RtlGetVersion>(ntdll, "RtlGetVersion")) {
        OSVERSIONINFOW info{};
        info.dwOSVersionInfoSize = sizeof info;
        if (get(&info) == 0) {
            id.os_major = info.dwMajorVersion;
            id.os_minor = info.dwMinorVersion;
            id.os_build = info.dwBuildNumber;
        }
    }

    // Toolhelp rather than EnumProcessModules: it lives in kernel32, so the DLL
    // gains no psapi import.
    HANDLE snap = ::CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, ::GetCurrentProcessId());
    if (snap != INVALID_HANDLE_VALUE) {
        MODULEENTRY32W entry{};
        entry.dwSize = sizeof entry;
        std::size_t used = 0;
        for (BOOL ok = ::Module32FirstW(snap, &entry); ok; ok = ::Module32NextW(snap, &entry)) {
            char name[MAX_MODULE_NAME32 + 1];
            base_name(entry.szModule, name, sizeof name);
            if (!is_overlay(name)) continue;
            const int wrote = std::snprintf(id.overlays + used, sizeof id.overlays - used,
                                            "%s%s", used ? "," : "", name);
            if (wrote < 0 || static_cast<std::size_t>(wrote) >= sizeof id.overlays - used) break;
            used += static_cast<std::size_t>(wrote);
        }
        ::CloseHandle(snap);
    }
    return id;
}

void format_host_identity(const HostIdentity& id, char* out, std::size_t len) {
    if (!out || len == 0) return;
    std::snprintf(out, len, "host: wine=%s wine_version=%s os=%lu.%lu.%lu overlays=%s",
                  id.wine ? "yes" : "no", id.wine_version[0] ? id.wine_version : "-",
                  id.os_major, id.os_minor, id.os_build,
                  id.overlays[0] ? id.overlays : "-");
}

}  // namespace kp::platform
