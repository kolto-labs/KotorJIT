// Exercises src/api/structs.cpp against synthetic buffers in this tool's own
// process, laid out to match two real engine structs.
//
// The module's whole claim is that a named read cannot be a wrong number. That
// claim is only worth something if it is checked against bytes somebody put
// there on purpose, through a real lua_State, running real Lua source. So this
// builds a CScriptEvent and a CSWSObject by hand and drives the module over
// them.
//
// WHY THESE STRUCTS
//
// CScriptEvent is the one the project already got wrong. Four of its six fields
// are CExoArrayLists, and `*(int*)(ev+4)` -- the obvious read -- is the data
// pointer, not the first int. CSWSObject carries the other half of the trap: a
// twelve-byte field at 0x90 that is a Vector and a twelve-byte field at 0x124
// that is a list. Same width, opposite meanings, and nothing but the corpus
// tells them apart.
//
// CSWSItem is here for one fact: it carries its CSWSObject at +0x10 where every
// other type carries it at +0x00. That makes it the layout where a nested view
// sits at a non-zero distance from the object's base, which is what a view that
// re-resolves an id has to get right when the engine moves the object.
//
// WHAT SECTIONS 9, 10, 14 AND 15 ARE FOR
//
// They are the four defects an adversarial review found in this module, each
// checked at the place it actually failed: a destroyed object read and written
// through anyway (9), a confidence gate that could not fire on any field a write
// was attempted on (10), a list header claiming twenty million elements (14),
// and a forged userdata wearing the view metatable (15).
//
// THE OFFSETS BELOW ARE NOT COPIED FROM THE GENERATED TABLE
//
// They are copied from the prose in data/research/phasor_structs.json, which
// states them independently of the `fields` array the generator reads:
//
//   "CScriptEvent: int_params 0x4, float_params 0x10, string_params 0x1C,
//    object_params 0x28"
//   "position 0x90 ... effects 0x124"
//
// The first thing the run does is assert the module reports those same offsets.
// Building the buffer out of the table and then reading it back through the
// table would agree with itself no matter what the table said.
//
// Build (from the repo root, one line). -Wall -Wextra because the cmake target
// compiles the module with them and a hand build that drops them proves less:
//   g++ -m32 -no-pie -std=c++20 -Wall -Wextra -O2 -Isrc -Ibuild/luajit32/src
//       tools/kp_structtest.cpp src/api/structs.cpp
//       src/platform/platform.cpp src/platform/platform_linux.cpp
//       build/luajit32/src/libluajit.a -ldl -lm -o build/kp_structtest
//
// Linux and 32-bit only, like kp_memtest: it probes and writes its own process,
// so cross-compiling it to Windows would produce a binary nobody runs. The
// Windows half of the module is proven by compiling structs.cpp with
// i686-w64-mingw32-g++, not by this tool.

#include <sys/mman.h>
#include <unistd.h>

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

#include "api/structs.hpp"
#include "platform/platform.hpp"

extern "C" {
#include "lauxlib.h"
#include "lua.h"
#include "lualib.h"
}

namespace structs = kp::api::structs;

