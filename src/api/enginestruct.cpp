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
// Code addresses are process-wide. Object pointers can be refreshed from a
// trusted RunScript context; publication happens on the same game thread.
hooks::ThiscallFn<int, int, int>            g_execute_command = nullptr;
hooks::ThiscallFn<int, int>                 g_push_int    = nullptr;
hooks::ThiscallFn<int, float>               g_push_float  = nullptr;
hooks::ThiscallFn<int, const void*>         g_push_string = nullptr;
// Object ids cross this boundary at the engine's width (abi::ObjectId): 32
// bits on i386, 64 on x86_64, where StackPopObject writes a full 8 bytes.
hooks::ThiscallFn<int, abi::ObjectId>       g_push_object = nullptr;
hooks::ThiscallFn<int, int*>                g_pop_int     = nullptr;
hooks::ThiscallFn<int, float*>              g_pop_float   = nullptr;
hooks::ThiscallFn<int, void*>               g_pop_string  = nullptr;
hooks::ThiscallFn<int, abi::ObjectId*>      g_pop_object  = nullptr;

int shim_execute(void* self, int id, int argc) { return g_execute_command(self, id, argc); }
int shim_push_int(void* vm, int v)             { return g_push_int(vm, v); }
int shim_push_float(void* vm, float v)         { return g_push_float(vm, v); }
int shim_push_string(void* vm, const void* s)  { return g_push_string(vm, s); }
int shim_push_object(void* vm, std::uint32_t v){ return g_push_object(vm, abi::ObjectId(v)); }
int shim_pop_int(void* vm, int* out)           { return g_pop_int(vm, out); }
int shim_pop_float(void* vm, float* out)       { return g_pop_float(vm, out); }
int shim_pop_string(void* vm, void* out)       { return g_pop_string(vm, out); }
int shim_pop_object(void* vm, std::uint32_t* o){
    abi::ObjectId wide = 0;
    const int rc = g_pop_object(vm, &wide);
    *o = abi::script_id(wide);
    return rc;
}

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

bool vm_binding_live(int routine) {
    const auto& b = binding();
    const auto& a = engine_access();
    if (!b.usable() || b.command_implementer != a.command_implementer ||
        b.virtual_machine != a.virtual_machine || !a.commands || !a.command_count ||
        a.command_count > 65536 || a.commands_offset > 65536)
        return false;
    if (!platform::is_readable(static_cast<const char*>(b.virtual_machine) +
                                   a.wrapper_internal_offset,
                               sizeof(void*))) return false;
    void* internal = *reinterpret_cast<void* const*>(
        static_cast<const char*>(b.virtual_machine) + a.wrapper_internal_offset);
    if (!internal || !platform::is_readable(internal, sizeof(void*))) return false;
    if (!platform::is_readable(b.command_implementer, a.commands_offset + sizeof(void*)))
        return false;
    const void* table = *reinterpret_cast<const void* const*>(
        static_cast<const char*>(b.command_implementer) + a.commands_offset);
    if (table != a.commands ||
        !platform::is_readable(table, layout::kEngine.command_entry_bytes * a.command_count))
        return false;
    return routine < 0 || (static_cast<unsigned>(routine) < a.command_count &&
        command_slot_live(table, static_cast<std::uint32_t>(routine)));
}

bool command_slot_live(const void* table, std::uint32_t routine) {
    const auto* entry = static_cast<const char*>(table) + layout::kEngine.command_entry_bytes * routine;
    std::uintptr_t ptr = 0;
    std::memcpy(&ptr, entry, sizeof ptr);
    if (ptr == 0) return false;
    if (abi::kX64 && (ptr & 1u) != 0) return true;   // virtual: vtable offset + 1
    return platform::is_readable(reinterpret_cast<const void*>(ptr), 1);
}

