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
        int v;
        if (index == 0) {
            v = def->i;
        } else if (p.type == Type::Object) {
            v = int(luaL_checkinteger(L, index));
        } else {
            v = int(luaL_checkinteger(L, index));
        }
        if (p.type == Type::Object) vm.push_object(self, std::uint32_t(v));
        else                        vm.push_int(self, v);
        return;
    }
    case Type::Float: {
        const float v = (index == 0) ? def->x : float(luaL_checknumber(L, index));
        vm.push_float(self, v);
        return;
    }
    case Type::String: {
        const char* v = (index == 0) ? (def->s ? def->s : "") : luaL_checkstring(L, index);
        ExoString s{v, std::uint32_t(std::strlen(v))};
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

    switch (r.returns) {
    case Type::Void:
        return 0;
    case Type::Int: {
        int v = 0;
        if (!vm.pop_int(self, &v)) return 0;
        lua_pushinteger(L, v);
        return 1;
    }
    case Type::Object: {
        std::uint32_t v = 0;
        if (!vm.pop_object(self, &v)) return 0;
        lua_pushinteger(L, lua_Integer(v));
        return 1;
    }
    case Type::Float: {
        float v = 0.0f;
        if (!vm.pop_float(self, &v)) return 0;
        lua_pushnumber(L, v);
        return 1;
    }
    case Type::String: {
        ExoString s{};
        if (!vm.pop_string(self, &s)) return 0;
        // A CExoString can carry a null pointer with a non-zero length after a
        // failed engine call; trusting the length would read from address zero.
        if (s.text == nullptr) lua_pushlstring(L, "", 0);
        else                   lua_pushlstring(L, s.text, s.length);
        // Popping a string allocates; giving it back is optional only in the
        // sense that its absence leaks rather than crashes.
        if (ex.destroy_string) ex.destroy_string(&s);
        return 1;
    }
    case Type::Vector: {
        Vec3 v;
        if (!ex.pop_vector(self, &v)) return 0;
        lua_createtable(L, 0, 3);
        lua_pushnumber(L, v.x); lua_setfield(L, -2, "x");
        lua_pushnumber(L, v.y); lua_setfield(L, -2, "y");
        lua_pushnumber(L, v.z); lua_setfield(L, -2, "z");
        return 1;
    }
    default: break;
    }

    EngineStruct kind;
    if (is_engine_struct(r.returns, kind)) {
        void* h = nullptr;
        if (!ex.pop_engine_structure(self, std::uint32_t(kind), &h) || h == nullptr)
            return 0;
        // What we pop, we own. The handle carries its type so passing an effect
        // where a location is wanted is caught at the next call rather than
        // pushing a wrong type id the VM rejects.
        push_engine_struct(L, kind, h, /*owned=*/true);
        return 1;
    }
    return 0;
}

// ------------------------------------------------------------ dispatch ------

int dispatch(lua_State* L) {
    const auto* r = static_cast<const Routine*>(lua_touserdata(L, lua_upvalueindex(1)));
    return call(L, *r, 1);
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
    const VmBinding& vm = binding();
    if (!vm.usable())
        return luaL_error(L, "%s: the script VM is not bound yet, so no engine "
                             "routine can be called", r.name);

    const int supplied = lua_gettop(L) - first_arg + 1;
    if (supplied < r.required_count)
        return luaL_error(L, "%s expects at least %d argument(s), got %d",
                          r.name, int(r.required_count), supplied < 0 ? 0 : supplied);
    if (supplied > r.param_count)
        return luaL_error(L, "%s takes at most %d argument(s), got %d",
                          r.name, int(r.param_count), supplied);

    // LAST declared parameter first. See the header note; reversing this is
    // invisible for symmetric signatures and silently wrong for the rest.
    for (int i = int(r.param_count) - 1; i >= 0; --i) {
        const int slot = (i < supplied) ? (first_arg + i) : 0;
        push_argument(L, r, std::uint8_t(i), slot);
    }

    const int rc = vm.execute_command(vm.command_implementer, int(r.id),
                                      int(r.param_count));
    if (rc != 0) {
        // The VM's own error codes. -2002 is COMMAND_NOT_FOUND, which on a
        // correct table means the build is not the one we think it is.
        return luaL_error(L, "%s (routine %d) failed: VM error %d",
                          r.name, int(r.id), rc);
    }
    return push_result(L, r);
}

// ------------------------------------------------------------ register ------

// CSWVirtualMachineCommands: vtable +0x00, has_caller +0x04, caller_id +0x08.
// data/hostapi.toml `kp.as` — write, call body, restore (including on error).
int l_as(lua_State* L) {
    const auto id = static_cast<std::uint32_t>(luaL_checkinteger(L, 1));
    luaL_checktype(L, 2, LUA_TFUNCTION);
    const VmBinding& vm = binding();
    if (vm.command_implementer == nullptr)
        return luaL_error(L, "kp.as needs the VM binding");

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
    cmds->has_caller = old_has;
    cmds->caller_id = old_id;
    if (rc != 0) return lua_error(L);
    return lua_gettop(L) - base;
}

void register_all(lua_State* L) {
    // Share one `kotor` table with the other modules rather than replacing it.
    lua_getglobal(L, "kotor");
    if (!lua_istable(L, -1)) {
        lua_pop(L, 1);
        lua_createtable(L, 0, 1024);
        lua_pushvalue(L, -1);
        lua_setglobal(L, "kotor");
    }

    const std::vector<Routine>& t = table();
    for (const auto& r : t) {
        // The Routine lives in a vector that outlives every state, so a light
        // userdata upvalue is safe and costs nothing to push.
        lua_pushlightuserdata(L, const_cast<Routine*>(&r));
        lua_pushcclosure(L, dispatch, 1);
        lua_setfield(L, -2, r.name);
    }
    lua_pop(L, 1);

    // kp.as — specified in data/hostapi.toml; the generator is not in-tree.
    lua_getglobal(L, "kp");
    if (!lua_istable(L, -1)) {
        lua_pop(L, 1);
        lua_newtable(L);
        lua_pushvalue(L, -1);
        lua_setglobal(L, "kp");
    }
    lua_pushcfunction(L, l_as);
    lua_setfield(L, -2, "as");
    lua_pop(L, 1);

    platform::log(platform::LogLevel::Info,
                  "api: registered %zu engine routines as kotor.<Name>", t.size());
}

}  // namespace kp::api
