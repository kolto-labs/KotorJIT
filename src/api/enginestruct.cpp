// Engine-structure handles, the accessors VmBinding does not carry, and the one
// place raw __thiscall addresses become the plain pointers VmBinding declares.
#include "api/enginestruct.hpp"

#include <cstring>

#include "platform/platform.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
}

namespace kp::api {

namespace {

VmEngineAccess g_access;

// --------------------------------------------------------------- the shims --
//
// VmBinding's members are declared without a calling-convention attribute, so
// they are cdecl. The VM's methods are __thiscall. These nine functions are the
// whole of the conversion: each holds the real method pointer in a file-scope
// variable and forwards.
//
// File-scope rather than per-binding because there is exactly one VM in the
// process. The game creates CVirtualMachine once; a second one would need a
// second set of shims, and nothing in the engine makes one.
hooks::ThiscallFn<int, int, int>            g_execute_command = nullptr;
hooks::ThiscallFn<int, int>                 g_push_int    = nullptr;
hooks::ThiscallFn<int, float>               g_push_float  = nullptr;
hooks::ThiscallFn<int, const void*>         g_push_string = nullptr;
hooks::ThiscallFn<int, std::uint32_t>       g_push_object = nullptr;
hooks::ThiscallFn<int, int*>                g_pop_int     = nullptr;
hooks::ThiscallFn<int, float*>              g_pop_float   = nullptr;
hooks::ThiscallFn<int, void*>               g_pop_string  = nullptr;
hooks::ThiscallFn<int, std::uint32_t*>      g_pop_object  = nullptr;

int shim_execute(void* self, int id, int argc) { return g_execute_command(self, id, argc); }
int shim_push_int(void* vm, int v)             { return g_push_int(vm, v); }
int shim_push_float(void* vm, float v)         { return g_push_float(vm, v); }
int shim_push_string(void* vm, const void* s)  { return g_push_string(vm, s); }
int shim_push_object(void* vm, std::uint32_t v){ return g_push_object(vm, v); }
int shim_pop_int(void* vm, int* out)           { return g_pop_int(vm, out); }
int shim_pop_float(void* vm, float* out)       { return g_pop_float(vm, out); }
int shim_pop_string(void* vm, void* out)       { return g_pop_string(vm, out); }
int shim_pop_object(void* vm, std::uint32_t* o){ return g_pop_object(vm, o); }

// ------------------------------------------------------------ the handles --

struct Handle {
    EngineStruct type;
    void*        ptr;
    bool         owned;
};

unsigned g_live = 0;
bool     g_warned_no_destructor = false;

const char* metatable_name(EngineStruct t) {
    switch (t) {
    case EngineStruct::Effect:   return "kp.effect";
    case EngineStruct::Event:    return "kp.event";
    case EngineStruct::Location: return "kp.location";
    case EngineStruct::Talent:   return "kp.talent";
    }
    return "kp.unknown";
}

int handle_gc(lua_State* L) {
    auto* h = static_cast<Handle*>(lua_touserdata(L, 1));
    if (!h || !h->ptr) return 0;
    if (h->owned) {
        const auto& a = engine_access();
        if (a.destroy_engine_structure && a.command_implementer) {
            a.destroy_engine_structure(a.command_implementer,
                                       static_cast<std::uint32_t>(h->type),
                                       h->ptr);
        } else if (!g_warned_no_destructor) {
            // Once, not per handle. A script in a loop would otherwise fill the
            // log with the same line and hide everything else.
            g_warned_no_destructor = true;
            platform::log(platform::LogLevel::Warn,
                          "engine structures are leaking: no destructor is "
                          "bound (site vmcmd.destroy_game_defined_structure)");
        }
    }
    h->ptr = nullptr;
    if (g_live) --g_live;
    return 0;
}

int handle_tostring(lua_State* L) {
    auto* h = static_cast<Handle*>(lua_touserdata(L, 1));
    lua_pushfstring(L, "%s: %p", metatable_name(h->type), h->ptr);
    return 1;
}

}  // namespace

// ------------------------------------------------------------- binding -----

void bind_engine_access(const VmEngineAccess& a) { g_access = a; }
const VmEngineAccess& engine_access() { return g_access; }

bool bind_sites(const VmSites& s, std::string& error) {
    auto need = [&](std::uintptr_t v, const char* name) {
        if (!v && error.empty()) error = std::string("unresolved site: ") + name;
        return v != 0;
    };

    // Every site is checked, not just up to the first miss, so `error` names
    // the first one and a reader of the log sees whether it was one site or all
    // of them.
    bool ok = true;
    ok = need(s.execute_command,    "vm.execute_command")    && ok;
    ok = need(s.stack_push_integer, "vm.stack_push_integer") && ok;
    ok = need(s.stack_pop_integer,  "vm.stack_pop_integer")  && ok;
    ok = need(s.stack_push_float,   "vm.stack_push_float")   && ok;
    ok = need(s.stack_pop_float,    "vm.stack_pop_float")    && ok;
    ok = need(s.stack_push_string,  "vm.stack_push_string")  && ok;
    ok = need(s.stack_pop_string,   "vm.stack_pop_string")   && ok;
    ok = need(s.stack_push_object,  "vm.stack_push_object")  && ok;
    ok = need(s.stack_pop_object,   "vm.stack_pop_object")   && ok;
    if (!ok) return false;
    if (!s.command_implementer || !s.virtual_machine) {
        error = "the VM objects are null; resolve them before binding";
        return false;
    }

    // Casting an integer address to a function pointer is the whole job of this
    // function, and it happens here and nowhere else.
    auto fn = [](std::uintptr_t a) { return reinterpret_cast<void*>(a); };

    g_execute_command = reinterpret_cast<decltype(g_execute_command)>(fn(s.execute_command));
    g_push_int    = reinterpret_cast<decltype(g_push_int)>(fn(s.stack_push_integer));
    g_pop_int     = reinterpret_cast<decltype(g_pop_int)>(fn(s.stack_pop_integer));
    g_push_float  = reinterpret_cast<decltype(g_push_float)>(fn(s.stack_push_float));
    g_pop_float   = reinterpret_cast<decltype(g_pop_float)>(fn(s.stack_pop_float));
    g_push_string = reinterpret_cast<decltype(g_push_string)>(fn(s.stack_push_string));
    g_pop_string  = reinterpret_cast<decltype(g_pop_string)>(fn(s.stack_pop_string));
    g_push_object = reinterpret_cast<decltype(g_push_object)>(fn(s.stack_push_object));
    g_pop_object  = reinterpret_cast<decltype(g_pop_object)>(fn(s.stack_pop_object));

    VmBinding b;
    b.command_implementer = s.command_implementer;
    b.virtual_machine     = s.virtual_machine;
    b.execute_command     = shim_execute;
    b.push_int    = shim_push_int;
    b.push_float  = shim_push_float;
    b.push_string = shim_push_string;
    b.push_object = shim_push_object;
    b.pop_int     = shim_pop_int;
    b.pop_float   = shim_pop_float;
    b.pop_string  = shim_pop_string;
    b.pop_object  = shim_pop_object;
    bind(b);

    VmEngineAccess a;
    a.virtual_machine     = s.virtual_machine;
    a.command_implementer = s.command_implementer;
    a.push_vector = reinterpret_cast<decltype(a.push_vector)>(fn(s.stack_push_vector));
    a.pop_vector  = reinterpret_cast<decltype(a.pop_vector)>(fn(s.stack_pop_vector));
    a.push_engine_structure =
        reinterpret_cast<decltype(a.push_engine_structure)>(fn(s.stack_push_engine_structure));
    a.pop_engine_structure =
        reinterpret_cast<decltype(a.pop_engine_structure)>(fn(s.stack_pop_engine_structure));
    a.destroy_engine_structure =
        reinterpret_cast<decltype(a.destroy_engine_structure)>(fn(s.destroy_game_defined_structure));
    a.destroy_string =
        reinterpret_cast<decltype(a.destroy_string)>(fn(s.exostring_dtor));

    // The command array. Reading it is a dereference of an address that came
    // out of a data file, so it is probed first: a wrong build must refuse the
    // read rather than fault inside the refusal path.
    const auto base = reinterpret_cast<std::uintptr_t>(s.command_implementer);
    const void* slot = reinterpret_cast<const void*>(base + s.commands_offset);
    if (platform::is_readable(slot, sizeof(void*))) {
        void* const* table = *reinterpret_cast<void* const* const*>(slot);
        if (table && platform::is_readable(table, sizeof(void*) * s.commands_count)) {
            a.commands = table;
            a.command_count = s.commands_count;
        }
    }
    if (!a.commands) {
        platform::log(platform::LogLevel::Warn,
                      "the routine command array is not readable at +0x%x; "
                      "unimplemented routines will report a VM error instead of "
                      "a script error", s.commands_offset);
    }

    bind_engine_access(a);
    return true;
}

// ------------------------------------------------------------- handles -----

void open_engine_structs(lua_State* L) {
    const EngineStruct kinds[] = {EngineStruct::Effect, EngineStruct::Event,
                                  EngineStruct::Location, EngineStruct::Talent};
    for (EngineStruct k : kinds) {
        if (luaL_newmetatable(L, metatable_name(k))) {
            lua_pushcfunction(L, handle_gc);
            lua_setfield(L, -2, "__gc");
            lua_pushcfunction(L, handle_tostring);
            lua_setfield(L, -2, "__tostring");
            // No __index: there is nothing to read. The engine hands us a
            // pointer and no layout, so a field accessor would have to invent
            // offsets, and an invented offset is a wrong answer rather than an
            // error.
            lua_pushboolean(L, 0);
            lua_setfield(L, -2, "__metatable");
        }
        lua_pop(L, 1);
    }
}

void push_engine_struct(lua_State* L, EngineStruct type, void* handle, bool owned) {
    auto* h = static_cast<Handle*>(lua_newuserdata(L, sizeof(Handle)));
    h->type  = type;
    h->ptr   = handle;
    h->owned = owned;
    luaL_getmetatable(L, metatable_name(type));
    if (lua_isnil(L, -1)) {
        // register_all opens the metatables, so this only happens if someone
        // pushed a handle into a state the bridge was never registered on.
        lua_pop(L, 1);
        open_engine_structs(L);
        luaL_getmetatable(L, metatable_name(type));
    }
    lua_setmetatable(L, -2);
    ++g_live;
}

void* check_engine_struct(lua_State* L, int index, EngineStruct type) {
    auto* h = static_cast<Handle*>(luaL_checkudata(L, index, metatable_name(type)));
    if (!h->ptr) {
        luaL_argerror(L, index, "this handle has already been released");
    }
    return h->ptr;
}

unsigned live_engine_structs() { return g_live; }

// ------------------------------------------------------ default parameters --

namespace {

// Both games' default tables are compiled in, because one binary serves both.
// The arrays are generated from each game's own nwscript.nss.
namespace k1_defaults {
#include "generated/routine_defaults_k1.inc"
}
namespace k2_defaults {
#include "generated/routine_defaults_k2.inc"
}

Game     g_game = Game::K1;
bool     g_game_latched = false;

}  // namespace

bool select_game(Game g) {
    // Latched on first use. table() hands out const Routine* that become Lua
    // upvalues, so swapping tables afterwards would leave live closures pointing
    // into the wrong game's array -- a wrong routine id silently called.
    if (g_game_latched && g != g_game) {
        platform::log(platform::LogLevel::Warn,
                      "api: refusing to switch game table after it has been "
                      "handed out; staying on %s",
                      g_game == Game::K1 ? "K1" : "K2");
        return false;
    }
    g_game = g;
    return true;
}

Game selected_game() {
    g_game_latched = true;
    return g_game;
}

const ParamDefault* find_default(std::uint16_t routine, std::uint8_t index) {
    const ParamDefault* first;
    std::size_t count;
    if (selected_game() == Game::K1) {
        first = k1_defaults::kParamDefaults;
        count = sizeof k1_defaults::kParamDefaults / sizeof(ParamDefault);
    } else {
        first = k2_defaults::kParamDefaults;
        count = sizeof k2_defaults::kParamDefaults / sizeof(ParamDefault);
    }
    // The generator emits in (routine, index) order, so a binary search would
    // work; linear is fine because this runs once per defaulted argument on a
    // path that already crosses the Lua boundary.
    for (std::size_t i = 0; i < count; ++i)
        if (first[i].routine == routine && first[i].index == index)
            return &first[i];
    return nullptr;
}

}  // namespace kp::api
