// Exercises src/api/entity.cpp without the game, against a fake routine
// dispatcher.
//
// The entity module is a layer over the engine routine bridge, and that bridge
// (src/api/routines.cpp) is being written in parallel. Rather than wait, this
// tool supplies the other side of api/routines.hpp itself: the REAL generated
// K1 routine table from src/generated/routines_k1.inc, and a hand-written
// `call` that answers thirteen of those routines out of a five-object make
// believe module. So the ids, names, return types and arities entity looks up
// are the game's own; only the answers are invented.
//
// What it proves:
//   * a handle is created, carries its id and its type, and prints as itself
//   * the call-through path reaches the bridge with arguments in DECLARED
//     order, checked with the asymmetric GetObjectByTag(string, int)
//   * a destroyed id is refused rather than answered
//   * a RECYCLED id -- same number, different object -- is refused too
//   * before the VM binding exists every function reports its documented
//     failure value instead of calling anything
//   * registering twice, into globals that already exist, keeps what was there
//
// What it cannot prove, and does not claim to: whether the real bridge wants
// its arguments in declared order. The fake agrees with whatever this file
// assumes. The assumption is written down at call_one() in entity.cpp and is
// checkable only against a real routines.cpp, or against the game.
//
// Usage:
//   kp_entitytest              the fake pops the arguments it read
//   kp_entitytest --keep-args  the fake leaves them on the stack
//
// Both must produce the same result. Which one the real bridge does is not
// stated by api/routines.hpp, so entity.cpp is written to tolerate either and
// this switch is how that is demonstrated rather than asserted.

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "api/entity.hpp"
#include "api/routines.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}

// ============================================================ fake engine ====

namespace {

// The engine's own object_type byte, as recovered in
// data/research/phasor_structs.json: 4=area, 5=creature, 9=placeable, 10=door.
//
// A real GetObjectType returns the VM's OBJECT_TYPE_* constants instead, which
// are a different set of numbers for the same idea. Using the struct-side
// numbers here is deliberate: the entity module stores the type and compares it
// for equality and never interprets it, so a fake that hands it an unexpected
// numbering is a better test than one that agrees with a constant table
// nothing in this repo actually holds.
struct FakeObject {
    std::uint32_t id;
    int           type;
    std::string   name;
    std::string   tag;
    float         x, y, z;
    std::uint32_t area;
    bool          is_pc;
    int           faction;
    bool          alive;
};

std::vector<FakeObject> g_world = {
    {0x00000001u,  4, "Endar Spire - Command Module", "m01aa",
     0.f, 0.f, 0.f, kp::api::entity::kInvalidObject, false, 0, true},
    {0x80000000u,  5, "Revan",       "pc",           10.0f, 20.0f, 0.5f,
     0x00000001u, true,  2, true},
    {0x80000001u,  5, "Bastila",     "bastila",      11.0f, 20.5f, 0.5f,
     0x00000001u, false, 2, true},
    {0x80000002u,  5, "Carth Onasi", "carth",        12.0f, 21.0f, 0.5f,
     0x00000001u, false, 2, true},
    {0x00000012u,  9, "Footlocker",  "footlocker01", 14.0f, 22.0f, 0.0f,
     0x00000001u, false, 0, true},
    {0x00000013u, 10, "Blast Door",  "door01",       18.0f, 25.0f, 0.0f,
     0x00000001u, false, 0, true},
};

// Party slots, in the engine's order: slot 0 is the leader.
std::vector<std::uint32_t> g_party = {0x80000000u, 0x80000001u, 0x80000002u};

bool g_keep_args = false;

// Every routine call the module made, so the tool can show what reached the
// bridge rather than describing it.
std::vector<std::string> g_calls;

FakeObject* live(std::uint32_t id) {
    for (auto& o : g_world)
        if (o.id == id && o.alive) return &o;
    return nullptr;
}

}  // namespace

// ================================================ the other half of the API ==
//
// These are the symbols api/routines.hpp declares. When src/api/routines.cpp
// lands it defines them for real and this file stops being linked into
// anything but its own tool.

