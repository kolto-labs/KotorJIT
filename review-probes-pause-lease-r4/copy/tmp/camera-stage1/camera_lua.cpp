#include "api/camera.hpp"
#include <cstdio>
#include <new>
#include <string>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
}
namespace kp::api::camera {
namespace {
constexpr const char* capture_type = "kp.camera.capture";
constexpr std::uint64_t capture_magic = 0x4b5043414d455231ULL; // "KPCAMER1"
struct Box { std::uint64_t magic; Capture value; };

const Capture& capture(lua_State* L, int index) {
    if (lua_type(L, index) != LUA_TUSERDATA || lua_objlen(L, index) != sizeof(Box))
        luaL_argerror(L, index, "camera capture allocation required");
    auto* box = static_cast<Box*>(luaL_checkudata(L, index, capture_type));
    if (box->magic != capture_magic) luaL_argerror(L, index, "invalid camera capture magic");
    return box->value;
}
void push_hex(lua_State* L, Address value) {
    char text[24];
    std::snprintf(text, sizeof text, "0x%llx", static_cast<unsigned long long>(value));
    lua_pushstring(L, text);
}
template<std::size_t N> void push_floats(lua_State* L, const std::array<float, N>& values) {
    lua_createtable(L, static_cast<int>(N), 0);
    for (std::size_t i = 0; i < N; ++i) { lua_pushnumber(L, values[i]); lua_rawseti(L, -2, static_cast<int>(i + 1)); }
}
int index(lua_State* L) {
    const Capture& c = capture(L, 1);
    const std::string key = luaL_checkstring(L, 2);
    if (key == "behavior") lua_pushstring(L, c.behavior == Behavior::Chase ? "chase" : "other");
    else if (key == "mode") lua_pushnumber(L, c.mode);
    else if (key == "pending_style") lua_pushnumber(L, c.pending_style);
    else if (key == "module") push_hex(L, c.module);
    else if (key == "camera") push_hex(L, c.camera);
    else if (key == "behavior_ptr") push_hex(L, c.behavior_ptr);
    else if (key == "behavior_vtable") push_hex(L, c.behavior_vtable);
    else if (c.behavior != Behavior::Chase) lua_pushnil(L); // chase fields are never read for other behaviours
    else if (key == "distance") lua_pushnumber(L, c.distance);
    else if (key == "speed") lua_pushnumber(L, c.speed);
    else if (key == "pitch") lua_pushnumber(L, c.pitch);
    else if (key == "height") lua_pushnumber(L, c.height);
    else if (key == "dolly") lua_pushnumber(L, c.dolly);
    else if (key == "base_distance") lua_pushnumber(L, c.base_distance);
    else if (key == "base_view_angle") lua_pushnumber(L, c.base_view_angle);
    else if (key == "style_row") lua_pushnumber(L, c.style_row);
    else if (key == "raw_28_unverified") push_floats(L, c.raw_28);
    else if (key == "raw_38_unverified") push_floats(L, c.raw_38);
    else if (key == "raw_50_unverified") push_floats(L, c.raw_50);
    else lua_pushnil(L);
    return 1;
}
int snapshot(lua_State* L) {
    Capture result; std::string error;
    if (!operations().snapshot(result, error)) {
        lua_pushnil(L); lua_pushlstring(L, error.data(), error.size());
        lua_pushstring(L, failure_name(operations().last_failure()));
        return 3;
    }
    new (lua_newuserdata(L, sizeof(Box))) Box{capture_magic, result};
    luaL_getmetatable(L, capture_type); lua_setmetatable(L, -2);
    return 1;
}
int capabilities(lua_State* L) {
    lua_newtable(L);
    lua_pushboolean(L, operations().available()); lua_setfield(L, -2, "available");
    const Profile* p = operations().profile();
    lua_pushstring(L, p ? p->name : "unsupported"); lua_setfield(L, -2, "profile");
    lua_pushstring(L, p ? model::abi_name(p->abi) : "no verified host binding"); lua_setfield(L, -2, "abi");
    lua_pushboolean(L, 0); lua_setfield(L, -2, "writes");
    lua_pushstring(L, "read-only; K1 GOG only; host-tested with synthetic memory, no live proof yet; "
                      "raw_*_unverified fields have unverified meaning");
    lua_setfield(L, -2, "limits");
    return 1;
}
}
void register_all(lua_State* L) {
    luaL_newmetatable(L, capture_type);
    lua_pushcfunction(L, index); lua_setfield(L, -2, "__index");
    lua_pushliteral(L, "protected camera capture"); lua_setfield(L, -2, "__metatable");
    lua_pop(L, 1);
    lua_getglobal(L, "kp");
    if (!lua_istable(L, -1)) { lua_pop(L, 1); lua_newtable(L); lua_pushvalue(L, -1); lua_setglobal(L, "kp"); }
    lua_newtable(L);
    static const luaL_Reg functions[] = {{"capabilities",capabilities},{"snapshot",snapshot},{nullptr, nullptr}};
    for (const luaL_Reg* r = functions; r->name; ++r) { lua_pushcfunction(L, r->func); lua_setfield(L, -2, r->name); }
    lua_setfield(L, -2, "camera");
    lua_pop(L, 1);
}
} // namespace kp::api::camera
