#include "api/entity.hpp"

#include <cstdio>
#include <string>

#include "api/routines.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
}

namespace kp::api::entity {

namespace {

// The metatable name is also the registry key, so one state gets one handle
// type no matter how many times registration runs.
const char* const kHandleType = "kp.object";

// Every routine this module calls, by name. Lookup is by name and not by id
// because the ids differ between K1 and K2 for the same routine, and a wrong id
// calls a real function with the wrong arguments. A name that is not in the
// running game's table simply makes the function report its documented failure
// value.
const char* const kIsValid       = "GetIsObjectValid";
const char* const kObjectType    = "GetObjectType";
const char* const kGetName       = "GetName";
const char* const kGetTag        = "GetTag";
const char* const kGetPosition   = "GetPosition";
const char* const kGetArea       = "GetArea";
const char* const kFirstPC       = "GetFirstPC";
const char* const kPartyCount    = "GetPartyMemberCount";
const char* const kPartyByIndex  = "GetPartyMemberByIndex";
const char* const kIsPartyMember = "IsObjectPartyMember";
const char* const kIsPC          = "GetIsPC";
const char* const kObjectByTag   = "GetObjectByTag";
const char* const kFaction       = "GetStandardFaction";

// ------------------------------------------------------- the routine call ---

// Object ids are pushed and read as Lua numbers, never as lua_Integer. Bit 31
// of an id selects one of the engine's two id spaces (CGameObject.id), so a
// character id has the high bit set and would come back negative through a
// 32-bit signed integer. A double represents every uint32 exactly.
void push_object_id(lua_State* L, std::uint32_t id) {
    lua_pushnumber(L, static_cast<lua_Number>(id));
}

bool object_id_at(lua_State* L, int index, std::uint32_t& out) {
    if (Handle* h = to_handle(L, index)) { out = h->id; return true; }
    if (!lua_isnumber(L, index)) return false;
    const lua_Number n = lua_tonumber(L, index);
    if (n < 0.0 || n > 4294967295.0) return false;
    out = static_cast<std::uint32_t>(n);
    return true;
}

// Call a routine whose `nargs` arguments are already on top of the stack, in
// DECLARED order.
//
// Declared order is deliberate and is stated here because it is the trap in
// this whole area. The VM pops a routine's first declared parameter first, so
// something has to push the last declared parameter first -- and api/routines.
// hpp says that reversal is the bridge's job. Pre-reversing here would undo it,
// and the mistake is invisible for a symmetric signature like GetObjectType and
// silently wrong for an asymmetric one like GetObjectByTag(string, int).
//
// On success exactly one value -- the routine's first result -- is left on top
// and 1 is returned. On failure the stack is restored and 0 is returned: no
// VM binding yet, no such routine in this build's table, or a routine that
// returned nothing.
int call_one(lua_State* L, const char* name, int nargs) {
    const int base = lua_gettop(L) - nargs;

    const Routine* r = ready() ? find(std::string(name)) : nullptr;
    if (!r) { lua_settop(L, base); return 0; }

    const int nres = call(L, *r, base + 1);
    if (nres <= 0) { lua_settop(L, base); return 0; }

    // Counted from the top, not from `base`, because the bridge is free to pop
    // the arguments it read or to leave them. Both layouts put the first result
    // at gettop - nres + 1.
    lua_pushvalue(L, lua_gettop(L) - nres + 1);
    lua_insert(L, base + 1);
    lua_settop(L, base + 1);
    return 1;
}

bool call_int(lua_State* L, const char* name, int nargs, int& out) {
    if (!call_one(L, name, nargs)) return false;
    const bool numeric = lua_isnumber(L, -1) != 0;
    if (numeric) out = static_cast<int>(lua_tointeger(L, -1));
    lua_pop(L, 1);
    return numeric;
}

bool call_object(lua_State* L, const char* name, int nargs, std::uint32_t& out) {
    if (!call_one(L, name, nargs)) return false;
    const bool ok = object_id_at(L, lua_gettop(L), out);
    lua_pop(L, 1);
    return ok;
}

// ------------------------------------------------------------- liveness -----

bool is_live(lua_State* L, std::uint32_t id) {
    if (id == kInvalidObject) return false;
    push_object_id(L, id);
    int alive = 0;
    return call_int(L, kIsValid, 1, alive) && alive != 0;
}

// Ids are printed for humans, so they are formatted here rather than through
// luaL_error. Lua 5.1's format string understands %d, %s, %f, %p and %c and
// nothing else -- %08X would be copied through literally.
struct IdText { char text[16]; };

IdText id_text(std::uint32_t id) {
    IdText t{};
    std::snprintf(t.text, sizeof t.text, "0x%08lX", static_cast<unsigned long>(id));
    return t;
}

// --------------------------------------------------------------- handles ----

int handle_tostring(lua_State* L) {
    Handle* h = static_cast<Handle*>(luaL_checkudata(L, 1, kHandleType));
    const IdText t = id_text(h->id);
    if (h->type_known) lua_pushfstring(L, "object %s type %d", t.text, h->type);
    else               lua_pushfstring(L, "object %s", t.text);
    return 1;
}

// Two handles are equal when they name the same id. Whether that id still
// resolves is a separate question, asked by :valid().
int handle_eq(lua_State* L) {
    Handle* a = to_handle(L, 1);
    Handle* b = to_handle(L, 2);
    lua_pushboolean(L, a && b && a->id == b->id);
    return 1;
}

// The id behind a handle argument, refused if it has gone stale.
//
// Two ways to be stale, and both matter. The id may no longer resolve, which is
// the ordinary case after a DestroyObject. Or it may resolve to an object of a
// different type, which is what a recycled id looks like from here. Either way
// the script is about to act on the wrong object, so this raises rather than
// answering. The non-raising test is :valid().
std::uint32_t live_id(lua_State* L, int index) {
    Handle* h = static_cast<Handle*>(luaL_checkudata(L, index, kHandleType));
    const IdText t = id_text(h->id);

    if (!ready())
        return luaL_error(L, "object %s cannot be used yet: the engine routine "
                             "bridge is not bound", t.text), 0u;
    if (!is_live(L, h->id))
        return luaL_error(L, "object %s no longer resolves", t.text), 0u;

    if (h->type_known) {
        push_object_id(L, h->id);
        int now = 0;
        if (call_int(L, kObjectType, 1, now) && now != h->type)
            return luaL_error(L, "object %s is a different object now: type %d, "
                                 "was %d. Object ids are recycled",
                              t.text, now, h->type), 0u;
    }
    return h->id;
}

// The id behind either kind of object argument. A handle is checked for
// staleness; a bare number is taken as given, because a number carries nothing
// to check it against.
std::uint32_t object_arg_checked(lua_State* L, int index) {
    if (to_handle(L, index)) return live_id(L, index);
    std::uint32_t id = 0;
    if (!object_id_at(L, index, id))
        luaL_argerror(L, index, "expected an object handle or an object id");
    return id;
}

// ------------------------------------------------- the shared workers -------
//
// Each of these is reached two ways: kotor.obj.name(o) and o:name(). One
// implementation, two bindings, so the two can never disagree.

int push_name(lua_State* L, std::uint32_t id) {
    push_object_id(L, id);
    if (!call_one(L, kGetName, 1)) { lua_pushnil(L); }
    return 1;
}

int push_tag(lua_State* L, std::uint32_t id) {
    push_object_id(L, id);
    if (!call_one(L, kGetTag, 1)) { lua_pushnil(L); }
    return 1;
}

// One table, not Phasor's three return values. The routine bridge already
// marshals a vector as a table, and two shapes for one concept is how a script
// ends up unpacking the wrong number of values.
int push_position(lua_State* L, std::uint32_t id) {
    push_object_id(L, id);
    if (!call_one(L, kGetPosition, 1)) { lua_pushnil(L); }
    return 1;
}

int push_type(lua_State* L, std::uint32_t id) {
    push_object_id(L, id);
    int t = 0;
    if (call_int(L, kObjectType, 1, t)) lua_pushinteger(L, t);
    else                                lua_pushnil(L);
    return 1;
}

int push_faction(lua_State* L, std::uint32_t id) {
    push_object_id(L, id);
    int f = 0;
    if (call_int(L, kFaction, 1, f)) lua_pushinteger(L, f);
    else                             lua_pushnil(L);
    return 1;
}

int push_area(lua_State* L, std::uint32_t id) {
    push_object_id(L, id);
    std::uint32_t area = 0;
    Handle h;
    if (call_object(L, kGetArea, 1, area) && resolve(L, area, h)) push_handle(L, h);
    else                                                          lua_pushnil(L);
    return 1;
}

int push_is_pc(lua_State* L, std::uint32_t id) {
    push_object_id(L, id);
    int r = 0;
    lua_pushboolean(L, call_int(L, kIsPC, 1, r) && r != 0);
    return 1;
}

int push_is_party_member(lua_State* L, std::uint32_t id) {
    push_object_id(L, id);
    int r = 0;
    lua_pushboolean(L, call_int(L, kIsPartyMember, 1, r) && r != 0);
    return 1;
}

// Phasor's rresolveplayer. No engine routine reverses GetPartyMemberByIndex, so
// this is a scan -- over at most three slots, which is why the absence of a
// reverse routine costs nothing here and cost Phasor a lookup table over 16.
int push_party_slot(lua_State* L, std::uint32_t id) {
    int count = 0;
    if (!call_int(L, kPartyCount, 0, count)) { lua_pushnil(L); return 1; }
    for (int i = 0; i < count; ++i) {
        lua_pushinteger(L, i);
        std::uint32_t member = 0;
        if (call_object(L, kPartyByIndex, 1, member) && member == id) {
            lua_pushinteger(L, i);   // the engine's own slot number, 0 first
            return 1;
        }
    }
    lua_pushnil(L);
    return 1;
}

// Every party member as a handle. Built directly on the Lua stack: a routine
// call can raise, a raise is a longjmp, and a longjmp past a std::vector leaks
// it. Nothing here has a destructor to skip.
int push_party(lua_State* L) {
    lua_newtable(L);
    const int result = lua_gettop(L);

    int count = 0;
    if (!call_int(L, kPartyCount, 0, count)) return 1;   // empty table

    int written = 0;
    for (int i = 0; i < count; ++i) {
        lua_pushinteger(L, i);
        std::uint32_t member = 0;
        if (!call_object(L, kPartyByIndex, 1, member)) continue;
        Handle h;
        if (!resolve(L, member, h)) continue;
        push_handle(L, h);
        lua_rawseti(L, result, ++written);   // 1-based array; [1] is slot 0
    }
    return 1;
}

// --------------------------------------------------- the Lua functions ------

int l_ready(lua_State* L) { lua_pushboolean(L, ready()); return 1; }

int l_valid(lua_State* L) {
    std::uint32_t id = 0;
    if (Handle* h = to_handle(L, 1)) id = h->id;
    else if (!object_id_at(L, 1, id))
        luaL_argerror(L, 1, "expected an object handle or an object id");
    lua_pushboolean(L, is_live(L, id));
    return 1;
}

// nil and a reason rather than a bare nil: "no such object" and "the bridge is
// not up yet" are different problems for the script author, and a lone nil
// cannot tell them apart.
int l_get(lua_State* L) {
    std::uint32_t id = 0;
    if (!object_id_at(L, 1, id))
        luaL_argerror(L, 1, "expected an object handle or an object id");

    Handle h;
    if (resolve(L, id, h)) { push_handle(L, h); return 1; }

    const IdText t = id_text(id);
    lua_pushnil(L);
    if (!ready()) lua_pushstring(L, "the engine routine bridge is not bound yet");
    else          lua_pushfstring(L, "no live object with id %s", t.text);
    return 2;
}

int l_pc(lua_State* L) {
    std::uint32_t id = 0;
    Handle h;
    if (call_object(L, kFirstPC, 0, id) && resolve(L, id, h)) push_handle(L, h);
    else                                                      lua_pushnil(L);
    return 1;
}

int l_party(lua_State* L) { return push_party(L); }

// Phasor's getteamsize, for the party-sized answer. Counting a faction is a
// different question and belongs with the faction routines.
int l_party_size(lua_State* L) {
    int count = 0;
    lua_pushinteger(L, call_int(L, kPartyCount, 0, count) ? count : 0);
    return 1;
}

// Phasor's resolveplayer. The index is the engine's: 0 is the party leader.
int l_party_member(lua_State* L) {
    const int index = static_cast<int>(luaL_checkinteger(L, 1));
    if (index < 0) luaL_argerror(L, 1, "party slot cannot be negative");

    lua_pushinteger(L, index);
    std::uint32_t id = 0;
    Handle h;
    if (call_object(L, kPartyByIndex, 1, id) && resolve(L, id, h)) push_handle(L, h);
    else                                                           lua_pushnil(L);
    return 1;
}

int l_find(lua_State* L) {
    const char* tag = luaL_checkstring(L, 1);
    const int nth = static_cast<int>(luaL_optinteger(L, 2, 0));

    // Declared order: GetObjectByTag(string sTag, int nNth). See call_one.
    lua_pushstring(L, tag);
    lua_pushinteger(L, nth);
    std::uint32_t id = 0;
    Handle h;
    if (call_object(L, kObjectByTag, 2, id) && resolve(L, id, h)) push_handle(L, h);
    else                                                          lua_pushnil(L);
    return 1;
}

int l_name(lua_State* L)     { return push_name(L, object_arg_checked(L, 1)); }
int l_tag(lua_State* L)      { return push_tag(L, object_arg_checked(L, 1)); }
int l_position(lua_State* L) { return push_position(L, object_arg_checked(L, 1)); }
int l_type(lua_State* L)     { return push_type(L, object_arg_checked(L, 1)); }
int l_area(lua_State* L)     { return push_area(L, object_arg_checked(L, 1)); }
int l_faction(lua_State* L)  { return push_faction(L, object_arg_checked(L, 1)); }
int l_is_pc(lua_State* L)    { return push_is_pc(L, object_arg_checked(L, 1)); }
int l_is_party_member(lua_State* L) {
    return push_is_party_member(L, object_arg_checked(L, 1));
}
int l_party_slot(lua_State* L) { return push_party_slot(L, object_arg_checked(L, 1)); }

// --------------------------------------------------------- handle methods ---

int m_id(lua_State* L) {
    Handle* h = static_cast<Handle*>(luaL_checkudata(L, 1, kHandleType));
    push_object_id(L, h->id);
    return 1;
}

// The type recorded when the handle was made, without asking the engine again.
// kotor.obj.type(o) asks; this reports. They differ exactly when the id has
// been recycled, and :valid() is the thing that notices.
int m_type(lua_State* L) {
    Handle* h = static_cast<Handle*>(luaL_checkudata(L, 1, kHandleType));
    if (h->type_known) lua_pushinteger(L, h->type);
    else               lua_pushnil(L);
    return 1;
}

// The one handle method that never raises, because it is the test the others
// are checked against.
int m_valid(lua_State* L) {
    Handle* h = static_cast<Handle*>(luaL_checkudata(L, 1, kHandleType));
    if (!is_live(L, h->id)) { lua_pushboolean(L, 0); return 1; }
    if (!h->type_known)     { lua_pushboolean(L, 1); return 1; }

    push_object_id(L, h->id);
    int now = 0;
    const bool asked = call_int(L, kObjectType, 1, now);
    lua_pushboolean(L, !asked || now == h->type);
    return 1;
}

int m_name(lua_State* L)     { return push_name(L, live_id(L, 1)); }
int m_tag(lua_State* L)      { return push_tag(L, live_id(L, 1)); }
int m_position(lua_State* L) { return push_position(L, live_id(L, 1)); }
int m_area(lua_State* L)     { return push_area(L, live_id(L, 1)); }
int m_faction(lua_State* L)  { return push_faction(L, live_id(L, 1)); }
int m_is_pc(lua_State* L)    { return push_is_pc(L, live_id(L, 1)); }
int m_is_party_member(lua_State* L) { return push_is_party_member(L, live_id(L, 1)); }
int m_party_slot(lua_State* L)      { return push_party_slot(L, live_id(L, 1)); }

// ------------------------------------------------------------ registration --

struct Entry { const char* name; lua_CFunction fn; };

const Entry kModule[] = {
    {"ready",           l_ready},
    {"valid",           l_valid},
    {"get",             l_get},
    {"pc",              l_pc},
    {"party",           l_party},
    {"party_size",      l_party_size},
    {"party_member",    l_party_member},
    {"party_slot",      l_party_slot},
    {"is_party_member", l_is_party_member},
    {"is_pc",           l_is_pc},
    {"name",            l_name},
    {"tag",             l_tag},
    {"position",        l_position},
    {"type",            l_type},
    {"area",            l_area},
    {"faction",         l_faction},
    {"find",            l_find},
};

const Entry kMethods[] = {
    {"id",              m_id},
    {"type",            m_type},
    {"valid",           m_valid},
    {"name",            m_name},
    {"tag",             m_tag},
    {"position",        m_position},
    {"area",            m_area},
    {"faction",         m_faction},
    {"is_pc",           m_is_pc},
    {"is_party_member", m_is_party_member},
    {"party_slot",      m_party_slot},
};

void fill(lua_State* L, const Entry* entries, std::size_t count) {
    for (std::size_t i = 0; i < count; ++i) {
        lua_pushcfunction(L, entries[i].fn);
        lua_setfield(L, -2, entries[i].name);
    }
}

// Reuse before create, at both levels. Other modules register into the same
// globals from their own files, and whichever ran first would lose everything
// it installed if the second one pushed a fresh table over the top.
void push_global_table(lua_State* L, const char* name) {
    lua_getglobal(L, name);
    if (lua_istable(L, -1)) return;
    lua_pop(L, 1);
    lua_newtable(L);
    lua_pushvalue(L, -1);
    lua_setglobal(L, name);
}

void push_subtable(lua_State* L, int parent, const char* name) {
    lua_getfield(L, parent, name);
    if (lua_istable(L, -1)) return;
    lua_pop(L, 1);
    lua_newtable(L);
    lua_pushvalue(L, -1);
    lua_setfield(L, parent, name);
}

void ensure_metatable(lua_State* L) {
    // luaL_newmetatable is itself check-and-reuse, and it is keyed in this
    // state's registry, so a second registration finds the first one's table
    // and existing handles keep working.
    if (luaL_newmetatable(L, kHandleType)) {
        lua_newtable(L);
        fill(L, kMethods, sizeof kMethods / sizeof kMethods[0]);
        lua_setfield(L, -2, "__index");

        lua_pushcfunction(L, handle_tostring);
        lua_setfield(L, -2, "__tostring");
        lua_pushcfunction(L, handle_eq);
        lua_setfield(L, -2, "__eq");

        // A script should not be able to reach in and rewrite the methods of
        // every handle in its state.
        lua_pushboolean(L, 0);
        lua_setfield(L, -2, "__metatable");
    }
    lua_pop(L, 1);
}

}  // namespace

// ------------------------------------------------------------ public API ----

bool ready() { return binding().usable(); }

void push_handle(lua_State* L, const Handle& h) {
    void* mem = lua_newuserdata(L, sizeof(Handle));
    *static_cast<Handle*>(mem) = h;
    luaL_getmetatable(L, kHandleType);
    lua_setmetatable(L, -2);
}

Handle* to_handle(lua_State* L, int index) {
    if (index < 0 && index > LUA_REGISTRYINDEX) index = lua_gettop(L) + index + 1;
    void* p = lua_touserdata(L, index);
    if (!p) return nullptr;
    if (!lua_getmetatable(L, index)) return nullptr;
    luaL_getmetatable(L, kHandleType);
    const bool ours = lua_rawequal(L, -1, -2) != 0;
    lua_pop(L, 2);
    return ours ? static_cast<Handle*>(p) : nullptr;
}

bool object_arg(lua_State* L, int index, std::uint32_t& id) {
    return object_id_at(L, index, id);
}

bool resolve(lua_State* L, std::uint32_t id, Handle& out) {
    if (!is_live(L, id)) return false;
    out.id = id;
    out.type = 0;
    out.type_known = false;

    push_object_id(L, id);
    int t = 0;
    if (call_int(L, kObjectType, 1, t)) { out.type = t; out.type_known = true; }
    return true;
}

void register_all(lua_State* L) {
    ensure_metatable(L);

    push_global_table(L, "kotor");                  // kotor
    push_subtable(L, lua_gettop(L), "obj");         // kotor, kotor.obj
    const int obj = lua_gettop(L);

    fill(L, kModule, sizeof kModule / sizeof kModule[0]);
    push_object_id(L, kInvalidObject);
    lua_setfield(L, obj, "INVALID");

    // data/hostapi.toml names these kp.obj.*. Bind that name to the same table
    // object rather than registering twice, and leave an existing kp.obj alone
    // in case someone got here first.
    push_global_table(L, "kp");                     // kotor, kotor.obj, kp
    lua_getfield(L, -1, "obj");
    const bool taken = lua_istable(L, -1);
    lua_pop(L, 1);
    if (!taken) {
        lua_pushvalue(L, obj);
        lua_setfield(L, -2, "obj");
    }
    lua_pop(L, 3);
}

}  // namespace kp::api::entity
