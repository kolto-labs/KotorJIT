// The escape hatch: raw typed reads and writes at an address, and a signature
// scan to find one.
//
// Three quarters of every real Phasor script is this module. 1,071 call sites
// across the 13 reference scripts are `readfloat(base + 0x1C)` and friends, and
// the typed layer above will always lag what somebody needs today. So the raw
// surface stays, with Phasor's names and Phasor's argument shapes, because the
// corpus is written against them.
//
// READS NEVER FAULT, AND NEVER RAISE
// ==================================
// Every read asks platform::is_readable about the whole span first and returns
// nil when the answer is no. Phasor raised "invalid read: N bytes from 0x..."
// instead; we return nil because pointer chasing is the normal case here, not
// the exceptional one:
//
//     local p = kotor.mem.readdword(base + 0x10)
//     local hp = p and kotor.mem.readfloat(p + 0x1C)
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

// Register the 23 functions into one script's state as kotor.mem.*.
//
// The `kotor` table is shared with the routine bridge and every other module, so
// this looks for an existing one and reuses it rather than replacing it. Same
// for the `mem` sub-table: registering twice into one state is idempotent.
void register_all(lua_State*);

}  // namespace kp::api::memory