namespace kp::api {

namespace {
#include "generated/routines_k1.inc"
}  // namespace

const std::vector<Routine>& table() {
    static const std::vector<Routine> t(
        kRoutines, kRoutines + sizeof kRoutines / sizeof kRoutines[0]);
    return t;
}

const Routine* find(const std::string& name) {
    for (const auto& r : table())
        if (name == r.name) return &r;
    return nullptr;
}

const Routine* find(std::uint16_t id) {
    for (const auto& r : table())
        if (r.id == id) return &r;
    return nullptr;
}

namespace {
VmBinding g_binding;
}

void bind(const VmBinding& b) { g_binding = b; }
const VmBinding& binding() { return g_binding; }

// The fake dispatcher.
//
// Arguments sit at first_arg upward in DECLARED order, which is the contract
// entity.cpp is written against: the reversal onto the VM stack is the real
// bridge's job, one layer below this. The log line records them in the order
// they were found, so a reversed caller would be visible in the output rather
// than hidden by a symmetric signature.
int call(lua_State* L, const Routine& r, int first_arg) {
    const int argc = lua_gettop(L) - first_arg + 1;

    std::string log = r.name;
    log += "(";
    for (int i = 0; i < argc; ++i) {
        if (i) log += ", ";
        const int idx = first_arg + i;
        if (lua_type(L, idx) == LUA_TSTRING) {
            log += "\"";
            log += lua_tostring(L, idx);
            log += "\"";
        } else if (lua_isnumber(L, idx)) {
            char buf[32];
            std::snprintf(buf, sizeof buf, "%.0f", double(lua_tonumber(L, idx)));
            log += buf;
        } else {
            log += lua_typename(L, lua_type(L, idx));
        }
    }
    log += ")";
    g_calls.push_back(log);

    const std::string name = r.name;

    // Read the arguments before touching the stack, so the two argument
    // disciplines below cannot change what a routine sees.
    std::uint32_t obj = 0;
    if (argc >= 1 && lua_isnumber(L, first_arg))
        obj = std::uint32_t(lua_tonumber(L, first_arg));
    const int   int_arg0 = argc >= 1 && lua_isnumber(L, first_arg)
                               ? int(lua_tointeger(L, first_arg)) : 0;
    const int   int_arg1 = argc >= 2 && lua_isnumber(L, first_arg + 1)
                               ? int(lua_tointeger(L, first_arg + 1)) : 0;
    std::string str_arg0 = argc >= 1 && lua_type(L, first_arg) == LUA_TSTRING
                               ? lua_tostring(L, first_arg) : "";

    // The half of the calling convention api/routines.hpp does not state.
    if (!g_keep_args) lua_settop(L, first_arg - 1);

    const FakeObject* o = live(obj);

    if (name == "GetIsObjectValid") { lua_pushinteger(L, o ? 1 : 0); return 1; }
    if (name == "GetObjectType") {
        if (!o) return 0;
        lua_pushinteger(L, o->type);
        return 1;
    }
    if (name == "GetName") { lua_pushstring(L, o ? o->name.c_str() : ""); return 1; }
    if (name == "GetTag")  { lua_pushstring(L, o ? o->tag.c_str()  : ""); return 1; }
    if (name == "GetPosition") {
        // A vector crosses as a table with x, y and z, which is what the
        // routine bridge documents for Type::Vector.
        if (!o) return 0;
        lua_newtable(L);
        lua_pushnumber(L, o->x); lua_setfield(L, -2, "x");
        lua_pushnumber(L, o->y); lua_setfield(L, -2, "y");
        lua_pushnumber(L, o->z); lua_setfield(L, -2, "z");
        return 1;
    }
    if (name == "GetArea") {
        lua_pushnumber(L, lua_Number(o ? o->area : entity::kInvalidObject));
        return 1;
    }
    if (name == "GetFirstPC") {
        for (const auto& w : g_world)
            if (w.alive && w.is_pc) { lua_pushnumber(L, lua_Number(w.id)); return 1; }
        lua_pushnumber(L, lua_Number(entity::kInvalidObject));
        return 1;
    }
    if (name == "GetPartyMemberCount") {
        lua_pushinteger(L, int(g_party.size()));
        return 1;
    }
    if (name == "GetPartyMemberByIndex") {
        const bool in_range = int_arg0 >= 0 && int_arg0 < int(g_party.size());
        lua_pushnumber(L, lua_Number(in_range ? g_party[std::size_t(int_arg0)]
                                              : entity::kInvalidObject));
        return 1;
    }
    if (name == "IsObjectPartyMember") {
        int found = 0;
        for (auto id : g_party) if (id == obj) found = 1;
        lua_pushinteger(L, found);
        return 1;
    }
    if (name == "GetIsPC") { lua_pushinteger(L, o && o->is_pc ? 1 : 0); return 1; }
    if (name == "GetStandardFaction") {
        if (!o) return 0;
        lua_pushinteger(L, o->faction);
        return 1;
    }
    if (name == "GetObjectByTag") {
        // The asymmetric signature: (string sTag, int nNth). If a caller
        // reversed its arguments, str_arg0 would be empty and int_arg1 would be
        // whatever a string coerces to, and this lookup would miss.
        int seen = 0;
        for (const auto& w : g_world) {
            if (!w.alive || w.tag != str_arg0) continue;
            if (seen++ == int_arg1) { lua_pushnumber(L, lua_Number(w.id)); return 1; }
        }
        lua_pushnumber(L, lua_Number(entity::kInvalidObject));
        return 1;
    }

    return luaL_error(L, "fake dispatcher does not implement %s", r.name);
}

}  // namespace kp::api

