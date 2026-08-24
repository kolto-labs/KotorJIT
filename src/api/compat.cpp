#include "api/compat.hpp"

#include <cstring>
#include <string>

#include "lua/host.hpp"
#include "platform/platform.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
}

namespace kp::api::compat {

namespace {

struct Alias  { const char* alias; const char* canonical; const char* dialect; };
struct EventC { const char* sapp; const char* lua_name; int value; const char* note; };

const Alias kAliases[] = {
#include "generated/compat_aliases.inc"
};
const EventC kEvents[] = {
#include "generated/compat_events.inc"
};

constexpr unsigned kAliasCount = sizeof kAliases / sizeof kAliases[0];
constexpr unsigned kEventCount = sizeof kEvents / sizeof kEvents[0];

// ------------------------------------------------------------------ print ---

int lua_print_to_log(lua_State* L) {
    // Same contract as Lua's own print: tostring every argument, tab-separated.
    // Going through the registered `tostring` rather than lua_tostring keeps
    // __tostring metamethods working, which is what a script expects.
    const int n = lua_gettop(L);
    std::string line;
    for (int i = 1; i <= n; ++i) {
        lua_getglobal(L, "tostring");
        lua_pushvalue(L, i);
        if (lua_pcall(L, 1, 1, 0) != 0) {
            lua_pop(L, 1);
            line += "(tostring failed)";
        } else {
            const char* s = lua_tostring(L, -1);
            line += s ? s : "(null)";
            lua_pop(L, 1);
        }
        if (i < n) line += '\t';
    }

    const lua::Script* owner = lua::Script::owner(L);
    platform::log(platform::LogLevel::Info, "[%s] %s",
                  owner ? owner->name().c_str() : "script", line.c_str());
    return 0;
}

// -------------------------------------------------------------- callbacks ---

// register_callback(event, "handler_name" | function)
//
// Both spellings are accepted because the two dialects differ: one passes a name
// so the handler can be replaced later, the other would rather pass the function.
// A name is resolved now, not at dispatch, so a typo is an error at the call
// site instead of an event that silently never fires.
int l_register_callback(lua_State* L) {
    const int constant = int(luaL_checkinteger(L, 1));
    const char* event = event_for_constant(constant);
    if (event == nullptr)
        return luaL_error(L, "register_callback: %d is not an event constant; "
                             "use one of the cb.EVENT_* values", constant);

    lua::Script* owner = lua::Script::owner(L);
    if (owner == nullptr)
        return luaL_error(L, "register_callback: no owning script");

    if (*event == '\0') {
        // The constant is real but nothing raises it here. Say so once rather
        // than accepting a handler that will never be called.
        const char* why = "";
        for (unsigned i = 0; i < kEventCount; ++i)
            if (kEvents[i].value == constant) { why = kEvents[i].note; break; }
        platform::log(platform::LogLevel::Warn,
                      "[%s] registered for an event this game does not have (%s)%s%s",
                      owner->name().c_str(),
                      [&] { for (unsigned i = 0; i < kEventCount; ++i)
                                if (kEvents[i].value == constant) return kEvents[i].sapp;
                            return "?"; }(),
                      *why ? ": " : "", why);
        lua_pushboolean(L, 0);
        return 1;
    }

    if (lua_isfunction(L, 2)) {
        lua_pushvalue(L, 2);
    } else {
        const char* fn = luaL_checkstring(L, 2);
        lua_getglobal(L, fn);
        if (!lua_isfunction(L, -1)) {
            lua_pop(L, 1);
            return luaL_error(L, "register_callback: '%s' is not a function", fn);
        }
    }
    owner->bind_callback(event, luaL_ref(L, LUA_REGISTRYINDEX));
    lua_pushboolean(L, 1);
    return 1;
}

int l_unregister_callback(lua_State* L) {
    const int constant = int(luaL_checkinteger(L, 1));
    const char* event = event_for_constant(constant);
    if (event == nullptr || *event == '\0') { lua_pushboolean(L, 0); return 1; }
    if (lua::Script* owner = lua::Script::owner(L))
        owner->bind_callback(event, LUA_NOREF);
    lua_pushboolean(L, 1);
    return 1;
}

// Copy one global under a second name. Both point at the same C function, so an
// alias costs nothing at call time -- which is the whole reason for doing this
// here rather than in a Lua shim.
bool alias_global(lua_State* L, const char* from, const char* to) {
    lua_getglobal(L, from);
    if (lua_isnil(L, -1)) { lua_pop(L, 1); return false; }
    lua_setglobal(L, to);
    return true;
}

// Find `name` in the kotor table or any of its sub-tables, one level down, and
// bind it to `to` both as kotor.<to> and as a bare global.
//
// Searching sub-tables matters because modules group their functions: raw memory
// lives at kotor.mem.readbyte rather than kotor.readbyte. Requiring the alias
// table to spell out each group would make it track internal layout, and it
// silently installed 11 of 57 aliases before this did.
//
// Both dialects expect these unqualified, so the bare global is the point; the
// kotor.<to> copy is for scripts that prefer to be explicit.
bool alias_in_table(lua_State* L, const char* from, const char* to) {
    lua_getglobal(L, "kotor");
    if (!lua_istable(L, -1)) { lua_pop(L, 1); return false; }
    const int kotor = lua_gettop(L);

    lua_getfield(L, kotor, from);
    if (!lua_isnil(L, -1)) {
        lua_pushvalue(L, -1);
        lua_setfield(L, kotor, to);
        lua_setglobal(L, to);
        lua_pop(L, 1);
        return true;
    }
    lua_pop(L, 1);

    lua_pushnil(L);
    while (lua_next(L, kotor) != 0) {
        // key at -2, value at -1
        if (lua_istable(L, -1)) {
            lua_getfield(L, -1, from);
            if (!lua_isnil(L, -1)) {
                lua_pushvalue(L, -1);
                lua_setfield(L, kotor, to);   // kotor.<alias>
                lua_setglobal(L, to);         // and bare <alias>
                lua_pop(L, 3);                // value, key, kotor
                return true;
            }
            lua_pop(L, 1);
        }
        lua_pop(L, 1);                        // value; key stays for lua_next
    }
    lua_pop(L, 1);
    return false;
}

// Both dialects also expect the CANONICAL names unqualified, not only the
// aliases. A script written for this runtime says readbyte(), not
// kotor.mem.readbyte().
void promote_canonical(lua_State* L, const char* name) {
    lua_getglobal(L, name);
    const bool have = !lua_isnil(L, -1);
    lua_pop(L, 1);
    if (!have) alias_in_table(L, name, name);
}

}  // namespace

const char* event_for_constant(int constant) {
    for (unsigned i = 0; i < kEventCount; ++i)
        if (kEvents[i].value == constant) return kEvents[i].lua_name;
    return nullptr;
}

const char* event_for_name(const char* sapp_name) {
    if (sapp_name == nullptr) return nullptr;
    for (unsigned i = 0; i < kEventCount; ++i)
        if (std::strcmp(kEvents[i].sapp, sapp_name) == 0) return kEvents[i].lua_name;
    return nullptr;
}

unsigned alias_count() { return kAliasCount; }
unsigned event_constant_count() { return kEventCount; }

void install_print(lua_State* L) {
    lua_pushcfunction(L, lua_print_to_log);
    lua_setglobal(L, "print");
}

void install(lua_State* L) {
    // 1. The cb table of event constants.
    lua_createtable(L, 0, int(kEventCount));
    for (unsigned i = 0; i < kEventCount; ++i) {
        lua_pushinteger(L, kEvents[i].value);
        lua_setfield(L, -2, kEvents[i].sapp);
    }
    lua_pushvalue(L, -1);
    lua_setglobal(L, "cb");
    // One dialect spells the same table `events`; both names, one table.
    lua_setglobal(L, "events");

    lua_pushcfunction(L, l_register_callback);
    lua_setglobal(L, "register_callback");
    lua_pushcfunction(L, l_unregister_callback);
    lua_setglobal(L, "unregister_callback");

    // 2. The aliases. A canonical name may live as a global or inside the kotor
    //    table depending on which module registered it, so try both.
    unsigned installed = 0, missing = 0;
    for (unsigned i = 0; i < kAliasCount; ++i) {
        promote_canonical(L, kAliases[i].canonical);
        if (alias_global(L, kAliases[i].canonical, kAliases[i].alias) ||
            alias_in_table(L, kAliases[i].canonical, kAliases[i].alias)) {
            ++installed;
        } else {
            ++missing;
            platform::log(platform::LogLevel::Debug,
                          "api: no function named %s, so %s was not aliased",
                          kAliases[i].canonical, kAliases[i].alias);
        }
    }

    // 3. Version and identity globals the two dialects read to decide what they
    //    are running under. We answer honestly rather than impersonating either:
    //    a script that branches on this should take the branch written for us.
    lua_pushstring(L, "KotorPhasor");   lua_setglobal(L, "_SERVERAPP");
    lua_pushstring(L, "KOTOR");         lua_setglobal(L, "_GAME");
    lua_pushinteger(L, 1);              lua_setglobal(L, "api_version");

    // 4. Lua version shims. LuaJIT is 5.1 with parts of 5.2, so most of what the
    //    shims patch is already here -- `bit` is built in, `loadstring` and
    //    `unpack` exist. `bit32` is the 5.2 spelling of the same library.
    lua_getglobal(L, "bit");
    if (lua_istable(L, -1)) lua_setglobal(L, "bit32"); else lua_pop(L, 1);

    platform::log(platform::LogLevel::Info,
                  "api: both dialects installed -- %u/%u aliases, %u event "
                  "constants%s",
                  installed, kAliasCount, kEventCount,
                  missing ? " (some canonical names not registered yet)" : "");
}

}  // namespace kp::api::compat
