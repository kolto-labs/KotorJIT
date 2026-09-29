// macOS implementation. Target: the x86_64 Steam builds of both games, which
// run natively on Intel Macs and under Rosetta 2 on Apple silicon.
//
// Three Darwin facts shape this file:
//
//  * There is no /proc. Protection and mapping questions go to the Mach VM
//    interface (mach_vm_region), which answers them without touching the
//    memory being asked about -- so a probe of a wrong address cannot fault.
//
//  * The game's __TEXT is mapped from a code-signed file. Both retail images
//    carry an ad-hoc-free signature with flags 0 (no hardened runtime, no
//    library validation) and a __TEXT maxprot of rwx, so a write to code is
//    permitted, but it has to be asked for as a copy-on-write of the file
//    page: mach_vm_protect with VM_PROT_COPY. Plain mprotect(RW) on such a
//    page can be refused; the retry here makes that a non-event.
//
//  * Under Rosetta the x86_64 process sees 4 KiB pages while the host uses
//    16 KiB. Rosetta tracks writes to translated code and retranslates, which
//    is what makes patching work there at all. Nothing in this layer depends
//    on the host page size: requests are expressed in the process's page size
//    and the kernel widens them.
#include "platform/platform.hpp"
#include "platform/target.hpp"

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <utility>

#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <sys/mman.h>
#include <sys/sysctl.h>
#include <unistd.h>

