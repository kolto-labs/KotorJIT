#include "api/memory.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <map>

#include "image/image.hpp"
#include "platform/platform.hpp"

extern "C" {
#include "lauxlib.h"
#include "lua.h"
}

namespace kp::api::memory {
namespace {

// 4 KiB on both targets: x86 Windows and x86 Linux. Windows' 64 KiB allocation
// granularity is a different number and is not the one that matters here -- what
// matters is the unit protection changes and mapping state are tracked in.
constexpr std::uintptr_t kPage = 4096;

// Phasor's readstring defaults to 160 characters and refuses more. The default
// is kept because the corpus depends on it -- readstring(addr) with no length is
// the common form and it must not read further than Phasor did. The ceiling is
// raised to 4096 because Phasor's 160 came from a fixed stack buffer we do not
// have, and KOTOR paths and dialogue lines exceed it.
constexpr std::size_t kDefaultStringChars = 160;
constexpr std::size_t kMaxStringChars     = 4096;

// ------------------------------------------------------------- scan bounds --

struct ScanState {
    std::uintptr_t          base = 0;
    std::vector<ScanRegion> regions;
    bool                    bound = false;    // the runtime handed these over
    bool                    derived = false;  // we went to the headers ourselves
};

ScanState& scan_state() {
    static ScanState s;
    return s;
}

// signature + occurrence -> address, misses included as 0. A signature scan of a
// multi-megabyte code section is not something to repeat once per frame, and a
// script that calls findsig in a tick callback is a script somebody will write.
std::map<std::string, std::uintptr_t>& memo() {
    static std::map<std::string, std::uintptr_t> m;
    return m;
}

void derive_regions() {
    ScanState& s = scan_state();
    // Once, pass or fail. Retrying the header parse on every call would turn a
    // findsig in a tick callback into a per-frame parse of the PE headers.
    s.derived = true;

    const std::uintptr_t base = platform::module_base(nullptr);
    if (base == 0) return;

    std::uint8_t magic[4] = {0};
    if (!platform::is_readable(reinterpret_cast<const void*>(base), sizeof magic)) return;
    std::memcpy(magic, reinterpret_cast<const void*>(base), sizeof magic);

    image::Format fmt;
    if (magic[0] == 'M' && magic[1] == 'Z') {
        fmt = image::Format::Pe32;
    } else if (magic[0] == 0x7f && magic[1] == 'E' && magic[2] == 'L' && magic[3] == 'F') {
        fmt = image::Format::Elf32;
    } else {
        return;
    }

    const auto sections = image::parse_mapped(base, fmt);
    if (!sections) return;

    s.base = base;
    for (const image::Section& sec : *sections) {
        if (!sec.executable || sec.size == 0) continue;
        s.regions.push_back(ScanRegion{sec.va, sec.size, sec.name});
    }
    std::sort(s.regions.begin(), s.regions.end(),
              [](const ScanRegion& a, const ScanRegion& b) { return a.va < b.va; });
}

bool in_executable_region(std::uintptr_t va, std::size_t len) {
    const ScanState& s = scan_state();
    // Deliberately does NOT trigger derive_regions(). This runs on the write
    // path, and a write should not be the thing that decides to go parse the
    // game's headers; if nothing is bound yet, the page goes back to ReadWrite,
    // which is the right answer for every span that is not code.
    for (const ScanRegion& r : s.regions)
        if (va < r.va + r.size && r.va < va + len) return true;
    return false;
}

// ------------------------------------------------------------ write funnel --

WriteObserver g_observer = nullptr;
void*         g_observer_user = nullptr;
unsigned long long g_writes = 0;

// The Lua statement that asked. luaL_where gives "chunk:line: " for level 1,
// which is the script's own call site -- worth more than the script name,
// because a corrupted save is traced back to a line, not to a file.
std::string call_site(lua_State* L) {
    luaL_where(L, 1);
    const char* w = lua_tostring(L, -1);
    std::string out = w ? w : "";
    lua_pop(L, 1);   // luaL_where pushed a string; leaving it would leak a slot
    return out;
}

std::string fmt(const char* f, double v);
std::string hex32(std::uintptr_t va);

// Everything that writes goes through here. One funnel is what makes "log every
// write" a property of the module rather than a habit each function has to keep.
void store(lua_State* L, std::uintptr_t va, const void* src, std::size_t len,
           const char* kind, const std::string& shown) {
    if (len == 0) return;

    void* dst = reinterpret_cast<void*>(va);

    // Mapped first. set_protection on an unmapped page fails too, but it fails
    // with an mprotect error in the log, and "invalid write" is the message the
    // corpus greps for.
    if (!platform::is_readable(dst, len))
        luaL_error(L, "invalid write: %d bytes from %s", int(len),
                   hex32(va).c_str());

    const bool exec = in_executable_region(va, len);

    if (!platform::set_protection(dst, len, platform::Protect::ReadWrite))
        luaL_error(L, "invalid write: %d bytes from %s", int(len),
                   hex32(va).c_str());

    std::memcpy(dst, src, len);

    // Back to where it was. We cannot ask what the protection used to be -- see
    // platform.hpp on why there is no out-parameter -- so the executable region
    // map is what stands in for the question.
    if (exec) {
        platform::set_protection(dst, len, platform::Protect::ReadExec);
        platform::flush_instruction_cache(dst, len);
    } else {
        platform::set_protection(dst, len, platform::Protect::ReadWrite);
    }

    ++g_writes;

    WriteRecord rec;
    rec.address = va;
    rec.width   = unsigned(len);
    rec.kind    = kind;
    rec.value   = shown;
    rec.where   = call_site(L);

    platform::log(platform::LogLevel::Info,
                  "mem write 0x%08X %s %d bytes = %s  <- %s",
                  (unsigned)va, kind, int(len), rec.value.c_str(),
                  rec.where.empty() ? "(unknown site)" : rec.where.c_str());

    if (g_observer) g_observer(rec, g_observer_user);
}

std::string fmt(const char* f, double v) {
    char buf[64];
    std::snprintf(buf, sizeof buf, f, v);
    return buf;
}

// Lua's own formatter understands %s %d %f %p %c and nothing else -- no width,
// no %X. So an address is rendered here and handed over as %s. Getting this
// wrong does not warn; it puts the literal "0x%08X" in the error message.
std::string hex32(std::uintptr_t va) {
    char buf[16];
    std::snprintf(buf, sizeof buf, "0x%08X", (unsigned)va);
    return buf;
}

// ------------------------------------------------------- argument handling --

// Phasor's coercion is loose and the corpus relies on it: a number, a boolean,
// or a string that parses WHOLE. Lua's own string-to-number rejects trailing
// junk, so "5x" raises here just as it did there.
lua_Number arg_number(lua_State* L, int idx) {
    if (lua_type(L, idx) == LUA_TBOOLEAN) return lua_toboolean(L, idx) ? 1.0 : 0.0;
    if (lua_isnumber(L, idx)) return lua_tonumber(L, idx);
    luaL_argerror(L, idx, lua_pushfstring(L, "expected number, got %s",
                                          luaL_typename(L, idx)));
    return 0;   // luaL_argerror does not return
}

std::uintptr_t arg_address(lua_State* L, int idx) {
    const lua_Number n = arg_number(L, idx);
    // The comparison also rejects NaN, which would otherwise cast to something
    // arbitrary and be probed as if it were an address.
    if (!(n >= -2147483648.0 && n <= 4294967295.0))
        luaL_argerror(L, idx, "address outside the 32-bit address space");
    return std::uintptr_t(std::uint32_t(std::int64_t(n)));
}

std::uintptr_t offset_by(lua_State* L, std::uintptr_t base, int idx) {
    const lua_Number n = arg_number(L, idx);
    if (!(n >= -2147483648.0 && n <= 4294967295.0))
        luaL_argerror(L, idx, "offset outside the 32-bit address space");
    // Wrap in 32 bits on purpose: base + a negative offset is how the corpus
    // walks backwards through a struct.
    return std::uintptr_t(std::uint32_t(base) + std::uint32_t(std::int64_t(n)));
}

void check_arity(lua_State* L, const char* fn, int lo, int hi) {
    const int n = lua_gettop(L);
    if (n < lo)
        luaL_error(L, "'%s' expects at least %d argument(s) (got %d)", fn, lo, n);
    if (n > hi)
        luaL_error(L, "'%s' expects at most %d argument(s) (got %d)", fn, hi, n);
}

// The numeric readers take (address) or (address, offset), so readbyte(a, 3)
// and readbyte(a + 3) are the same call. The optional argument is genuinely
// trailing here, which is why these do not need the arity dispatch the writers
// do.
std::uintptr_t read_target(lua_State* L, const char* fn) {
    check_arity(L, fn, 1, 2);
    std::uintptr_t a = arg_address(L, 1);
    if (lua_gettop(L) == 2 && !lua_isnoneornil(L, 2)) a = offset_by(L, a, 2);
    return a;
}

// ------------------------------------------------------------------ reads --

bool probe_read(std::uintptr_t va, void* out, std::size_t len) {
    const void* p = reinterpret_cast<const void*>(va);
    if (!platform::is_readable(p, len)) return false;
    std::memcpy(out, p, len);
    return true;
}

// Walk forward one page-bounded chunk at a time, stopping at the first
// all-zero unit. Probing the whole requested span in one go would be wrong in
// both directions: a string that legitimately ends one byte before an unmapped
// page would be reported unreadable, and a string with no terminator would be
// read straight into the page that is not there.
//
// Returns false only when nothing at all could be read, which is the nil case.
// Running out of readable memory part way yields the prefix, because the
// address the script gave was fine and the answer is real as far as it goes.
bool read_units(std::uintptr_t va, std::size_t max_units, std::size_t unit,
                std::vector<std::uint8_t>& out) {
    out.clear();
    std::uintptr_t cur = va;
    std::size_t got = 0;

    while (got < max_units) {
        const std::uintptr_t page_end = (cur & ~(kPage - 1)) + kPage;
        std::size_t chunk = std::size_t(page_end - cur);
        const std::size_t want = (max_units - got) * unit;
        if (chunk > want) chunk = want;
        chunk -= chunk % unit;
        // A unit straddling the page boundary: probe across it rather than
        // splitting the read, since is_readable already spans pages.
        if (chunk == 0) chunk = unit;

        const void* p = reinterpret_cast<const void*>(cur);
        if (!platform::is_readable(p, chunk)) return !out.empty();

        const auto* b = static_cast<const std::uint8_t*>(p);
        for (std::size_t i = 0; i < chunk; i += unit) {
            bool terminator = true;
            for (std::size_t k = 0; k < unit; ++k)
                if (b[i + k] != 0) { terminator = false; break; }
            if (terminator) return true;
            out.insert(out.end(), b + i, b + i + unit);
            ++got;
        }
        cur += chunk;
    }
    return true;
}

template <typename T>
int read_scalar(lua_State* L, const char* fn) {
    const std::uintptr_t a = read_target(L, fn);
    T v{};
    if (!probe_read(a, &v, sizeof v)) { lua_pushnil(L); return 1; }
    lua_pushnumber(L, lua_Number(v));
    return 1;
}

// A macro rather than a template parameter because the only thing that varies
// besides the type is the name in the arity message, and C++ has no clean way
// to pass a string literal as a template argument that reads better than this.
#define KP_READER(name, T)                                                     \
    int l_##name(lua_State* L) { return read_scalar<T>(L, #name); }

KP_READER(readbyte,   std::uint8_t)
KP_READER(readchar,   std::int8_t)
KP_READER(readword,   std::uint16_t)
KP_READER(readshort,  std::int16_t)
KP_READER(readdword,  std::uint32_t)
KP_READER(readint,    std::int32_t)
KP_READER(readfloat,  float)
KP_READER(readdouble, double)

#undef KP_READER

// Bit index normalisation, Phasor 2's: address += bit / 8, bit %= 8, and bit 0
// is the LEAST significant bit. Phasor 1 counted from the other end, which is
// the single most likely thing to be wrong when porting an old script.
std::uintptr_t normalise_bit(lua_State* L, std::uintptr_t a, int idx, unsigned& bit) {
    const lua_Number n = arg_number(L, idx);
    if (!(n >= 0 && n <= 4294967295.0))
        luaL_argerror(L, idx, "bit index must be zero or positive");
    const std::uint32_t b = std::uint32_t(std::int64_t(n));
    bit = b % 8;
    return std::uintptr_t(std::uint32_t(a) + (b / 8));
}

int l_readbit(lua_State* L) {
    // gettop == 3 selects Phasor's legacy (base, offset, bit) form. The optional
    // argument sits in the MIDDLE, so counting arguments from the end cannot
    // decide it and the arity has to be looked at directly.
    check_arity(L, "readbit", 2, 3);
    std::uintptr_t a = arg_address(L, 1);
    int bit_idx = 2;
    if (lua_gettop(L) == 3) { a = offset_by(L, a, 2); bit_idx = 3; }

    unsigned bit = 0;
    a = normalise_bit(L, a, bit_idx, bit);

    std::uint8_t v = 0;
    if (!probe_read(a, &v, 1)) { lua_pushnil(L); return 1; }
    lua_pushboolean(L, (v >> bit) & 1);
    return 1;
}

std::size_t string_length_arg(lua_State* L, int idx) {
    if (lua_gettop(L) < idx || lua_isnoneornil(L, idx)) return kDefaultStringChars;
    const lua_Number n = arg_number(L, idx);
    if (!(n >= 0 && n <= lua_Number(kMaxStringChars)))
        luaL_argerror(L, idx,
                      "can only read strings to a maximum size of 4096 characters");
    return std::size_t(n);
}

int l_readstring(lua_State* L) {
    // NO offset form here, unlike the numeric readers: Phasor's second parameter
    // is a LENGTH, and the corpus uses it that way -- readstring(base + 0x8, 8).
    check_arity(L, "readstring", 1, 2);
    const std::uintptr_t a = arg_address(L, 1);
    const std::size_t max_chars = string_length_arg(L, 2);

    std::vector<std::uint8_t> buf;
    if (!read_units(a, max_chars, 1, buf)) { lua_pushnil(L); return 1; }
    lua_pushlstring(L, reinterpret_cast<const char*>(buf.data()), buf.size());
    return 1;
}

int l_readwidestring(lua_State* L) {
    check_arity(L, "readwidestring", 1, 2);
    const std::uintptr_t a = arg_address(L, 1);
    const std::size_t max_chars = string_length_arg(L, 2);

    std::vector<std::uint8_t> buf;
    if (!read_units(a, max_chars, 2, buf)) { lua_pushnil(L); return 1; }

    // Lua has no wide string, so this narrows. Anything outside Latin-1 becomes
    // '?' rather than being silently truncated to its low byte, so a script can
    // see that the text did not survive the conversion.
    std::string narrow;
    narrow.reserve(buf.size() / 2);
    for (std::size_t i = 0; i + 1 < buf.size(); i += 2) {
        const std::uint16_t w = std::uint16_t(buf[i] | (buf[i + 1] << 8));
        narrow.push_back(w <= 0xFF ? char(w) : '?');
    }
    lua_pushlstring(L, narrow.data(), narrow.size());
    return 1;
}

// ----------------------------------------------------------------- writes --

template <typename T>
int write_scalar(lua_State* L, const char* fn, const char* kind,
                 double lo, double hi, const char* shown_fmt) {
    check_arity(L, fn, 2, 3);
    std::uintptr_t a = arg_address(L, 1);
    int value_idx = 2;
    if (lua_gettop(L) == 3) { a = offset_by(L, a, 2); value_idx = 3; }

    const lua_Number raw = arg_number(L, value_idx);
    if (!(raw >= lo && raw <= hi))
        luaL_error(L, "invalid write: value (%f) outside of type's range",
                   double(raw));

    const T v = T(raw);
    store(L, a, &v, sizeof v, kind, fmt(shown_fmt, double(raw)));
    return 0;
}

#define KP_WRITER(name, T, kind, lo, hi, shown)                                \
    int l_##name(lua_State* L) {                                               \
        return write_scalar<T>(L, #name, kind, lo, hi, shown);                 \
    }

KP_WRITER(writebyte,   std::uint8_t,  "byte",   0.0,           255.0,        "%.0f")
KP_WRITER(writechar,   std::int8_t,   "char",   -128.0,        127.0,        "%.0f")
KP_WRITER(writeword,   std::uint16_t, "word",   0.0,           65535.0,      "%.0f")
KP_WRITER(writeshort,  std::int16_t,  "short",  -32768.0,      32767.0,      "%.0f")
KP_WRITER(writedword,  std::uint32_t, "dword",  0.0,           4294967295.0, "%.0f")
KP_WRITER(writeint,    std::int32_t,  "int",    -2147483648.0, 2147483647.0, "%.0f")
KP_WRITER(writefloat,  float,         "float",  -3.402823466e38, 3.402823466e38, "%g")
KP_WRITER(writedouble, double,        "double", -HUGE_VAL,     HUGE_VAL,     "%g")

#undef KP_WRITER

int l_writebit(lua_State* L) {
    // gettop == 4 selects the legacy (base, offset, bit, value) form.
    check_arity(L, "writebit", 3, 4);
    std::uintptr_t a = arg_address(L, 1);
    int bit_idx = 2;
    if (lua_gettop(L) == 4) { a = offset_by(L, a, 2); bit_idx = 3; }

    unsigned bit = 0;
    a = normalise_bit(L, a, bit_idx, bit);

    // Phasor popped this as (x == 1), so writebit(a, 0, 2) silently CLEARED the
    // bit. That is a trap, not a feature, so anything that is not a boolean or
    // 0/1 raises here instead of quietly doing the opposite of what was meant.
    const int vi = bit_idx + 1;
    bool set = false;
    if (lua_type(L, vi) == LUA_TBOOLEAN) {
        set = lua_toboolean(L, vi) != 0;
    } else {
        const lua_Number n = arg_number(L, vi);
        if (n != 0.0 && n != 1.0)
            luaL_argerror(L, vi, "bit value must be a boolean, 0, or 1");
        set = n == 1.0;
    }

    std::uint8_t v = 0;
    // The only read in the module that raises instead of returning nil: this is
    // the read half of a read-modify-write, so a nil here would mean a silently
    // skipped write.
    if (!probe_read(a, &v, 1))
        luaL_error(L, "invalid read: 1 bytes from %s", hex32(a).c_str());

    const std::uint8_t updated = std::uint8_t(set ? (v | (1u << bit))
                                                  : (v & ~(1u << bit)));
    char shown[32];
    std::snprintf(shown, sizeof shown, "bit %u := %d", bit, set ? 1 : 0);
    store(L, a, &updated, 1, "bit", shown);
    return 0;
}

int l_writestring(lua_State* L) {
    check_arity(L, "writestring", 2, 3);
    std::uintptr_t a = arg_address(L, 1);
    int text_idx = 2;
    if (lua_gettop(L) == 3) { a = offset_by(L, a, 2); text_idx = 3; }

    std::size_t len = 0;
    const char* text = lua_tolstring(L, text_idx, &len);
    if (!text)
        luaL_argerror(L, text_idx, lua_pushfstring(L, "expected string, got %s",
                                                   luaL_typename(L, text_idx)));

    // Body plus terminator in one store, so the write log records one span the
    // size of what was actually touched. Phasor wrote the NUL separately, which
    // made the log understate the damage by a byte.
    std::vector<std::uint8_t> bytes(text, text + len);
    bytes.push_back(0);
    store(L, a, bytes.data(), bytes.size(), "string",
          std::string("\"") + std::string(text, len) + "\"");
    return 0;
}

int l_writewidestring(lua_State* L) {
    check_arity(L, "writewidestring", 2, 3);
    std::uintptr_t a = arg_address(L, 1);
    int text_idx = 2;
    if (lua_gettop(L) == 3) { a = offset_by(L, a, 2); text_idx = 3; }

    std::size_t len = 0;
    const char* text = lua_tolstring(L, text_idx, &len);
    if (!text)
        luaL_argerror(L, text_idx, lua_pushfstring(L, "expected string, got %s",
                                                   luaL_typename(L, text_idx)));

    std::vector<std::uint8_t> bytes;
    bytes.reserve((len + 1) * 2);
    for (std::size_t i = 0; i < len; ++i) {
        bytes.push_back(std::uint8_t(text[i]));
        bytes.push_back(0);
    }
    bytes.push_back(0);
    bytes.push_back(0);
    store(L, a, bytes.data(), bytes.size(), "widestring",
          std::string("L\"") + std::string(text, len) + "\"");
    return 0;
}

// ---------------------------------------------------------------- findsig --

struct Pattern {
    std::vector<std::uint8_t> value;
    std::vector<std::uint8_t> mask;   // 0x00 = wildcard nibble pair, 0xF0/0x0F/0xFF
};

int nibble(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

// '?' is a NIBBLE wildcard, which is Phasor's rule and not the more common
// byte-wildcard one: "4?" matches any byte whose high nibble is 4. Whitespace is
// skipped, which Phasor did not allow -- every signature anyone pastes is
// space-separated, and rejecting that would be a papercut with no upside.
bool parse_pattern(const char* text, std::size_t len, Pattern& out) {
    std::vector<int> nibbles;
    std::vector<bool> wild;
    for (std::size_t i = 0; i < len; ++i) {
        const char c = text[i];
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r') continue;
        if (c == '?') { nibbles.push_back(0); wild.push_back(true); continue; }
        const int n = nibble(c);
        if (n < 0) return false;
        nibbles.push_back(n);
        wild.push_back(false);
    }
    if (nibbles.empty()) return false;
    // An odd nibble count gets a trailing wildcard, as Phasor does.
    if (nibbles.size() % 2) { nibbles.push_back(0); wild.push_back(true); }

    for (std::size_t i = 0; i < nibbles.size(); i += 2) {
        std::uint8_t v = std::uint8_t((nibbles[i] << 4) | nibbles[i + 1]);
        std::uint8_t m = 0;
        if (!wild[i])     m |= 0xF0;
        if (!wild[i + 1]) m |= 0x0F;
        out.value.push_back(std::uint8_t(v & m));
        out.mask.push_back(m);
    }
    return true;
}

bool matches_at(const std::uint8_t* p, const Pattern& pat) {
    for (std::size_t i = 0; i < pat.value.size(); ++i)
        if ((p[i] & pat.mask[i]) != pat.value[i]) return false;
    return true;
}

// Scan one contiguous readable run. Runs are built page by page so a section
// with a hole in it -- which the encrypted K1 build can present mid-decipher --
// costs a skipped page rather than a fault.
std::uintptr_t scan_regions_for(const Pattern& pat, std::uint32_t occurrence) {
    const std::size_t n = pat.value.size();
    std::uint32_t seen = 0;

    for (const ScanRegion& r : scan_regions()) {
        if (r.size < n) continue;
        std::uintptr_t cursor = r.va;
        const std::uintptr_t end = r.va + r.size;

        while (cursor < end) {
            if (!platform::is_readable(reinterpret_cast<const void*>(cursor), 1)) {
                cursor = (cursor & ~(kPage - 1)) + kPage;
                continue;
            }
            std::uintptr_t run_end = (cursor & ~(kPage - 1)) + kPage;
            if (run_end > end) run_end = end;
            while (run_end < end &&
                   platform::is_readable(reinterpret_cast<const void*>(run_end), 1)) {
                const std::uintptr_t next = run_end + kPage;
                run_end = next > end ? end : next;
            }

            if (run_end - cursor >= n) {
                const auto* base = reinterpret_cast<const std::uint8_t*>(cursor);
                const std::size_t span = std::size_t(run_end - cursor) - n + 1;
                for (std::size_t i = 0; i < span; ++i) {
                    if (!matches_at(base + i, pat)) continue;
                    if (seen == occurrence) return cursor + i;
                    ++seen;
                }
            }
            cursor = run_end;
        }
    }
    return 0;
}

int l_findsig(lua_State* L) {
    check_arity(L, "findsig", 1, 2);
    std::size_t len = 0;
    const char* text = lua_tolstring(L, 1, &len);
    if (!text)
        luaL_argerror(L, 1, lua_pushfstring(L, "expected string, got %s",
                                            luaL_typename(L, 1)));

    Pattern pat;
    if (!parse_pattern(text, len, pat))
        luaL_argerror(L, 1, "signature must be hex digits and '?' wildcards");

    std::uint32_t occurrence = 0;
    if (lua_gettop(L) == 2 && !lua_isnoneornil(L, 2)) {
        const lua_Number n = arg_number(L, 2);
        if (!(n >= 0 && n <= 4294967295.0))
            luaL_argerror(L, 2, "occurrence must be zero or positive");
        occurrence = std::uint32_t(std::int64_t(n));
    }

    // The key carries the module base, so a rebased or reloaded module does not
    // hand back an address from the previous mapping.
    char key[64];
    std::snprintf(key, sizeof key, "%08X|%u|", (unsigned)scan_base(), occurrence);
    const std::string memo_key = std::string(key) + std::string(text, len);

    auto& cache = memo();
    auto it = cache.find(memo_key);
    if (it == cache.end()) {
        const std::uintptr_t hit = scan_regions_for(pat, occurrence);
        it = cache.emplace(memo_key, hit).first;   // misses are cached too
    }

    if (it->second == 0) { lua_pushnil(L); return 1; }
    lua_pushnumber(L, lua_Number(it->second));
    return 1;
}

// ----------------------------------------------------------- registration --

struct Entry {
    const char*  name;
    lua_CFunction fn;
};

const Entry kFunctions[] = {
    {"readbit",         l_readbit},
    {"readbyte",        l_readbyte},
    {"readchar",        l_readchar},
    {"readword",        l_readword},
    {"readshort",       l_readshort},
    {"readdword",       l_readdword},
    {"readint",         l_readint},
    {"readfloat",       l_readfloat},
    {"readdouble",      l_readdouble},
    {"readstring",      l_readstring},
    {"readwidestring",  l_readwidestring},
    {"writebit",        l_writebit},
    {"writebyte",       l_writebyte},
    {"writechar",       l_writechar},
    {"writeword",       l_writeword},
    {"writeshort",      l_writeshort},
    {"writedword",      l_writedword},
    {"writeint",        l_writeint},
    {"writefloat",      l_writefloat},
    {"writedouble",     l_writedouble},
    {"writestring",     l_writestring},
    {"writewidestring", l_writewidestring},
    {"findsig",         l_findsig},
};

}  // namespace

// ------------------------------------------------------------ public API ----

void bind_scan_regions(std::uintptr_t module_base, std::vector<ScanRegion> regions) {
    ScanState& s = scan_state();
    s.base = module_base;
    s.regions = std::move(regions);
    std::sort(s.regions.begin(), s.regions.end(),
              [](const ScanRegion& a, const ScanRegion& b) { return a.va < b.va; });
    s.bound = true;
    s.derived = true;
    // Addresses found against the previous bounds are not valid against these.
    memo().clear();
}

const std::vector<ScanRegion>& scan_regions() {
    ScanState& s = scan_state();
    if (!s.bound && !s.derived) derive_regions();
    return s.regions;
}

std::uintptr_t scan_base() {
    ScanState& s = scan_state();
    if (!s.bound && !s.derived) derive_regions();
    return s.base;
}

std::uintptr_t find_unique(const std::uint8_t* bytes, std::size_t n) {
    if (bytes == nullptr || n == 0) return 0;
    Pattern pat;
    pat.value.assign(bytes, bytes + n);
    pat.mask.assign(n, 0xFF);
    const std::uintptr_t first = scan_regions_for(pat, 0);
    if (first == 0) return 0;
    if (scan_regions_for(pat, 1) != 0) return 0;
    return first;
}

void set_write_observer(WriteObserver obs, void* user) {
    g_observer = obs;
    g_observer_user = user;
}

unsigned long long writes_performed() { return g_writes; }

void register_all(lua_State* L) {
    const int base = lua_gettop(L);

    // The `kp` table is shared with the routine bridge and every other
    // module. Creating a fresh one here would silently drop whatever registered
    // first, and which module that is depends on runtime ordering.
    lua_getglobal(L, "kp");
    if (!lua_istable(L, -1)) {
        lua_pop(L, 1);
        lua_createtable(L, 0, 1);
        lua_pushvalue(L, -1);
        lua_setglobal(L, "kp");
    }

    lua_getfield(L, -1, "mem");
    if (!lua_istable(L, -1)) {
        lua_pop(L, 1);
        lua_createtable(L, 0, int(sizeof kFunctions / sizeof kFunctions[0]));
        lua_pushvalue(L, -1);
        lua_setfield(L, -3, "mem");
    }

    for (const Entry& e : kFunctions) {
        lua_pushcfunction(L, e.fn);
        lua_setfield(L, -2, e.name);
    }

    lua_settop(L, base);
}

}  // namespace kp::api::memory
