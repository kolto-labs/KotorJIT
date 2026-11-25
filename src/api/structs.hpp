// Named, checked field access on the engine's own structures.
//
// The idiom this replaces, taken from the Phasor reference corpus:
//
//     stats_player_kills = readword(stats_base + 0x8)    -- Confirmed.
//
// The offset is a literal, the width is whichever function the author happened
// to call, and "Confirmed" is a comment. Nothing checks any of it. What goes
// here instead:
//
//     local o = kp.struct.at(addr, "CSWSObject")
//     print(o.current_hp, o.position.x, #o.effects)
//
// The offsets come from data/research/phasor_structs.json through
// tools/gen_structs.py, which re-derives the evidence rather than trusting the
// file: a contiguity walk, Ghidra's ~1000 free field_<hex> name assertions, and
// exact size totals. The generated table then repeats the walk in constexpr, so
// a bad offset is a compile error rather than a wrong number at runtime.
//
// THE TWELVE-BYTE TRAP
//
// Several fields Ghidra emits as `unsigned char[0xC]` are really
// CExoArrayList {void* data; int size; int capacity}. Reading slot 0 as an int
// returns THE DATA POINTER, not element zero. This project already shipped that
// mistake once, on CScriptEvent.int_params. So a list field never reads back as
// a number: it reads back as a sequence with a length, and the generator refuses
// to emit any unclassified twelve-byte field at all.
//
// CExoString {char* ptr; uint32 len} gets the same care. Eight bytes, and slot 0
// is a pointer.
//
// READS NEVER FAULT
//
// Every read probes the address through kp::platform::is_readable first and
// returns nil when the span is not mapped. A script chasing a stale pointer gets
// nil, not a crash inside a hook body.
//
// WRITES RESPECT WIDTH
//
// Writing 0x1234 into a u8 field is an error, not a truncation, and assigning to
// an aggregate field -- a nested struct, a Vector, a string, a list -- is refused
// outright rather than storing four bytes into twelve.
//
// A VIEW WITH AN ID RE-RESOLVES ON EVERY ACCESS
//
// kp.struct.view(id) keeps the id, and everything that touches the object's
// bytes asks the resolver again first -- every field read, every field write,
// every list length, every address, not only valid() and address(). The two
// that do not are typeof() and #view, and they do not because they answer out
// of the layout table rather than out of the object: a name and a byte size
// that are the same whether the object is there or not.
//
// An object destroyed between two ticks leaves its storage to the
// next allocation, so a write through a remembered address lands in whatever
// moved in. A view whose id stops resolving raises "view of object 0x... is
// stale" from then on, permanently: the engine reuses object ids, and a view
// that recovered would be reading a different object under the same name.
// kp.struct.valid() is the one call that answers instead of raising.
//
// Nested views and list headers inherit the id and their own distance from the
// object's base, so creature.object.current_hp is exactly as live as creature.
// kp.struct.at(address, type) tracks nothing, by definition: it holds an
// address, and it goes stale the way an address does.
//
// A SEQUENCE LENGTH IS CAPPED
//
// A CExoArrayList's element count is read live out of the engine's memory, so a
// header that has gone stale reports a number like twenty million rather than
// reporting that it is stale. Walking one costs a page probe per element, which
// is tens of seconds -- inside a tick callback, a hung game. So #list, .size and
// totable() stop at 65536 elements. The truncation is logged, the header's own
// number stays readable as .reported_size, and the out-of-range message names
// the cap, so a capped list cannot be mistaken for a short one.
//
// A USERDATA IS OURS OR IT IS NOTHING
//
// Views and sequences are checked by allocation size and by a magic word before
// anything inside them is read, not by their metatable alone. Scripts have the
// debug library, so debug.setmetatable can put this module's metatable onto a
// userdata this module never made; luaL_checkudata would accept it and the first
// field read would run off the end of the allocation.
#pragma once

#include <cstddef>
#include <cstdint>

struct lua_State;