namespace kp::platform {
namespace {

std::size_t page_size() {
    static const std::size_t ps = static_cast<std::size_t>(::getpagesize());
    return ps;
}

vm_prot_t to_vm_prot(Protect p) {
    switch (p) {
        case Protect::ReadExec:      return VM_PROT_READ | VM_PROT_EXECUTE;
        case Protect::ReadWrite:     return VM_PROT_READ | VM_PROT_WRITE;
        case Protect::ReadWriteExec: return VM_PROT_READ | VM_PROT_WRITE | VM_PROT_EXECUTE;
    }
    return VM_PROT_READ;
}

std::pair<mach_vm_address_t, mach_vm_size_t> page_span(const void* addr, std::size_t len) {
    const std::size_t ps = page_size();
    const auto raw   = reinterpret_cast<std::uintptr_t>(addr);
    const auto start = raw & ~static_cast<std::uintptr_t>(ps - 1);
    const auto end   = (raw + len + ps - 1) & ~static_cast<std::uintptr_t>(ps - 1);
    return {static_cast<mach_vm_address_t>(start), static_cast<mach_vm_size_t>(end - start)};
}

std::string basename_of(const std::string& path) {
    const auto slash = path.find_last_of('/');
    return slash == std::string::npos ? path : path.substr(slash + 1);
}

std::size_t round_to_pages(std::size_t len) {
    const std::size_t ps = page_size();
    return (len + ps - 1) & ~(ps - 1);
}

}  // namespace

bool set_protection(void* addr, std::size_t len, Protect p) {
    if (!addr || len == 0) return false;
    const auto [start, span] = page_span(addr, len);
    const vm_prot_t want = to_vm_prot(p);
    kern_return_t kr = mach_vm_protect(mach_task_self(), start, span, FALSE, want);
    if (kr != KERN_SUCCESS && (want & VM_PROT_WRITE) != 0) {
        // A file-backed code page: ask for a private copy we may write.
        kr = mach_vm_protect(mach_task_self(), start, span, FALSE, want | VM_PROT_COPY);
    }
    if (kr != KERN_SUCCESS) {
        log(LogLevel::Error, "mach_vm_protect(0x%llx, %llu, %d) failed: %s",
            static_cast<unsigned long long>(start), static_cast<unsigned long long>(span),
            static_cast<int>(want), mach_error_string(kr));
        return false;
    }
    return true;
}

void* alloc_exec(std::size_t len) {
    if (len == 0) return nullptr;
    void* p = ::mmap(nullptr, round_to_pages(len), PROT_READ | PROT_WRITE,
                     MAP_PRIVATE | MAP_ANON, -1, 0);
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
    auto [cur, span] = page_span(addr, len);
    const mach_vm_address_t end = cur + span;
    while (cur < end) {
        mach_vm_address_t region = cur;
        mach_vm_size_t size = 0;
        vm_region_basic_info_data_64_t info{};
        mach_msg_type_number_t count = VM_REGION_BASIC_INFO_COUNT_64;
        mach_port_t object = MACH_PORT_NULL;
        const kern_return_t kr = mach_vm_region(mach_task_self(), &region, &size,
                                                VM_REGION_BASIC_INFO_64,
                                                reinterpret_cast<vm_region_info_t>(&info),
                                                &count, &object);
        if (object != MACH_PORT_NULL) mach_port_deallocate(mach_task_self(), object);
        // mach_vm_region returns the first region AT OR AFTER the address; a
        // region that starts past `cur` means `cur` itself is unmapped.
        if (kr != KERN_SUCCESS || region > cur) return false;
        if ((info.protection & VM_PROT_READ) == 0) return false;
        cur = region + size;
    }
    return true;
}

int page_protection(const void* addr) {
    mach_vm_address_t region = reinterpret_cast<std::uintptr_t>(addr);
    const mach_vm_address_t want = region;
    mach_vm_size_t size = 0;
    vm_region_basic_info_data_64_t info{};
    mach_msg_type_number_t count = VM_REGION_BASIC_INFO_COUNT_64;
    mach_port_t object = MACH_PORT_NULL;
    const kern_return_t kr = mach_vm_region(mach_task_self(), &region, &size, VM_REGION_BASIC_INFO_64,
                                            reinterpret_cast<vm_region_info_t>(&info), &count, &object);
    if (object != MACH_PORT_NULL) mach_port_deallocate(mach_task_self(), object);
    if (kr != KERN_SUCCESS || region > want) return -1;
    return static_cast<int>(info.protection);
}

void flush_instruction_cache(void* addr, std::size_t len) {
    auto* p = static_cast<char*>(addr);
    __builtin___clear_cache(p, p + len);
}

std::uintptr_t module_base(const char* name) {
    const std::string want = (name && *name) ? basename_of(name) : std::string();
    const std::uint32_t n = _dyld_image_count();
    for (std::uint32_t i = 0; i < n; ++i) {
        const mach_header* h = _dyld_get_image_header(i);
        if (h == nullptr) continue;
        if (want.empty()) {
            // Main image: the one dyld mapped as MH_EXECUTE.
            if (h->filetype == MH_EXECUTE) return reinterpret_cast<std::uintptr_t>(h);
            continue;
        }
        const char* path = _dyld_get_image_name(i);
        if (path != nullptr && basename_of(path) == want) return reinterpret_cast<std::uintptr_t>(h);
    }
    return 0;
}

// Host facts for the receipt line. `translated` is the documented way to ask
// whether this process runs under Rosetta: sysctl.proc_translated is 1 there,
// 0 on Intel, and absent (ENOENT) on macOS versions that predate Rosetta 2.
DarwinHost darwin_host() {
    DarwinHost h;
    std::size_t len = sizeof h.os_version;
    if (::sysctlbyname("kern.osproductversion", h.os_version, &len, nullptr, 0) != 0)
        std::snprintf(h.os_version, sizeof h.os_version, "unknown");
    len = sizeof h.hw_model;
    if (::sysctlbyname("hw.model", h.hw_model, &len, nullptr, 0) != 0)
        std::snprintf(h.hw_model, sizeof h.hw_model, "unknown");
    int translated = 0;
    len = sizeof translated;
    if (::sysctlbyname("sysctl.proc_translated", &translated, &len, nullptr, 0) == 0)
        h.translated = translated == 1;
    return h;
}

void format_darwin_host(const DarwinHost& h, char* out, std::size_t len) {
    std::snprintf(out, len, "host: os=macos-%s model=%s rosetta=%s arch=x86_64", h.os_version,
                  h.hw_model, h.translated ? "yes" : "no");
}

}  // namespace kp::platform
