// Exercises kp.vec without a game.
//
// Two halves. The Lua half runs each behaviour as its own named chunk against a
// bare state that has only the standard libraries and kp.vec, so a failure
// names the behaviour rather than the first assert in a long script. The VM
// half binds a fake NWScript VM and pushes kp.vec values through the real
// routine bridge (kp::api::call), which is what proves a kp.vec is still the
// plain {x, y, z} table the bridge has always marshalled.
//
// Usage:
//   kp_vectortest

#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>

#include "api/enginestruct.hpp"
#include "api/routines.hpp"
#include "api/vector.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}

namespace {

unsigned g_failures = 0;
unsigned g_checks = 0;

void check(bool condition, const char* what) {
    ++g_checks;
    std::printf("  %-64s %s\n", what, condition ? "ok" : "FAIL");
    if (!condition) ++g_failures;
}

// Runs one chunk as one named test. The chunk asserts; any Lua error fails the
// test and its message is printed under it.
void run(lua_State* L, const char* name, const char* chunk) {
    const int base = lua_gettop(L);
    bool ok = luaL_loadbuffer(L, chunk, std::strlen(chunk), name) == 0
           && lua_pcall(L, 0, 0, 0) == 0;
    if (!ok) {
        const char* msg = lua_tostring(L, -1);
        std::printf("    %s: %s\n", name, msg != nullptr ? msg : "(no message)");
    }
    lua_settop(L, base);
    check(ok, name);
}

// Shared by the Lua chunks: `raises(substring, fn, ...)` asserts that fn
// raises and that the message mentions `substring`.
const char* kPrelude = R"LUA(
function raises(needle, fn, ...)
    local ok, err = pcall(fn, ...)
    assert(not ok, "expected an error mentioning '" .. needle .. "', got success")
    err = tostring(err)
    assert(err:find(needle, 1, true),
           "expected an error mentioning '" .. needle .. "', got: " .. err)
end
function near(a, b) return math.abs(a - b) < 1e-9 end
function same(v, x, y, z) return near(v.x, x) and near(v.y, y) and near(v.z, z) end
)LUA";

// ------------------------------------------------------------ the Lua half ---

