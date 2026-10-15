// The escape hatch: raw typed reads and writes at an address, and a signature
// scan to find one.
//
// The typed struct layer will always lag what somebody needs today -- a field
// that is not in the generated layouts, or an offset found in the binary this
// afternoon. So the raw surface stays: kp.mem.readbyte / readfloat /
// writeword, with an optional offset so readbyte(a, 3) and readbyte(a + 3)
// are the same call.
//
// READS NEVER FAULT, AND NEVER RAISE
// ==================================
// Every read asks platform::is_readable about the whole span first and returns
// nil when the answer is no. Pointer chasing is the normal case here, not the
// exceptional one, and a raise would cost a pcall per hop:
//
//     local p = kp.mem.readdword(base + 0x10)
//     local hp = p and kp.mem.readfloat(p + 0x1C)
//
// With a raise, that idiom costs a pcall per hop. A read that yields nil is not
// ambiguous with a read that yields zero -- these functions return numbers, and
// in Lua `nil ~= 0`.
//
// The probe is a query, not a touch: VirtualQuery on Windows, msync on Linux.
// Neither dereferences the address, so a wrong pointer cannot take the game
// down through the check that exists to prevent exactly that.
//
// WRITES STAY SHARP
// =================
// A scripting runtime that cannot write memory cannot do what people install it
// for. There is no null-page refusal, no code-section opt-in, no allow-list. The
// line is drawn at REPORTING: every write goes through one funnel that logs the
// address, the width, the value, and the `source:line` of the Lua statement that
// asked for it. A corrupted save can then be traced back to the statement that
// corrupted it, which is the outcome that actually helps. A guard that refuses
// the write only moves the argument.
//
// Writes do restore page protection. A span inside a known executable region
// goes back to ReadExec and gets an instruction-cache flush; anything else goes
// back to ReadWrite. That is bookkeeping, not policy -- leaving the game's code
// pages writable forever is a change we did not intend to make.
//
// STRINGS ARE BOUNDED TWICE
// =========================
// An unterminated read walking off the end of a page is the classic way this
// crashes. readstring/readwidestring take a length, default 160, hard cap 4096,
// and walk forward in page-bounded chunks: the probe happens per chunk, so a
// string that runs into an unmapped page returns the readable prefix instead of
// faulting on byte 4,095.
//
// findsig IS BOUNDED TOO
// ======================
// Scanning the whole address space is how a signature search becomes a hang. The
// scan covers the executable regions of the game module and nothing else. The
// runtime hands those over with bind_scan_regions() once the image has been
// parsed AND deciphered -- that ordering matters on the encrypted K1 build,
// where scanning ciphertext would match nothing and waste the wait. Absent a
// binding, the regions are derived from the mapped image headers on first use.
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

struct lua_State;

namespace kp::api::memory {

// One span findsig is allowed to look at. Executable, and belonging to the
// module the runtime identified -- never a bare "everything mapped".
struct ScanRegion {
    std::uintptr_t va   = 0;
    std::size_t    size = 0;
    std::string    name;   // section name, for diagnostics only
};

// Hand the scanner its bounds. The runtime calls this after image::load()
// reports Ok, because only then is the code section plaintext. Calling it again
// replaces the set and drops the memo -- a rebased module invalidates every
// address findsig previously returned.
void bind_scan_regions(std::uintptr_t module_base, std::vector<ScanRegion>);

// The bounds in use, deriving them from the mapped image on first call if the
// runtime never bound any. Sorted by address, so occurrence indices are stable.
const std::vector<ScanRegion>& scan_regions();

// Base the current regions were bound against. 0 when nothing is bound yet.
std::uintptr_t scan_base();

// Unique exact hit in bound executable regions. 0 if none or not unique.
std::uintptr_t find_unique(const std::uint8_t* bytes, std::size_t n);

// One masked pattern for scan_masked(). A byte matches when
// (byte & mask[i]) == (value[i] & mask[i]); mask 0x00 is a wildcard byte.
// mask[0] must be 0xFF: patterns are bucketed by their first byte.
struct MaskedPattern {
    const std::uint8_t* value = nullptr;
    const std::uint8_t* mask  = nullptr;
    std::size_t         n     = 0;
};

// Per-pattern outcome. `count` saturates at 2, which is all a caller needs to
// tell missing (0), unique (1) and ambiguous (2) apart.
struct MaskedHit {
    std::uintptr_t first = 0;
    std::uint32_t  count = 0;
};

// Every pattern against the bound executable regions in ONE pass, so ten
// thousand manifest patterns cost one walk of .text rather than ten thousand.
// A pattern with n == 0 or mask[0] != 0xFF is reported as count 0.
std::vector<MaskedHit> scan_masked(const std::vector<MaskedPattern>& patterns);

// Every write, after it happened. This is the reporting half of "sharp writes":
// the default sink is the platform log, and the runtime can add a journal on
// top without this module knowing what a journal is.
struct WriteRecord {
    std::uintptr_t address = 0;
    unsigned       width   = 0;      // bytes actually stored
    std::string    kind;             // "dword", "float", "string", ...
    std::string    value;            // formatted, for a human reading a log
    std::string    where;            // "script.lua:42: ", from luaL_where
};

using WriteObserver = void (*)(const WriteRecord&, void* user);
void set_write_observer(WriteObserver, void* user);

// How many writes this process has performed. A cheap way for a diagnostic
// command to say "12 writes since load" without holding the records.
unsigned long long writes_performed();

// Register the 23 functions into one script's state as kp.mem.*.
//
// The `kp` table is shared with the routine bridge and every other module, so
// this looks for an existing one and reuses it rather than replacing it. Same
// for the `mem` sub-table: registering twice into one state is idempotent.
void register_all(lua_State*);

}  // namespace kp::api::memory
