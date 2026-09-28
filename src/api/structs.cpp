#include "api/structs.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <utility>
#include <vector>

#include "platform/platform.hpp"

extern "C" {
#include "lauxlib.h"
#include "lua.h"
}

namespace kp::api::structs {
namespace {

// The generated layout table. It is included here and nowhere else, so the only
// way to reach a field is through the accessors below -- there is no path that
// takes an offset from a script and an address and multiplies them together.
#include "generated/structs_k1.inc"

constexpr std::size_t kLayoutCount = sizeof kLayouts / sizeof kLayouts[0];

// 4 KiB on both targets. Only used to bound how far a string read walks before
// asking the probe again, so that a CExoString running into an unmapped page
// yields the readable prefix instead of faulting on its last byte.
constexpr std::uintptr_t kPage = 4096;

// A CExoString carries its own length, and the engine's lengths are honest, but
// a stale pointer read as a string is not. This bounds the damage a garbage
// length can do to one allocation rather than to the whole address space.
constexpr std::uint32_t kMaxStringBytes = 65536;

// The same bound, for the other number this module reads out of live memory and
// then loops on: a CExoArrayList's element count.
//
// Every element access probes its own span, so the cost of a walk is one syscall
// per element. A stale or wrong header does not say "stale", it says twenty
// million, and twenty million probes is the calling thread gone for half a
// minute -- inside a tick callback or a hook body, that is the game hung. The
// cap is not a guess about what the engine holds: the largest list in the corpus
// is an area's object list, in the hundreds. Anything past this is a header
// nobody should be walking.
//
// It truncates loudly. seq_length logs once per sequence when it clamps, the
// header's own number stays readable as `.reported_size`, and the out-of-range
// message names the cap, so a capped list can never be mistaken for a short one.
constexpr std::uint32_t kMaxSeqElements = 65536;

const char kViewType[] = "kp.struct.view";
const char kSeqType[]  = "kp.struct.sequence";

// Per-script opt-in for writing offsets the corpus did not confirm. Keyed by the
// address of this byte, so nothing a script can write to the registry collides.
const char kUnverifiedKey = 0;

AddressResolver    g_resolver = nullptr;
unsigned long long g_writes   = 0;

// --------------------------------------------------------------- raw reads --

// Every read in this file goes through here. A bad address is answered, not
// dereferenced: the probe is a query (VirtualQuery, msync) so a script chasing a
// pointer that went stale between two ticks gets nil rather than taking the game
// down from inside a hook body.
bool read_span(std::uintptr_t addr, void* out, std::size_t len) {
    const void* p = reinterpret_cast<const void*>(addr);
    if (!platform::is_readable(p, len)) return false;
    std::memcpy(out, p, len);
    return true;
}

template <typename T>
bool read_at(std::uintptr_t addr, T& out) {
    return read_span(addr, &out, sizeof(T));
}

// Bytes from `addr`, stopping at the first page the probe refuses. Returns what
// it managed to read, which may be shorter than `len` and may be empty.
std::string read_bounded(std::uintptr_t addr, std::size_t len) {
    std::string out;
    out.reserve(std::min<std::size_t>(len, kPage));
    while (out.size() < len) {
        const std::uintptr_t at   = addr + out.size();
        const std::size_t    room = std::size_t(kPage - (at % kPage));
        const std::size_t    take = std::min(room, len - out.size());
        const std::size_t    was  = out.size();
        out.resize(was + take);
        if (!read_span(at, out.data() + was, take)) { out.resize(was); break; }
    }
    return out;
}

// ------------------------------------------------------------ name lookups --

// Fields are stored in offset order, which is what the contiguity assert needs
// and the wrong order for looking one up by name. 445 strcmps per field access
// in a tick callback is a cost worth removing once rather than paying forever,
// so each layout gets a name-sorted index the first time it is touched.
struct NameIndex {
    std::vector<std::vector<const Field*>> by_layout;
};

NameIndex& name_index() {
    static NameIndex idx = [] {
        NameIndex n;
        n.by_layout.resize(kLayoutCount);
        for (std::size_t i = 0; i < kLayoutCount; ++i) {
            auto& v = n.by_layout[i];
            v.reserve(kLayouts[i].field_count);
            for (std::uint32_t f = 0; f < kLayouts[i].field_count; ++f)
                v.push_back(&kLayouts[i].fields[f]);
            std::sort(v.begin(), v.end(), [](const Field* a, const Field* b) {
                return std::strcmp(a->name, b->name) < 0;
            });
        }
        return n;
    }();
    return idx;
}

std::size_t layout_index(const Layout* l) {
    return std::size_t(l - kLayouts);
}

const Field* find_field(const Layout* layout, const char* name) {
    const auto& v = name_index().by_layout[layout_index(layout)];
    auto it = std::lower_bound(v.begin(), v.end(), name,
                               [](const Field* f, const char* n) {
                                   return std::strcmp(f->name, n) < 0;
                               });
    if (it == v.end() || std::strcmp((*it)->name, name) != 0) return nullptr;
    return *it;
}

// Levenshtein, capped. Used only to build the "did you mean" list, so an exact
// distance past the cap is not worth computing.
int edit_distance(const char* a, const char* b, int cap) {
    const int la = int(std::strlen(a)), lb = int(std::strlen(b));
    if (std::abs(la - lb) > cap) return cap + 1;
    std::vector<int> prev(std::size_t(lb) + 1), cur(std::size_t(lb) + 1);
    for (int j = 0; j <= lb; ++j) prev[std::size_t(j)] = j;
    for (int i = 1; i <= la; ++i) {
        cur[0] = i;
        int best = cur[0];
        for (int j = 1; j <= lb; ++j) {
            // Cast through unsigned char: `a` is a name a script typed, so a
            // byte above 0x7F reaches here, and tolower on a negative char is
            // undefined.
            const int cost = (std::tolower(static_cast<unsigned char>(a[i - 1])) ==
                              std::tolower(static_cast<unsigned char>(b[j - 1]))) ? 0 : 1;
            cur[std::size_t(j)] = std::min({prev[std::size_t(j)] + 1,
                                            cur[std::size_t(j) - 1] + 1,
                                            prev[std::size_t(j) - 1] + cost});
            best = std::min(best, cur[std::size_t(j)]);
        }
        if (best > cap) return cap + 1;
        prev.swap(cur);
    }
    return prev[std::size_t(lb)];
}

// The near-miss list a misspelled field name is answered with.
//
// A typo in the offset idiom reads whatever is next door and says nothing. The
// whole point of naming fields is that the mistake becomes visible, and a
// message that only says "no such field" on a 445-field struct is visible but
// not useful.
std::string near_misses(const Layout* layout, const char* wanted) {
    const int cap = std::max(2, int(std::strlen(wanted)) / 3);
    std::vector<std::pair<int, const char*>> hits;
    for (std::uint32_t i = 0; i < layout->field_count; ++i) {
        const char* n = layout->fields[i].name;
        int d = edit_distance(wanted, n, cap);
        if (d > cap && std::strstr(n, wanted) == nullptr) continue;
        if (d > cap) d = cap;   // a substring match ranks after the edits
        hits.emplace_back(d, n);
    }
    std::sort(hits.begin(), hits.end(), [](const auto& a, const auto& b) {
        if (a.first != b.first) return a.first < b.first;
        return std::strcmp(a.second, b.second) < 0;
    });
    if (hits.empty()) return {};
    std::string out = " Did you mean: ";
    for (std::size_t i = 0; i < hits.size() && i < 5; ++i) {
        if (i) out += ", ";
        out += hits[i].second;
    }
    return out + "?";
}

std::string near_layouts(const char* wanted) {
    const int cap = std::max(2, int(std::strlen(wanted)) / 3);
    std::vector<std::pair<int, const char*>> hits;
    for (std::size_t i = 0; i < kLayoutCount; ++i) {
        const int d = edit_distance(wanted, kLayouts[i].name, cap);
        if (d <= cap) hits.emplace_back(d, kLayouts[i].name);
    }
    std::sort(hits.begin(), hits.end());
    if (hits.empty()) return {};
    std::string out = " Did you mean: ";
    for (std::size_t i = 0; i < hits.size() && i < 5; ++i) {
        if (i) out += ", ";
        out += hits[i].second;
    }
    return out + "?";
}

const char* kind_name(Kind k) {
    switch (k) {
    case Kind::Unknown:   return "unknown";
    case Kind::U8:        return "u8";
    case Kind::I8:        return "i8";
    case Kind::U16:       return "u16";
    case Kind::I16:       return "i16";
    case Kind::U32:       return "u32";
    case Kind::I32:       return "i32";
    case Kind::U64:       return "u64";
    case Kind::F32:       return "f32";
    case Kind::Ptr:       return "ptr";
    case Kind::Struct:    return "struct";
    case Kind::Vector:    return "Vector";
    case Kind::ExoString: return "CExoString";
    case Kind::LocString: return "CExoLocString";
    case Kind::ResRef:    return "CResRef";
    case Kind::List:      return "CExoArrayList";
    case Kind::Array:     return "array";
    case Kind::Blob:      return "bytes";
    }
    return "unknown";
}

const char* confidence_name(Confidence c) {
    switch (c) {
    case Confidence::High: return "high";
    case Confidence::Med:  return "med";
    case Confidence::Low:  return "low";
    }
    return "low";
}

// -------------------------------------------------------------- userdata ----

// A view is an address plus a layout. When it came from an object id it keeps
// the id and its own distance from that object's base, so every access can
// re-ask the resolver rather than trusting an address that was true one tick
// ago. `id_offset` is what makes that work through a nested view: the
// CSWSObject embedded at CSWSCreature+0 and the CSWSCreatureStats at +0xA74 are
// both reached from the same id, at different distances.
struct View {
    std::uint32_t  magic;
    std::uintptr_t addr;        // where this view's bytes were as of the last resolve
    const Layout*  layout;
    std::uint32_t  object_id;
    std::uint32_t  id_offset;   // this view's distance from the object's base
    bool           has_id;
    bool           retired;     // the id stopped resolving; see refresh()
};

// An inline array or a CExoArrayList, which differ in exactly one way: an array
// knows its count at build time and a list has to be asked every time, because
// the engine's Add can move the storage and change the count between two reads.
//
// It carries the same id as the view it came from, for the same reason: the
// header lives inside the object, so a destroyed object means a header that is
// no longer a header.
struct Seq {
    std::uint32_t  magic;
    std::uintptr_t head;         // the CExoArrayList header, or the array itself
    const Layout*  elem_layout;  // for Kind::Struct elements
    const char*    owner_struct;
    const char*    owner_field;
    std::uint32_t  elem_size;
    std::uint32_t  fixed_count;  // arrays only
    std::uint32_t  object_id;
    std::uint32_t  head_offset;  // the header's distance from the object's base
    Kind           elem;
    bool           is_list;
    bool           has_id;
    bool           retired;
};

// Two words that mean "this really is one of ours". See check_ud.
constexpr std::uint32_t kViewMagic = 0x5653544Bu;  // 'KTSV'
constexpr std::uint32_t kSeqMagic  = 0x5153544Bu;  // 'KTSQ'

// Is this pointer one of the entries of kLayouts, and not merely inside it?
//
// layout_index() turns a Layout* into an array index by subtraction, and
// push_element dereferences elem_layout. Both are safe for pointers this file
// produced and neither is safe for a pointer that arrived out of a forged
// userdata, so the check is here rather than assumed at every use.
bool layout_in_table(const Layout* l) {
    const auto lo = reinterpret_cast<std::uintptr_t>(kLayouts);
    const auto at = reinterpret_cast<std::uintptr_t>(l);
    if (at < lo || at >= lo + sizeof kLayouts) return false;
    return (at - lo) % sizeof(Layout) == 0;
}

// Is the value at `index` a userdata this file made?
//
// luaL_checkudata compares the metatable and stops there, which is not enough
// here. luaL_openlibs gives every script the debug library, so a script can take
// this metatable off a real view with debug.getmetatable and put it on a
// userdata that is not ours -- newproxy() makes a zero-byte one. Reading a View
// out of that reads off the end of the allocation, which is the fault this
// module promised never to take.
//
// So the size is checked first, before anything dereferences the pointer, and a
// magic word is checked after. lua_objlen on a userdata is the size Lua
// allocated, which a script has no way to choose.
void* check_ud(lua_State* L, int index, const char* tname, std::size_t want) {
    void* p = lua_touserdata(L, index);
    if (!p) return nullptr;
    if (lua_objlen(L, index) != want) return nullptr;
    if (!lua_getmetatable(L, index)) return nullptr;
    luaL_getmetatable(L, tname);
    const bool ours = lua_rawequal(L, -1, -2) != 0;
    lua_pop(L, 2);
    return ours ? p : nullptr;
}

View* to_view(lua_State* L, int index) {
    auto* v = static_cast<View*>(check_ud(L, index, kViewType, sizeof(View)));
    if (!v || v->magic != kViewMagic || !layout_in_table(v->layout)) return nullptr;
    return v;
}

Seq* to_seq(lua_State* L, int index) {
    auto* s = static_cast<Seq*>(check_ud(L, index, kSeqType, sizeof(Seq)));
    if (!s || s->magic != kSeqMagic) return nullptr;
    if (s->elem_layout && !layout_in_table(s->elem_layout)) return nullptr;
    return s;
}

void push_view(lua_State* L, std::uintptr_t addr, const Layout* layout,
               std::uint32_t id, bool has_id, std::uint32_t id_offset) {
    auto* v = static_cast<View*>(lua_newuserdata(L, sizeof(View)));
    v->magic = kViewMagic;
    v->addr = addr;
    v->layout = layout;
    v->object_id = id;
    v->id_offset = id_offset;
    v->has_id = has_id;
    v->retired = false;
    luaL_getmetatable(L, kViewType);
    lua_setmetatable(L, -2);
}

void push_seq(lua_State* L, const Seq& s) {
    auto* p = static_cast<Seq*>(lua_newuserdata(L, sizeof(Seq)));
    *p = s;
    p->magic = kSeqMagic;
    luaL_getmetatable(L, kSeqType);
    lua_setmetatable(L, -2);
}

// ------------------------------------------------------------ re-resolving --

// Ask the resolver again, before this access rather than after it.
//
// data/hostapi.toml states the contract: a view "holds an object id and
// re-resolves it, so it cannot outlive its object", and the failure it names is
// "view of object 0x... is stale". That has to happen on the read and on the
// write, not only in valid() and address(). Between two ticks the engine can
// destroy the object and hand its storage to the next allocation, and a write
// through the remembered address then lands in whatever moved in -- with a log
// line naming a field of an object that no longer exists.
//
// The design says "once per tick". This module has no tick source and takes no
// dependency on one, so it re-asks on every access instead. The resolver is a
// hash lookup in the object array; a field read that already costs a syscall
// can afford it.
//
// Retirement is sticky on purpose. The engine hands out object ids from two
// counters that grow toward each other and it reuses them, so a view that
// started resolving again after a failure would be reading a different object
// under the same name. A stale view is a refusal, permanently.
//
// The one thing that costs: a resolver that answers 0 for an object that is in
// fact alive retires the view for good. That is the safe direction, and the
// window is small -- the resolver has to have worked at least once, or there
// would be no view to retire.
bool refresh(View* v) {
    if (!v->has_id) return true;
    if (v->retired) return false;
    // No resolver means the question cannot be answered, so it is not answered
    // with the old address. This is not retirement: the entity module installs
    // the resolver and could install another one.
    if (!g_resolver) return false;
    const char* unused = nullptr;
    const std::uintptr_t base = g_resolver(v->object_id, &unused);
    if (base == 0) {
        v->retired = true;
        v->addr = 0;
        return false;
    }
    v->addr = base + v->id_offset;
    return true;
}

bool refresh(Seq* s) {
    if (!s->has_id) return true;
    if (s->retired) return false;
    if (!g_resolver) return false;
    const char* unused = nullptr;
    const std::uintptr_t base = g_resolver(s->object_id, &unused);
    if (base == 0) {
        s->retired = true;
        s->head = 0;
        return false;
    }
    s->head = base + s->head_offset;
    return true;
}

int stale_view(lua_State* L, const View* v, const char* what) {
    return luaL_error(L, "view of object 0x%08X is stale: it no longer resolves to an "
                         "address, so %s was not touched. kp.struct.valid() answers "
                         "this without raising",
                      unsigned(v->object_id), what);
}

int stale_seq(lua_State* L, const Seq* s) {
    return luaL_error(L, "%s.%s belongs to object 0x%08X, which is stale: its header no "
                         "longer resolves to an address, so nothing was read",
                      s->owner_struct, s->owner_field, unsigned(s->object_id));
}

// The element count the header claims, untouched. Reported rather than walked.
std::uint32_t seq_reported_length(const Seq& s) {
    if (!s.is_list) return s.fixed_count;
    std::int32_t n = 0;
    if (!read_at(s.head + 4, n)) return 0;
    if (n < 0) return 0;
    return std::uint32_t(n);
}

// The live element count of a list, or the fixed count of an array, capped at
// what this module is willing to walk. A list whose header is not mapped has no
// elements as far as a script is concerned; that is the same answer as an empty
// list, and it is the only answer that does not invite iterating over garbage.
// Has this field already reported an over-long header?
//
// Once per field, not once per sequence userdata: `obj.effects` builds a fresh
// sequence every time it is indexed, so a per-sequence flag would put a line in
// the log on every iteration of `while i <= #obj.effects`. The names come from
// the generated table, so comparing the pointers is comparing the fields.
bool first_cap_report(const char* owner_struct, const char* owner_field) {
    static std::vector<std::pair<const char*, const char*>> seen;
    for (const auto& e : seen)
        if (e.first == owner_struct && e.second == owner_field) return false;
    seen.emplace_back(owner_struct, owner_field);
    return true;
}

std::uint32_t seq_length(Seq& s) {
    const std::uint32_t n = seq_reported_length(s);
    if (n <= kMaxSeqElements) return n;
    if (first_cap_report(s.owner_struct, s.owner_field)) {
        platform::log(platform::LogLevel::Warn,
                      "%s.%s at 0x%08X says it holds %u elements. That is past the %u "
                      "this module will walk, so it reports %u; the header's own number "
                      "is still readable as .reported_size",
                      s.owner_struct, s.owner_field, unsigned(s.head),
                      unsigned(n), unsigned(kMaxSeqElements), unsigned(kMaxSeqElements));
    }
    return kMaxSeqElements;
}

// Where the elements actually live. Read every time for a list, because this is
// the slot the whole module exists to stop a script reading as a value.
bool seq_data(const Seq& s, std::uintptr_t& out) {
    if (!s.is_list) { out = s.head; return true; }
    std::uint32_t p = 0;
    if (!read_at(s.head, p)) return false;
    out = p;
    return true;
}

// ---------------------------------------------------------------- pushing ----

// One value of `kind` at `addr`, or nil when the span is not mapped.
//
// `size` and `elem_size` are the field's, so a Blob knows how many bytes it is
// and an Array element knows its stride. Every branch reads exactly the width
// the generated table declared -- that is the whole difference between this and
// picking readdword because it was the function you remembered.
int push_scalar(lua_State* L, std::uintptr_t addr, Kind kind, std::uint32_t size) {
    switch (kind) {
    case Kind::U8:  { std::uint8_t  v; if (!read_at(addr, v)) break; lua_pushnumber(L, v); return 1; }
    case Kind::I8:  { std::int8_t   v; if (!read_at(addr, v)) break; lua_pushnumber(L, v); return 1; }
    case Kind::U16: { std::uint16_t v; if (!read_at(addr, v)) break; lua_pushnumber(L, v); return 1; }
    case Kind::I16: { std::int16_t  v; if (!read_at(addr, v)) break; lua_pushnumber(L, v); return 1; }
    case Kind::U32:
    case Kind::Ptr: { std::uint32_t v; if (!read_at(addr, v)) break; lua_pushnumber(L, v); return 1; }
    case Kind::I32: { std::int32_t  v; if (!read_at(addr, v)) break; lua_pushnumber(L, v); return 1; }
    case Kind::U64: { std::uint64_t v; if (!read_at(addr, v)) break;
                      // Past 2^53 this is lossy, which is stated rather than
                      // hidden: there is one u64 field in the whole corpus and
                      // Lua 5.1 has no integer type to hand it back in.
                      lua_pushnumber(L, lua_Number(v)); return 1; }
    case Kind::F32: { float v; if (!read_at(addr, v)) break; lua_pushnumber(L, v); return 1; }

    case Kind::Vector: {
        float v[3];
        if (!read_span(addr, v, sizeof v)) break;
        lua_createtable(L, 0, 3);
        lua_pushnumber(L, v[0]); lua_setfield(L, -2, "x");
        lua_pushnumber(L, v[1]); lua_setfield(L, -2, "y");
        lua_pushnumber(L, v[2]); lua_setfield(L, -2, "z");
        return 1;
    }

    case Kind::ExoString: {
        // Slot 0 is a char*, not the text. Reading it as a number is the
        // eight-byte version of the twelve-byte trap.
        std::uint32_t ptr = 0, len = 0;
        if (!read_at(addr, ptr) || !read_at(addr + 4, len)) break;
        if (len == 0) { lua_pushliteral(L, ""); return 1; }
        if (ptr == 0) break;               // a length with no buffer is garbage
        if (len > kMaxStringBytes) len = kMaxStringBytes;
        const std::string s = read_bounded(ptr, len);
        if (s.empty() && len != 0) break;
        lua_pushlstring(L, s.data(), s.size());
        return 1;
    }

    case Kind::LocString: {
        // Same eight bytes as a CExoString and not the same meaning, which is
        // why the research file marks every one of these `med`. It comes back
        // as its parts rather than as text this module cannot resolve.
        std::uint32_t ptr = 0;
        std::int32_t  strref = 0;
        if (!read_at(addr, ptr) || !read_at(addr + 4, strref)) break;
        lua_createtable(L, 0, 2);
        lua_pushnumber(L, ptr);    lua_setfield(L, -2, "ptr");
        lua_pushnumber(L, strref); lua_setfield(L, -2, "strref");
        return 1;
    }

    case Kind::ResRef: {
        char buf[16];
        if (!read_span(addr, buf, sizeof buf)) break;
        std::size_t n = 0;
        while (n < sizeof buf && buf[n] != '\0') ++n;
        lua_pushlstring(L, buf, n);
        return 1;
    }

    case Kind::Blob: {
        const std::string s = read_bounded(addr, size);
        if (s.size() != size) break;
        lua_pushlstring(L, s.data(), s.size());
        return 1;
    }

    default:
        break;
    }
    lua_pushnil(L);
    return 1;
}

// ------------------------------------------------------------- view index ----

int view_index(lua_State* L) {
    View* v = to_view(L, 1);
    if (!v) return luaL_error(L, "not a struct view");
    // Before the field lookup, so `at` below cannot be computed from an address
    // the resolver has already stopped agreeing with. Nothing between here and
    // the read re-enters Lua, so one refresh covers the whole access.
    if (!refresh(v)) return stale_view(L, v, "the field you asked for");
    const char* key = lua_tostring(L, 2);
    if (!key) return luaL_error(L, "%s is indexed by field name, not by %s",
                                v->layout->name, luaL_typename(L, 2));

    const Field* f = find_field(v->layout, key);
    if (!f) {
        const std::string hint = near_misses(v->layout, key);
        return luaL_error(L, "%s has no field named '%s'.%s "
                             "(%d bytes, %d fields; kp.struct.fields(\"%s\") lists them)",
                          v->layout->name, key, hint.c_str(),
                          int(v->layout->size), int(v->layout->field_count),
                          v->layout->name);
    }

    const std::uintptr_t at = v->addr + f->offset;

    switch (f->kind) {
    case Kind::Struct: {
        const Layout* nested = find(f->struct_name);
        if (!nested)
            return luaL_error(L, "%s.%s is a %s and this build has no layout for it",
                              v->layout->name, f->name, f->struct_name);
        // The nested view inherits the id and its own distance from the base, so
        // `creature.object.current_hp` re-resolves exactly as `creature` does.
        push_view(L, at, nested, v->object_id, v->has_id, v->id_offset + f->offset);
        return 1;
    }

    case Kind::List:
    case Kind::Array: {
        Seq s{};
        s.head = at;
        s.elem = f->elem;
        s.elem_size = f->elem_size;
        s.fixed_count = f->count;
        s.is_list = (f->kind == Kind::List);
        s.elem_layout = (f->elem == Kind::Struct) ? find(f->struct_name) : nullptr;
        s.owner_struct = v->layout->name;
        s.owner_field = f->name;
        s.object_id = v->object_id;
        s.head_offset = v->id_offset + f->offset;
        s.has_id = v->has_id;
        push_seq(L, s);
        return 1;
    }

    default:
        return push_scalar(L, at, f->kind, f->size);
    }
}

// -------------------------------------------------------------- view write ----

bool unverified_allowed(lua_State* L) {
    lua_pushlightuserdata(L, const_cast<char*>(&kUnverifiedKey));
    lua_rawget(L, LUA_REGISTRYINDEX);
    if (!lua_isnil(L, -1)) {
        const bool on = lua_toboolean(L, -1) != 0;
        lua_pop(L, 1);
        return on;
    }
    lua_pop(L, 1);
    return false;
}

struct Range { double lo, hi; };

bool integer_range(Kind k, Range& r) {
    switch (k) {
    case Kind::U8:  r = {0, 255}; return true;
    case Kind::I8:  r = {-128, 127}; return true;
    case Kind::U16: r = {0, 65535}; return true;
    case Kind::I16: r = {-32768, 32767}; return true;
    case Kind::U32:
    case Kind::Ptr: r = {0, 4294967295.0}; return true;
    case Kind::I32: r = {-2147483648.0, 2147483647.0}; return true;
    case Kind::U64: r = {0, 18446744073709551615.0}; return true;
    default: return false;
    }
}

// The Lua statement that asked. A corrupted save is traced back to a line, not
// to a file, so this is worth the two stack operations.
std::string call_site(lua_State* L) {
    luaL_where(L, 1);
    const char* w = lua_tostring(L, -1);
    std::string out = w ? w : "";
    lua_pop(L, 1);
    return out;
}

int view_newindex(lua_State* L) {
    View* v = to_view(L, 1);
    if (!v) return luaL_error(L, "not a struct view");
    // First, and before `at` is computed from v->addr further down. A write is
    // the access that cannot be taken back: a destroyed object's storage belongs
    // to whatever the allocator handed it to next.
    if (!refresh(v)) return stale_view(L, v, "the field you assigned to");
    const char* key = lua_tostring(L, 2);
    if (!key) return luaL_error(L, "%s is indexed by field name, not by %s",
                                v->layout->name, luaL_typename(L, 2));

    const Field* f = find_field(v->layout, key);
    if (!f) {
        const std::string hint = near_misses(v->layout, key);
        return luaL_error(L, "%s has no field named '%s'.%s "
                             "A view does not take new fields; it is a window onto %d bytes",
                          v->layout->name, key, hint.c_str(), int(v->layout->size));
    }

    Range range{};
    const bool integral = integer_range(f->kind, range);
    if (!integral && f->kind != Kind::F32)
        return luaL_error(L, "%s.%s is %s, %d bytes. Assigning to an aggregate would store "
                             "a few bytes over a whole field, so it is refused; write its "
                             "parts instead",
                          v->layout->name, f->name, f->type_text, int(f->size));

    // The confidence gate sits after the kind check and before the store, so
    // that when it speaks it is the reason.
    //
    // It used to come first. That reads well and reported badly: every field the
    // corpus marks below high confidence is an aggregate, so the gate's message
    // was printed for writes the next check was going to refuse anyway, opting
    // in changed nothing, and the gate had never once decided an outcome. It
    // still has to come before the readability probe -- a low-confidence offset
    // that happens to be mapped must be refused by the gate, not waved through
    // to a "not mapped" message that would be wrong about why.
    if (f->confidence != Confidence::High && !unverified_allowed(L))
        return luaL_error(L, "%s.%s is %s confidence: the corpus did not confirm this offset, "
                             "so a wrong write here corrupts a neighbour. Reading it is fine. "
                             "Call kp.struct.allow_unverified_writes(true) to opt in",
                          v->layout->name, f->name, confidence_name(f->confidence));

    if (lua_type(L, 3) != LUA_TNUMBER)
        return luaL_error(L, "%s.%s takes a number, not a %s",
                          v->layout->name, f->name, luaL_typename(L, 3));
    const double value = double(lua_tonumber(L, 3));

    if (integral) {
        if (std::floor(value) != value)
            return luaL_error(L, "%s.%s is %s: %f is not a whole number, and truncating it "
                                 "quietly is how a wrong value gets written",
                              v->layout->name, f->name, kind_name(f->kind), value);
        if (value < range.lo || value > range.hi)
            return luaL_error(L, "%.0f does not fit %s.%s, which is %s (%d byte(s), %.0f..%.0f). "
                                 "Writing a wider value over a narrower field is an error here, "
                                 "not a truncation",
                              value, v->layout->name, f->name, kind_name(f->kind),
                              int(f->size), range.lo, range.hi);
    } else if (std::isfinite(value) &&
               std::fabs(value) > 3.402823466e38) {
        return luaL_error(L, "%g does not fit %s.%s, which is a 32-bit float",
                          value, v->layout->name, f->name);
    }

    const std::uintptr_t at = v->addr + f->offset;

    // The probe is a readability query, and a mapping can be readable without
    // being writable. It is here because it catches the common failure -- a
    // stale or null base -- without pretending to catch every one.
    if (!platform::is_readable(reinterpret_cast<const void*>(at), f->size))
        return luaL_error(L, "%s.%s is at 0x%08X, which is not mapped. Nothing was written",
                          v->layout->name, f->name, unsigned(at));

    void* dst = reinterpret_cast<void*>(at);
    switch (f->kind) {
    case Kind::U8:  { auto x = std::uint8_t(value);  std::memcpy(dst, &x, 1); break; }
    case Kind::I8:  { auto x = std::int8_t(value);   std::memcpy(dst, &x, 1); break; }
    case Kind::U16: { auto x = std::uint16_t(value); std::memcpy(dst, &x, 2); break; }
    case Kind::I16: { auto x = std::int16_t(value);  std::memcpy(dst, &x, 2); break; }
    case Kind::U32:
    case Kind::Ptr: { auto x = std::uint32_t(value); std::memcpy(dst, &x, 4); break; }
    case Kind::I32: { auto x = std::int32_t(value);  std::memcpy(dst, &x, 4); break; }
    case Kind::U64: { auto x = std::uint64_t(value); std::memcpy(dst, &x, 8); break; }
    case Kind::F32: { auto x = float(value);         std::memcpy(dst, &x, 4); break; }
    default: return luaL_error(L, "unreachable: %s.%s", v->layout->name, f->name);
    }

    ++g_writes;
    // Reported, not prevented. The same bargain kp.mem makes: the write goes
    // through, and the log says exactly which statement asked for it.
    //
    // An integer is logged as an integer and in hex as well. %g turns a pointer
    // into 2.87454e+08, and a log line nobody can read against the value they
    // typed is not a report.
    //
    // The hex is masked to the field's own width. -100 into an i8 stored one
    // byte, so it prints 0x9C; sign-extending it to 0xFFFFFFFFFFFFFF9C would be
    // a hex string that does not match the bytes that were written, which is
    // worse than not printing one.
    if (integral) {
        // Through int64 only when it is negative: the one u64 field in the
        // corpus can hold a value past INT64_MAX, and converting that to a
        // signed type is undefined rather than wrong.
        const auto raw = value < 0
            ? static_cast<std::uint64_t>(static_cast<std::int64_t>(value))
            : static_cast<std::uint64_t>(value);
        const std::uint64_t mask = f->size >= 8 ? ~std::uint64_t(0)
                                                : (std::uint64_t(1) << (f->size * 8)) - 1;
        platform::log(platform::LogLevel::Info,
                      "%sstruct write %s.%s at 0x%08X, %u byte(s) = %.0f (0x%llX)",
                      call_site(L).c_str(), v->layout->name, f->name,
                      unsigned(at), unsigned(f->size), value,
                      static_cast<unsigned long long>(raw & mask));
    } else
        platform::log(platform::LogLevel::Info,
                      "%sstruct write %s.%s at 0x%08X, %u byte(s) = %g",
                      call_site(L).c_str(), v->layout->name, f->name,
                      unsigned(at), unsigned(f->size), value);
    return 0;
}

int view_len(lua_State* L) {
    View* v = to_view(L, 1);
    if (!v) return luaL_error(L, "not a struct view");
    lua_pushnumber(L, v->layout->size);
    return 1;
}

int view_tostring(lua_State* L) {
    View* v = to_view(L, 1);
    if (!v) return luaL_error(L, "not a struct view");
    char buf[128];
    // tostring is what a print() in a diagnostic reaches for, so it reports a
    // stale view rather than raising in the middle of someone's log line.
    const bool live = refresh(v);
    if (v->has_id && !live)
        std::snprintf(buf, sizeof buf, "%s: stale (object 0x%08X)",
                      v->layout->name, unsigned(v->object_id));
    else if (v->has_id)
        std::snprintf(buf, sizeof buf, "%s: 0x%08X (object 0x%08X)",
                      v->layout->name, unsigned(v->addr), unsigned(v->object_id));
    else
        std::snprintf(buf, sizeof buf, "%s: 0x%08X", v->layout->name, unsigned(v->addr));
    lua_pushstring(L, buf);
    return 1;
}

// -------------------------------------------------------------- sequences ----

int push_element(lua_State* L, const Seq& s, std::uint32_t index_zero_based) {
    if (s.elem == Kind::Unknown || s.elem_size == 0)
        return luaL_error(L,
            "%s.%s is a CExoArrayList whose element type the research corpus never states, "
            "so its stride is unknown. Its size and data pointer are readable; indexing it "
            "is refused rather than guessing a stride and returning a wrong number",
            s.owner_struct, s.owner_field);

    std::uintptr_t data = 0;
    if (!seq_data(s, data)) { lua_pushnil(L); return 1; }
    if (data == 0) { lua_pushnil(L); return 1; }

    const std::uintptr_t at = data + std::uintptr_t(index_zero_based) * s.elem_size;
    if (s.elem == Kind::Struct) {
        if (!s.elem_layout)
            return luaL_error(L, "%s.%s holds a struct this build has no layout for",
                              s.owner_struct, s.owner_field);
        // An inline array's elements sit inside the object, so they inherit the
        // id at their own distance from its base. A CExoArrayList's do not: the
        // storage is a separate allocation the engine may reallocate, so an id
        // plus a distance would name a place that stops being the element. Those
        // stay address-backed, and go stale the way kp.struct.at does.
        if (!s.is_list && s.has_id)
            push_view(L, at, s.elem_layout, s.object_id, true,
                      s.head_offset + index_zero_based * s.elem_size);
        else
            push_view(L, at, s.elem_layout, 0, false, 0);
        return 1;
    }
    return push_scalar(L, at, s.elem, s.elem_size);
}

int seq_index(lua_State* L) {
    Seq* s = to_seq(L, 1);
    if (!s) return luaL_error(L, "not a struct sequence");
    if (!refresh(s)) return stale_seq(L, s);

    if (lua_type(L, 2) == LUA_TNUMBER) {
        const double raw = double(lua_tonumber(L, 2));
        const std::uint32_t n = seq_length(*s);
        if (std::floor(raw) != raw || raw < 1 || raw > double(n)) {
            const std::uint32_t said = seq_reported_length(*s);
            if (said > n)
                return luaL_error(L, "%s.%s: index %g is outside 1..%u. The header says "
                                     "%u elements, which is past the %u this module walks; "
                                     "a size that large is a header to distrust, not a list "
                                     "to iterate",
                                  s->owner_struct, s->owner_field, raw, unsigned(n),
                                  unsigned(said), unsigned(kMaxSeqElements));
            return luaL_error(L, "%s.%s: index %g is outside 1..%u",
                              s->owner_struct, s->owner_field, raw, unsigned(n));
        }
        return push_element(L, *s, std::uint32_t(raw) - 1);
    }

    const char* key = lua_tostring(L, 2);
    if (!key) return luaL_error(L, "%s.%s is indexed by number, or by size/capacity/data",
                                s->owner_struct, s->owner_field);

    // These are the CExoArrayList's own field names, which is why they are the
    // ones offered. `data` hands back the pointer on purpose and under a name
    // that says what it is; the failure this module removes is getting that
    // pointer back when you asked for element zero.
    if (std::strcmp(key, "size") == 0 || std::strcmp(key, "count") == 0) {
        lua_pushnumber(L, seq_length(*s));
        return 1;
    }
    if (std::strcmp(key, "capacity") == 0) {
        if (!s->is_list) { lua_pushnumber(L, s->fixed_count); return 1; }
        std::int32_t cap = 0;
        if (!read_at(s->head + 8, cap)) { lua_pushnil(L); return 1; }
        lua_pushnumber(L, cap);
        return 1;
    }
    if (std::strcmp(key, "data") == 0) {
        std::uintptr_t d = 0;
        if (!seq_data(*s, d)) { lua_pushnil(L); return 1; }
        lua_pushnumber(L, lua_Number(d));
        return 1;
    }
    if (std::strcmp(key, "stride") == 0) {
        lua_pushnumber(L, s->elem_size);
        return 1;
    }
    if (std::strcmp(key, "elem") == 0) {
        lua_pushstring(L, s->elem == Kind::Struct && s->elem_layout
                              ? s->elem_layout->name : kind_name(s->elem));
        return 1;
    }
    // What the header claims, uncapped. `size` is what this module will walk;
    // the two differ only when the header is not to be believed, and a script
    // that wants to see that difference should not have to guess at it.
    if (std::strcmp(key, "reported_size") == 0) {
        lua_pushnumber(L, seq_reported_length(*s));
        return 1;
    }
    return luaL_error(L, "%s.%s: no key '%s'. A %s is indexed by number, or by "
                         "size, capacity, data, stride, elem, reported_size",
                      s->owner_struct, s->owner_field, key,
                      s->is_list ? "CExoArrayList" : "inline array");
}

int seq_newindex(lua_State* L) {
    Seq* s = to_seq(L, 1);
    if (!s) return luaL_error(L, "not a struct sequence");
    return luaL_error(L,
        "%s.%s is read-only through a typed view. Element storage is the engine's to grow "
        "and move, so writing an element means agreeing about a stride the corpus did not "
        "always recover. Take .data and use kp.mem if you mean it",
        s->owner_struct, s->owner_field);
}

int seq_len(lua_State* L) {
    Seq* s = to_seq(L, 1);
    if (!s) return luaL_error(L, "not a struct sequence");
    if (!refresh(s)) return stale_seq(L, s);
    lua_pushnumber(L, seq_length(*s));
    return 1;
}

int seq_tostring(lua_State* L) {
    Seq* s = to_seq(L, 1);
    if (!s) return luaL_error(L, "not a struct sequence");
    char buf[192];
    if (!refresh(s)) {
        std::snprintf(buf, sizeof buf, "%s %s.%s: stale (object 0x%08X)",
                      s->is_list ? "CExoArrayList" : "array",
                      s->owner_struct, s->owner_field, unsigned(s->object_id));
        lua_pushstring(L, buf);
        return 1;
    }
    std::snprintf(buf, sizeof buf, "%s %s.%s: %u element(s) of %s at 0x%08X",
                  s->is_list ? "CExoArrayList" : "array",
                  s->owner_struct, s->owner_field, unsigned(seq_length(*s)),
                  kind_name(s->elem), unsigned(s->head));
    lua_pushstring(L, buf);
    return 1;
}

// ------------------------------------------------------------- module API ----

const Layout* layout_arg(lua_State* L, int index) {
    const char* name = luaL_checkstring(L, index);
    const Layout* l = find(name);
    if (!l) {
        const std::string hint = near_layouts(name);
        luaL_error(L, "no layout named '%s'.%s (%d layouts; kp.struct.types() lists them)",
                   name, hint.c_str(), int(kLayoutCount));
    }
    return l;
}

std::uintptr_t address_arg(lua_State* L, int index) {
    const double a = luaL_checknumber(L, index);
    if (!(a >= 0.0) || a > 4294967295.0 || std::floor(a) != a)
        luaL_argerror(L, index, "expected a 32-bit address");
    return std::uintptr_t(a);
}

int l_at(lua_State* L) {
    // A zero address is accepted rather than refused. It is what a failed
    // pointer chase yields, and every read through the resulting view returns
    // nil, which is the answer a script can branch on.
    const std::uintptr_t addr = address_arg(L, 1);
    push_view(L, addr, layout_arg(L, 2), 0, false, 0);
    return 1;
}

int l_view(lua_State* L) {
    // Guarded the same way an address is. Converting a NaN or an out-of-range
    // double to an integer type is undefined, and an object id arrives from
    // wherever the script got it.
    const double raw = luaL_checknumber(L, 1);
    if (!(raw >= 0.0) || raw > 4294967295.0 || std::floor(raw) != raw)
        return luaL_argerror(L, 1, "expected a 32-bit object id");
    const std::uint32_t id = std::uint32_t(raw);

    if (!g_resolver) {
        lua_pushnil(L);
        lua_pushstring(L, "no object address resolver is installed yet; use "
                          "kp.struct.at(address, type) until the entity module binds one");
        return 2;
    }
    const char* type_name = nullptr;
    const std::uintptr_t addr = g_resolver(id, &type_name);
    if (addr == 0) {
        lua_pushnil(L);
        lua_pushstring(L, "object does not resolve to an address");
        return 2;
    }

    const Layout* layout = nullptr;
    if (lua_gettop(L) >= 2 && !lua_isnil(L, 2)) {
        layout = layout_arg(L, 2);
    } else if (type_name) {
        layout = find(type_name);
    }
    if (!layout) {
        lua_pushnil(L);
        lua_pushstring(L, "the resolver did not name a layout for this object's type; "
                          "pass one explicitly");
        return 2;
    }
    push_view(L, addr, layout, id, true, 0);
    return 1;
}

int l_types(lua_State* L) {
    lua_createtable(L, int(kLayoutCount), 0);
    for (std::size_t i = 0; i < kLayoutCount; ++i) {
        lua_pushstring(L, kLayouts[i].name);
        lua_rawseti(L, -2, int(i) + 1);
    }
    return 1;
}

int l_fields(lua_State* L) {
    const char* name = luaL_checkstring(L, 1);
    const Layout* l = find(name);
    if (!l) { lua_pushnil(L); return 1; }

    lua_createtable(L, int(l->field_count), 0);
    for (std::uint32_t i = 0; i < l->field_count; ++i) {
        const Field& f = l->fields[i];
        lua_createtable(L, 0, 9);
        lua_pushstring(L, f.name);            lua_setfield(L, -2, "name");
        lua_pushnumber(L, f.offset);          lua_setfield(L, -2, "offset");
        lua_pushnumber(L, f.size);            lua_setfield(L, -2, "size");
        lua_pushstring(L, f.type_text);       lua_setfield(L, -2, "type");
        lua_pushstring(L, kind_name(f.kind)); lua_setfield(L, -2, "kind");
        lua_pushstring(L, confidence_name(f.confidence));
        lua_setfield(L, -2, "confidence");
        if (f.meaning) { lua_pushstring(L, f.meaning); lua_setfield(L, -2, "meaning"); }
        if (f.kind == Kind::List || f.kind == Kind::Array) {
            lua_pushstring(L, kind_name(f.elem)); lua_setfield(L, -2, "elem");
            lua_pushnumber(L, f.elem_size);       lua_setfield(L, -2, "stride");
        }
        if (f.list_shape_unconfirmed) {
            lua_pushboolean(L, 1);
            lua_setfield(L, -2, "list_shape_unconfirmed");
        }
        lua_rawseti(L, -2, int(i) + 1);
    }
    return 1;
}

int l_typeof(lua_State* L) {
    if (View* v = to_view(L, 1)) { lua_pushstring(L, v->layout->name); return 1; }
    if (Seq* s = to_seq(L, 1)) {
        lua_pushstring(L, s->is_list ? "CExoArrayList" : "array");
        return 1;
    }
    lua_pushnil(L);
    return 1;
}

int l_address(lua_State* L) {
    if (View* v = to_view(L, 1)) {
        // The same re-resolve a read or a write does, so this can no longer say
        // "gone" while an index of the same view still hands back bytes.
        if (!refresh(v)) { lua_pushnil(L); return 1; }
        lua_pushnumber(L, lua_Number(v->addr));
        return 1;
    }
    if (Seq* s = to_seq(L, 1)) {
        if (!refresh(s)) { lua_pushnil(L); return 1; }
        lua_pushnumber(L, lua_Number(s->head));
        return 1;
    }
    lua_pushnil(L);
    return 1;
}

int l_valid(lua_State* L) {
    View* v = to_view(L, 1);
    if (!v) { lua_pushboolean(L, 0); return 1; }
    if (!refresh(v)) { lua_pushboolean(L, 0); return 1; }
    lua_pushboolean(L, platform::is_readable(reinterpret_cast<const void*>(v->addr),
                                             v->layout->size) ? 1 : 0);
    return 1;
}

int l_size(lua_State* L) {
    const char* name = luaL_checkstring(L, 1);
    const Layout* l = find(name);
    if (!l) { lua_pushnil(L); return 1; }
    lua_pushnumber(L, l->size);
    return 1;
}

int l_how_to_obtain(lua_State* L) {
    const Layout* l = layout_arg(L, 1);
    lua_pushstring(L, l->how_to_obtain ? l->how_to_obtain : "");
    return 1;
}

int l_allow_unverified_writes(lua_State* L) {
    const bool was = unverified_allowed(L);
    if (lua_gettop(L) >= 1) {
        lua_pushlightuserdata(L, const_cast<char*>(&kUnverifiedKey));
        lua_pushboolean(L, lua_toboolean(L, 1));
        lua_rawset(L, LUA_REGISTRYINDEX);
    }
    lua_pushboolean(L, was ? 1 : 0);
    return 1;
}

// ipairs in 5.1 walks raw table slots, so a sequence userdata is not iterable
// with it. Rather than pretend otherwise, this hands back a plain table.
int l_totable(lua_State* L) {
    Seq* s = to_seq(L, 1);
    if (!s) return luaL_error(L, "kp.struct.totable expects a list or array view");
    if (!refresh(s)) return stale_seq(L, s);
    const std::uint32_t n = seq_length(*s);
    lua_createtable(L, int(n), 0);
    for (std::uint32_t i = 0; i < n; ++i) {
        push_element(L, *s, i);
        // An element that did not read is where the walk ends. Storing the nil
        // would leave a hole, and a table with a hole in it has no honest
        // length; stopping and saying so does. The count that got built is the
        // table's length, which is the number the caller goes on to use.
        if (lua_isnil(L, -1)) {
            lua_pop(L, 1);
            platform::log(platform::LogLevel::Warn,
                          "%s.%s: element %u of %u did not read, so the table stops there",
                          s->owner_struct, s->owner_field, unsigned(i + 1), unsigned(n));
            break;
        }
        lua_rawseti(L, -2, int(i) + 1);
    }
    return 1;
}

int l_writes_performed(lua_State* L) {
    lua_pushnumber(L, lua_Number(g_writes));
    return 1;
}

struct Entry { const char* name; lua_CFunction fn; };

const Entry kFunctions[] = {
    {"at",                       l_at},
    {"view",                     l_view},
    {"types",                    l_types},
    {"fields",                   l_fields},
    {"typeof",                   l_typeof},
    {"address",                  l_address},
    {"valid",                    l_valid},
    {"size",                     l_size},
    {"how_to_obtain",            l_how_to_obtain},
    {"allow_unverified_writes",  l_allow_unverified_writes},
    {"totable",                  l_totable},
    {"writes_performed",         l_writes_performed},
};

void open_metatable(lua_State* L, const char* tname,
                    lua_CFunction index, lua_CFunction newindex,
                    lua_CFunction len, lua_CFunction tostring) {
    if (luaL_newmetatable(L, tname)) {
        lua_pushcfunction(L, index);    lua_setfield(L, -2, "__index");
        lua_pushcfunction(L, newindex); lua_setfield(L, -2, "__newindex");
        lua_pushcfunction(L, len);      lua_setfield(L, -2, "__len");
        lua_pushcfunction(L, tostring); lua_setfield(L, -2, "__tostring");
        // getmetatable(view) answers false rather than handing over the table.
        //
        // Stated plainly, because it is weaker than it looks: this stops the
        // plain getmetatable and nothing else. src/lua/host.cpp calls
        // luaL_openlibs, so every script also has the debug library, and
        // debug.getmetatable(view) returns the table anyway. Nothing in this
        // file can prevent that.
        //
        // So the module does not rest on this. What it rests on is check_ud:
        // a userdata is ours only if its size and its magic word say so, and
        // both of those are set by C code a script cannot reach. A metatable
        // borrowed with debug.setmetatable buys nothing.
        //
        // What remains is `debug.getmetatable(v).__index = f`, which hijacks
        // field reads for every view in that state. The fix for that is not
        // here: it is host.cpp not opening the debug library, or opening it
        // with getmetatable and setmetatable removed.
        lua_pushboolean(L, 0);
        lua_setfield(L, -2, "__metatable");
    }
    lua_pop(L, 1);
}

// The shared-table check, in the shape src/api/memory.cpp and src/api/entity.cpp
// already use. Two modules disagreeing about it is a bug that only appears
// under one load order, so this does not invent a third version.
void push_global_table(lua_State* L, const char* name) {
    lua_getglobal(L, name);
    if (!lua_istable(L, -1)) {
        lua_pop(L, 1);
        lua_createtable(L, 0, 4);
        lua_pushvalue(L, -1);
        lua_setglobal(L, name);
    }
}

void push_subtable(lua_State* L, int parent, const char* name) {
    lua_getfield(L, parent, name);
    if (!lua_istable(L, -1)) {
        lua_pop(L, 1);
        lua_createtable(L, 0, int(sizeof kFunctions / sizeof kFunctions[0]));
        lua_pushvalue(L, -1);
        lua_setfield(L, parent, name);
    }
}

}  // namespace

// ------------------------------------------------------------ public API ----

const Layout* table() { return kLayouts; }
std::size_t   layout_count() { return kLayoutCount; }

const Layout* find(const char* name) {
    if (!name) return nullptr;
    for (std::size_t i = 0; i < kLayoutCount; ++i)
        if (std::strcmp(kLayouts[i].name, name) == 0) return &kLayouts[i];
    return nullptr;
}

void set_address_resolver(AddressResolver r) { g_resolver = r; }

unsigned long long writes_performed() { return g_writes; }

void register_all(lua_State* L) {
    const int base = lua_gettop(L);

    open_metatable(L, kViewType, view_index, view_newindex, view_len, view_tostring);
    open_metatable(L, kSeqType, seq_index, seq_newindex, seq_len, seq_tostring);

    push_global_table(L, "kp");                   // kp
    push_subtable(L, lua_gettop(L), "struct");     // kp, kp.struct
    const int tbl = lua_gettop(L);

    for (const Entry& e : kFunctions) {
        lua_pushcfunction(L, e.fn);
        lua_setfield(L, tbl, e.name);
    }

    lua_settop(L, base);
}

}  // namespace kp::api::structs
