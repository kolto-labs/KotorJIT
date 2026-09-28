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

// x86 has a coherent instruction cache, so this is a formality there. It is
// here because the contract "we wrote code, now it may be executed" should be
// stated in one place rather than assumed by every caller.
void flush_instruction_cache(void* addr, std::size_t len);

// Base address of a loaded module. A null or empty name means the main
// executable -- swkotor.exe under Wine, the kotor2 ELF natively. Returns 0 when
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

}  // namespace kp::platform