void lua_cases() {
    lua_State* L = luaL_newstate();
    luaL_openlibs(L);
    kp::api::register_vector(L);
    luaL_dostring(L, kPrelude);

    std::printf("\n=== kp.vec (Lua) ===\n");

    run(L, "vec.construct_finite_only", R"LUA(
        assert(type(kp) == "table" and type(kp.vec) == "function", "kp.vec is not bound")
        local v = kp.vec(1, 2.5, -3)
        assert(type(v) == "table", "kp.vec returns a table")
        assert(rawget(v, "x") == 1 and rawget(v, "y") == 2.5 and rawget(v, "z") == -3,
               "coordinates are raw x/y/z fields")
        -- From a table: GetPosition's plain result, or another vec. Always a copy.
        local plain = { x = 4, y = 5, z = 6 }
        local w = kp.vec(plain)
        assert(same(w, 4, 5, 6) and not rawequal(w, plain), "table form copies")
        local c = kp.vec(v)
        assert(same(c, 1, 2.5, -3) and not rawequal(c, v), "vec form copies")
        c.x = 99
        assert(v.x == 1, "a copy is independent of its source")
        -- Finite numbers only, exactly three of them.
        raises("kp.vec", kp.vec)
        raises("kp.vec", kp.vec, 1, 2)
        raises("kp.vec", kp.vec, 1, 2, 3, 4)
        raises("z", kp.vec, 1, 2, "3")
        raises("finite", kp.vec, 1, 2, 0/0)
        raises("finite", kp.vec, math.huge, 2, 3)
        raises("finite", kp.vec, 1, -math.huge, 3)
        raises("z", kp.vec, { x = 1, y = 2 })
        raises("finite", kp.vec, { x = 1, y = 0/0, z = 3 })
        raises("kp.vec", kp.vec, true)
    )LUA");

    run(L, "vec.arith_ops", R"LUA(
        local a, b = kp.vec(1, 2, 3), kp.vec(10, 20, 30)
        assert(same(a + b, 11, 22, 33), "add")
        assert(same(b - a, 9, 18, 27), "sub")
        assert(same(a * 2, 2, 4, 6), "vec * number")
        assert(same(2 * a, 2, 4, 6), "number * vec")
        assert(same(b / 10, 1, 2, 3), "vec / number")
        assert(same(-a, -1, -2, -3), "unary minus")
        assert(same(a + { x = 1, y = 1, z = 1 }, 2, 3, 4), "vec + plain table")
        -- Every result is a fresh vec; operands are never modified.
        local s = a + b
        assert(not rawequal(s, a) and not rawequal(s, b), "fresh result")
        assert(same(a, 1, 2, 3) and same(b, 10, 20, 30), "operands unchanged")
        assert((a + b).length ~= nil, "result carries the vec methods")
        raises("division by zero", function() return a / 0 end)
        raises("number", function() return a * b end)
        raises("number", function() return 2 / a end)
        raises("number", function() return a * "2" end)
        raises("x", function() return a + 1 end)
        raises("finite", function() return a * math.huge end)
    )LUA");

    run(L, "vec.length_normalize_zero", R"LUA(
        local v = kp.vec(3, 4, 0)
        assert(v:length() == 5, "length")
        assert(v:lengthsq() == 25, "lengthsq")
        local n = v:normalize()
        assert(near(n:length(), 1) and same(n, 0.6, 0.8, 0), "normalize")
        assert(same(v, 3, 4, 0), "normalize does not modify its receiver")
        -- Zero has no direction. It normalises to a fresh zero, not NaN.
        local z = kp.vec(0, 0, 0)
        local zn = z:normalize()
        assert(same(zn, 0, 0, 0) and not rawequal(zn, z), "zero normalises to fresh zero")
        assert(z:length() == 0, "zero length")
    )LUA");

    run(L, "vec.dot_cross", R"LUA(
        local x, y = kp.vec(1, 0, 0), kp.vec(0, 1, 0)
        assert(x:dot(y) == 0, "orthogonal dot")
        assert(kp.vec(1, 2, 3):dot(kp.vec(4, 5, 6)) == 32, "dot")
        assert(same(x:cross(y), 0, 0, 1), "x cross y is z")
        assert(same(y:cross(x), 0, 0, -1), "y cross x is -z")
        assert(kp.vec(1, 2, 3):dot({ x = 1, y = 1, z = 1 }) == 6, "dot with plain table")
        raises("x", function() return x:dot(5) end)
    )LUA");

    run(L, "vec.lerp_endpoints", R"LUA(
        local a, b = kp.vec(0, 0, 0), kp.vec(10, -20, 4)
        assert(same(a:lerp(b, 0), 0, 0, 0), "t = 0 is the start")
        assert(same(a:lerp(b, 1), 10, -20, 4), "t = 1 is the end")
        assert(same(a:lerp(b, 0.5), 5, -10, 2), "t = 0.5 is the midpoint")
        assert(not rawequal(a:lerp(b, 0), a), "lerp returns a fresh vec")
        raises("finite", function() return a:lerp(b, 0/0) end)
        raises("number", function() return a:lerp(b) end)
    )LUA");

    run(L, "vec.distance", R"LUA(
        local a, b = kp.vec(1, 1, 1), kp.vec(4, 5, 1)
        assert(a:distance(b) == 5 and b:distance(a) == 5, "distance is symmetric")
        assert(a:distancesq(b) == 25, "distancesq")
        assert(a:distance({ x = 1, y = 1, z = 1 }) == 0, "distance to a plain table")
    )LUA");

    run(L, "vec.equality", R"LUA(
        local a, b = kp.vec(1, 2, 3), kp.vec(1, 2, 3)
        assert(not rawequal(a, b), "two constructions are two tables")
        assert(a == b, "equal coordinates compare equal")
        assert(a ~= kp.vec(1, 2, 3.5), "different coordinates compare unequal")
        -- Lua 5.1 only consults __eq when both sides share it, so a plain
        -- table is never equal to a vec. Documented, not an accident.
        assert(a ~= { x = 1, y = 2, z = 3 }, "a plain table is not equal to a vec")
    )LUA");

    run(L, "vec.metatable_protected", R"LUA(
        local v = kp.vec(1, 2, 3)
        assert(getmetatable(v) == "kp.vec", "getmetatable returns the protection marker")
        raises("protected", setmetatable, v, {})
        assert(debug.getmetatable(v) == debug.getmetatable(kp.vec(0, 0, 0)),
               "every vec shares one metatable")
    )LUA");

    run(L, "vec.mutated_fields_revalidated", R"LUA(
        local v = kp.vec(1, 2, 3)
        v.x = 7                           -- fields are ordinary and writable
        assert(v:length() == math.sqrt(49 + 4 + 9), "a numeric write is honoured")
        v.y = "two"
        raises("y", v.length, v)
        v.y = 2; v.z = 0/0
        raises("finite", v.length, v)
        raises("finite", function() return v + v end)
    )LUA");

    run(L, "vec.tostring_unpack_copy", R"LUA(
        local v = kp.vec(3, 4.5, -1)
        assert(tostring(v) == "vec(3, 4.5, -1)", "tostring: " .. tostring(v))
        local x, y, z = v:unpack()
        assert(x == 3 and y == 4.5 and z == -1, "unpack")
        local c = v:copy()
        assert(c == v and not rawequal(c, v), "copy")
    )LUA");

    // No method or constructor may share a name with an NWScript routine,
    // compared case-insensitively against the catalogue compiled into the
    // bridge.
    {
        const int base = lua_gettop(L);
        luaL_dostring(L, "local t = {'vec'} "
                         "local mt = kp and kp.vec and debug.getmetatable(kp.vec(0,0,0)) "
                         "if mt then for k in pairs(mt.__index) do t[#t+1] = k end end "
                         "return t");
        bool clean = lua_istable(L, -1) && lua_objlen(L, -1) > 1;
        const std::size_t n = lua_istable(L, -1) ? lua_objlen(L, -1) : 0;
        for (std::size_t i = 1; i <= n; ++i) {
            lua_rawgeti(L, -1, int(i));
            std::string name = lua_tostring(L, -1);
            lua_pop(L, 1);
            for (const kp::api::Routine& r : kp::api::table()) {
                std::string rn = r.name;
                if (rn.size() != name.size()) continue;
                bool eq = true;
                for (std::size_t j = 0; j < rn.size(); ++j)
                    if (std::tolower((unsigned char)rn[j]) != std::tolower((unsigned char)name[j]))
                        eq = false;
                if (eq) {
                    std::printf("    '%s' collides with routine %s\n", name.c_str(), r.name);
                    clean = false;
                }
            }
        }
        lua_settop(L, base);
        check(clean && !kp::api::table().empty(), "vec.names_not_routines");
    }

    lua_close(L);
}

