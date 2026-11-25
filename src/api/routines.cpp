// The NWScript engine-routine bridge.
//
// The game dispatches every engine routine through one runtime array of function
// pointers indexed by routine id. Calling one is three steps: push the arguments
// onto the VM's own stack, invoke the dispatcher with the id and an argument
// count, then pop whatever the routine returned. No per-routine hook, no new
// bytecode, and no patched nwscript.nss -- one bridge covers all 769 callable
// routines on KOTOR 1 and 803 on KOTOR 2.
//
// PUSH ORDER IS THE TRAP
// ======================
// The VM stack is a stack. A routine handler pops its FIRST declared parameter
// first, so the bridge pushes the LAST declared parameter first. Get this
// backwards and every symmetric signature still works -- Random(int),
// GetTag(object) -- while everything else silently reads its arguments
// transposed. That failure has no symptom at the call site; it shows up as a
// creature spawning at the wrong coordinates an hour later.
//
// EVERY DECLARED PARAMETER IS PUSHED
// ==================================
// See the long note in enginestruct.hpp. NWScript defaults are a compiler
// feature, and the engine handlers disagree about whether to consult paramCount,
// so the bridge always pushes the full declared count and lets find_default()
// supply what the script omitted.

#include "api/routines.hpp"

#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

#include "api/enginestruct.hpp"
#include "platform/platform.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
}

