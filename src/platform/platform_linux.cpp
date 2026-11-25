// Linux/ELF implementation. Target: the native 32-bit TSL binary, and the
// standalone hook tool that proves the engine against its own process.

#include "platform/platform.hpp"

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <string>
#include <utility>

#include <sys/mman.h>
#include <unistd.h>

namespace kp::platform {
namespace {

std::size_t page_size() {
    static const std::size_t ps = static_cast<std::size_t>(::sysconf(_SC_PAGESIZE));
    return ps;
}

int to_prot(Protect p) {
    switch (p) {
        case Protect::ReadExec:      return PROT_READ | PROT_EXEC;
        case Protect::ReadWrite:     return PROT_READ | PROT_WRITE;
        case Protect::ReadWriteExec: return PROT_READ | PROT_WRITE | PROT_EXEC;
    }
    return PROT_READ;
}

// Round the request out to whole pages. mprotect rejects an unaligned start
// outright, and silently covering only the first page would leave the tail of a
// boundary-straddling patch read-only -- a fault at write time, in the middle of
// a half-applied patch, which is the worst possible place to discover it.
std::pair<void*, std::size_t> page_span(void* addr, std::size_t len) {
    const std::size_t ps = page_size();
    const auto raw = reinterpret_cast<std::uintptr_t>(addr);
    if (len == 0 || ps == 0) return {nullptr, 0};
    const std::uintptr_t max_addr = std::numeric_limits<std::uintptr_t>::max();
    if (len - 1 > static_cast<std::size_t>(max_addr - raw)) return {nullptr, 0};
    const std::uintptr_t last = raw + (len - 1);
    const std::uintptr_t start = raw & ~static_cast<std::uintptr_t>(ps - 1);
    const std::uintptr_t end_page = last & ~static_cast<std::uintptr_t>(ps - 1);
    if (end_page > max_addr - ps) return {nullptr, 0};
    const std::uintptr_t end = end_page + ps;
    return {reinterpret_cast<void*>(start), static_cast<std::size_t>(end - start)};
}

std::string basename_of(const std::string& path) {
    const auto slash = path.find_last_of('/');
    return slash == std::string::npos ? path : path.substr(slash + 1);
}

}  // namespace

bool set_protection(void* addr, std::size_t len, Protect p) {
    if (!addr || len == 0) return false;
    const auto [start, span] = page_span(addr, len);
    if (span == 0) return false;
    if (::mprotect(start, span, to_prot(p)) != 0) {
        log(LogLevel::Error, "mprotect(%p, %zu) failed: %s",
            start, span, std::strerror(errno));
        return false;
    }
    return true;
}

static std::size_t round_to_pages(std::size_t len) {
    const std::size_t ps = page_size();
    return (len + ps - 1) & ~(ps - 1);
}

void* alloc_exec(std::size_t len) {
    if (len == 0) return nullptr;
    // Writable but NOT executable. commit_exec flips it. See the header for why
    // this is two calls instead of one.
    void* p = ::mmap(nullptr, round_to_pages(len), PROT_READ | PROT_WRITE,
                     MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (p == MAP_FAILED) {
        log(LogLevel::Error, "mmap(%zu) failed: %s", len, std::strerror(errno));
        return nullptr;
    }
    return p;
}

bool commit_exec(void* addr, std::size_t len) {
    return set_protection(addr, len, Protect::ReadExec);
}

void free_exec(void* addr, std::size_t len) {
    if (!addr) return;
    ::munmap(addr, round_to_pages(len));
}

bool is_readable(const void* addr, std::size_t len) {
    if (!addr || len == 0) return false;
    // msync reports ENOMEM for an address range that is not mapped, which makes
    // it a probe that costs one syscall and cannot itself fault. It says nothing
    // about read permission, but PROT_NONE code pages do not occur in either
    // target -- the case that actually happens is a wholly wrong address.
    const auto [start, span] = page_span(const_cast<void*>(addr), len);
    if (span == 0) return false;
    return ::msync(start, span, MS_ASYNC) == 0 || errno != ENOMEM;
}

bool is_writable(const void* addr, std::size_t len) {
    if (!addr || len == 0) return false;
    const auto raw = reinterpret_cast<std::uintptr_t>(addr);
    const std::uintptr_t max_addr = std::numeric_limits<std::uintptr_t>::max();
    if (len - 1 > static_cast<std::size_t>(max_addr - raw)) return false;
    const unsigned long long want_start = raw;
    const unsigned long long want_end = raw + (len - 1);

    std::FILE* f = std::fopen("/proc/self/maps", "r");
    if (!f) return false;
    unsigned long long cursor = want_start;
    char line[1024];
    while (std::fgets(line, sizeof(line), f)) {
        unsigned long long start = 0, end = 0;
        char perms[8] = {0};
        if (std::sscanf(line, "%llx-%llx %7s", &start, &end, perms) < 3) continue;
        if (end <= cursor) continue;
        if (start > cursor) break;
        if (perms[1] != 'w') break;
        if (end - 1 >= want_end) {
            std::fclose(f);
            return true;
        }
        cursor = end;
    }
    std::fclose(f);
    return false;
}

void flush_instruction_cache(void* addr, std::size_t len) {
    auto* p = static_cast<char*>(addr);
    __builtin___clear_cache(p, p + len);
}

std::uintptr_t module_base(const char* name) {
    // /proc/self/maps rather than dl_iterate_phdr: the ELF target is EXEC (not
    // PIE) and the interesting case is "where did the loader put this file",
    // which maps answers directly for the main image and every shared object,
    // including ones we never linked against.
    std::FILE* f = std::fopen("/proc/self/maps", "r");
    if (!f) return 0;

    const std::string want = (name && *name) ? basename_of(name) : std::string();
    std::uintptr_t found = 0;
    char line[1024];

    while (std::fgets(line, sizeof(line), f)) {
        unsigned long long start = 0, end = 0;
        char perms[8] = {0};
        char path[512] = {0};
        // The path is optional (anonymous mappings have none), so a short scan
        // is expected, not an error.
        const int fields = std::sscanf(line, "%llx-%llx %7s %*s %*s %*s %511[^\n]",
                                       &start, &end, perms, path);
        if (fields < 3) continue;
        (void)end;

        std::string mapped = (fields >= 4) ? path : std::string();
        // sscanf's %[^\n] keeps the leading spaces the maps format pads with.
        const auto first = mapped.find_first_not_of(' ');
        mapped = (first == std::string::npos) ? std::string() : mapped.substr(first);
        if (mapped.empty() || mapped.front() == '[') continue;

        if (want.empty()) {
            // Main image: the first file-backed mapping is the one the ELF
            // headers were loaded from, and its start is the load base.
            static std::string self_path;
            if (self_path.empty()) {
                char buf[512];
                const ssize_t n = ::readlink("/proc/self/exe", buf, sizeof(buf) - 1);
                if (n > 0) { buf[n] = '\0'; self_path = buf; }
            }
            if (mapped == self_path) {
                found = static_cast<std::uintptr_t>(start);
                break;
            }
        } else if (basename_of(mapped) == want) {
            found = static_cast<std::uintptr_t>(start);
            break;
        }
    }

    std::fclose(f);
    return found;
}

}  // namespace kp::platform
