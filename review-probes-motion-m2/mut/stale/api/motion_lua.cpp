#include "api/motion.hpp"
#include "api/engine_gate.hpp"
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <limits>
#include <new>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
}
// kp.motion.{capabilities,capture,relocate,restore,observe}. The capture is a
// protected userdata (size + metatable + magic checked on every access, as in
// model_lua.cpp); fields are copied out on read, so nothing Lua holds can
// alias engine memory. Failures return nil, "<kind>: <reason>".
//
// Order inside every op: binding -> engine-thread gate -> pure argument
// checks -> core (guards, chain, getter, fences, policy, setter, readback).
// A gate refusal therefore precedes every read, call and argument error.
namespace kp::api::motion {
namespace {
constexpr const char* capture_type = "kp.motion.capture";
constexpr std::uint64_t capture_magic = 0x4b504d4f54494f31ULL; // "KPMOTIO1"
struct Box { std::uint64_t magic; Capture value; };
char token_key;                                    // registry key (address only)
std::atomic<std::uint64_t> g_next_token{0};
std::atomic<OwnerProbe> g_owner{nullptr};
std::atomic<void*> g_owner_context{nullptr};

int failure(lua_State* L, const std::string& error) {
    lua_pushnil(L); lua_pushlstring(L, error.data(), error.size()); return 2;
}
// Binding and gate, before anything else.
bool preflight(lua_State* L, int& results) {
    if (!operations().available()) { results = failure(L, "unsupported: no verified native motion binding"); return false; }
    if (!engine::on_engine_thread()) { results = failure(L, engine::gate_refusal()); return false; }
    return true;
}
Writer writer_of(lua_State* L) {
    OwnerProbe probe = g_owner.load();
    return probe ? probe(L, g_owner_context.load()) : Writer::None;
}
const Capture& checked(lua_State* L, int index) {
    if (lua_type(L, index) != LUA_TUSERDATA || lua_objlen(L, index) != sizeof(Box))
        luaL_argerror(L, index, "motion capture allocation required");
    auto* box = static_cast<Box*>(luaL_checkudata(L, index, capture_type));
    if (box->magic != capture_magic) luaL_argerror(L, index, "invalid motion capture magic");
    return box->value;
}
void push_capture(lua_State* L, const Capture& c) {
    new (lua_newuserdata(L, sizeof(Box))) Box{capture_magic, c};
    luaL_getmetatable(L, capture_type); lua_setmetatable(L, -2);
}
bool exact_id(lua_State* L, int index, std::uint32_t& out) {
    if (lua_type(L, index) != LUA_TNUMBER) return false;
    double id = lua_tonumber(L, index);
    if (!std::isfinite(id) || id < 0 || id > 4294967295. || std::floor(id) != id) return false;
    out = static_cast<std::uint32_t>(id);
    return true;
}
void vec3(lua_State* L, const std::array<float, 3>& v) {
    lua_createtable(L, 0, 3);
    lua_pushnumber(L, v[0]); lua_setfield(L, -2, "x");
    lua_pushnumber(L, v[1]); lua_setfield(L, -2, "y");
    lua_pushnumber(L, v[2]); lua_setfield(L, -2, "z");
}
int index(lua_State* L) {
    const Capture& c = checked(L, 1);
    std::string key(luaL_checkstring(L, 2));
    if (key == "id") lua_pushnumber(L, c.id);
    else if (key == "area_id") lua_pushnumber(L, c.area_id);
    else if (key == "epoch") lua_pushnumber(L, static_cast<lua_Number>(c.epoch));
    else if (key == "object") {
        char text[32]; std::snprintf(text, sizeof text, "0x%llx", static_cast<unsigned long long>(c.object));
        lua_pushstring(L, text);
    }
    else if (key == "position") vec3(L, c.position);
    else if (key == "orientation") vec3(L, c.orientation);
    else if (key == "facing") lua_pushnumber(L, c.facing);
    else if (key == "push_gate_raw") lua_pushnumber(L, c.push_gate_raw);
    else if (key == "dirty_position") lua_pushboolean(L, c.dirty_position);
    else if (key == "dirty_orientation") lua_pushboolean(L, c.dirty_orientation);
    else if (key == "collision_registered") lua_pushboolean(L, c.collision_registered);
    else if (key == "owned") lua_pushboolean(L, c.owned);
    else if (key == "quaternion_raw") {
        lua_createtable(L, 4, 0);
        for (int i = 0; i < 4; ++i) { lua_pushnumber(L, c.quaternion_raw[i]); lua_rawseti(L, -2, i + 1); }
    }
    else if (key == "quaternion_order") lua_pushliteral(L, "unverified");
    else lua_pushnil(L);
    return 1;
}
int newindex(lua_State* L) {
    checked(L, 1);
    return luaL_error(L, "motion capture is read-only");
}
int capture(lua_State* L) {
    int results = 0;
    if (!preflight(L, results)) return results;
    std::uint32_t id = 0;
    if (!exact_id(L, 1, id)) return failure(L, "value: server ID must be an exact uint32 number");
    Capture result; std::string error;
    if (!operations().capture(id, result, error)) return failure(L, error);
    std::uint64_t token = state_token(L);
    result.owned = token != 0 && operations().owner_of(id) == token;
    push_capture(L, result);
    return 1;
}
// target: a table or kp.vec with numeric x, y, z. Strings are not numbers.
bool read_target(lua_State* L, int index, std::array<float, 3>& out, std::string& error) {
    int type = lua_type(L, index);
    if (type != LUA_TTABLE && type != LUA_TUSERDATA) { error = "value: target must be {x=,y=,z=} or a kp.vec"; return false; }
    const char* names[3] = {"x", "y", "z"};
    for (int i = 0; i < 3; ++i) {
        lua_getfield(L, index, names[i]);
        if (lua_type(L, -1) != LUA_TNUMBER) {
            lua_pop(L, 1);
            error = std::string("value: target.") + names[i] + " must be a number"; return false;
        }
        double v = lua_tonumber(L, -1); lua_pop(L, 1);
        if (!std::isfinite(v)) { error = std::string("value: target.") + names[i] + " is not finite"; return false; }
        if (std::fabs(v) > static_cast<double>(std::numeric_limits<float>::max())) {
            error = std::string("value: target.") + names[i] + " overflows a float"; return false;
        }
        out[i] = static_cast<float>(v);
    }
    return true;
}
// opts: nil or a table whose only key is allow_stale_collision (a boolean).
// Unknown keys are refused so a typo cannot fall back to the default.
bool read_opts(lua_State* L, int index, bool& allow, std::string& error) {
    allow = false;
    if (lua_isnoneornil(L, index)) return true;
    if (lua_type(L, index) != LUA_TTABLE) { error = "value: opts must be a table"; return false; }
    lua_pushnil(L);
    while (lua_next(L, index)) {
        bool known = lua_type(L, -2) == LUA_TSTRING && std::strcmp(lua_tostring(L, -2), "allow_stale_collision") == 0;
        if (!known) { lua_pop(L, 2); error = "value: unknown opts key (only allow_stale_collision)"; return false; }
        if (lua_type(L, -1) != LUA_TBOOLEAN) { lua_pop(L, 2); error = "value: allow_stale_collision must be a boolean"; return false; }
        allow = lua_toboolean(L, -1) != 0;
        lua_pop(L, 1);
    }
    return true;
}
int relocate(lua_State* L) {
    int results = 0;
    if (!preflight(L, results)) return results;
    // R3 before argument checks (plan order); the core checks it again.
    if (writer_of(L) != Writer::Loaded || state_token(L) == 0)
        return failure(L, "unsupported: only a loaded script can move placeables");
    const Capture& from = checked(L, 1);
    std::array<float, 3> target{}; bool allow = false; std::string error;
    if (!read_target(L, 2, target, error)) return failure(L, error);
    if (!read_opts(L, 3, allow, error)) return failure(L, error);
    Capture copy = from, out; Status status = Status::Noop;
    if (!operations().relocate(state_token(L), writer_of(L), copy, target, allow, out, status, error))
        return failure(L, error);
    push_capture(L, out);
    if (status == Status::Moved) lua_pushliteral(L, "moved"); else lua_pushliteral(L, "noop");
    return 2;
}
int restore(lua_State* L) {
    int results = 0;
    if (!preflight(L, results)) return results;
    std::uint32_t id = 0;
    if (lua_type(L, 1) == LUA_TUSERDATA) id = checked(L, 1).id;
    else if (!exact_id(L, 1, id)) return failure(L, "value: restore takes a motion capture or an exact uint32 ID");
    Capture out; std::string error;
    if (!operations().restore(state_token(L), writer_of(L), id, out, error)) return failure(L, error);
    push_capture(L, out);
    return 1;
}
int observe(lua_State* L) {
    int results = 0;
    if (!preflight(L, results)) return results;
    const Capture& c = checked(L, 1);
    Observation o; std::string error;
    if (!operations().observe(c.id, c.object, o, error)) return failure(L, error);
    lua_createtable(L, 0, 5);
    lua_pushboolean(L, o.pushed); lua_setfield(L, -2, "pushed");
    lua_pushnumber(L, o.push_gate_raw); lua_setfield(L, -2, "push_gate_raw");
    lua_pushboolean(L, o.dirty_position); lua_setfield(L, -2, "dirty_position");
    if (o.has_tick) { lua_pushnumber(L, static_cast<lua_Number>(o.ticks_since_write)); lua_setfield(L, -2, "ticks_since_write"); }
    lua_pushliteral(L, "unverified"); lua_setfield(L, -2, "client");
    return 1;
}
void string_list(lua_State* L, std::initializer_list<const char*> items) {
    lua_createtable(L, static_cast<int>(items.size()), 0);
    int i = 0;
    for (const char* s : items) { lua_pushstring(L, s); lua_rawseti(L, -2, ++i); }
}
int capabilities(lua_State* L) {
    lua_newtable(L);
    bool available = operations().available();
    lua_pushboolean(L, available); lua_setfield(L, -2, "available");
    const auto* p = operations().profile();
    lua_pushstring(L, p ? p->name : "unsupported"); lua_setfield(L, -2, "profile");
    lua_pushstring(L, p ? "windows-i386-thiscall" : "no verified host binding"); lua_setfield(L, -2, "abi");
    if (available) string_list(L, {"position"}); else lua_createtable(L, 0, 0);
    lua_setfield(L, -2, "writes");
    string_list(L, {"id", "area_id", "position", "orientation", "facing", "push_gate_raw", "dirty_position",
                    "dirty_orientation", "collision_registered", "quaternion_raw", "owned"});
    lua_setfield(L, -2, "reads");
    lua_createtable(L, static_cast<int>(sizeof all_failures / sizeof all_failures[0]), 0);
    int i = 0;
    for (Failure f : all_failures) { lua_pushstring(L, failure_name(f)); lua_rawseti(L, -2, ++i); }
    lua_setfield(L, -2, "refusals");
    lua_pushliteral(L,
        "K1 GOG only; server placeables only. Every call must run on the engine thread from a loaded "
        "script; the console, the harness and a chunk top level may read but not move. "
        "Writes: position only, one engine SetPosition per call, never orientation, never across areas. "
        "Collision: a placeable with a registered walkmesh is refused by default, because a raw move "
        "leaves its walkmesh behind; opts.allow_stale_collision = true opts in and the old spot may "
        "still block while the new one is walk-through. "
        "Bounds (policy): step <= 5.0 m, height change <= 1.0 m, <= 25.0 m from the origin, "
        "|coordinate| <= 1e5. One script owns a moved object until it restores it. "
        "No auto-restore yet: an object moved by a script that unloads or reloads stays moved and "
        "locked until the runtime stops. A save taken while an object is moved keeps the moved pose. "
        "observe is a server-side proxy (the client push was issued); the client position is not read. "
        "push_gate_raw value meaning is unverified. quaternion_raw component order is unverified. "
        "facing is atan2(y,x) in degrees [0,360); its match to GetFacing is unverified. "
        "No live readback yet.");
    lua_setfield(L, -2, "limits");
    return 1;
}
}

void bind_owner_probe(OwnerProbe probe, void* context) {
    g_owner.store(nullptr); g_owner_context.store(context); g_owner.store(probe);
}

std::uint64_t state_token(lua_State* L) {
    lua_pushlightuserdata(L, &token_key);
    lua_rawget(L, LUA_REGISTRYINDEX);
    std::uint64_t token = 0;
    if (lua_type(L, -1) == LUA_TUSERDATA && lua_objlen(L, -1) == sizeof token)
        std::memcpy(&token, lua_touserdata(L, -1), sizeof token);
    lua_pop(L, 1);
    return token;
}

void register_all(lua_State* L) {
    // A fresh owner token per state, from a process-wide counter. The ledger
    // keys on it, never on lua_State*; a hot reload makes a new state and so
    // a new token.
    if (state_token(L) == 0) {
        std::uint64_t token = ++g_next_token;
        lua_pushlightuserdata(L, &token_key);
        std::memcpy(lua_newuserdata(L, sizeof token), &token, sizeof token);
        lua_rawset(L, LUA_REGISTRYINDEX);
    }
    luaL_newmetatable(L, capture_type);
    lua_pushcfunction(L, index); lua_setfield(L, -2, "__index");
    lua_pushcfunction(L, newindex); lua_setfield(L, -2, "__newindex");
    lua_pushliteral(L, "protected motion capture"); lua_setfield(L, -2, "__metatable");
    lua_pop(L, 1);
    lua_getglobal(L, "kp");
    if (!lua_istable(L, -1)) { lua_pop(L, 1); lua_newtable(L); lua_pushvalue(L, -1); lua_setglobal(L, "kp"); }
    lua_newtable(L);
    lua_pushcfunction(L, capabilities); lua_setfield(L, -2, "capabilities");
    lua_pushcfunction(L, capture); lua_setfield(L, -2, "capture");
    lua_pushcfunction(L, relocate); lua_setfield(L, -2, "relocate");
    lua_pushcfunction(L, restore); lua_setfield(L, -2, "restore");
    lua_pushcfunction(L, observe); lua_setfield(L, -2, "observe");
    lua_setfield(L, -2, "motion");
    lua_pop(L, 1);
}
} // namespace kp::api::motion