namespace {

// Offsets as the research prose states them, not as the field table stores
// them. Checked against the module below.
constexpr std::uint32_t kEvIntParams    = 0x04;
constexpr std::uint32_t kEvFloatParams  = 0x10;
constexpr std::uint32_t kEvStringParams = 0x1C;
constexpr std::uint32_t kEvObjectParams = 0x28;
constexpr std::uint32_t kObjPosition    = 0x90;
constexpr std::uint32_t kObjEffects     = 0x124;
constexpr std::uint32_t kObjCurrentHp   = 0xDC;
constexpr std::uint32_t kObjDialogOwner = 0x54;
constexpr std::uint32_t kObjAiLevel     = 0x78;

constexpr std::uint32_t kScriptEventSize = 52;
constexpr std::uint32_t kServerObjectSize = 552;

// The other thing the research prose states independently: CSWSItem carries its
// CSWSObject at +0x10, where every other type carries it at +0x00. That makes it
// the one layout where a nested view's offset from the object's base is not
// zero, which is what the re-resolve has to get right.
constexpr std::uint32_t kItemSize          = 664;
constexpr std::uint32_t kItemServerObject  = 0x10;

// A CExoArrayList as the engine lays it out. Slot 0 is the data pointer; that
// is the entire hazard.
struct ListHeader {
    std::uint32_t data;
    std::int32_t  size;
    std::int32_t  capacity;
};

struct ExoString {
    std::uint32_t ptr;
    std::uint32_t len;
};

// Backing storage for the elements the lists point at. Static so the addresses
// stay valid for the whole run.
std::int32_t  g_ints[3]    = {11, 22, 33};
float         g_floats[2]  = {1.5f, -2.5f};
std::uint32_t g_objects[2] = {0x7FFFFFF0u, 0x00000001u};
char          g_text_a[]   = "k_def_heartbeat01";
char          g_text_b[]   = "Bastila";
ExoString     g_strings[2];

alignas(8) std::uint8_t g_event[kScriptEventSize];
alignas(8) std::uint8_t g_object[kServerObjectSize];

// One item, in two places. The engine reallocates and the object array answers
// with the new address; nothing tells the script its view moved.
alignas(8) std::uint8_t g_item[kItemSize];
alignas(8) std::uint8_t g_item_moved[kItemSize];
bool g_item_has_moved = false;

std::uint32_t addr_of(const void* p) {
    return std::uint32_t(reinterpret_cast<std::uintptr_t>(p));
}

void put_list(std::uint8_t* base, std::uint32_t offset, const void* data,
              std::int32_t size, std::int32_t capacity) {
    ListHeader h{data ? addr_of(data) : 0u, size, capacity};
    std::memcpy(base + offset, &h, sizeof h);
}

void build_buffers() {
    std::memset(g_event, 0, sizeof g_event);
    std::memset(g_object, 0, sizeof g_object);

    g_strings[0] = {addr_of(g_text_a), std::uint32_t(std::strlen(g_text_a))};
    g_strings[1] = {addr_of(g_text_b), std::uint32_t(std::strlen(g_text_b))};

    // CScriptEvent. event_type is a u16 at 0, so 0x0202 in the low half and
    // 0xDEAD in the high half proves the read takes two bytes and not four.
    const std::uint16_t event_type = 0x0202;
    const std::uint16_t field_2    = 0xDEAD;
    std::memcpy(g_event + 0, &event_type, 2);
    std::memcpy(g_event + 2, &field_2, 2);

    put_list(g_event, kEvIntParams, g_ints, 3, 4);
    put_list(g_event, kEvFloatParams, g_floats, 2, 2);
    put_list(g_event, kEvStringParams, g_strings, 2, 2);
    put_list(g_event, kEvObjectParams, g_objects, 2, 8);

    // CSWSObject. Twelve bytes at 0x90 that are three floats, and twelve bytes
    // at 0x124 that are a list. A reader that cannot tell them apart gets one
    // of the two badly wrong.
    const float pos[3] = {12.5f, -3.25f, 100.0f};
    std::memcpy(g_object + kObjPosition, pos, sizeof pos);
    put_list(g_object, kObjEffects, g_objects, 2, 2);

    // Two more fields the sections below need to see move, or see not move.
    // current_hp is what a write through a destroyed object would land in;
    // dialog_owner is one of the 22 pointers the generator demotes to med
    // confidence, so it is a field the confidence gate can actually decide.
    const std::uint32_t hp = 100;
    std::memcpy(g_object + kObjCurrentHp, &hp, 4);
    const std::uint32_t owner = 0xAABBCCDDu;
    std::memcpy(g_object + kObjDialogOwner, &owner, 4);

    // The item, before and after the engine moves it. Same field, two addresses
    // and two values, so a view that failed to follow reads the old number
    // rather than reading nothing.
    std::memset(g_item, 0, sizeof g_item);
    std::memset(g_item_moved, 0, sizeof g_item_moved);
    const std::uint32_t hp_before = 77, hp_after = 88;
    std::memcpy(g_item + kItemServerObject + kObjCurrentHp, &hp_before, 4);
    std::memcpy(g_item_moved + kItemServerObject + kObjCurrentHp, &hp_after, 4);
}

int g_failures = 0;
int g_checks   = 0;

void check(const char* what, bool ok) {
    ++g_checks;
    std::printf("  %-4s %s\n", ok ? "ok" : "FAIL", what);
    if (!ok) ++g_failures;
}

// The offsets the module will actually use, asked for through its own public
// table rather than through Lua, so a disagreement is reported before any
// buffer is read.
std::uint32_t offset_of(const char* layout_name, const char* field) {
    const structs::Layout* l = structs::find(layout_name);
    if (!l) return 0xFFFFFFFFu;
    for (std::uint32_t i = 0; i < l->field_count; ++i)
        if (std::strcmp(l->fields[i].name, field) == 0) return l->fields[i].offset;
    return 0xFFFFFFFFu;
}

// A stand-in for the pointer chain the entity module will own: g_pAppManager,
// the server app, the object array hash. Nothing in the tree resolves an id yet,
// so without this the id-driven half of the module would ship having never run.
//
// It answers for exactly one id and names the layout the way a real resolver
// will, from the object's type byte.
constexpr std::uint32_t kLiveObject = 0x0000002A;
constexpr std::uint32_t kDeadObject = 0x0000002B;
constexpr std::uint32_t kItemObject = 0x0000002C;

bool g_object_retired = false;

std::uintptr_t fake_resolver(std::uint32_t object_id, const char** type_name_out) {
    if (object_id == kItemObject) {
        if (type_name_out) *type_name_out = "CSWSItem";
        return reinterpret_cast<std::uintptr_t>(g_item_has_moved ? g_item_moved : g_item);
    }
    if (object_id != kLiveObject || g_object_retired) return 0;
    if (type_name_out) *type_name_out = "CSWSObject";
    return reinterpret_cast<std::uintptr_t>(g_object);
}

// Installing the resolver is a Lua call so the run can show both halves: what
// kotor.struct.view answers before anything binds a resolver, and what it
// answers afterwards.
int l_install_resolver(lua_State*) {
    structs::set_address_resolver(fake_resolver);
    return 0;
}

// The object is destroyed. This is what a view holding an id is for -- the
// address it used to sit at is now someone else's.
int l_retire_object(lua_State*) {
    g_object_retired = true;
    return 0;
}

// The engine reallocated the item. Same id, different address -- which is the
// case a view that remembers an address gets wrong quietly, by reading numbers
// that were true a tick ago.
int l_move_item(lua_State*) {
    g_item_has_moved = true;
    return 0;
}

// The id starts resolving again, which is not the same as the object coming
// back. The engine reuses ids, so this stands in for a different object having
// been given the id the retired view remembers.
int l_reissue_id(lua_State*) {
    g_object_retired = false;
    return 0;
}

// A region big enough to hold more elements than the module will walk, and
// mapped, so a capped walk stops because of the cap and not because it ran into
// an unmapped page. Sized past the cap for the same reason.
constexpr std::uint32_t kBigElements  = 70000;
constexpr std::int32_t  kGarbageCount = 20000000;
std::uint8_t* g_big = nullptr;

// The effects list header is rewritten to claim twenty million elements over a
// pointer that is perfectly readable. This is what a stale header looks like:
// nothing about it says stale, it just says a number no list holds.
int l_inflate_effects(lua_State*) {
    put_list(g_object, kObjEffects, g_big, kGarbageCount, kGarbageCount);
    return 0;
}

unsigned g_log_lines = 0;

void log_sink(kp::platform::LogLevel level, const char* message, void*) {
    ++g_log_lines;
    std::printf("    [%s] %s\n", kp::platform::to_string(level), message);
}

// So the Lua side can show that a repeated access does not repeat the warning.
int l_log_lines(lua_State* L) {
    lua_pushnumber(L, g_log_lines);
    return 1;
}

// Everything the module is supposed to do, written the way a script would write
// it. Kept as one chunk so the output reads top to bottom.
const char kLua[] = R"LUA(
checks_run = 0
failures = 0

local function ok(what, cond)
    checks_run = checks_run + 1
    if not cond then
        failures = failures + 1
        print(("  FAIL %s"):format(what))
    else
        print(("  ok   %s"):format(what))
    end
end

local function raises(what, fn)
    checks_run = checks_run + 1
    local good, err = pcall(fn)
    if good then
        failures = failures + 1
        print(("  FAIL %s -- no error raised"):format(what))
    else
        print(("  ok   %s"):format(what))
        print(("         %s"):format(err))
    end
end

-- Raising is not enough where the point is WHICH check refused. A gate that
-- reports someone else's refusal is the defect this file was rewritten for, so
-- the message has to be the one that was claimed.
local function raises_saying(what, needle, fn)
    checks_run = checks_run + 1
    local good, err = pcall(fn)
    if good then
        failures = failures + 1
        print(("  FAIL %s -- no error raised"):format(what))
    elseif not tostring(err):find(needle, 1, true) then
        failures = failures + 1
        print(("  FAIL %s -- raised, but not saying %q"):format(what, needle))
        print(("         %s"):format(err))
    else
        print(("  ok   %s"):format(what))
        print(("         %s"):format(err))
    end
end

print("\n-- 1. a named read, at the width the table declares -------------")
local ev = kotor.struct.at(event_addr, "CScriptEvent")
ok("tostring(view) names the layout and the address: " .. tostring(ev),
   tostring(ev):find("CScriptEvent") ~= nil)
ok("ev.event_type == 0x0202 (a u16 read, not the dword 0xDEAD0202)",
   ev.event_type == 0x0202)
ok("ev.field_2 == 0xDEAD (the neighbour is intact and separate)",
   ev.field_2 == 0xDEAD)
ok("kotor.struct.size('CScriptEvent') == 52", kotor.struct.size("CScriptEvent") == 52)
ok("kotor.struct.typeof(ev) == 'CScriptEvent'", kotor.struct.typeof(ev) == "CScriptEvent")
ok("kotor.struct.valid(ev)", kotor.struct.valid(ev) == true)

print("\n-- 2. THE TRAP: a CExoArrayList reads back as a list ------------")
-- The wrong answer, produced on purpose so the two sit side by side.
local raw = ev.int_params.data
print(("         the dword at ev+0x4 is 0x%08X -- that is the DATA POINTER,"):format(raw))
print( "         which is what readdword(ev+4) hands a Phasor-style script")
ok("#ev.int_params == 3 (the live size at +8, not the pointer)", #ev.int_params == 3)
ok("ev.int_params[1] == 11", ev.int_params[1] == 11)
ok("ev.int_params[2] == 22", ev.int_params[2] == 22)
ok("ev.int_params[3] == 33", ev.int_params[3] == 33)
ok("ev.int_params.capacity == 4", ev.int_params.capacity == 4)
ok("ev.int_params.data ~= ev.int_params[1] (pointer is not element zero)",
   ev.int_params.data ~= ev.int_params[1])
ok("the list is never a number: type(ev.int_params) == 'userdata'",
   type(ev.int_params) == "userdata")
local t = kotor.struct.totable(ev.int_params)
ok("totable gives {11,22,33}", #t == 3 and t[1] == 11 and t[3] == 33)
raises("index 4 of a 3-element list is refused, not read",
       function() return ev.int_params[4] end)

print("\n-- 3. list elements that are CExoStrings, not char* -------------")
ok("#ev.string_params == 2", #ev.string_params == 2)
ok("ev.string_params[1] == 'k_def_heartbeat01' (deref'd through {char*,len})",
   ev.string_params[1] == "k_def_heartbeat01")
ok("ev.string_params[2] == 'Bastila'", ev.string_params[2] == "Bastila")
ok("#ev.object_params == 2 and ev.object_params[1] == 0x7FFFFFF0",
   #ev.object_params == 2 and ev.object_params[1] == 0x7FFFFFF0)

print("\n-- 4. a list whose element type the corpus never states ---------")
ok("#ev.float_params == 2 (size and capacity are still readable)",
   #ev.float_params == 2)
ok("ev.float_params.data is a pointer", ev.float_params.data ~= 0)
raises("indexing it is refused rather than guessing a 4-byte stride",
       function() return ev.float_params[1] end)

print("\n-- 5. an unknown field names the struct and the near misses -----")
raises("ev.int_param (singular) is an error, not a read of something nearby",
       function() return ev.int_param end)
raises("ev.hit_points is an error and lists nothing that does not exist",
       function() return ev.hit_points end)
raises("assigning a new field is refused too",
       function() ev.brand_new_field = 1 end)
raises("an unknown layout name is an error",
       function() return kotor.struct.at(event_addr, "CSWSCreatur") end)

print("\n-- 6. a named write, at the field's width -----------------------")
ev.event_type = 0x1234
ok("ev.event_type reads back 0x1234", ev.event_type == 0x1234)
ok("ev.field_2 is still 0xDEAD (the write stayed inside two bytes)",
   ev.field_2 == 0xDEAD)
raises("0x10000 into a u16 is an error, not a truncation to 0",
       function() ev.event_type = 0x10000 end)
raises("-1 into a u16 is an error, not a wrap to 65535",
       function() ev.event_type = -1 end)
raises("1.5 into a u16 is an error, not a floor",
       function() ev.event_type = 1.5 end)
raises("a string into a u16 is an error",
       function() ev.event_type = "7" end)
ok("after four refusals ev.event_type is still 0x1234", ev.event_type == 0x1234)
raises("assigning to a CExoArrayList field is refused outright",
       function() ev.int_params = 0 end)
raises("writing an element through the list view is refused",
       function() ev.int_params[1] = 99 end)

print("\n-- 7. twelve bytes that are a Vector, not a list ----------------")
local obj = kotor.struct.at(object_addr, "CSWSObject")
local p = obj.position
ok("obj.position is a table, not a pointer", type(p) == "table")
ok("obj.position.x == 12.5", p.x == 12.5)
ok("obj.position.y == -3.25", p.y == -3.25)
ok("obj.position.z == 100", p.z == 100)
ok("#obj.effects == 2 -- same width at 0x124, and it IS a list",
   #obj.effects == 2)

print("\n-- 8. a bad address returns nil rather than faulting ------------")
local gone = kotor.struct.at(unmapped, "CScriptEvent")
ok("a view over an unmapped page is still a view", kotor.struct.typeof(gone) == "CScriptEvent")
ok("gone.event_type is nil", gone.event_type == nil)
ok("kotor.struct.valid(gone) is false", kotor.struct.valid(gone) == false)
ok("#gone.int_params == 0 (an unreadable header has no elements)",
   #gone.int_params == 0)
ok("gone.int_params[1] is refused by the range check, not by a fault",
   pcall(function() return gone.int_params[1] end) == false)
local null = kotor.struct.at(0, "CSWSObject")
ok("a view at address 0 reads nil rather than raising", null.position == nil)
raises("and a write through it says so, having written nothing",
       function() null.current_hp = 1 end)

print("\n-- 9. an object id, before and after a resolver exists ----------")
local before, why = kotor.struct.view(live_id)
ok("with no resolver installed, view() returns nil and says why", before == nil)
print(("         %s"):format(tostring(why)))
install_resolver()
local by_id = kotor.struct.view(live_id)
ok("view(id) picks CSWSObject from what the resolver named",
   kotor.struct.typeof(by_id) == "CSWSObject")
ok("it reads the same bytes kotor.struct.at reached", by_id.position.x == 12.5)
ok("kotor.struct.address(by_id) re-resolves to the object address",
   kotor.struct.address(by_id) == object_addr)
ok("kotor.struct.valid(by_id) is true", kotor.struct.valid(by_id) == true)
local forced = kotor.struct.view(live_id, "CScriptEvent")
ok("an explicit type name overrides the resolver's choice",
   kotor.struct.typeof(forced) == "CScriptEvent")
local missing, why2 = kotor.struct.view(dead_id)
ok("an id the resolver does not know returns nil and says why", missing == nil)
print(("         %s"):format(tostring(why2)))
raises("a NaN object id is an argument error, not a conversion",
       function() return kotor.struct.view(0/0) end)

-- The reason a view holds an id rather than an address: the object can go away
-- and the address it used to sit at can be handed to something else. Everything
-- below is taken while it is alive, then asked again once it is not.
local eff = by_id.effects
ok("while it is alive, by_id.current_hp == 100", by_id.current_hp == 100)
ok("and #by_id.effects == 2", #eff == 2)

-- A nested view at a non-zero offset, which is the case that proves the view
-- re-resolves the ID rather than remembering an address. CSWSItem carries its
-- CSWSObject at +0x10 where every other type carries it at +0x00.
local item = kotor.struct.view(item_id)
local embedded = item.server_object
ok("view(item_id) picks CSWSItem from what the resolver named",
   kotor.struct.typeof(item) == "CSWSItem")
ok("item.server_object is the CSWSObject at +0x10: current_hp == 77",
   embedded.current_hp == 77)
ok("its address is 16 past the item's",
   kotor.struct.address(embedded) - kotor.struct.address(item) == 16)
move_item()
ok("the engine reallocates the item, and the nested view follows it: 88",
   embedded.current_hp == 88)
ok("still 16 past the item's new address, not 16 past the old one",
   kotor.struct.address(embedded) - kotor.struct.address(item) == 16
   and kotor.struct.address(item) == item_addr_moved)
ok("and the outer view followed too", kotor.struct.address(item) ~= item_addr)

retire_object()
ok("once the object is destroyed, valid(by_id) is false",
   kotor.struct.valid(by_id) == false)
ok("and address(by_id) is nil rather than a stale pointer",
   kotor.struct.address(by_id) == nil)
raises_saying("READING a field now raises rather than handing back the dead object's bytes",
              "is stale", function() return by_id.current_hp end)
raises_saying("WRITING one raises before anything is stored",
              "is stale", function() by_id.current_hp = 4242 end)
raises_saying("a nested read is stale too, at its own offset",
              "is stale", function() return by_id.position end)
raises_saying("and the list taken while it was alive: its header is inside the object",
              "is stale", function() return #eff end)
raises_saying("so is indexing that list", "is stale", function() return eff[1] end)
raises_saying("and totable of it", "is stale", function() return kotor.struct.totable(eff) end)
ok("tostring says stale instead of printing an address: " .. tostring(by_id),
   tostring(by_id):find("stale") ~= nil)
ok("writes_performed() is still 1: nothing was written into the dead object",
   kotor.struct.writes_performed() == 1)

-- Ids are reused. The engine hands them out from two counters that grow toward
-- each other, so an id that resolves again is not the same object coming back.
reissue_id()
raises_saying("the id resolves again, and the retired view still refuses: it would be "
              .. "a different object under the same name",
              "is stale", function() return by_id.current_hp end)
local fresh = kotor.struct.view(live_id)
ok("a view taken now reads normally", fresh.current_hp == 100)

print("\n-- 10. an offset nobody confirmed is readable, not writable -----")
-- CSWSObject.dialog_owner is one of the 22 pointers that sit at the head of a
-- ptr+size+capacity triple nobody has confirmed is a CExoArrayList. The
-- generator demotes those to med confidence, which is what makes this gate
-- reachable at all: every field the research file itself marks med or low is an
-- aggregate, and an aggregate is refused a write one check earlier.
local dialog
for _, fld in ipairs(kotor.struct.fields("CSWSObject")) do
    if fld.name == "dialog_owner" then dialog = fld end
end
ok("dialog_owner is a ptr, med confidence, list shape unconfirmed",
   dialog.kind == "ptr" and dialog.confidence == "med"
   and dialog.list_shape_unconfirmed == true)
ok("reading it needs no opt-in: 0xAABBCCDD", obj.dialog_owner == 0xAABBCCDD)
raises_saying("writing it is refused, and the confidence gate is the reason",
              "med confidence", function() obj.dialog_owner = 0x11223344 end)
ok("the refusal wrote nothing", obj.dialog_owner == 0xAABBCCDD)
ok("allow_unverified_writes(true) returns the previous setting (false)",
   kotor.struct.allow_unverified_writes(true) == false)
obj.dialog_owner = 0x11223344
ok("opted in, the same write goes through -- the gate decided the outcome",
   obj.dialog_owner == 0x11223344)
kotor.struct.allow_unverified_writes(false)
raises_saying("opted back out, it is refused again",
              "med confidence", function() obj.dialog_owner = 0 end)
ok("and the value is the one the opted-in write left", obj.dialog_owner == 0x11223344)

-- A negative write, to see what the log line says about it. The hex has to be
-- the four bytes that were stored, not a sign-extended sixty-four-bit version
-- of them.
obj.ai_level = -100
ok("obj.ai_level reads back -100", obj.ai_level == -100)

-- The other half of the same fix: an aggregate is now refused as an aggregate,
-- rather than being refused by a gate that had nothing to do with it.
local pl = kotor.struct.at(0, "CSWSPlaceable")
raises_saying("CSWSPlaceable.orientation is f32[4]: refused as an aggregate",
              "aggregate", function() pl.orientation = 1 end)
kotor.struct.allow_unverified_writes(true)
raises_saying("opted in, still an aggregate -- the opt-in was never the question",
              "aggregate", function() pl.orientation = 1 end)
kotor.struct.allow_unverified_writes(false)

print("\n-- 11. the table describes itself ------------------------------")
local f = kotor.struct.fields("CScriptEvent")
ok("fields('CScriptEvent') has 6 entries", #f == 6)
ok("field 3 is int_params at 0x4, 12 bytes, CExoArrayList",
   f[3].name == "int_params" and f[3].offset == 4 and f[3].size == 12
   and f[3].type == "CExoArrayList")
ok("its element kind is reported as i32 with stride 4",
   f[3].elem == "i32" and f[3].stride == 4)
ok("float_params reports an unknown element kind", f[4].elem == "unknown")
ok("fields() of an unknown layout is nil", kotor.struct.fields("Nope") == nil)
ok("types() lists 25 layouts", #kotor.struct.types() == 25)

local shape = 0
for _, name in ipairs(kotor.struct.types()) do
    for _, fld in ipairs(kotor.struct.fields(name)) do
        if fld.list_shape_unconfirmed then shape = shape + 1 end
    end
end
ok("22 fields carry the 'may be a split-form CExoArrayList' warning: " .. shape,
   shape == 22)

print("\n-- 12. registration is idempotent and shares its table ----------")
ok("kp.struct is the same table as kotor.struct", kp.struct == kotor.struct)
ok("kotor.mem left by another module is untouched", kotor.mem == "sentinel")
ok("the view metatable is not reachable from Lua",
   getmetatable(ev) == false)

print("\n-- 13. writes are reported --------------------------------------")
ok("writes_performed() == 3 (a u16, an opted-in pointer, a negative i32)",
   kotor.struct.writes_performed() == 3)

print("\n-- 14. a header that claims twenty million elements -------------")
-- The size field is read live out of the game's memory, so it is exactly as
-- trustworthy as the header it came from. Walking one costs a page probe per
-- element: twenty million of those is the calling thread gone for half a minute,
-- and in a tick callback that is the game hung.
inflate_effects()
local lines_before = log_lines()
local big = obj.effects
ok("the data pointer is readable, so nothing else stops the walk", big.data ~= 0)
ok(".reported_size hands back what the header claims: " .. big.reported_size,
   big.reported_size == 20000000)
ok("#list is capped at 65536: " .. #big, #big == 65536)
ok(".size agrees with #, so the two cannot disagree in a loop", big.size == #big)
local t0 = os.clock()
local walked = kotor.struct.totable(big)
local elapsed = os.clock() - t0
ok(("totable built %d entries in %.2f s"):format(#walked, elapsed),
   #walked == 65536 and elapsed < 5.0)
raises_saying("an index past the cap is refused, and the message says why",
              "past the 65536", function() return big[100000] end)
ok("the truncation was logged: " .. (log_lines() - lines_before) .. " new line(s)",
   log_lines() - lines_before == 1)
local before_repeat = log_lines()
local n1, n2 = #obj.effects, #obj.effects
ok("once for the field, not once per access -- obj.effects builds a new sequence "
   .. "every time it is indexed",
   log_lines() == before_repeat and n1 == 65536 and n2 == 65536)

print("\n-- 15. a userdata wearing the view metatable --------------------")
-- getmetatable(view) is false, and that is worth exactly what the debug library
-- lets it be worth. This is stated rather than defended against: the fix is in
-- src/lua/host.cpp, which opens the debug library for every script.
local mt = debug.getmetatable(ev)
ok("debug.getmetatable reaches the metatable that __metatable hides",
   type(mt) == "table")
ok("so does the registry: debug.getregistry()['kp.struct.view'] is the same table",
   debug.getregistry()["kp.struct.view"] == mt)
-- newproxy makes a zero-byte userdata. Wearing this metatable, it used to be
-- read as a View: layout pointer and all, off the end of an empty allocation.
local fake = newproxy(false)
debug.setmetatable(fake, mt)
ok("the forgery is a userdata carrying the view metatable",
   type(fake) == "userdata" and debug.getmetatable(fake) == mt)
raises_saying("reading a field of it raises rather than reading off the end of it",
              "not a struct view", function() return fake.current_hp end)
raises_saying("writing one does too", "not a struct view",
              function() fake.current_hp = 1 end)
raises_saying("so does #", "not a struct view", function() return #fake end)
raises_saying("so does tostring", "not a struct view", function() return tostring(fake) end)
ok("typeof(forgery) is nil, not a layout name", kotor.struct.typeof(fake) == nil)
ok("valid(forgery) is false", kotor.struct.valid(fake) == false)
ok("address(forgery) is nil", kotor.struct.address(fake) == nil)
local fake_seq = newproxy(false)
debug.setmetatable(fake_seq, debug.getmetatable(ev.int_params))
raises_saying("a forged sequence is refused the same way", "not a struct sequence",
              function() return #fake_seq end)
raises_saying("and totable of one", "expects a list or array view",
              function() return kotor.struct.totable(fake_seq) end)
ok("a real view still works after all of that", ev.event_type == 0x1234)
)LUA";

}  // namespace

int main() {
    build_buffers();

    std::printf("kp_structtest: %zu layouts compiled in, %u fields in CScriptEvent\n",
                structs::layout_count(),
                structs::find("CScriptEvent") ? structs::find("CScriptEvent")->field_count : 0);

    std::printf("\n-- 0. the module's offsets agree with the research prose ---\n");
    check("CScriptEvent.int_params    @0x04", offset_of("CScriptEvent", "int_params") == kEvIntParams);
    check("CScriptEvent.float_params  @0x10", offset_of("CScriptEvent", "float_params") == kEvFloatParams);
    check("CScriptEvent.string_params @0x1C", offset_of("CScriptEvent", "string_params") == kEvStringParams);
    check("CScriptEvent.object_params @0x28", offset_of("CScriptEvent", "object_params") == kEvObjectParams);
    check("CSWSObject.position        @0x90", offset_of("CSWSObject", "position") == kObjPosition);
    check("CSWSObject.effects         @0x124", offset_of("CSWSObject", "effects") == kObjEffects);
    check("CScriptEvent is 52 bytes", structs::find("CScriptEvent")->size == kScriptEventSize);
    check("CSWSObject is 552 bytes", structs::find("CSWSObject")->size == kServerObjectSize);

    kp::platform::set_log_sink(log_sink, nullptr);

    lua_State* L = luaL_newstate();
    if (!L) { std::fprintf(stderr, "no lua state\n"); return 1; }
    luaL_openlibs(L);

    // Something else got to the kotor table first. Registration must find it
    // and add to it, not replace it.
    lua_createtable(L, 0, 1);
    lua_pushstring(L, "sentinel");
    lua_setfield(L, -2, "mem");
    lua_setglobal(L, "kotor");

    structs::register_all(L);
    structs::register_all(L);   // twice on purpose: registering again is a no-op

    lua_pushnumber(L, addr_of(g_event));  lua_setglobal(L, "event_addr");
    lua_pushnumber(L, addr_of(g_object)); lua_setglobal(L, "object_addr");
    lua_pushnumber(L, kLiveObject);       lua_setglobal(L, "live_id");
    lua_pushnumber(L, kDeadObject);       lua_setglobal(L, "dead_id");
    lua_pushnumber(L, kItemObject);       lua_setglobal(L, "item_id");
    lua_pushnumber(L, addr_of(g_item));       lua_setglobal(L, "item_addr");
    lua_pushnumber(L, addr_of(g_item_moved)); lua_setglobal(L, "item_addr_moved");
    lua_pushcfunction(L, l_move_item);        lua_setglobal(L, "move_item");
    lua_pushcfunction(L, l_install_resolver); lua_setglobal(L, "install_resolver");
    lua_pushcfunction(L, l_retire_object);    lua_setglobal(L, "retire_object");
    lua_pushcfunction(L, l_reissue_id);       lua_setglobal(L, "reissue_id");
    lua_pushcfunction(L, l_inflate_effects);  lua_setglobal(L, "inflate_effects");
    lua_pushcfunction(L, l_log_lines);        lua_setglobal(L, "log_lines");

    // Mapped, and larger than the module's element cap, so section 14 measures
    // the cap rather than the readability probe.
    g_big = static_cast<std::uint8_t*>(
        mmap(nullptr, kBigElements * 4, PROT_READ | PROT_WRITE,
             MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
    if (g_big == MAP_FAILED) { std::perror("mmap"); return 1; }

    // Grow LuaJIT's arena and compile the chunk BEFORE the hole is punched.
    // kp_memtest hit this first and wrote it down: an mmap made after a munmap
    // is routinely handed the page that was just released, so the "bad" address
    // stops being bad and the nil checks read live memory instead. This tool
    // reproduced it exactly -- two checks passed that should not have -- which
    // is the argument for allocating up front rather than hoping.
    if (luaL_dostring(L, "local t = {} for i = 1, 400 do t[i] = string.rep('x', 8192) end") != 0) {
        std::fprintf(stderr, "warm-up failed: %s\n", lua_tostring(L, -1));
        return 1;
    }
    if (luaL_loadstring(L, kLua) != 0) {
        std::fprintf(stderr, "lua: %s\n", lua_tostring(L, -1));
        return 1;
    }

    // The hole last, and in the middle of a mapping this process keeps, so the
    // free span is exactly one page. LuaJIT's allocator asks for chunks far
    // larger than that, so it cannot reclaim this one.
    auto* region = static_cast<std::uint8_t*>(
        mmap(nullptr, 8192, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
    if (region == MAP_FAILED) { std::perror("mmap"); return 1; }
    munmap(region + 4096, 4096);
    const std::uint32_t unmapped = addr_of(region + 4096);
    check("the unmapped page fails the readability probe",
          !kp::platform::is_readable(reinterpret_cast<const void*>(unmapped), 4));

    lua_pushnumber(L, unmapped);
    lua_setglobal(L, "unmapped");

    if (lua_pcall(L, 0, 0, 0) != 0) {
        std::fprintf(stderr, "lua: %s\n", lua_tostring(L, -1));
        return 1;
    }

    lua_getglobal(L, "failures");
    g_failures += int(lua_tonumber(L, -1));
    lua_pop(L, 1);
    lua_getglobal(L, "checks_run");
    const int lua_checks = int(lua_tonumber(L, -1));
    lua_pop(L, 1);

    // The Lua side read its own write back through the same module, which would
    // agree with itself even if both halves were wrong about the offset. This
    // reads the bytes from C++.
    std::printf("\n-- the write, verified from C++ rather than through the module --\n");
    std::uint16_t stored = 0;
    std::memcpy(&stored, g_event + 0, 2);
    std::printf("  g_event[0x00..0x01] = 0x%04X\n", stored);
    check("the u16 at offset 0 is 0x1234", stored == 0x1234);
    std::uint16_t neighbour = 0;
    std::memcpy(&neighbour, g_event + 2, 2);
    std::printf("  g_event[0x02..0x03] = 0x%04X\n", neighbour);
    check("the u16 at offset 2 is untouched", neighbour == 0xDEAD);

    // The write the confidence gate refused until the script opted in.
    std::uint32_t dialog = 0;
    std::memcpy(&dialog, g_object + kObjDialogOwner, 4);
    std::printf("  g_object[0x54] = 0x%08X\n", dialog);
    check("the opted-in pointer write stored 0x11223344", dialog == 0x11223344u);

    // The one that matters most: the retired object's storage. Two refusals in
    // section 9 said nothing was written, and this is the only place that can
    // say whether that was true.
    std::uint32_t hp = 0;
    std::memcpy(&hp, g_object + kObjCurrentHp, 4);
    std::printf("  g_object[0xDC] = %u\n", hp);
    check("current_hp is still 100: the write through the destroyed object "
          "reached nothing", hp == 100);

    std::int32_t ai = 0;
    std::memcpy(&ai, g_object + kObjAiLevel, 4);
    std::printf("  g_object[0x78] = %d (0x%08X)\n", ai, unsigned(ai));
    check("the negative write stored four bytes of -100, and the log line's hex "
          "0x9C is those bytes and not a sign-extended 64-bit copy", ai == -100);

    check("structs::writes_performed() == 3", structs::writes_performed() == 3);
    // Three stores, and one warning about the twenty-million-element header.
    check("four log lines: three writes and one truncation", g_log_lines == 4);

    std::printf("\n%d Lua check(s) + %d C++ check(s), %d failure(s)\n",
                lua_checks, g_checks, g_failures);
    lua_close(L);
    return g_failures == 0 ? 0 : 1;
}
