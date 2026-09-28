#include "api/vector.hpp"

#include <cmath>
#include <cstdio>

#include "api/output.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
}

namespace kp::api {

namespace {

// Registry key of the shared metatable. luaL_newmetatable's string key, so the
// same name finds it from every function in this file.
const char kMeta[] = "kp.vec.meta";

// What getmetatable(v) returns. A string, so the answer is informative and the
// table itself is out of a script's reach.
const char kProtect[] = "kp.vec";

struct V3 {
    lua_Number x, y, z;
};

const char* const kAxis[3] = {"x", "y", "z"};

// Read one coordinate. `who` names the operation and `what` the operand, so a
// bad field reads "kp.vec:dot: other.y must be a finite number (got string)".
lua_Number read_axis(lua_State* L, int idx, int axis, const char* who, const char* what) {
    lua_getfield(L, idx, kAxis[axis]);
    const int t = lua_type(L, -1);
    if (t != LUA_TNUMBER) {
        luaL_error(L, "%s: %s%s%s must be a finite number (got %s)", who,
                   what, *what ? "." : "", kAxis[axis], lua_typename(L, t));
    }
    const lua_Number n = lua_tonumber(L, -1);
    lua_pop(L, 1);
    if (!std::isfinite(n)) {
        luaL_error(L, "%s: %s%s%s must be a finite number (got %s)", who,
                   what, *what ? "." : "", kAxis[axis], std::isnan(n) ? "nan" : "inf");
    }
    return n;
}

// Any table with finite numeric x, y, z: a vec, or a routine's plain result.
V3 read_vec(lua_State* L, int idx, const char* who, const char* what) {
    if (lua_type(L, idx) != LUA_TTABLE) {
        luaL_error(L, "%s: %s must be a vec or a table with x, y, z (got %s)",
                   who, what, luaL_typename(L, idx));
    }
    V3 v;
    v.x = read_axis(L, idx, 0, who, what);
    v.y = read_axis(L, idx, 1, who, what);
    v.z = read_axis(L, idx, 2, who, what);
    return v;
}

lua_Number read_scalar(lua_State* L, int idx, const char* who, const char* what) {
    if (lua_type(L, idx) != LUA_TNUMBER) {
        luaL_error(L, "%s: %s must be a finite number (got %s)", who, what,
                   luaL_typename(L, idx));
    }
    const lua_Number n = lua_tonumber(L, idx);
    if (!std::isfinite(n))
        luaL_error(L, "%s: %s must be a finite number (got %s)", who, what,
                   std::isnan(n) ? "nan" : "inf");
    return n;
}

// A fresh vec. The result is checked too: finite inputs can still overflow.
int push_vec(lua_State* L, const V3& v, const char* who) {
    if (!std::isfinite(v.x) || !std::isfinite(v.y) || !std::isfinite(v.z))
        return luaL_error(L, "%s: result is not finite", who);
    lua_createtable(L, 0, 3);
    lua_pushnumber(L, v.x); lua_setfield(L, -2, "x");
    lua_pushnumber(L, v.y); lua_setfield(L, -2, "y");
    lua_pushnumber(L, v.z); lua_setfield(L, -2, "z");
    luaL_getmetatable(L, kMeta);
    lua_setmetatable(L, -2);
    return 1;
}

// A scalar result, checked the same way. 1e155 is a finite coordinate whose
// square is not, so length, dot and distance can overflow from good inputs.
//
// Both helpers round through a volatile double. The 32-bit build does its
// floating point on the x87, whose 80-bit registers hold 1e310 comfortably:
// without the store, the check can pass on a value that becomes inf the
// moment it lands in a Lua number, and length() of the same vector would
// answer differently depending on what the optimiser kept in a register.
int push_scalar(lua_State* L, lua_Number n, const char* who) {
    const volatile lua_Number stored = n;
    const lua_Number r = stored;
    if (!std::isfinite(r)) return luaL_error(L, "%s: result is not finite", who);
    lua_pushnumber(L, r);
    return 1;
}

lua_Number dot(const V3& a, const V3& b) {
    const volatile lua_Number r = a.x * b.x + a.y * b.y + a.z * b.z;
    return r;
}

// ---------------------------------------------------------- constructor ---

int l_vec(lua_State* L) {
    const int argc = lua_gettop(L);
    if (argc == 1 && lua_type(L, 1) == LUA_TTABLE)
        return push_vec(L, read_vec(L, 1, "kp.vec", ""), "kp.vec");
    if (argc == 3) {
        V3 v;
        lua_Number* out[3] = {&v.x, &v.y, &v.z};
        for (int i = 0; i < 3; ++i) *out[i] = read_scalar(L, i + 1, "kp.vec", kAxis[i]);
        return push_vec(L, v, "kp.vec");
    }
    if (argc == 1)
        return luaL_error(L, "kp.vec expects 3 numbers or one table with x, y, z (got %s)",
                          luaL_typename(L, 1));
    return luaL_error(L, "kp.vec expects 3 numbers or one table with x, y, z (got %d arguments)",
                      argc);
}

// ------------------------------------------------------------ operators ---

int m_add(lua_State* L) {
    const V3 a = read_vec(L, 1, "kp.vec +", "left operand");
    const V3 b = read_vec(L, 2, "kp.vec +", "right operand");
    return push_vec(L, {a.x + b.x, a.y + b.y, a.z + b.z}, "kp.vec +");
}

int m_sub(lua_State* L) {
    const V3 a = read_vec(L, 1, "kp.vec -", "left operand");
    const V3 b = read_vec(L, 2, "kp.vec -", "right operand");
    return push_vec(L, {a.x - b.x, a.y - b.y, a.z - b.z}, "kp.vec -");
}

// vec * number or number * vec. vec * vec has two reasonable meanings (dot,
// cross) and neither is the obvious one, so it is an error.
int m_mul(lua_State* L) {
    const bool left_vec = lua_type(L, 1) == LUA_TTABLE;
    const bool right_vec = lua_type(L, 2) == LUA_TTABLE;
    if (left_vec == right_vec)
        return luaL_error(L, "kp.vec *: expects a vec and a number (got %s and %s); "
                             "use dot or cross for two vecs",
                          luaL_typename(L, 1), luaL_typename(L, 2));
    const int vi = left_vec ? 1 : 2;
    const V3 v = read_vec(L, vi, "kp.vec *", "vec operand");
    const lua_Number k = read_scalar(L, 3 - vi, "kp.vec *", "number operand");
    return push_vec(L, {v.x * k, v.y * k, v.z * k}, "kp.vec *");
}

int m_div(lua_State* L) {
    if (lua_type(L, 1) != LUA_TTABLE)
        return luaL_error(L, "kp.vec /: only vec / number is defined (got %s / vec)",
                          luaL_typename(L, 1));
    const V3 v = read_vec(L, 1, "kp.vec /", "vec operand");
    const lua_Number k = read_scalar(L, 2, "kp.vec /", "number operand");
    if (k == 0) return luaL_error(L, "kp.vec /: division by zero");
    return push_vec(L, {v.x / k, v.y / k, v.z / k}, "kp.vec /");
}

int m_unm(lua_State* L) {
    const V3 v = read_vec(L, 1, "kp.vec unary -", "operand");
    return push_vec(L, {-v.x, -v.y, -v.z}, "kp.vec unary -");
}

// Exact, and never raises: == on a vec whose fields were overwritten with
// junk answers false rather than throwing out of a comparison.
int m_eq(lua_State* L) {
    bool eq = true;
    for (int i = 0; i < 3 && eq; ++i) {
        lua_getfield(L, 1, kAxis[i]);
        lua_getfield(L, 2, kAxis[i]);
        eq = lua_type(L, -1) == LUA_TNUMBER && lua_type(L, -2) == LUA_TNUMBER
          && lua_tonumber(L, -1) == lua_tonumber(L, -2);
        lua_pop(L, 2);
    }
    lua_pushboolean(L, eq);
    return 1;
}

int m_tostring(lua_State* L) {
    char buf[3][32];
    for (int i = 0; i < 3; ++i) {
        lua_getfield(L, 1, kAxis[i]);
        if (lua_type(L, -1) == LUA_TNUMBER)
            std::snprintf(buf[i], sizeof buf[i], "%.14g", double(lua_tonumber(L, -1)));
        else
            std::snprintf(buf[i], sizeof buf[i], "<%s>", luaL_typename(L, -1));
        lua_pop(L, 1);
    }
    lua_pushfstring(L, "vec(%s, %s, %s)", buf[0], buf[1], buf[2]);
    return 1;
}

// -------------------------------------------------------------- methods ---

V3 self(lua_State* L, const char* who) {
    if (lua_type(L, 1) != LUA_TTABLE)
        luaL_error(L, "%s: call it as a method, v:%s(...) (got %s for self)", who,
                   who + sizeof("kp.vec:") - 1, luaL_typename(L, 1));
    return read_vec(L, 1, who, "self");
}

int m_length(lua_State* L) {
    const V3 v = self(L, "kp.vec:length");
    return push_scalar(L, std::sqrt(dot(v, v)), "kp.vec:length");
}

int m_lengthsq(lua_State* L) {
    const V3 v = self(L, "kp.vec:lengthsq");
    return push_scalar(L, dot(v, v), "kp.vec:lengthsq");
}

int m_normalize(lua_State* L) {
    const V3 v = self(L, "kp.vec:normalize");
    const lua_Number len = std::sqrt(dot(v, v));
    // An overflowed length would divide every axis to zero, and an underflowed
    // one would read as the zero vector. Both raise; only a true zero vector
    // normalises to zero.
    if (!std::isfinite(len))
        return luaL_error(L, "kp.vec:normalize: length is not finite");
    if (len == 0) {
        if (v.x != 0 || v.y != 0 || v.z != 0)
            return luaL_error(L, "kp.vec:normalize: length underflows to zero");
        return push_vec(L, {0, 0, 0}, "kp.vec:normalize");
    }
    return push_vec(L, {v.x / len, v.y / len, v.z / len}, "kp.vec:normalize");
}

int m_dot(lua_State* L) {
    const V3 a = self(L, "kp.vec:dot");
    const V3 b = read_vec(L, 2, "kp.vec:dot", "other");
    return push_scalar(L, dot(a, b), "kp.vec:dot");
}

int m_cross(lua_State* L) {
    const V3 a = self(L, "kp.vec:cross");
    const V3 b = read_vec(L, 2, "kp.vec:cross", "other");
    return push_vec(L, {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x},
                    "kp.vec:cross");
}

int m_distancesq(lua_State* L) {
    const V3 a = self(L, "kp.vec:distancesq");
    const V3 b = read_vec(L, 2, "kp.vec:distancesq", "other");
    const V3 d{a.x - b.x, a.y - b.y, a.z - b.z};
    return push_scalar(L, dot(d, d), "kp.vec:distancesq");
}

int m_distance(lua_State* L) {
    const V3 a = self(L, "kp.vec:distance");
    const V3 b = read_vec(L, 2, "kp.vec:distance", "other");
    const V3 d{a.x - b.x, a.y - b.y, a.z - b.z};
    return push_scalar(L, std::sqrt(dot(d, d)), "kp.vec:distance");
}

// a + (b - a) * t, written so t = 0 and t = 1 return the endpoints exactly.
int m_lerp(lua_State* L) {
    const V3 a = self(L, "kp.vec:lerp");
    const V3 b = read_vec(L, 2, "kp.vec:lerp", "other");
    const lua_Number t = read_scalar(L, 3, "kp.vec:lerp", "t");
    const lua_Number s = 1 - t;
    return push_vec(L, {a.x * s + b.x * t, a.y * s + b.y * t, a.z * s + b.z * t},
                    "kp.vec:lerp");
}

int m_copy(lua_State* L) {
    return push_vec(L, self(L, "kp.vec:copy"), "kp.vec:copy");
}

int m_unpack(lua_State* L) {
    const V3 v = self(L, "kp.vec:unpack");
    lua_pushnumber(L, v.x);
    lua_pushnumber(L, v.y);
    lua_pushnumber(L, v.z);
    return 3;
}

const luaL_Reg kMethods[] = {
    {"length",     m_length},
    {"lengthsq",   m_lengthsq},
    {"normalize",  m_normalize},
    {"dot",        m_dot},
    {"cross",      m_cross},
    {"distance",   m_distance},
    {"distancesq", m_distancesq},
    {"lerp",       m_lerp},
    {"copy",       m_copy},
    {"unpack",     m_unpack},
    {nullptr, nullptr},
};

const luaL_Reg kOperators[] = {
    {"__add",      m_add},
    {"__sub",      m_sub},
    {"__mul",      m_mul},
    {"__div",      m_div},
    {"__unm",      m_unm},
    {"__eq",       m_eq},
    {"__tostring", m_tostring},
    {nullptr, nullptr},
};

}  // namespace

void register_vector(lua_State* L) {
    // Once per state. A second call (the runtime and the console both calling
    // a shared initialiser) reuses the metatable rather than splitting vecs
    // made before and after it into two incompatible kinds.
    if (luaL_newmetatable(L, kMeta)) {
        luaL_register(L, nullptr, kOperators);
        lua_createtable(L, 0, int(sizeof kMethods / sizeof kMethods[0]) - 1);
        luaL_register(L, nullptr, kMethods);
        lua_setfield(L, -2, "__index");
        lua_pushstring(L, kProtect);
        lua_setfield(L, -2, "__metatable");
    }
    lua_pop(L, 1);

    push_kp_table(L);
    lua_pushcfunction(L, l_vec);
    lua_setfield(L, -2, "vec");
    lua_pop(L, 1);
}

}  // namespace kp::api
