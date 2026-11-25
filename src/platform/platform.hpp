// The four OS facts the hook engine needs, and nothing else.
//
// Page protection, executable memory, module base, and a place to send log
// lines. The engine above this layer is pure byte manipulation and must stay
// that way -- every #ifdef WIN32 in the project lives in platform_win32.cpp or
// platform_linux.cpp, never in hooks/.
//
// One deliberate asymmetry, called out because it looks like an omission:
// set_protection() has no "previous protection" out-parameter even though
// VirtualProtect offers one. Linux cannot answer that question -- there is no
// mprotect query -- so a portable API that promised it would be lying on one of
// the two targets. Callers state what to restore instead.
#pragma once

#include <cstddef>
#include <cstdint>

namespace kp::platform {

enum class Protect {
    ReadExec,       // the normal resting state of code
    ReadWrite,      // what a patch needs, transiently
    ReadWriteExec,  // never requested by the engine; see alloc_exec
};

// Change protection over the pages spanning [addr, addr+len). A five-byte patch
// four bytes before a page boundary touches two pages; implementations align
// down and round up rather than assuming one.
bool set_protection(void* addr, std::size_t len, Protect);

// Executable allocation is a two-step handshake on purpose: alloc_exec returns
// writable-but-not-executable pages, and commit_exec flips them to
// executable-but-not-writable. W^X is enforced by hardened kernels and by
// SELinux policy; a single RWX request can be refused outright, which would
// surface as a mysterious engine failure rather than as the policy decision it
// is. Nothing here ever asks for both at once.
void* alloc_exec(std::size_t len);
bool  commit_exec(void* addr, std::size_t len);
void  free_exec(void* addr, std::size_t len);

// Is [addr, addr+len) mapped and readable right now?
//
// The engine verifies a site's original bytes before patching it, which means
// it dereferences an address that came from a data file. If that address is not
// mapped -- wrong build, an unloaded module, a table entry that drifted -- the
// verification itself faults, and the refusal path that exists precisely to
// prevent damage becomes the thing that crashes the game. So the probe comes
// first and a bad address is refused, not read.
bool is_readable(const void* addr, std::size_t len);

// Is [addr, addr+len) mapped and writable right now without changing protection?
bool is_writable(const void* addr, std::size_t len);

// x86 has a coherent instruction cache, so this is a formality there. It is
// here because the contract "we wrote code, now it may be executed" should be
// stated in one place rather than assumed by every caller.
void flush_instruction_cache(void* addr, std::size_t len);

// Base address of a loaded module. A null or empty name means the main
// executable -- swkotor.exe under Wine, the kotor2 ELF natively, the
// MH_EXECUTE image (its mach_header, slide included) on macOS. Returns 0 when
// the module is not loaded.
std::uintptr_t module_base(const char* name);

enum class LogLevel { Debug, Info, Warn, Error };

const char* to_string(LogLevel);

// The runtime installs its own sink (file, in-game console, Lua). Until it
// does, lines go to stderr, which is what makes the standalone tool readable
// without any setup.
using LogSink = void (*)(LogLevel, const char* message, void* user);
void set_log_sink(LogSink, void* user);

// gnu_printf rather than printf under MinGW: the default there is ms_printf,
// which rejects %zu even though the runtime we link against accepts it.
#if defined(__MINGW32__)
#define KP_PRINTF_FMT(a, b) __attribute__((format(gnu_printf, a, b)))
#elif defined(__GNUC__)
#define KP_PRINTF_FMT(a, b) __attribute__((format(printf, a, b)))
#else
#define KP_PRINTF_FMT(a, b)
#endif

void log(LogLevel, const char* fmt, ...) KP_PRINTF_FMT(2, 3);

#if defined(__APPLE__) || defined(KP_DARWIN_SHIM)
// Current protection of the page holding `addr` as a VM_PROT_* mask, or -1
// when it is unmapped. The x86_64 detour engine records this before a write
// and restores exactly it afterwards.
int page_protection(const void* addr);

// What the process is running on, for the receipt: macOS version, model and
// whether Rosetta 2 is translating it. One line, fixed keys:
// "host: os=macos-<v> model=<m> rosetta=<yes|no> arch=x86_64".
struct DarwinHost {
    char os_version[32] = {};
    char hw_model[64] = {};
    bool translated = false;
};
DarwinHost darwin_host();
void format_darwin_host(const DarwinHost&, char* out, std::size_t len);
#endif

#if defined(_WIN32)
// What the process is really running on, for a receipt that has to tell a
// native Windows run from Wine. Wine answers every Win32 call the hook engine
// makes, so nothing above this layer can tell; wine_get_version in ntdll is the
// one export Wine ships that Windows never does. The OS build comes from
// RtlGetVersion because GetVersionEx lies to unmanifested executables.
//
// Overlays are loaded modules whose names match known injectors (GOG Galaxy,
// Steam/Discord/other *overlay*, NVIDIA capture nvspcap*). They share the
// process with our WGL and DirectInput hooks, so a receipt names them. Base
// names only: a full path would carry the user's profile directory.
struct HostIdentity {
    bool          wine = false;
    char          wine_version[32] = {};   // empty unless wine
    unsigned long os_major = 0, os_minor = 0, os_build = 0;
    char          overlays[256] = {};      // comma-separated lowercase base names
};

HostIdentity host_identity();

// One line, fixed keys, for kotorjit.log. The receipt script and its test
// parse exactly these keys: "host: wine=<yes|no> wine_version=<v|-> os=<M.m.b>
// overlays=<a,b|->".
void format_host_identity(const HostIdentity&, char* out, std::size_t len);
#endif

}  // namespace kp::platform