namespace kp::api::structs {

// What a field is, once the research file's type text has been resolved.
//
// Unknown appears in exactly one place: the element type of a CExoArrayList the
// research prose never states. Indexing such a list is refused, because guessing
// a stride is how you get a silent wrong value, which is the failure this module
// exists to remove.
enum class Kind : std::uint8_t {
    Unknown,
    U8, I8, U16, I16, U32, I32, U64, F32,
    Ptr,
    Struct,     // an embedded named layout
    Vector,     // three floats, read back as {x=,y=,z=}
    ExoString,  // {char*, u32 len}
    LocString,  // {void*, i32 strref}
    ResRef,     // 16-byte NUL-padded resource name
    List,       // CExoArrayList {void*, i32 size, i32 capacity}
    Array,      // an inline array of `count` elements
    Blob,       // opaque bytes, read back as a Lua string
};

// How much the corpus vouches for a field. Anything below High is readable but
// not writable unless a script opts in, because writing an offset nobody
// confirmed is writing somewhere nobody has looked.
//
// Two sources feed this. Most of it is the research file's own per-field
// marking. The rest is the generator demoting a pointer that has the shape of a
// CExoArrayList head without the annotation that would confirm it -- see
// list_shape_unconfirmed below. Without that demotion the gate would be
// unreachable: every field the corpus marks med or low is an aggregate, and an
// aggregate is refused a write before confidence is consulted.
enum class Confidence : std::uint8_t { High, Med, Low };

struct Field {
    const char*   name;
    const char*   type_text;    // as written in the research file, for reporting
    const char*   meaning;      // may be null
    const char*   struct_name;  // layout name for Struct, element layout for Array
    std::uint32_t offset;
    std::uint32_t size;         // bytes this field occupies inside the struct
    std::uint32_t elem_size;    // stride for Array and List; 0 when unknown
    std::uint32_t count;        // element count for Array; 0 for List, whose count is live
    Kind          kind;
    Kind          elem;         // element kind for Array and List
    Confidence    confidence;

    // A ptr+size+capacity triple that has the shape of a split-form
    // CExoArrayList but carries no annotation saying it is one.
    //
    // The research notes say that census is incomplete and that confirming a
    // case needs disassembly, so the generator leaves these typed as Ptr rather
    // than promoting a guess -- a wrongly promoted list is the same class of
    // error as a missed one, pointing the other way. But a script reading such
    // a field gets a bare pointer number back, which is the exact failure this
    // module exists to remove, so the suspicion travels with the field and
    // kp.struct.fields() reports it instead of leaving it in a comment at
    // the bottom of a generated file.
    //
    // It also costs the field its high confidence. Reading one of these is a
    // pointer-shaped number either way, but writing one either stores into a
    // pointer or replaces a live CExoArrayList's data pointer with a number, and
    // which of those it is has not been established. So a write takes the
    // allow_unverified_writes opt-in.
    bool          list_shape_unconfirmed;
};

struct Layout {
    const char*   name;
    std::uint32_t size;
    const Field*  fields;
    std::uint32_t field_count;
    const char*   how_to_obtain;   // the pointer chain, for error messages and docs
};

// The walk the generator performs in Python, repeated at compile time.
//
// Duplicated on purpose. The Python check protects the data file; this one
// protects the generated file, which someone will eventually hand-edit to add
// "just one field". A wrong offset there stops the build.
constexpr bool layout_is_packed(const Field* f, std::size_t n, std::uint32_t total) {
    std::uint32_t run = 0;
    for (std::size_t i = 0; i < n; ++i) {
        if (f[i].offset != run) return false;
        run = f[i].offset + f[i].size;
    }
    return run == total;
}

// Every layout the running build knows, and one by name. `find` returns null
// rather than raising, so callers decide whether an unknown name is an error.
const Layout* table();
std::size_t   layout_count();
const Layout* find(const char* name);

// How an object id becomes an address.
//
// That chain is the `entity` module's job -- g_pAppManager, the server app, the
// object array hash. This module only needs the answer, so it takes a function
// pointer and works without one: kp.struct.at(address, name) is fully usable
// before anything installs a resolver, and kp.struct.view(id) reports that it
// is unavailable rather than guessing.
//
// `type_name_out` is set to the layout the object's type byte selects, or left
// alone when the resolver cannot tell.
using AddressResolver = std::uintptr_t (*)(std::uint32_t object_id,
                                           const char** type_name_out);
void set_address_resolver(AddressResolver);

// Runtime gate: true on 32-bit K1 builds where kLayouts offsets match; false
// on K2 or 64-bit builds so kp.struct.* refuses cleanly instead of reading wrong offsets.
void set_supported(bool supported);
bool is_supported();

// How many typed writes this process has performed.
//
// Writes here are as sharp as kp.mem's -- the field table decides the width
// and the confidence gate decides whether a script may touch an offset nobody
// confirmed, and neither of those is a refusal to write. So the same bargain
// applies: every store is logged with its address, field, width, value and the
// Lua line that asked, and this counter lets a diagnostic command say how many
// happened without holding the records.
unsigned long long writes_performed();

// Install kp.struct.* into one script's state.
//
// Called once per lua_State, after the state exists and before the chunk runs.
// The `kp` table is shared with the routine bridge and every other module, so
// this checks for it and reuses it rather than replacing what is already there.
void register_all(lua_State*);

}  // namespace kp::api::structs
