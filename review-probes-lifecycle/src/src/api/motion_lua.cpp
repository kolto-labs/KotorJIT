#include "api/motion.hpp"
#include <cmath>
#include <cstdio>
#include <new>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
}
// kp.motion.{capabilities,capture}. Read-only. The capture is a protected
// userdata (size + metatable + magic checked on every access, as in
// model_lua.cpp); fields are copied out on read, so nothing Lua holds can
// alias engine memory. Failures return nil, "<kind>: <reason>".
namespace kp::api::motion {
namespace {
constexpr const char* capture_type = "kp.motion.capture";
constexpr std::uint64_t capture_magic = 0x4b504d4f54494f31ULL; // "KPMOTIO1"
struct Box { std::uint64_t magic; Capture value; };

int failure(lua_State* L, const std::string& error) {
    lua_pushnil(L); lua_pushlstring(L, error.data(), error.size()); return 2;
}
const Capture& checked(lua_State* L, int index) {
    if (lua_type(L, index) != LUA_TUSERDATA || lua_objlen(L, index) != sizeof(Box))
        luaL_argerror(L, index, "motion capture allocation required");
    auto* box = static_cast<Box*>(luaL_checkudata(L, index, capture_type));
    if (box->magic != capture_magic) luaL_argerror(L, index, "invalid motion capture magic");
    return box->value;
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
    if (lua_type(L, 1) != LUA_TNUMBER) return failure(L, "value: server ID must be an exact uint32 number");
    double id = lua_tonumber(L, 1);
    if (!std::isfinite(id) || id < 0 || id > 4294967295. || std::floor(id) != id)
        return failure(L, "value: server ID must be an exact uint32 number");
    Capture result; std::string error;
    if (!operations().capture(static_cast<std::uint32_t>(id), result, error)) return failure(L, error);
    new (lua_newuserdata(L, sizeof(Box))) Box{capture_magic, result};
    luaL_getmetatable(L, capture_type); lua_setmetatable(L, -2);
    return 1;
}
int capabilities(lua_State* L) {
    lua_newtable(L);
    lua_pushboolean(L, operations().available()); lua_setfield(L, -2, "available");
    const auto* p = operations().profile();
    lua_pushstring(L, p ? p->name : "unsupported"); lua_setfield(L, -2, "profile");
    lua_pushstring(L, p ? "windows-i386-thiscall" : "no verified host binding"); lua_setfield(L, -2, "abi");
    lua_pushboolean(L, 0); lua_setfield(L, -2, "writes");
    lua_pushliteral(L, "id area_id position orientation facing push_gate_raw dirty_position "
                       "dirty_orientation collision_registered quaternion_raw");
    lua_setfield(L, -2, "reads");
    lua_pushliteral(L, "K1 GOG only; server placeables only; read-only. push_gate_raw is a client-push gate "
                       "whose value meaning is unverified. quaternion_raw component order is unverified. "
                       "facing is atan2(y,x) in degrees [0,360); its match to GetFacing is unverified. "
                       "No live readback yet.");
    lua_setfield(L, -2, "limits");
    return 1;
}
}
void register_all(lua_State* L) {
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
    lua_setfield(L, -2, "motion");
    lua_pop(L, 1);
}
} // namespace kp::api::motion
