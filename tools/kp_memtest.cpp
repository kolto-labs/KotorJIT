// Exercises src/api/memory.cpp against buffers in this tool's own process.
//
// The module is the one part of the host API with no safe way to be wrong: a
// read that faults takes the game down, and a write that lands one field early
// corrupts a save. Neither failure is visible from Lua. So the proof is a real
// process with known bytes at known addresses, driven through a real lua_State
// by real Lua source, not a description of what the code should do.
//
// What is demonstrated, in order:
//
//   1. every read type against a packed struct with values chosen so a wrong
//      width or a wrong sign gives a different answer than a right one
//   2. every write type into a second struct, verified from C++ afterwards, so
//      a write that only appeared to work does not pass
//   3. the write log, which is the whole safety argument for keeping writes
//      sharp -- every store shows its address, width, value and Lua call site
//   4. a bad address returning nil rather than faulting, using a page this
//      process mapped and then unmapped, so the address is known-bad rather
//      than hoped-bad
//   5. an unterminated string stopping at the cap, and a second one stopping at
//      the edge of a mapped page instead of walking into the one after it
//   6. findsig: exact match, nibble wildcard, occurrence index, and a miss
//
// Linux and 32-bit only, like kp_hooktool: it detours and probes its own
// process, so cross-compiling it to Windows would produce a binary nobody runs.
//
// Build (from the repo root):
//   g++ -m32 -no-pie -std=c++20 -O2 -Isrc -Ibuild/luajit32/src
//       tools/kp_memtest.cpp src/api/memory.cpp
//       src/platform/platform.cpp src/platform/platform_linux.cpp
//       src/image/*.cpp build/luajit32/src/libluajit.a -ldl -lm -o build/kp_memtest
//
// -no-pie is not a preference. src/image reads the ELF program headers out of
// the live mapping and checks that p_vaddr covers them; in a PIE those values
// are link-relative and the check correctly fails, so a PIE build would find no
// executable regions and findsig's real-image bound would look broken when it
// is not. Both real targets are non-relocatable: the K1 PE cannot rebase and the
// TSL ELF is EXEC.

#include <sys/mman.h>
#include <unistd.h>

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "api/memory.hpp"
#include "platform/platform.hpp"

extern "C" {
#include "lauxlib.h"
#include "lua.h"
#include "lualib.h"
}