namespace {
// The bytes the bound is read from. Normally the live prologue. When another
// module's detour replaced the head, the original instructions are spliced
// back in from the relocated copy, so nothing is ever decoded out of the
// other module's jump; without that copy only the untouched tail is offered.
std::size_t dispatcher_bytes(const VmSites& s, std::uint8_t* buf, std::size_t cap) {
    if (s.execute_command == 0) return 0;
    const auto* p = reinterpret_cast<const std::uint8_t*>(s.execute_command);
    if (!platform::is_readable(p, cap)) return 0;
    std::memcpy(buf, p, cap);
    if (!s.execute_command_foreign) return cap;
    const std::size_t head = s.execute_command_head < cap ? s.execute_command_head : cap;
    if (!s.execute_command_prologue.empty() && s.execute_command_prologue.size() == head) {
        std::memcpy(buf, s.execute_command_prologue.data(), head);
        return cap;
    }
    std::memmove(buf, buf + head, cap - head);
    return cap - head;
}
}  // namespace

std::uint32_t discover_command_count(const VmSites& s) {
#if defined(__x86_64__) || defined(_M_X64)
    // The table's field (vmcmd.command_count) and the live dispatcher must
    // agree. There is no KPM-style table growth on the Mac builds; a
    // disagreement means the code is not what the table was generated from.
    std::uint8_t buf[32];
    const std::size_t got = dispatcher_bytes(s, buf, sizeof buf);
    if (got == 0) return 0;
    std::uint32_t live = 0;
    if (!decode_execute_command_bound_x64(buf, got, live)) {
        // Another module's detour hid the compare and its displaced original
        // was not found. The table's count is the generator's verified figure
        // for this exact build; use it rather than refuse.
        if (s.execute_command_foreign && s.commands_count != 0) {
            platform::log(platform::LogLevel::Warn,
                          "vm: ExecuteCommand is detoured by another module; using the table's bound %u",
                          s.commands_count);
            return s.commands_count;
        }
        return 0;
    }
    if (s.commands_count != 0 && s.commands_count != live) {
        platform::log(platform::LogLevel::Error,
                      "vm: ExecuteCommand bound %u differs from the table's %u", live, s.commands_count);
        return 0;
    }
    return live;
#else
    std::uint32_t bound = s.commands_count ? s.commands_count : 0x304;
    std::uint8_t buf[32];
    if (const std::size_t got = dispatcher_bytes(s, buf, sizeof buf); got != 0) {
        std::uint32_t imm = 0;
        if (decode_execute_command_bound(buf, got, imm) && imm > bound)
            bound = imm;
    }
    if (s.execute_command_foreign && s.execute_command_prologue.empty())
        platform::log(platform::LogLevel::Warn,
                      "vm: ExecuteCommand is detoured by another module and its original compare was not "
                      "found; assuming bound %u (routines a table-growing patch added past it are not "
                      "reachable from Lua)", bound);
    return bound;
#endif
}

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

    // Validate before changing shims or either published binding. A null table
    // faults inside ExecuteCommand; it cannot degrade to an ordinary VM error.
    const std::uint32_t count = discover_command_count(s);
    if (!count || count > 65536 || s.commands_offset > 65536 ||
        !platform::is_readable(s.command_implementer, s.commands_offset + sizeof(void*)) ||
        !platform::is_readable(static_cast<const char*>(s.virtual_machine) +
                                   s.wrapper_internal_offset,
                               sizeof(void*))) {
        error = "VM context is not readable";
        return false;
    }
    void* internal = *reinterpret_cast<void* const*>(
        static_cast<const char*>(s.virtual_machine) + s.wrapper_internal_offset);
    const void* commands = *reinterpret_cast<const void* const*>(
        static_cast<const char*>(s.command_implementer) + s.commands_offset);
    if (!internal || !platform::is_readable(internal, sizeof(void*)) || !commands ||
        !platform::is_readable(commands, layout::kEngine.command_entry_bytes * count)) {
        error = "VM internal or command table is not readable";
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

    a.commands = commands;
    a.command_count = count;
    a.commands_offset = s.commands_offset;
    a.wrapper_internal_offset = s.wrapper_internal_offset;
    // No engine call or callback between these assignments: game-thread
    // consumers observe one complete context, including all stack accessors.
    bind_engine_access(a);
    bind(b);
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