// ==================================================================== driver =

namespace {

void heading(const char* text) {
    std::printf("\n=== %s %.*s\n", text,
                int(60 - std::strlen(text)),
                "--------------------------------------------------------------");
}

void run(lua_State* L, const char* chunk) {
    if (luaL_dostring(L, chunk) != 0) {
        std::printf("  LUA ERROR: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
    }
}

// What reached the bridge. The two liveness routines are counted rather than
// listed: entity re-asks them before every use of a handle, which is the point
// of the design and would otherwise be four fifths of this output.
void show_calls() {
    std::size_t checks = 0;
    std::string rest;
    for (const auto& c : g_calls) {
        if (c.rfind("GetIsObjectValid(", 0) == 0 ||
            c.rfind("GetObjectType(", 0) == 0) { ++checks; continue; }
        if (!rest.empty()) rest += ", ";
        rest += c;
    }
    std::printf("  routines called: %s\n", rest.empty() ? "none" : rest.c_str());
    if (checks)
        std::printf("                   (+%zu liveness re-checks, one pair per "
                    "handle use)\n", checks);
    g_calls.clear();
}

// Stubs with the real signatures, so the binding is non-null everywhere
// VmBinding::usable() looks. They are never called: every routine call in this
// tool goes through kp::api::call above, which answers out of the fake world
// instead of touching the VM.
int stub_execute(void*, int, int) { return 0; }
int stub_push_int(void*, int)     { return 0; }
int stub_pop_int(void*, int*)     { return 0; }

kp::api::VmBinding usable_binding() {
    static int receiver = 0;
    kp::api::VmBinding b;
    b.command_implementer = &receiver;
    b.virtual_machine     = &receiver;
    b.execute_command     = stub_execute;
    b.push_int            = stub_push_int;
    b.pop_int             = stub_pop_int;
    return b;
}

}  // namespace

int main(int argc, char** argv) {
    for (int i = 1; i < argc; ++i)
        if (std::strcmp(argv[i], "--keep-args") == 0) g_keep_args = true;

    std::printf("kp_entitytest: entity module over a fake routine dispatcher\n");
    std::printf("  routine table : %zu real K1 routines from "
                "src/generated/routines_k1.inc\n", kp::api::table().size());
    std::printf("  fake world    : %zu objects, party of %zu\n",
                g_world.size(), g_party.size());
    std::printf("  arguments     : the fake %s them\n",
                g_keep_args ? "LEAVES on the stack" : "pops");

    lua_State* L = luaL_newstate();
    luaL_openlibs(L);

    heading("registration reuses tables that already exist");
    // Stand in for another module that registered first.
    run(L, "kp = { marker = function() return 42 end, "
           "mem = { readbyte = function() return 0 end } }\n");
    kp::api::entity::register_all(L);
    kp::api::entity::register_all(L);   // twice on purpose
    run(L, "print('  kp.marker survived      :', kp.marker() == 42)\n"
           "print('  kp.mem.readbyte survived   :', kp.mem.readbyte ~= nil)\n"
           "print('  kp.obj installed        :', type(kp.obj))\n"
           "assert(kotor == nil, 'native registration must not create kotor')\n"
           "print('  kp.obj.INVALID          :', string.format('0x%08X', kp.obj.INVALID))\n");

    heading("before the VM binding exists");
    run(L, "print('  ready()                    :', kp.obj.ready())\n"
           "print('  valid(pc id)               :', kp.obj.valid(0x80000000))\n"
           "print('  pc()                       :', kp.obj.pc())\n"
           "print('  party() entries            :', #kp.obj.party())\n"
           "local h, why = kp.obj.get(0x80000000)\n"
           "print('  get()                      :', h, why)\n");
    show_calls();

    kp::api::bind(usable_binding());
    heading("handle creation and type tagging");
    run(L, "pc = kp.obj.pc()\n"
           "print('  pc()                       :', tostring(pc))\n"
           "print('  pc:id()                    :', string.format('0x%08X', pc:id()))\n"
           "print('  pc:type()                  :', pc:type())\n"
           "print('  pc:name()                  :', pc:name())\n"
           "print('  pc:valid()                 :', pc:valid())\n"
           "print('  pc:is_pc()                 :', pc:is_pc())\n"
           "locker = kp.obj.get(0x00000012)\n"
           "print('  a placeable                :', tostring(locker), locker:name())\n"
           "print('  handles compare by id      :', kp.obj.get(pc:id()) == pc)\n"
           "print('  a creature is not a locker :', locker == pc)\n");
    show_calls();

    heading("the call-through path");
    run(L, "local p = kp.obj.position(pc)\n"
           "print('  position(pc)               :', p.x, p.y, p.z)\n"
           "print('  tag(pc), name by id        :', kp.obj.tag(pc), kp.obj.name(0x80000001))\n"
           "print('  area(pc)                   :', tostring(kp.obj.area(pc)), kp.obj.area(pc):name())\n"
           "print('  faction(pc)                :', kp.obj.faction(pc))\n"
           "print('  type by routine            :', kp.obj.type(locker))\n");
    show_calls();

    heading("the party, and the argument order that is easy to reverse");
    run(L, "print('  party_size()               :', kp.obj.party_size())\n"
           "for i, m in ipairs(kp.obj.party()) do\n"
           "  print(string.format('  party()[%d]                 : %s  slot=%d  %s',\n"
           "        i, m:name(), m:party_slot(), tostring(m)))\n"
           "end\n"
           "print('  party_member(1)            :', kp.obj.party_member(1):name())\n"
           "print('  is_party_member(locker)    :', kp.obj.is_party_member(locker))\n"
           "print('  find(\"door01\")             :', kp.obj.find('door01'):name())\n"
           "print('  find(\"footlocker01\", 1)    :', kp.obj.find('footlocker01', 1))\n");
    std::printf("  the two-argument call, as the bridge saw it:\n");
    show_calls();

    heading("a destroyed id is refused, not answered");
    for (auto& o : g_world) if (o.id == 0x00000012u) o.alive = false;
    std::printf("  (the fake world just destroyed 0x00000012)\n");
    run(L, "print('  locker:valid()             :', locker:valid())\n"
           "print('  kp.obj.valid(id)        :', kp.obj.valid(0x00000012))\n"
           "local h, why = kp.obj.get(0x00000012)\n"
           "print('  get()                      :', h, why)\n"
           "local ok, err = pcall(function() return locker:name() end)\n"
           "print('  locker:name()              :', ok, err)\n");
    show_calls();

    heading("a RECYCLED id is refused too");
    g_world.push_back({0x00000012u, 10, "Security Door", "sec01",
                       30.f, 30.f, 0.f, 0x00000001u, false, 0, true});
    std::printf("  (the fake world handed 0x00000012 to a new door)\n");
    run(L, "print('  the id resolves again      :', kp.obj.valid(0x00000012))\n"
           "print('  a fresh handle is fine     :', kp.obj.get(0x00000012):name())\n"
           "print('  the OLD handle:valid()     :', locker:valid())\n"
           "local ok, err = pcall(function() return locker:tag() end)\n"
           "print('  the OLD handle:tag()       :', ok, err)\n");
    show_calls();

    heading("unbinding the VM mid-session");
    kp::api::bind(kp::api::VmBinding{});
    run(L, "print('  ready()                    :', kp.obj.ready())\n"
           "print('  party_size()               :', kp.obj.party_size())\n"
           "print('  name(pc id)                :', kp.obj.name(0x80000000))\n"
           "local ok, err = pcall(function() return pc:name() end)\n"
           "print('  a handle says why          :', ok, err)\n");
    show_calls();

    lua_close(L);
    std::printf("\ndone\n");
    return 0;
}