// ------------------------------------------------------------- the VM half ---

float g_pushed[3] = {0, 0, 0};
int   g_push_vector_calls = 0;
int   g_execute_id = -1;
float g_pop_value[3] = {1.5f, -2.0f, 7.25f};

int execute(void*, int id, int) { g_execute_id = id; return 0; }
int push_int(void*, int) { return 1; }
int push_float(void*, float) { return 1; }
int push_object(void*, std::uint32_t) { return 1; }
int push_string(void*, const void*) { return 1; }
int pop_int(void*, int* out) { *out = 0; return 1; }
int pop_float(void*, float* out) { *out = 0.0f; return 1; }
int pop_string(void*, void*) { return 0; }

int KP_THISCALL push_vector(void*, float x, float y, float z) {
    ++g_push_vector_calls;
    g_pushed[0] = x; g_pushed[1] = y; g_pushed[2] = z;
    return 1;
}
int KP_THISCALL pop_vector(void*, kp::api::Vec3* out) {
    out->x = g_pop_value[0]; out->y = g_pop_value[1]; out->z = g_pop_value[2];
    return 1;
}

// Local routine literals rather than catalogue ids: the test is about the
// vector boundary, not about which K1 routine happens to take one.
const kp::api::Param kVecParam[] = {{kp::api::Type::Vector, "v", false}};
const kp::api::Routine kTakesVector{30, "VecProbeIn", kp::api::Type::Void, kVecParam, 1, 1};
const kp::api::Routine kGivesVector{31, "VecProbeOut", kp::api::Type::Vector, nullptr, 0, 0};