namespace {

// Packed, so the offsets below are the offsets a script would use, and so the
// double and the dword land unaligned -- which is what a real engine struct
// walked with base+offset looks like.
#pragma pack(push, 1)
struct Probe {
    std::uint8_t  u8;        // +0x00
    std::int8_t   i8;        // +0x01
    std::uint16_t u16;       // +0x02
    std::int16_t  i16;       // +0x04
    std::uint32_t u32;       // +0x06
    std::int32_t  i32;       // +0x0A
    float         f32;       // +0x0E
    double        f64;       // +0x12
    std::uint8_t  bits;      // +0x1A
    char          str[16];   // +0x1B
    std::uint16_t wstr[8];   // +0x2B
    std::uint8_t  tail;      // +0x3B, so the two-argument write form has a
                             // target that is not part of another field
};
#pragma pack(pop)

Probe g_read{};
Probe g_write{};

unsigned g_write_events = 0;

void on_write(const kp::api::memory::WriteRecord& r, void*) {
    ++g_write_events;
    std::printf("    [write log] 0x%08X %-11s %d byte(s) = %-12s %s\n",
                unsigned(r.address), r.kind.c_str(), int(r.width),
                r.value.c_str(),
                r.where.empty() ? "(no site)" : r.where.c_str());
}

// The log sink would otherwise interleave the module's own lines into the
// results on stderr. The observer above already prints what matters.
void quiet_sink(kp::platform::LogLevel, const char*, void*) {}

// A page this process maps and then throws away. Its address is real, it is
// correctly aligned, and it is definitely not mapped -- which a made-up
// constant like 0xDEADBEEF cannot promise.
std::uintptr_t unmapped_page() {
    void* p = ::mmap(nullptr, 4096, PROT_READ | PROT_WRITE,
                     MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (p == MAP_FAILED) return 0;
    ::munmap(p, 4096);
    return reinterpret_cast<std::uintptr_t>(p);
}

// Two pages, second one dropped, with `len` non-NUL bytes placed so they end
// exactly at the boundary. A reader that probes the whole 4096-byte request in
// one call reports this unreadable; a reader that walks page-bounded chunks
// returns the prefix. That is the difference this proves.
std::uintptr_t string_at_page_edge(std::size_t len) {
    auto* p = static_cast<std::uint8_t*>(
        ::mmap(nullptr, 8192, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
    if (p == MAP_FAILED) return 0;
    ::munmap(p + 4096, 4096);
    std::memset(p + 4096 - len, 'A', len);
    return reinterpret_cast<std::uintptr_t>(p + 4096 - len);
}

// A page-aligned buffer standing in for a code section, so findsig can be
// proved against bytes whose address this tool chose. A `static const` array
// would live in .rodata, which is not executable and therefore correctly
// outside the scan bounds -- the scan finding nothing there would look like a
// bug in the scanner rather than the bound working.
std::uintptr_t synthetic_code_region(std::size_t& size_out) {
    auto* p = static_cast<std::uint8_t*>(
        ::mmap(nullptr, 4096, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
    if (p == MAP_FAILED) { size_out = 0; return 0; }
    std::memset(p, 0x90, 4096);

    // Two near-copies of a function prologue. They differ in one nibble at the
    // last byte, which is what makes "2?" and "??" give different answers.
    const std::uint8_t a[] = {0x55, 0x8B, 0xEC, 0x83, 0xEC, 0x20};
    const std::uint8_t b[] = {0x55, 0x8B, 0xEC, 0x83, 0xEC, 0x38};
    std::memcpy(p + 0x100, a, sizeof a);
    std::memcpy(p + 0x200, b, sizeof b);

    size_out = 4096;
    return reinterpret_cast<std::uintptr_t>(p);
}

const char* kLua = R"LUA(
local mem = kp.mem
local fails, checks = 0, 0

local function eq(name, got, want)
  checks = checks + 1
  local ok = got == want
  if not ok then fails = fails + 1 end
  print(string.format("  %-40s %-24s %s", name, tostring(got),
        ok and "ok" or ("FAIL, wanted " .. tostring(want))))
end

local function near(name, got, want)
  checks = checks + 1
  local ok = type(got) == "number" and math.abs(got - want) < 1e-9
  if not ok then fails = fails + 1 end
  print(string.format("  %-40s %-24s %s", name, tostring(got),
        ok and "ok" or ("FAIL, wanted " .. tostring(want))))
end

local function raises(name, fn, needle)
  checks = checks + 1
  local ok, err = pcall(fn)
  local good = (not ok) and tostring(err):find(needle, 1, true) ~= nil
  if not good then fails = fails + 1 end
  print(string.format("  %-40s %-24s %s", name,
        ok and "(no error)" or "raised",
        good and "ok" or ("FAIL, wanted error containing " .. needle)))
end

print("\n-- reads: every type, against known bytes ------------------------")
eq  ("readbyte(p)",                mem.readbyte(p),            0xA5)
eq  ("readchar(p)",                mem.readchar(p),            -91)
eq  ("readbyte(p, 1)",             mem.readbyte(p, 1),         0xA5)
eq  ("readword(p, 2)",             mem.readword(p, 2),         0xBEEF)
eq  ("readword(p + 2)",            mem.readword(p + 2),        0xBEEF)
eq  ("readshort(p, 4)",            mem.readshort(p, 4),        -12345)
eq  ("readdword(p, 6)",            mem.readdword(p, 6),        0xDEADBEEF)
eq  ("readint(p, 10)",             mem.readint(p, 10),         -123456789)
near("readfloat(p, 14)",           mem.readfloat(p, 14),       1.5)
near("readdouble(p, 18)",          mem.readdouble(p, 18),      -2.25)
eq  ("readstring(p + 27)",         mem.readstring(p + 27),     "hello")
eq  ("readstring(p + 27, 3)",      mem.readstring(p + 27, 3),  "hel")
eq  ("readwidestring(p + 43)",     mem.readwidestring(p + 43), "wide")

print("\n-- readbit: bit 0 is the LSB, and the index normalises -----------")
-- bits byte is 0x42 = 0100 0010
eq  ("readbit(p + 26, 0)",         mem.readbit(p + 26, 0),     false)
eq  ("readbit(p + 26, 1)",         mem.readbit(p + 26, 1),     true)
eq  ("readbit(p + 26, 6)",         mem.readbit(p + 26, 6),     true)
eq  ("readbit(p, 26, 6) legacy",   mem.readbit(p, 26, 6),      true)
eq  ("readbit(p, 26*8 + 6) norm",  mem.readbit(p, 26 * 8 + 6), true)

print("\n-- a bad address is nil, not a fault ------------------------------")
eq  ("readbyte(unmapped)",         mem.readbyte(bad),          nil)
eq  ("readdword(unmapped)",        mem.readdword(bad),         nil)
eq  ("readfloat(unmapped)",        mem.readfloat(bad),         nil)
eq  ("readdouble(unmapped)",       mem.readdouble(bad),        nil)
eq  ("readbit(unmapped, 3)",       mem.readbit(bad, 3),        nil)
eq  ("readstring(unmapped)",       mem.readstring(bad),        nil)
eq  ("readwidestring(unmapped)",   mem.readwidestring(bad),    nil)
eq  ("readdword(null page)",       mem.readdword(nullp),       nil)
eq  ("readstring(null page)",      mem.readstring(nullp),      nil)

print("\n-- unterminated strings stop at the bound -------------------------")
eq  ("#readstring(unterm)",        #mem.readstring(unterm),         160)
eq  ("#readstring(unterm, 4096)",  #mem.readstring(unterm, 4096),   4096)
eq  ("#readstring(page edge, 4096)", #mem.readstring(edge, 4096),   10)
raises("readstring(p, 5000)", function() return mem.readstring(p, 5000) end,
       "maximum size of 4096")

print("\n-- writes: sharp, and every one logged ----------------------------")
mem.writebyte  (w,  0, 0xA5)
mem.writechar  (w,  1, -91)
mem.writeword  (w,  2, 0xBEEF)
mem.writeshort (w,  4, -12345)
mem.writedword (w,  6, 0xDEADBEEF)
mem.writeint   (w, 10, -123456789)
mem.writefloat (w, 14, 1.5)
mem.writedouble(w, 18, -2.25)
mem.writebit   (w, 26, 1, true)
mem.writebit   (w, 26, 6, true)
mem.writebit   (w, 26, 3, true)
mem.writebit   (w, 26, 3, false)
mem.writestring(w, 27, "hello")
mem.writewidestring(w, 43, "wide")
-- the two-argument form: no offset, value straight after the address
mem.writebyte  (w + 59, 0x7F)

print("\n-- writes read back through the read path -------------------------")
eq  ("readdword(w, 6)",            mem.readdword(w, 6),        0xDEADBEEF)
eq  ("readstring(w + 27)",         mem.readstring(w + 27),     "hello")
eq  ("readbyte(w + 59)",           mem.readbyte(w + 59),       0x7F)

print("\n-- misuse raises, it does not corrupt -----------------------------")
raises("writebyte out of range", function() mem.writebyte(w, 300) end,
       "outside of type's range")
raises("writeshort out of range", function() mem.writeshort(w, 40000) end,
       "outside of type's range")
raises("write to unmapped page", function() mem.writedword(bad, 1) end,
       "invalid write")
raises("readbyte with a table", function() mem.readbyte({}) end,
       "expected number")
raises("readbyte with junk string", function() mem.readbyte("0x10z") end,
       "expected number")
raises("writebit with 2", function() mem.writebit(w, 0, 2) end,
       "boolean, 0, or 1")

print("\n-- findsig, bounded to the regions the host bound -----------------")
eq  ("findsig exact",              mem.findsig("558BEC83EC20"),      sig + 0x100)
eq  ("findsig spaced",            mem.findsig("55 8B EC 83 EC 20"),  sig + 0x100)
eq  ("findsig byte wildcard",      mem.findsig("558BEC83EC??"),      sig + 0x100)
eq  ("findsig occurrence 1",       mem.findsig("558BEC83EC??", 1),   sig + 0x200)
eq  ("findsig occurrence 2 misses", mem.findsig("558BEC83EC??", 2),  nil)
eq  ("findsig nibble '2?'",        mem.findsig("558BEC83EC2?"),      sig + 0x100)
eq  ("findsig nibble '3?'",        mem.findsig("558BEC83EC3?"),      sig + 0x200)
eq  ("findsig odd length",         mem.findsig("558BEC83EC2"),       sig + 0x100)
eq  ("findsig miss is nil",        mem.findsig("DEADBEEFCAFE"),      nil)
eq  ("findsig memoised repeat",    mem.findsig("558BEC83EC20"),      sig + 0x100)
raises("findsig bad hex", function() mem.findsig("zzzz") end, "hex digits")
raises("findsig empty",   function() mem.findsig("") end,     "hex digits")

failures = fails
checks_run = checks
)LUA";

template <typename T>
bool same(const char* what, T got, T want, int& fails) {
    const bool ok = got == want;
    if (!ok) ++fails;
    std::printf("  %-40s %-24s %s\n", what,
                ok ? "matches" : "differs", ok ? "ok" : "FAIL");
    return ok;
}

}  // namespace

int main() {
    namespace mem = kp::api::memory;

    g_read.u8  = 0xA5;
    g_read.i8  = -91;                 // the same byte, read signed
    g_read.u16 = 0xBEEF;
    g_read.i16 = -12345;
    g_read.u32 = 0xDEADBEEFu;
    g_read.i32 = -123456789;
    g_read.f32 = 1.5f;
    g_read.f64 = -2.25;
    g_read.bits = 0x42;               // 0100 0010
    std::memcpy(g_read.str, "hello", 6);
    const std::uint16_t wide[] = {'w', 'i', 'd', 'e', 0};
    std::memcpy(g_read.wstr, wide, sizeof wide);

    kp::platform::set_log_sink(quiet_sink, nullptr);

    std::printf("kp_memtest: src/api/memory.cpp against this process\n");
    std::printf("  sizeof(void*) = %d, probe struct at %p, %d bytes\n",
                int(sizeof(void*)), (void*)&g_read, int(sizeof(Probe)));

    // Ask for the default bounds FIRST, before anything is bound, so the output
    // shows what the module would scan inside the game: the executable sections
    // of the mapped main image, parsed by src/image. The addresses move with the
    // build, so nothing asserts on them -- the point is that the set is small
    // and section-shaped rather than "all of memory".
    std::printf("\n-- default findsig bounds, derived from the mapped image --\n");
    std::printf("  module base 0x%08X\n", unsigned(mem::scan_base()));
    const auto& derived = mem::scan_regions();
    if (derived.empty()) {
        std::printf("  (none: headers not parseable from memory in this build)\n");
    }
    for (const auto& r : derived)
        std::printf("  %-16s 0x%08X  %d bytes\n", r.name.c_str(),
                    unsigned(r.va), int(r.size));

    // 8 KiB of 'A' with no terminator anywhere. Both string caps are proved
    // against it: the 160 default and the 4096 ceiling.
    std::vector<char> unterminated(8192, 'A');

    std::size_t sig_size = 0;
    const std::uintptr_t sig = synthetic_code_region(sig_size);
    if (!sig) {
        std::fprintf(stderr, "mmap failed; cannot run\n");
        return 1;
    }

    // Hand the scanner bounds of our own, the way the runtime will hand it the
    // deciphered code section. This replaces the derived set and drops the memo.
    mem::bind_scan_regions(sig, {mem::ScanRegion{sig, sig_size, "synthetic"}});
    std::printf("\n  bound synthetic scan region 0x%08X, %d bytes\n",
                unsigned(sig), int(sig_size));

    mem::set_write_observer(on_write, nullptr);

    lua_State* L = luaL_newstate();
    luaL_openlibs(L);
    mem::register_all(L);

    // Registering twice must be idempotent: the runtime may call this again
    // after another module has already put things in the same table.
    mem::register_all(L);

    // Grow LuaJIT's arena BEFORE any holes are punched below. This tool proved
    // its own bug here first: an mmap made after munmap gets handed the page
    // that was just released, so `bad` stopped being a bad address and the nil
    // checks read live memory instead. Allocating up front means the only
    // mmaps left are the ones that create the holes.
    if (luaL_dostring(L, "local t = {} for i = 1, 400 do t[i] = string.rep('x', 8192) end") != 0) {
        std::fprintf(stderr, "warm-up failed: %s\n", lua_tostring(L, -1));
        return 1;
    }

    // Compile the checks now too, for the same reason: loading an 8 KiB chunk
    // allocates, and the allocation must not land in a hole that does not exist
    // yet. The compiled function stays on the stack until it is called.
    if (luaL_loadstring(L, kLua) != 0) {
        std::fprintf(stderr, "lua: %s\n", lua_tostring(L, -1));
        return 1;
    }

    // Holes last, and in this order, so nothing can reclaim them.
    const std::uintptr_t edge = string_at_page_edge(10);
    const std::uintptr_t bad  = unmapped_page();
    if (!edge || !bad) {
        std::fprintf(stderr, "mmap failed; cannot run\n");
        return 1;
    }

    // And then check, rather than assume. An address that turned out to be
    // mapped after all would make every nil check below pass for the wrong
    // reason -- which is exactly what happened the first time this ran.
    std::printf("\n-- addresses this tool made unreadable on purpose ----------\n");
    const bool bad_ok  = !kp::platform::is_readable((const void*)bad, 1);
    const bool edge_ok = !kp::platform::is_readable((const void*)(edge + 10), 1);
    std::printf("  unmapped page      0x%08X  is_readable = %s\n",
                unsigned(bad), bad_ok ? "false (good)" : "TRUE, page was reclaimed");
    std::printf("  page after string  0x%08X  is_readable = %s\n",
                unsigned(edge + 10), edge_ok ? "false (good)" : "TRUE, page was reclaimed");
    if (!bad_ok || !edge_ok) {
        std::fprintf(stderr, "the harness could not keep its holes; cannot run\n");
        return 1;
    }

    lua_pushnumber(L, lua_Number(reinterpret_cast<std::uintptr_t>(&g_read)));
    lua_setglobal(L, "p");
    lua_pushnumber(L, lua_Number(reinterpret_cast<std::uintptr_t>(&g_write)));
    lua_setglobal(L, "w");
    lua_pushnumber(L, lua_Number(bad));
    lua_setglobal(L, "bad");
    lua_pushnumber(L, lua_Number(reinterpret_cast<std::uintptr_t>(unterminated.data())));
    lua_setglobal(L, "unterm");
    lua_pushnumber(L, lua_Number(edge));
    lua_setglobal(L, "edge");
    lua_pushnumber(L, lua_Number(sig));
    lua_setglobal(L, "sig");
    // The null page. mmap_min_addr keeps the low 64 KiB unmapped on any stock
    // kernel, and a stale or zeroed pointer is how a bad address actually
    // presents in the game -- more often than a page somebody unmapped.
    lua_pushnumber(L, 0x10);
    lua_setglobal(L, "nullp");

    if (lua_pcall(L, 0, 0, 0) != 0) {
        std::fprintf(stderr, "lua: %s\n", lua_tostring(L, -1));
        return 1;
    }

    lua_getglobal(L, "failures");
    int fails = int(lua_tonumber(L, -1));
    lua_pop(L, 1);
    lua_getglobal(L, "checks_run");
    const int checks = int(lua_tonumber(L, -1));
    lua_pop(L, 1);

    // The Lua side read its own writes back through the same module, which
    // would agree with itself even if both halves were wrong about the offset.
    // These compare the bytes from C++.
    std::printf("\n-- writes verified from C++, not through the module -------\n");
    same("g_write.u8 == 0xA5",        g_write.u8,  g_read.u8,  fails);
    same("g_write.i8 == -91",         g_write.i8,  g_read.i8,  fails);
    same("g_write.u16 == 0xBEEF",     g_write.u16, g_read.u16, fails);
    same("g_write.i16 == -12345",     g_write.i16, g_read.i16, fails);
    same("g_write.u32 == 0xDEADBEEF", g_write.u32, g_read.u32, fails);
    same("g_write.i32 == -123456789", g_write.i32, g_read.i32, fails);
    same("g_write.f32 == 1.5f",       g_write.f32, g_read.f32, fails);
    same("g_write.f64 == -2.25",      g_write.f64, g_read.f64, fails);
    same("g_write.bits == 0x42",      g_write.bits, g_read.bits, fails);
    same("g_write.str == \"hello\"",
         std::string(g_write.str), std::string("hello"), fails);
    same("g_write.wstr == L\"wide\"",
         std::memcmp(g_write.wstr, g_read.wstr, sizeof wide) == 0, true, fails);

    std::printf("\n-- write reporting -----------------------------------------\n");
    std::printf("  writes_performed() = %llu, observer saw %u\n",
                mem::writes_performed(), g_write_events);
    if (mem::writes_performed() != g_write_events) ++fails;

    std::printf("\n%d Lua check(s) + 11 byte comparison(s), %d failure(s)\n",
                checks, fails);
    lua_close(L);
    return fails == 0 ? 0 : 1;
}