namespace kp::api {

namespace {

VmBinding g_binding;

// GetFacing is currently the one live routine whose result boundary needs
// diagnosis.  Keep this per-thread and deliberately tiny: it records only the
// bridge calls made by routine 28, never arbitrary VM stack contents.
struct DispatchTrace {
    bool active = false;
    std::uint16_t routine = 0;
    Type returns = Type::Void;
    std::uintptr_t command_implementer = 0;
    std::uintptr_t virtual_machine = 0;
    int execute_status = 0;
    bool execute_called = false;
    bool push_result_entered = false;
    int result_count = -1;
    bool pop_attempted = false;
    int pop_status = 0;
    bool pop_bound = false;
    bool stack_checked = false;
    bool stack_balanced = true;
    std::int32_t sp_before = 0;
    std::int32_t sp_after = 0;
};

struct StackBalanceTrace {
    bool active = false;
    std::uint16_t routine = 0;
    bool checked = false;
    bool balanced = true;
    std::int32_t sp_before = 0;
    std::int32_t sp_after = 0;
};

thread_local DispatchTrace g_trace;
thread_local StackBalanceTrace g_balance;

bool read_vm_stack_pointer(const VmBinding& vm, const VmEngineAccess& ex, std::int32_t& out) {
    if (ex.stack_pointer_offset == 0 || vm.virtual_machine == nullptr) return false;
    const auto* wrapper_ptr = static_cast<const char*>(vm.virtual_machine) + ex.wrapper_internal_offset;
    if (!platform::is_readable(wrapper_ptr, sizeof(void*))) return false;
    const void* internal = *reinterpret_cast<void* const*>(wrapper_ptr);
    if (internal == nullptr) return false;
    const auto* sp_ptr = static_cast<const char*>(internal) + ex.stack_pointer_offset;
    if (!platform::is_readable(sp_ptr, sizeof(std::int32_t))) return false;
    std::memcpy(&out, sp_ptr, sizeof(std::int32_t));
    return true;
}

bool trace_this(const Routine& r) {
    return r.id == 28 && std::strcmp(r.name, "GetFacing") == 0;
}

void begin_trace(const Routine& r, const VmBinding& vm) {
    if (!trace_this(r)) return;
    g_trace = DispatchTrace{};
    g_trace.active = true;
    g_trace.routine = r.id;
    g_trace.returns = r.returns;
    g_trace.command_implementer = reinterpret_cast<std::uintptr_t>(vm.command_implementer);
    g_trace.virtual_machine = reinterpret_cast<std::uintptr_t>(vm.virtual_machine);
}

int traced_result_count(int count) {
    if (g_trace.active) g_trace.result_count = count;
    return count;
}

// Both games' tables are compiled in; selected_game() latches the choice.
namespace k1_table {
using kp::api::Param;
using kp::api::Routine;
using kp::api::Type;
#include "generated/routines_k1.inc"
}
namespace k2_table {
using kp::api::Param;
using kp::api::Routine;
using kp::api::Type;
#include "generated/routines_k2.inc"
}

std::vector<Routine>& mutable_table() {
    static std::vector<Routine> t;
    return t;
}

const char* type_name(Type t) {
    switch (t) {
    case Type::Void:     return "void";
    case Type::Int:      return "int";
    case Type::Float:    return "float";
    case Type::String:   return "string";
    case Type::Object:   return "object";
    case Type::Vector:   return "vector";
    case Type::Effect:   return "effect";
    case Type::Event:    return "event";
    case Type::Location: return "location";
    case Type::Talent:   return "talent";
    }
    return "?";
}

bool is_engine_struct(Type t, EngineStruct& out) {
    switch (t) {
    case Type::Effect:   out = EngineStruct::Effect;   return true;
    case Type::Event:    out = EngineStruct::Event;    return true;
    case Type::Location: out = EngineStruct::Location; return true;
    case Type::Talent:   out = EngineStruct::Talent;   return true;
    default: return false;
    }
}

// ------------------------------------------------------------- pushing ------

// Push one argument. `index` is the Lua stack slot, or 0 meaning "the script
// omitted this one, use the recovered default".
void push_argument(lua_State* L, const Routine& r, std::uint8_t param, int index) {
    const Param& p = r.params[param];
    const VmBinding& vm = binding();
    const VmEngineAccess& ex = engine_access();
    void* self = vm.virtual_machine;

    const ParamDefault* def = (index == 0) ? find_default(r.id, param) : nullptr;
    if (index == 0 && def == nullptr) {
        // The header said this parameter has a default, but the value was a
        // compiler builtin we cannot evaluate -- OBJECT_SELF most of the time,
        // which is the caller and not a constant. Naming it is the whole point:
        // "argument 3 missing" would send someone hunting the wrong thing.
        luaL_error(L, "%s: argument %d (%s %s) has no recoverable default, "
                      "so it must be supplied",
                   r.name, int(param) + 1, type_name(p.type), p.name);
    }

    switch (p.type) {
    case Type::Int:
    case Type::Object: {
        if (index == 0) {
            const int v = def->i;
            if (p.type == Type::Object) vm.push_object(self, std::uint32_t(v));
            else                        vm.push_int(self, v);
            return;
        }
        if (p.type == Type::Object) {
            // Object ids travel as Lua numbers, never lua_Integer: bit 31
            // selects one of the engine's two id spaces, so a character id
            // has the high bit set and would not survive a 32-bit signed
            // round-trip. Same convention as api/entity.cpp's
            // push_object_id/object_id_at.
            const lua_Number n = luaL_checknumber(L, index);
            // !isfinite first: NaN compares false against every relational
            // operator, so a bare `n < 0.0 || n > ...` guard lets NaN through
            // and the uint32_t cast below is undefined behaviour on it. Same
            // fix as lua/value.cpp's Object case for the same bridge.
            if (!std::isfinite(n) || n < 0.0 || n > 4294967295.0) {
                luaL_error(L, "%s: argument %d (%s %s) is not a valid object id",
                           r.name, int(param) + 1, type_name(p.type), p.name);
            }
            vm.push_object(self, std::uint32_t(n));
        } else {
            vm.push_int(self, int(luaL_checkinteger(L, index)));
        }
        return;
    }
    case Type::Float: {
        const float v = (index == 0) ? def->x : float(luaL_checknumber(L, index));
        vm.push_float(self, v);
        return;
    }
    case Type::String: {
        const char* v = (index == 0) ? (def->s ? def->s : "") : luaL_checkstring(L, index);
        ExoString s{v, std::uint32_t(std::strlen(v) + 1)};
        vm.push_string(self, &s);
        return;
    }
    case Type::Vector: {
        Vec3 v;
        if (index == 0) {
            v = Vec3{def->x, def->y, def->z};
        } else {
            // A vector is a table with x, y, z. Accepting three loose numbers
            // instead would make the argument count ambiguous the moment a
            // routine takes two vectors.
            luaL_checktype(L, index, LUA_TTABLE);
            lua_getfield(L, index, "x"); v.x = float(lua_tonumber(L, -1)); lua_pop(L, 1);
            lua_getfield(L, index, "y"); v.y = float(lua_tonumber(L, -1)); lua_pop(L, 1);
            lua_getfield(L, index, "z"); v.z = float(lua_tonumber(L, -1)); lua_pop(L, 1);
        }
        // StackPushVector takes the Vector by value, which under __thiscall is
        // three stacked floats -- see the note in enginestruct.hpp, which cites
        // the thunk's own `ret 0xC`. This is NOT three separate scalar pushes.
        push_vector_value(ex, self, v);
        return;
    }
    default: break;
    }

    EngineStruct kind;
    if (is_engine_struct(p.type, kind)) {
        if (index == 0)
            luaL_error(L, "%s: argument %d (%s %s) cannot be defaulted",
                       r.name, int(param) + 1, type_name(p.type), p.name);
        void* h = check_engine_struct(L, index, kind);
        // The bare id 0..3, not the stack tag. The VM adds the 0x10 itself.
        ex.push_engine_structure(self, std::uint32_t(kind), h);
        return;
    }
    luaL_error(L, "%s: argument %d has type %s, which the bridge cannot push",
               r.name, int(param) + 1, type_name(p.type));
}

// ------------------------------------------------------------- popping ------

int push_result(lua_State* L, const Routine& r) {
    const VmBinding& vm = binding();
    const VmEngineAccess& ex = engine_access();
    void* self = vm.virtual_machine;

    if (g_trace.active) g_trace.push_result_entered = true;

    switch (r.returns) {
    case Type::Void:
        return traced_result_count(0);
    case Type::Int: {
        int v = 0;
        if (!vm.pop_int)
            return luaL_error(L, "%s: expected %s return, VM pop_int failed "
                              "(routine=%u, status=unbound)",
                              r.name, type_name(r.returns), unsigned(r.id));
        const int status = vm.pop_int(self, &v);
        if (!status)
            return luaL_error(L, "%s: expected %s return, VM pop_int failed "
                              "(routine=%u, status=%d)",
                              r.name, type_name(r.returns), unsigned(r.id), status);
        lua_pushinteger(L, v);
        return traced_result_count(1);
    }
    case Type::Object: {
        std::uint32_t v = 0;
        if (!vm.pop_object)
            return luaL_error(L, "%s: expected %s return, VM pop_object failed "
                              "(routine=%u, status=unbound)",
                              r.name, type_name(r.returns), unsigned(r.id));
        const int status = vm.pop_object(self, &v);
        if (!status)
            return luaL_error(L, "%s: expected %s return, VM pop_object failed "
                              "(routine=%u, status=%d)",
                              r.name, type_name(r.returns), unsigned(r.id), status);
        // See push_argument: object ids must travel as Lua numbers, not
        // lua_Integer, or a high-bit id round-trips through Lua as negative.
        lua_pushnumber(L, static_cast<lua_Number>(v));
        return traced_result_count(1);
    }
    case Type::Float: {
        float v = 0.0f;
        if (g_trace.active) g_trace.pop_bound = vm.pop_float != nullptr;
        if (!vm.pop_float)
            return luaL_error(L, "%s: expected %s return, VM pop_float failed "
                              "(routine=%u, status=unbound)",
                              r.name, type_name(r.returns), unsigned(r.id));
        const int status = vm.pop_float(self, &v);
        if (g_trace.active) {
            g_trace.pop_attempted = true;
            g_trace.pop_status = status;
        }
        if (!status)
            // A missing scalar used to return zero Lua values.  Inside a table
            // constructor that silently removed the field (GetFacing exposed
            // this); status and routine id are bounded VM-side diagnostics.
            return luaL_error(L, "%s: expected %s return, VM pop_float failed "
                              "(routine=%u, status=%d)",
                              r.name, type_name(r.returns), unsigned(r.id), status);
        lua_pushnumber(L, v);
        return traced_result_count(1);
    }
    case Type::String: {
        ExoString s{};
        if (!vm.pop_string)
            return luaL_error(L, "%s: expected %s return, VM pop_string failed "
                              "(routine=%u, status=unbound)",
                              r.name, type_name(r.returns), unsigned(r.id));
        const int status = vm.pop_string(self, &s);
        if (!status)
            return luaL_error(L, "%s: expected %s return, VM pop_string failed "
                              "(routine=%u, status=%d)",
                              r.name, type_name(r.returns), unsigned(r.id), status);
        // A CExoString can carry a null pointer with a non-zero length after a
        // failed engine call; trusting the length would read from address zero.
        // Native CExoString stores allocation capacity, including its NUL,
        // not logical content length. Assignment may retain spare capacity.
        std::size_t length = 0;
        if (s.text != nullptr) {
            const char* end = nullptr;
            const auto address = reinterpret_cast<std::uintptr_t>(s.text);
            if (s.length && s.length <= UINTPTR_MAX - address &&
                platform::is_readable(s.text, s.length))
                end = static_cast<const char*>(std::memchr(s.text, '\0', s.length));
            if (!end) {
                // luaL_error longjmps: release the owned pop before raising.
                if (ex.destroy_string) ex.destroy_string(&s);
                return luaL_error(L, "%s: malformed native string return (invalid or unterminated allocation)", r.name);
            }
            length = static_cast<std::size_t>(end - s.text);
        }
        lua_pushlstring(L, s.text ? s.text : "", length);
        // Popping a string allocates; giving it back is optional only in the
        // sense that its absence leaks rather than crashes.
        if (ex.destroy_string) ex.destroy_string(&s);
        return traced_result_count(1);
    }
    case Type::Vector: {
        Vec3 v;
        if (!ex.pop_vector)
            return luaL_error(L, "%s: expected %s return, VM pop_vector failed "
                              "(routine=%u, status=unbound)",
                              r.name, type_name(r.returns), unsigned(r.id));
        const int status = ex.pop_vector(self, &v);
        if (!status)
            return luaL_error(L, "%s: expected %s return, VM pop_vector failed "
                              "(routine=%u, status=%d)",
                              r.name, type_name(r.returns), unsigned(r.id), status);
        lua_createtable(L, 0, 3);
        lua_pushnumber(L, v.x); lua_setfield(L, -2, "x");
        lua_pushnumber(L, v.y); lua_setfield(L, -2, "y");
        lua_pushnumber(L, v.z); lua_setfield(L, -2, "z");
        return traced_result_count(1);
    }
    default: break;
    }

    EngineStruct kind;
    if (is_engine_struct(r.returns, kind)) {
        void* h = nullptr;
        if (!ex.pop_engine_structure)
            return luaL_error(L, "%s: expected %s return, VM pop_engine_structure failed "
                              "(routine=%u, status=unbound)",
                              r.name, type_name(r.returns), unsigned(r.id));
        const int status = ex.pop_engine_structure(self, std::uint32_t(kind), &h);
        if (!status || h == nullptr)
            return luaL_error(L, "%s: expected %s return, VM pop_engine_structure failed "
                              "(routine=%u, status=%d, handle=%s)",
                              r.name, type_name(r.returns), unsigned(r.id), status,
                              h ? "set" : "null");
        // What we pop, we own. The handle carries its type so passing an effect
        // where a location is wanted is caught at the next call rather than
        // pushing a wrong type id the VM rejects.
        push_engine_struct(L, kind, h, /*owned=*/true);
        return traced_result_count(1);
    }
    return traced_result_count(0);
}

// ------------------------------------------------------------ dispatch ------

int dispatch(lua_State* L) {
    const char* name = luaL_checkstring(L, 1);
    const Routine* r = find(name);
    if (r == nullptr) {
        const bool closure = std::strcmp(name, "AssignCommand") == 0
                          || std::strcmp(name, "DelayCommand") == 0
                          || std::strcmp(name, "ActionDoCommand") == 0;
        if (closure)
            return luaL_error(L, "nwscript.call: '%s' takes an NWScript action closure "
                                 "and cannot be called directly from Lua", name);
        return luaL_error(L, "nwscript.call: unknown routine '%s' for the selected game", name);
    }
    return call(L, *r, 2);
}

// Read the last opt-in GetFacing dispatch from the current game thread.  This
// exposes bridge control-flow only; pointers are identities, never dereferenced
// by this diagnostic path.
int l_last_routine_trace(lua_State* L) {
    if (!g_trace.active) {
        lua_pushnil(L);
        return 1;
    }
    lua_createtable(L, 0, 12);
    auto integer = [L](const char* name, lua_Number value) {
        lua_pushnumber(L, value);
        lua_setfield(L, -2, name);
    };
    auto boolean = [L](const char* name, bool value) {
        lua_pushboolean(L, value ? 1 : 0);
        lua_setfield(L, -2, name);
    };
    integer("routine", g_trace.routine);
    lua_pushstring(L, type_name(g_trace.returns));
    lua_setfield(L, -2, "returns");
    integer("command_implementer", static_cast<lua_Number>(g_trace.command_implementer));
    integer("virtual_machine", static_cast<lua_Number>(g_trace.virtual_machine));
    boolean("execute_called", g_trace.execute_called);
    integer("execute_status", g_trace.execute_status);
    boolean("push_result_entered", g_trace.push_result_entered);
    integer("result_count", g_trace.result_count);
    boolean("pop_bound", g_trace.pop_bound);
    boolean("pop_attempted", g_trace.pop_attempted);
    integer("pop_status", g_trace.pop_status);
    boolean("stack_checked", g_trace.stack_checked);
    boolean("stack_balanced", g_trace.stack_balanced);
    integer("sp_before", g_trace.sp_before);
    integer("sp_after", g_trace.sp_after);
    return 1;
}

int l_last_stack_balance(lua_State* L) {
    if (!g_balance.active) {
        lua_pushnil(L);
        return 1;
    }
    lua_createtable(L, 0, 5);
    lua_pushnumber(L, g_balance.routine);
    lua_setfield(L, -2, "routine");
    lua_pushboolean(L, g_balance.checked ? 1 : 0);
    lua_setfield(L, -2, "checked");
    lua_pushboolean(L, g_balance.balanced ? 1 : 0);
    lua_setfield(L, -2, "balanced");
    lua_pushinteger(L, g_balance.sp_before);
    lua_setfield(L, -2, "sp_before");
    lua_pushinteger(L, g_balance.sp_after);
    lua_setfield(L, -2, "sp_after");
    return 1;
}

int l_vm_ready(lua_State* L) {
    lua_pushboolean(L, vm_binding_live() ? 1 : 0);
    return 1;
}

int l_engine_type(lua_State* L) {
    if (lua_gettop(L) < 1 || !lua_isuserdata(L, 1) || !lua_getmetatable(L, 1)) {
        lua_pushnil(L);
        return 1;
    }
    static const struct { const char* mt; const char* name; } kKinds[] = {
        {"kp.effect", "effect"},
        {"kp.event", "event"},
        {"kp.location", "location"},
        {"kp.talent", "talent"},
    };
    for (const auto& k : kKinds) {
        luaL_getmetatable(L, k.mt);
        const bool eq = !lua_isnil(L, -1) && lua_rawequal(L, -1, -2) != 0;
        lua_pop(L, 1);
        if (eq) {
            lua_pop(L, 1);
            lua_pushstring(L, k.name);
            return 1;
        }
    }
    lua_pop(L, 1);
    lua_pushnil(L);
    return 1;
}

int l_routine(lua_State* L) {
    const Routine* r = nullptr;
    if (lua_type(L, 1) == LUA_TNUMBER) {
        const lua_Number raw = lua_tonumber(L, 1);
        if (std::isfinite(raw) && raw >= 0.0 && raw <= 65535.0 && std::floor(raw) == raw) {
            r = find(static_cast<std::uint16_t>(raw));
        }
    } else if (lua_type(L, 1) == LUA_TSTRING) {
        r = find(std::string(lua_tostring(L, 1)));
    } else {
        return luaL_argerror(L, 1, "expected routine name or integer id");
    }
    if (r == nullptr) {
        lua_pushnil(L);
        return 1;
    }

    const VmEngineAccess& ex = engine_access();
    bool needs_vec = r->returns == Type::Vector;
    bool needs_struct = r->returns == Type::Effect || r->returns == Type::Event ||
                        r->returns == Type::Location || r->returns == Type::Talent;
    for (std::uint8_t i = 0; i < r->param_count; ++i) {
        const Type t = r->params[i].type;
        if (t == Type::Vector) needs_vec = true;
        if (t == Type::Effect || t == Type::Event || t == Type::Location || t == Type::Talent)
            needs_struct = true;
    }

    bool callable = true;
    const char* why_not = nullptr;
    if (ex.virtual_machine != nullptr) {
        if (needs_vec && (!ex.push_vector || !ex.pop_vector)) {
            callable = false;
            why_not = "vector marshallers unresolved (vm.stack_push_vector / vm.stack_pop_vector)";
        } else if (needs_struct && (!ex.push_engine_structure || !ex.pop_engine_structure)) {
            callable = false;
            why_not = "engine structure marshallers unresolved (vm.stack_push_engine_structure / vm.stack_pop_engine_structure)";
        } else if (ex.commands != nullptr && !vm_binding_live(r->id)) {
            callable = false;
            why_not = "command slot unavailable on live dispatcher table";
        }
    }

    lua_createtable(L, 0, 7);
    lua_pushinteger(L, r->id);
    lua_setfield(L, -2, "id");
    lua_pushstring(L, r->name);
    lua_setfield(L, -2, "name");
    lua_pushstring(L, type_name(r->returns));
    lua_setfield(L, -2, "returns");
    lua_pushinteger(L, r->required_count);
    lua_setfield(L, -2, "required");
    lua_pushboolean(L, callable ? 1 : 0);
    lua_setfield(L, -2, "callable");
    if (why_not != nullptr) {
        lua_pushstring(L, why_not);
        lua_setfield(L, -2, "why_not");
    }
    lua_createtable(L, r->param_count, 0);
    for (std::uint8_t i = 0; i < r->param_count; ++i) {
        lua_createtable(L, 0, 3);
        lua_pushstring(L, r->params[i].name);
        lua_setfield(L, -2, "name");
        lua_pushstring(L, type_name(r->params[i].type));
        lua_setfield(L, -2, "type");
        lua_pushboolean(L, r->params[i].has_default ? 1 : 0);
        lua_setfield(L, -2, "has_default");
        lua_rawseti(L, -2, int(i) + 1);
    }
    lua_setfield(L, -2, "params");
    return 1;
}

int l_routines(lua_State* L) {
    const auto& tbl = table();
    lua_createtable(L, int(tbl.size()), 0);
    for (std::size_t i = 0; i < tbl.size(); ++i) {
        lua_pushstring(L, tbl[i].name);
        lua_rawseti(L, -2, int(i) + 1);
    }
    return 1;
}

int l_gametime_inner(lua_State* L) {
    const Routine* r_mod = find("GetModule");
    const Routine* r_hr  = find("GetTimeHour");
    const Routine* r_min = find("GetTimeMinute");
    const Routine* r_sec = find("GetTimeSecond");
    const Routine* r_ms  = find("GetTimeMillisecond");
    if (!r_mod || !r_hr || !r_min || !r_sec || !r_ms) {
        lua_pushnil(L);
        return 1;
    }
    const int base = lua_gettop(L);
    if (call(L, *r_mod, base + 1) < 1 || !lua_isnumber(L, -1) ||
        lua_tonumber(L, -1) == 2130706432.0 /* OBJECT_INVALID */) {
        lua_settop(L, base);
        lua_pushnil(L);
        return 1;
    }
    lua_pop(L, 1);

    auto read_int = [&](const Routine* r, int& out) -> bool {
        const int top = lua_gettop(L);
        if (call(L, *r, top + 1) < 1 || !lua_isnumber(L, -1)) {
            lua_settop(L, top);
            return false;
        }
        out = static_cast<int>(lua_tointeger(L, -1));
        lua_settop(L, top);
        return true;
    };
    int hr = 0, min = 0, sec = 0, ms = 0;
    if (!read_int(r_hr, hr) || !read_int(r_min, min) ||
        !read_int(r_sec, sec) || !read_int(r_ms, ms)) {
        lua_pushnil(L);
        return 1;
    }
    lua_createtable(L, 0, 4);
    lua_pushinteger(L, hr);  lua_setfield(L, -2, "hour");
    lua_pushinteger(L, min); lua_setfield(L, -2, "minute");
    lua_pushinteger(L, sec); lua_setfield(L, -2, "second");
    lua_pushinteger(L, ms);  lua_setfield(L, -2, "millisecond");
    return 1;
}

int l_gametime(lua_State* L) {
    if (!vm_binding_live()) {
        lua_pushnil(L);
        return 1;
    }
    lua_pushcfunction(L, l_gametime_inner);
    if (lua_pcall(L, 0, 1, 0) != 0) {
        lua_pop(L, 1);
        lua_pushnil(L);
    }
    return 1;
}

}  // namespace

// --------------------------------------------------------------- table ------

const std::vector<Routine>& table() {
    std::vector<Routine>& t = mutable_table();
    if (t.empty()) {
        if (selected_game() == Game::K1)
            t.assign(std::begin(k1_table::kRoutines), std::end(k1_table::kRoutines));
        else
            t.assign(std::begin(k2_table::kRoutines), std::end(k2_table::kRoutines));
    }
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

void bind(const VmBinding& b) { g_binding = b; }
const VmBinding& binding() { return g_binding; }

// ---------------------------------------------------------------- call ------

int call(lua_State* L, const Routine& r, int first_arg) {
    const VmBinding vm = binding();
    if (!vm_binding_live(r.id))
        return luaL_error(L, "%s: live VM context or command slot is unavailable; "
                             "waiting for a trusted script context", r.name);

    const int supplied = lua_gettop(L) - first_arg + 1;
    if (supplied < r.required_count)
        return luaL_error(L, "%s expects at least %d argument(s), got %d",
                          r.name, int(r.required_count), supplied < 0 ? 0 : supplied);
    if (supplied > r.param_count)
        return luaL_error(L, "%s takes at most %d argument(s), got %d",
                          r.name, int(r.param_count), supplied);

    // Reject unsupported binary strings before ANY native stack mutation.
    // Validation inside the reverse push loop could strand later arguments.
    for (int i = 0; i < int(r.param_count); ++i) {
        if (r.params[i].type != Type::String) continue;
        std::size_t length = 0;
        const char* text = nullptr;
        if (i < supplied) {
            text = luaL_checklstring(L, first_arg + i, &length);
        } else if (const ParamDefault* def = find_default(r.id, std::uint8_t(i))) {
            text = def->s ? def->s : "";
            length = std::strlen(text);
        } else {
            return luaL_error(L, "%s: string argument %d has no recoverable default", r.name, i + 1);
        }
        if (length >= UINT32_MAX || std::memchr(text, '\0', length))
            return luaL_error(L, "%s: string argument %d must fit a native C string without embedded NUL bytes",
                              r.name, i + 1);
    }

    begin_trace(r, vm);

    const VmEngineAccess& ex = engine_access();
    std::int32_t sp_before = 0;
    const bool sp_before_ok = read_vm_stack_pointer(vm, ex, sp_before);

    // LAST declared parameter first. See the header note; reversing this is
    // invisible for symmetric signatures and silently wrong for the rest.
    for (int i = int(r.param_count) - 1; i >= 0; --i) {
        const int slot = (i < supplied) ? (first_arg + i) : 0;
        push_argument(L, r, std::uint8_t(i), slot);
    }

    if (!vm_binding_live(r.id) || binding().command_implementer != vm.command_implementer)
        return luaL_error(L, "%s: VM context changed before dispatch", r.name);
    const int rc = vm.execute_command(vm.command_implementer, int(r.id),
                                      int(r.param_count));
    if (g_trace.active) {
        g_trace.execute_called = true;
        g_trace.execute_status = rc;
    }
    // K1's ExecuteCommandGetLastConversation has a byte-verified inverted
    // status convention: after it successfully pushes its CExoString it
    // returns STACK_PUSH_ERROR (-2000).  Every other handler we bridge uses
    // zero on success, so keep the exception confined to the one routine.
    // Treating -2000 as globally successful would turn genuine stack failures
    // from every other command into corrupt Lua results.
    constexpr int kStackPushError = -2000;
    const bool is_last_conversation = r.id == 711 && r.returns == Type::String;
    const bool success = is_last_conversation ? rc == kStackPushError : rc == 0;
    if (!success) {
        // The VM's own error codes. -2002 is COMMAND_NOT_FOUND, which on a
        // correct table means the build is not the one we think it is.
        return luaL_error(L, "%s (routine %d) failed: VM error %d",
                          r.name, int(r.id), rc);
    }
    const int nres = push_result(L, r);
    std::int32_t sp_after = 0;
    const bool sp_after_ok = sp_before_ok && read_vm_stack_pointer(vm, ex, sp_after);
    const bool checked = sp_before_ok && sp_after_ok;
    const bool balanced = !checked || sp_before == sp_after;
    g_balance = StackBalanceTrace{true, r.id, checked, balanced, sp_before, sp_after};
    if (g_trace.active) {
        g_trace.stack_checked = checked;
        g_trace.stack_balanced = balanced;
        g_trace.sp_before = sp_before;
        g_trace.sp_after = sp_after;
    }
    if (checked && !balanced) {
        platform::log(platform::LogLevel::Warn,
                      "%s (routine %u): VM stack imbalance (sp_before=%d, sp_after=%d)",
                      r.name, unsigned(r.id), int(sp_before), int(sp_after));
    }
    return nres;
}

// ------------------------------------------------------------ register ------

// CSWVirtualMachineCommands: vtable +0x00, has_caller +0x04, caller_id +0x08 on
// i386; has_caller +0x08 and a 64-bit caller_id +0x10 on x86_64 (both Mac
// builds' RunScript store them there; see api/abi_layout.hpp).
// data/hostapi.toml `nwscript.with_caller`: write, call body, restore (including on error).
int l_as(lua_State* L) {
    if (lua_type(L, 1) != LUA_TNUMBER)
        return luaL_argerror(L, 1, "caller id must be an unsigned 32-bit integer");
    const lua_Number raw_id = lua_tonumber(L, 1);
    if (!std::isfinite(raw_id) || raw_id < 0.0 || raw_id > 4294967295.0 ||
        std::floor(raw_id) != raw_id) {
        return luaL_argerror(L, 1, "caller id must be in 0..4294967295");
    }
    const auto id = static_cast<std::uint32_t>(raw_id);
    luaL_checktype(L, 2, LUA_TFUNCTION);
    const VmBinding& vm = binding();
    if (!vm_binding_live())
        return luaL_error(L, "nwscript.with_caller needs a live VM context");

    auto* cmds = static_cast<char*>(vm.command_implementer);
    auto* has_caller = reinterpret_cast<std::int32_t*>(cmds + layout::kEngine.commands_has_caller);
    auto* caller_id = reinterpret_cast<abi::ObjectId*>(cmds + layout::kEngine.commands_caller_id);
    const std::int32_t old_has = *has_caller;
    const abi::ObjectId old_id = *caller_id;
    *has_caller = 1;
    *caller_id = abi::ObjectId(id);

    const int extras = lua_gettop(L) - 2;
    const int base = lua_gettop(L);
    lua_pushvalue(L, 2);
    for (int i = 0; i < extras; ++i) lua_pushvalue(L, 3 + i);
    const int rc = lua_pcall(L, extras, LUA_MULTRET, 0);
    if (!vm_binding_live() || binding().command_implementer != cmds)
        return luaL_error(L, "nwscript.with_caller: VM context changed before caller restoration");
    *has_caller = old_has;
    *caller_id = old_id;
    if (rc != 0) return lua_error(L);
    return lua_gettop(L) - base;
}

void register_all(lua_State* L) {
    lua_getglobal(L, "nwscript");
    if (!lua_istable(L, -1)) {
        lua_pop(L, 1);
        lua_createtable(L, 0, 4);
        lua_pushvalue(L, -1);
        lua_setglobal(L, "nwscript");
    }
    lua_pushcfunction(L, dispatch);
    lua_setfield(L, -2, "call");
    lua_pushcfunction(L, l_as);
    lua_setfield(L, -2, "with_caller");
    lua_pushcfunction(L, l_last_routine_trace);
    lua_setfield(L, -2, "last_trace");
    lua_pushcfunction(L, l_last_stack_balance);
    lua_setfield(L, -2, "last_stack_balance");
    lua_pop(L, 1);

    platform::log(platform::LogLevel::Info,
                  "api: registered nwscript.call for %zu engine routines", table().size());
}

void register_kp_routines(lua_State* L) {
    lua_getglobal(L, "kp");
    if (!lua_istable(L, -1)) {
        lua_pop(L, 1);
        lua_createtable(L, 0, 5);
        lua_pushvalue(L, -1);
        lua_setglobal(L, "kp");
    }
    lua_pushcfunction(L, l_vm_ready);    lua_setfield(L, -2, "vm_ready");
    lua_pushcfunction(L, l_routine);     lua_setfield(L, -2, "routine");
    lua_pushcfunction(L, l_routines);    lua_setfield(L, -2, "routines");
    lua_pushcfunction(L, l_engine_type); lua_setfield(L, -2, "engine_type");
    lua_pushcfunction(L, l_gametime);    lua_setfield(L, -2, "gametime");
    lua_pop(L, 1);
}

}  // namespace kp::api