int call_in(lua_State* L) { return kp::api::call(L, kTakesVector, 1); }
int call_out(lua_State* L) { return kp::api::call(L, kGivesVector, 1); }

void vm_cases() {
    std::printf("\n=== kp.vec through the routine bridge (fake VM) ===\n");

    int fake_vm = 0;
    void* wrapper = &fake_vm;
    void* commands[772];
    for (void*& c : commands) c = reinterpret_cast<void*>(&execute);
    struct Commands {
        void* vtable = nullptr;
        int has_caller = 0;
        std::uint32_t caller_id = 0;
        void* const* table = nullptr;
    } implementer;
    implementer.table = commands;

    kp::api::VmBinding binding;
    binding.command_implementer = &implementer;
    binding.virtual_machine = &wrapper;
    binding.execute_command = execute;
    binding.push_int = push_int;
    binding.push_float = push_float;
    binding.push_object = push_object;
    binding.push_string = push_string;
    binding.pop_int = pop_int;
    binding.pop_float = pop_float;
    binding.pop_string = pop_string;
    kp::api::bind(binding);

    kp::api::VmEngineAccess access;
    access.command_implementer = &implementer;
    access.virtual_machine = &wrapper;
    access.commands = commands;
    access.command_count = 772;
    access.push_vector = push_vector;
    access.pop_vector = pop_vector;
    kp::api::bind_engine_access(access);

    lua_State* L = luaL_newstate();
    luaL_openlibs(L);
    kp::api::register_vector(L);
    lua_pushcfunction(L, call_in);  lua_setglobal(L, "vec_in");
    lua_pushcfunction(L, call_out); lua_setglobal(L, "vec_out");

    // A kp.vec goes in as three floats.
    g_push_vector_calls = 0;
    const bool in_ok = luaL_dostring(L, "vec_in(kp.vec(3, 4, -5))") == 0;
    if (!in_ok) std::printf("    %s\n", lua_tostring(L, -1));
    lua_settop(L, 0);
    check(in_ok && g_push_vector_calls == 1 && g_execute_id == 30
          && g_pushed[0] == 3.0f && g_pushed[1] == 4.0f && g_pushed[2] == -5.0f,
          "vec.plain_table_still_marshals (kp.vec in)");

    // The plain-table path is unchanged.
    g_push_vector_calls = 0;
    const bool plain_ok = luaL_dostring(L, "vec_in({ x = 1, y = 2, z = 3 })") == 0;
    lua_settop(L, 0);
    check(plain_ok && g_push_vector_calls == 1
          && g_pushed[0] == 1.0f && g_pushed[1] == 2.0f && g_pushed[2] == 3.0f,
          "vec.plain_table_still_marshals (plain table in)");

    // A vector result is still a plain table; kp.vec takes it and gives back a
    // value the bridge pushes as the same three floats.
    g_push_vector_calls = 0;
    const bool round_ok = luaL_dostring(L, R"LUA(
        local t = vec_out()
        assert(type(t) == "table" and getmetatable(t) == nil, "result is a plain table")
        local v = kp.vec(t)
        assert(v.x == t.x and v.y == t.y and v.z == t.z, "kp.vec keeps the coordinates")
        vec_in(v)
    )LUA") == 0;
    if (!round_ok) std::printf("    %s\n", lua_tostring(L, -1));
    lua_settop(L, 0);
    check(round_ok && g_push_vector_calls == 1 && g_pushed[0] == g_pop_value[0]
          && g_pushed[1] == g_pop_value[1] && g_pushed[2] == g_pop_value[2],
          "vec.plain_table_still_marshals (round trip)");

    lua_close(L);
    kp::api::bind_engine_access({});
    kp::api::bind({});
}

}  // namespace

int main() {
    lua_cases();
    vm_cases();
    std::printf("\n%u check(s), %u failure(s)\n", g_checks, g_failures);
    return g_failures == 0 ? 0 : 1;
}
