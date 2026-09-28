// kp.scripts, kp.scriptname, kp.scriptdir. See scripts_lua.hpp for the surface.
#include "api/scripts_lua.hpp"

#include <cmath>
#include <cstdint>
#include <string>

#include "api/timers.hpp"
#include "lua/host.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
}

namespace kp::api::scripts {

namespace {

// One host per process. Every state reads it at call time, so rebinding (or
// unbinding at shutdown) takes effect everywhere at once.
lua::Host* g_host = nullptr;

lua::Host& host_or_error(lua_State* L, const char* fn) {
    if (g_host == nullptr) luaL_error(L, "kp.scripts.%s: no script host is running", fn);
    return *g_host;
}

const char* state_name(lua::ScriptState s) {
    switch (s) {
    case lua::ScriptState::Loaded:       return "loaded";
    case lua::ScriptState::FailedToLoad: return "failed";
    case lua::ScriptState::Quarantined:  return "quarantined";
    case lua::ScriptState::Unloaded:     return "unloaded";
    }
    return "unknown";
}

const char* op_name(lua::LifecycleOp op) {
    switch (op) {
    case lua::LifecycleOp::Load:   return "load";
    case lua::LifecycleOp::Unload: return "unload";
    case lua::LifecycleOp::Reload: return "reload";
    }
    return "unknown";
}

void set_string(lua_State* L, const char* k, const std::string& v) {
    lua_pushlstring(L, v.data(), v.size());
    lua_setfield(L, -2, k);
}
void set_number(lua_State* L, const char* k, double v) {
    lua_pushnumber(L, v);
    lua_setfield(L, -2, k);
}

int l_list(lua_State* L) {
    lua::Host& h = host_or_error(L, "list");
    lua_newtable(L);
    int i = 0;
    for (const auto& sp : h.scripts()) {
        const lua::Script& s = *sp;
        lua_newtable(L);
        set_string(L, "name", s.name());
        set_string(L, "path", s.path());
        set_string(L, "state", state_name(s.state()));
        set_number(L, "generation", double(s.generation()));
        set_number(L, "priority", s.priority());
        set_number(L, "errors", s.error_count());
        set_number(L, "timers", s.L() != nullptr ? double(timers::pending(s.L())) : 0.0);
        if (!s.last_load_error().empty()) set_string(L, "last_error", s.last_load_error());
        lua_rawseti(L, -2, ++i);
    }
    return 1;
}

// Every check that can raise runs before a std::string exists: luaL_error
// longjmps, and a destructor it skips is a leak at best.
int queue(lua_State* L, lua::LifecycleOp op, const char* fn) {
    lua::Host& h = host_or_error(L, fn);
    if (lua_type(L, 1) != LUA_TSTRING)
        return luaL_error(L, "kp.scripts.%s: expected a script name (string), got %s",
                          fn, luaL_typename(L, 1));
    size_t len = 0;
    const char* name = lua_tolstring(L, 1, &len);
    lua_pushnumber(L, double(h.request(op, std::string(name, len))));
    return 1;
}

int l_load(lua_State* L)   { return queue(L, lua::LifecycleOp::Load, "load"); }
int l_unload(lua_State* L) { return queue(L, lua::LifecycleOp::Unload, "unload"); }
int l_reload(lua_State* L) { return queue(L, lua::LifecycleOp::Reload, "reload"); }

int l_result(lua_State* L) {
    if (lua_type(L, 1) != LUA_TNUMBER)
        return luaL_error(L, "kp.scripts.result: expected a request id (number), got %s",
                          luaL_typename(L, 1));
    const double raw = lua_tonumber(L, 1);
    lua::Host& h = host_or_error(L, "result");
    // Ids are positive integers well below 2^53. Anything else -- a fraction,
    // an infinity, NaN, a value the uint64 cast would make undefined -- cannot
    // be an id this host issued, so it answers nil like an unknown id. No
    // error: result() is a poll, and polling a bad id is not a script fault.
    const bool is_id = raw >= 1 && raw <= 9007199254740992.0 && std::floor(raw) == raw;
    const lua::RequestResult* r = is_id ? h.result(std::uint64_t(raw)) : nullptr;
    if (r == nullptr) { lua_pushnil(L); return 1; }
    if (r->status == lua::RequestStatus::Pending) { lua_pushliteral(L, "pending"); return 1; }
    lua_newtable(L);
    lua_pushboolean(L, r->status == lua::RequestStatus::Ok);
    lua_setfield(L, -2, "ok");
    if (!r->error.empty()) set_string(L, "error", r->error);
    set_number(L, "generation", double(r->generation));
    set_string(L, "name", r->name);
    set_string(L, "op", op_name(r->op));
    return 1;
}

// nil where no Script owns the state: the F12 console. data/hostapi.toml says
// "every lua_State has an owning script", which the console state disproves.
int l_scriptname(lua_State* L) {
    if (lua::Script* s = lua::Script::owner(L)) {
        lua_pushlstring(L, s->name().data(), s->name().size());
        return 1;
    }
    lua_pushnil(L);
    return 1;
}

int l_scriptdir(lua_State* L) {
    if (g_host == nullptr) { lua_pushliteral(L, ""); return 1; }
    const std::string& d = g_host->script_dir();
    lua_pushlstring(L, d.data(), d.size());
    return 1;
}

void push_kp_table(lua_State* L) {
    lua_getglobal(L, "kp");
    if (lua_istable(L, -1)) return;
    lua_pop(L, 1);
    lua_newtable(L);
    lua_pushvalue(L, -1);
    lua_setglobal(L, "kp");
}

}  // namespace

void bind_host(lua::Host* h) { g_host = h; }
lua::Host* bound_host() { return g_host; }

void register_all(lua_State* L) {
    push_kp_table(L);

    lua_newtable(L);
    static const luaL_Reg kScripts[] = {
        {"list", l_list},
        {"load", l_load},
        {"unload", l_unload},
        {"reload", l_reload},
        {"result", l_result},
        {nullptr, nullptr},
    };
    for (const luaL_Reg* r = kScripts; r->name != nullptr; ++r) {
        lua_pushcfunction(L, r->func);
        lua_setfield(L, -2, r->name);
    }
    lua_setfield(L, -2, "scripts");

    lua_pushcfunction(L, l_scriptname);
    lua_setfield(L, -2, "scriptname");
    lua_pushcfunction(L, l_scriptdir);
    lua_setfield(L, -2, "scriptdir");

    lua_pop(L, 1);  // kp
}

}  // namespace kp::api::scripts
