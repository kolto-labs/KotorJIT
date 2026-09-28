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
};

thread_local DispatchTrace g_trace;

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
        ex.push_vector(self, v.x, v.y, v.z);
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
    return push_result(L, r);
}

// ------------------------------------------------------------ register ------

// CSWVirtualMachineCommands: vtable +0x00, has_caller +0x04, caller_id +0x08.
// data/hostapi.toml `nwscript.with_caller`: write, call body, restore (including on error).
int l_as(lua_State* L) {
    const auto id = static_cast<std::uint32_t>(luaL_checkinteger(L, 1));
    luaL_checktype(L, 2, LUA_TFUNCTION);
    const VmBinding& vm = binding();
    if (!vm_binding_live())
        return luaL_error(L, "nwscript.with_caller needs a live VM context");

    struct Commands {
        void*         vtable;
        std::int32_t  has_caller;
        std::uint32_t caller_id;
    };
    auto* cmds = static_cast<Commands*>(vm.command_implementer);
    const std::int32_t old_has = cmds->has_caller;
    const std::uint32_t old_id = cmds->caller_id;
    cmds->has_caller = 1;
    cmds->caller_id = id;

    const int extras = lua_gettop(L) - 2;
    const int base = lua_gettop(L);
    lua_pushvalue(L, 2);
    for (int i = 0; i < extras; ++i) lua_pushvalue(L, 3 + i);
    const int rc = lua_pcall(L, extras, LUA_MULTRET, 0);
    if (!vm_binding_live() || binding().command_implementer != cmds)
        return luaL_error(L, "nwscript.with_caller: VM context changed before caller restoration");
    cmds->has_caller = old_has;
    cmds->caller_id = old_id;
    if (rc != 0) return lua_error(L);
    return lua_gettop(L) - base;
}

void register_all(lua_State* L) {
    lua_getglobal(L, "nwscript");
    if (!lua_istable(L, -1)) {
        lua_pop(L, 1);
        lua_createtable(L, 0, 3);
        lua_pushvalue(L, -1);
        lua_setglobal(L, "nwscript");
    }
    lua_pushcfunction(L, dispatch);
    lua_setfield(L, -2, "call");
    lua_pushcfunction(L, l_as);
    lua_setfield(L, -2, "with_caller");
    lua_pushcfunction(L, l_last_routine_trace);
    lua_setfield(L, -2, "last_trace");
    lua_pop(L, 1);

    platform::log(platform::LogLevel::Info,
                  "api: registered nwscript.call for %zu engine routines", table().size());
}

}  // namespace kp::api
