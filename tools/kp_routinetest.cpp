// Exercises the VM routine bridge's result boundary without a game.
//
// A declared result must either arrive as one Lua value or raise.  Returning
// zero values is not an error-equivalent: Lua table constructors silently omit
// it, which made a failed GetFacing look like absent world state.

#include <cmath>
#include <cstdio>
#include <cstring>

#include "api/routines.hpp"
#include "api/output.hpp"
#include "api/enginestruct.hpp"
#include "runtime/internal.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
}

namespace {

int g_failures = 0;
int g_pop_calls = 0;
bool g_pop_succeeds = true;
int g_execute_status = 0;
int g_pop_string_calls = 0;
int g_execute_calls = 0;
int g_push_calls = 0;
int g_execute_id = -1;
int g_execute_argc = -1;
float g_pushed_float = 0.0f;

void check(bool condition, const char* what) {
    if (condition) return;
    ++g_failures;
    std::fprintf(stderr, "FAIL: %s\n", what);
}

int execute(void*, int id, int argc) {
    ++g_execute_calls;
    g_execute_id = id;
    g_execute_argc = argc;
    return g_execute_status;
}
int push_int(void*, int) { ++g_push_calls; return 1; }
int push_float(void*, float value) { ++g_push_calls; g_pushed_float = value; return 1; }
int push_object(void*, std::uint32_t) { ++g_push_calls; return 1; }
int pop_int(void*, int* out) { *out = 0; return 1; }
int pop_float(void*, float* out) {
    ++g_pop_calls;
    if (!g_pop_succeeds) return 0;
    *out = 123.25f;
    return 1;
}
int pop_string(void*, void* out) {
    ++g_pop_string_calls;
    auto* s = static_cast<kp::api::ExoString*>(out);
    s->text = "last";
    s->length = 4;
    return 1;
}

const kp::api::Routine kGetFacing{28, "GetFacing", kp::api::Type::Float,
                                  nullptr, 0, 0};
const kp::api::Routine kVoid{29, "VoidProbe", kp::api::Type::Void,
                              nullptr, 0, 0};
const kp::api::Routine kGetLastConversation{711, "GetLastConversation", kp::api::Type::String,
                                              nullptr, 0, 0};

int call_facing(lua_State* L) { return kp::api::call(L, kGetFacing, 1); }
int call_void(lua_State* L) { return kp::api::call(L, kVoid, 1); }
int call_last_conversation(lua_State* L) { return kp::api::call(L, kGetLastConversation, 1); }

int invoke(lua_State* L, lua_CFunction fn) {
    lua_pushcfunction(L, fn);
    return lua_pcall(L, 0, LUA_MULTRET, 0);
}

bool trace_bool(lua_State* L, const char* key) {
    lua_getfield(L, -1, key);
    const bool value = lua_toboolean(L, -1) != 0;
    lua_pop(L, 1);
    return value;
}

int trace_int(lua_State* L, const char* key) {
    lua_getfield(L, -1, key);
    const int value = int(lua_tointeger(L, -1));
    lua_pop(L, 1);
    return value;
}

}  // namespace

int main() {
    int fake_vm = 0;
    void* wrapper = &fake_vm;
    void* commands[772];
    for (void*& command : commands) command = reinterpret_cast<void*>(&execute);
    struct Commands {
        void* vtable = nullptr;
        int has_caller = 0;
        std::uint32_t caller_id = 0;
        void* const* table = nullptr;
    } implementer;
    struct Internal {
        unsigned char padding[0x3d4]{};
        void* implementer = nullptr;
    } first, second;
    kp::api::VmSites sites;
    sites.layout_resolved = true;
    sites.wrapper_internal_offset = 0x1c;
    sites.command_implementer_offset = 0x3d4;
    // bind_sites only inspects these addresses here; the shim functions are
    // never executed by the capture regression.
    sites.execute_command = sites.stack_push_integer = sites.stack_pop_integer =
        sites.stack_push_float = sites.stack_pop_float = sites.stack_push_string =
        sites.stack_pop_string = sites.stack_push_object = sites.stack_pop_object =
        reinterpret_cast<std::uintptr_t>(&execute);
    kp::runtime::set_vm_sites(sites);
    first.implementer = &implementer;
    kp::runtime::capture_vm(&first);
    check(!kp::runtime::vm_bound() && !kp::api::binding().usable(),
          "null command table refuses capture without latching usable");
    implementer.table = commands;
    kp::runtime::capture_vm(&first);
    check(kp::runtime::vm_bound() && kp::api::vm_binding_live(548),
          "same trusted context retries after command table initialization");
    Commands replacement;
    replacement.table = commands;
    second.implementer = &replacement;
    kp::runtime::capture_vm(&second);
    check(kp::api::binding().command_implementer == &implementer,
          "a live cached context is retained when another VM runs");
    implementer.table = nullptr;
    kp::runtime::capture_vm(&second);
    check(kp::api::binding().command_implementer == &replacement && kp::api::vm_binding_live(548),
          "invalid cached context refreshes to a valid trusted implementer");
    kp::runtime::set_vm_sites({});
    check(!kp::runtime::vm_bound() && !kp::api::binding().usable(), "VM reset invalidates binding");
    implementer.table = commands;
    kp::api::VmBinding binding;
    binding.command_implementer = &implementer;
    binding.virtual_machine = &wrapper;
    binding.execute_command = execute;
    binding.push_int = push_int;
    binding.push_float = push_float;
    binding.push_object = push_object;
    binding.pop_int = pop_int;
    binding.pop_float = pop_float;
    binding.pop_string = pop_string;
    kp::api::bind(binding);
    kp::api::VmEngineAccess access;
    access.command_implementer = &implementer;
    access.virtual_machine = &wrapper;
    access.commands = commands;
    access.command_count = 772;
    kp::api::bind_engine_access(access);

    lua_State* L = luaL_newstate();
    check(L != nullptr, "Lua state is created");
    if (!L) return 1;

    implementer.table = nullptr;
    const int before = g_execute_calls;
    check(invoke(L, call_facing) != 0 && g_execute_calls == before,
          "table invalidation raises Lua error before dispatcher entry");
    lua_settop(L, 0);
    implementer.table = commands;
    commands[28] = nullptr;
    check(invoke(L, call_facing) != 0 && g_execute_calls == before,
          "null selected command slot refuses dispatch");
    lua_settop(L, 0);
    commands[28] = reinterpret_cast<void*>(&execute);

    g_pop_succeeds = true;
    g_pop_calls = 0;
    check(invoke(L, call_facing) == 0, "successful float pop returns normally");
    check(lua_gettop(L) == 1, "successful float pop returns exactly one Lua value");
    check(std::fabs(lua_tonumber(L, -1) - 123.25) < 0.0001,
          "successful float pop preserves the float value");
    check(g_pop_calls == 1, "successful float routine pops once");
    lua_settop(L, 0);

    g_pop_succeeds = false;
    g_pop_calls = 0;
    check(invoke(L, call_facing) != 0, "failed float pop raises a Lua error");
    const char* error = lua_tostring(L, -1);
    check(error && std::strstr(error, "GetFacing"), "float-pop error names the routine");
    check(error && std::strstr(error, "float"), "float-pop error names the return kind");
    check(error && std::strstr(error, "pop_float"), "float-pop error names the VM pop");
    check(error && std::strstr(error, "routine=28") && std::strstr(error, "status=0"),
          "float-pop error has bounded VM diagnostics");
    check(g_pop_calls == 1, "failed float routine attempts exactly one pop");
    lua_settop(L, 0);

    // The production diagnostic is intentionally read-only.  A caller catches
    // the normal Lua error, then asks for the exact GetFacing dispatch facts.
    kp::api::register_all(L);
    lua_getglobal(L, "kotor");
    check(lua_isnil(L, -1), "routine registration does not create kotor or export routine members");
    lua_pop(L, 1);

    g_pop_succeeds = true;
    g_execute_id = -1;
    g_execute_argc = -1;
    g_pushed_float = 0.0f;
    kp::api::register_output(L);
    lua_getglobal(L, "kp");
    lua_getfield(L, -1, "diagnostic");
    lua_remove(L, -2);
    lua_pushliteral(L, "native output must not dispatch an engine routine");
    check(lua_pcall(L, 1, 0, 0) == 0, "kp.diagnostic is callable beside the engine bridge");
    check(g_execute_id == -1, "kp.diagnostic does not dispatch routine 74");
    lua_getglobal(L, "nwscript");
    lua_getfield(L, -1, "call");
    lua_remove(L, -2);
    lua_pushliteral(L, "log");
    lua_pushnumber(L, 42.5);
    check(lua_pcall(L, 2, 1, 0) == 0, "nwscript.call reaches the catalogued log routine");
    check(g_execute_id == 74 && g_execute_argc == 1,
          "nwscript.call dispatches log as routine 74 with one argument");
    check(std::fabs(g_pushed_float - 42.5f) < 0.0001f,
          "nwscript.call preserves log's float argument");
    lua_settop(L, 0);

    lua_getglobal(L, "nwscript");
    lua_getfield(L, -1, "call");
    lua_remove(L, -2);
    lua_pushliteral(L, "DefinitelyNotARoutine");
    check(lua_pcall(L, 1, 0, 0) != 0, "unknown routine raises an actionable Lua error");
    const char* bridge_error = lua_tostring(L, -1);
    check(bridge_error && std::strstr(bridge_error, "unknown routine")
          && std::strstr(bridge_error, "DefinitelyNotARoutine"),
          "unknown-routine error names the rejected routine");
    lua_settop(L, 0);

    lua_getglobal(L, "nwscript");
    lua_getfield(L, -1, "call");
    lua_remove(L, -2);
    lua_pushliteral(L, "DelayCommand");
    check(lua_pcall(L, 1, 0, 0) != 0, "action-closure routine is still excluded");
    bridge_error = lua_tostring(L, -1);
    check(bridge_error && std::strstr(bridge_error, "DelayCommand")
          && std::strstr(bridge_error, "action closure"),
          "excluded-routine error explains the action-closure boundary");
    lua_settop(L, 0);

    lua_State* console = luaL_newstate();
    check(console != nullptr, "second Lua state is created");
    if (console != nullptr) {
        kp::api::register_all(console);
        lua_getglobal(console, "nwscript");
        lua_getfield(console, -1, "call");
        check(lua_isfunction(console, -1),
              "a second state receives the same nwscript.call bridge");
        lua_close(console);
    }

    g_pop_succeeds = false;
    g_pop_calls = 0;
    lua_getglobal(L, "nwscript");
    lua_getfield(L, -1, "call");
    lua_remove(L, -2);
    lua_pushliteral(L, "GetFacing");
    lua_pushnumber(L, 7);
    check(lua_pcall(L, 2, LUA_MULTRET, 0) != 0,
          "GetFacing keeps its normal Lua failure while tracing");
    lua_settop(L, 0);  // discard the normal error before querying diagnostics
    lua_getglobal(L, "nwscript");
    lua_getfield(L, -1, "last_trace");
    check(lua_pcall(L, 0, 1, 0) == 0, "GetFacing trace can be read after the normal routine error");
    check(lua_istable(L, -1), "trace is a Lua table");
    if (lua_istable(L, -1)) {
        check(trace_int(L, "routine") == 28, "trace records GetFacing routine id");
        check(trace_bool(L, "execute_called"), "trace records ExecuteCommand entry");
        check(trace_int(L, "execute_status") == 0, "trace records ExecuteCommand status");
        check(trace_bool(L, "push_result_entered"), "trace records result-boundary entry");
        check(trace_bool(L, "pop_bound"), "trace records bound float pop");
        check(trace_bool(L, "pop_attempted"), "trace records float pop attempt");
        check(trace_int(L, "pop_status") == 0, "trace records float pop status");
        check(trace_int(L, "result_count") == -1, "trace records no returned Lua value");
    }
    lua_settop(L, 0);

    // K1's real ExecuteCommandGetLastConversation returns STACK_PUSH_ERROR
    // (-2000) after successfully pushing its string. This is a routine-local
    // engine defect, not the generic ExecuteCommand success convention.
    g_execute_status = -2000;
    g_pop_string_calls = 0;
    check(invoke(L, call_last_conversation) == 0,
          "GetLastConversation accepts its documented inverted success status");
    check(lua_gettop(L) == 1 && std::strcmp(lua_tostring(L, -1), "last") == 0,
          "GetLastConversation returns the popped CExoString");
    check(g_pop_string_calls == 1, "GetLastConversation pops its string once");
    lua_settop(L, 0);

    g_execute_status = -2000;
    check(invoke(L, call_facing) != 0,
          "the inverted status is not accepted for unrelated routines");
    lua_settop(L, 0);

    g_execute_status = 0;
    g_pop_string_calls = 0;
    check(invoke(L, call_last_conversation) != 0,
          "GetLastConversation does not accept zero as its success status");
    check(g_pop_string_calls == 0, "failed GetLastConversation does not pop a phantom string");
    lua_settop(L, 0);

    binding.pop_float = nullptr;
    kp::api::bind(binding);
    check(invoke(L, call_facing) != 0, "unbound float pop raises instead of dereferencing null");
    error = lua_tostring(L, -1);
    check(error && std::strstr(error, "GetFacing") && std::strstr(error, "status=unbound"),
          "unbound float pop has a bounded diagnostic");
    lua_settop(L, 0);
    binding.pop_float = pop_float;
    binding.pop_string = pop_string;
    kp::api::bind(binding);

    g_pop_calls = 0;
    check(invoke(L, call_void) == 0, "void routine still returns normally");
    check(lua_gettop(L) == 0, "void routine returns no Lua values");
    check(g_pop_calls == 0, "void routine does not pop a result");

    // The public caller wrapper forwards arbitrary values and restores both
    // caller fields after success, nesting, and a non-string Lua error.
    lua_pushlightuserdata(L, &implementer);
    lua_pushcclosure(L, [](lua_State* state) -> int {
        auto* caller = static_cast<Commands*>(lua_touserdata(state, lua_upvalueindex(1)));
        lua_pushinteger(state, caller->has_caller);
        lua_pushnumber(state, caller->caller_id);
        return 2;
    }, 1);
    lua_setglobal(L, "caller_probe");
    implementer.has_caller = 0;
    implementer.caller_id = 91;
    const char* caller_test = R"lua(
        local token = {}
        local a, b, c = nwscript.with_caller(7, function(x, y, z)
            local has, id = caller_probe()
            if has ~= 1 or id ~= 7 then error('outer caller') end
            nwscript.with_caller(8, function()
                local has, id = caller_probe()
                if has ~= 1 or id ~= 8 then error('nested caller') end
            end)
            local has, id = caller_probe()
            if has ~= 1 or id ~= 7 then error('nested restoration') end
            return x, y, z
        end, token, nil, 42)
        if a ~= token or b ~= nil or c ~= 42 then error('argument/result forwarding') end
    )lua";
    check(luaL_dostring(L, caller_test) == 0, "with_caller preserves nesting and variadic results");
    check(implementer.has_caller == 0 && implementer.caller_id == 91,
          "successful caller wrapper restores both fields");
    lua_settop(L, 0);
    lua_getglobal(L, "nwscript");
    lua_getfield(L, -1, "with_caller");
    lua_remove(L, -2);
    lua_pushnumber(L, 9);
    lua_pushcfunction(L, [](lua_State* state) -> int {
        lua_pushlightuserdata(state, reinterpret_cast<void*>(123));
        return lua_error(state);
    });
    check(lua_pcall(L, 2, 0, 0) != 0 && lua_touserdata(L, -1) == reinterpret_cast<void*>(123),
          "with_caller propagates the original error object");
    check(implementer.has_caller == 0 && implementer.caller_id == 91,
          "failed caller wrapper restores both fields");
    lua_settop(L, 0);
    implementer.caller_id = 0;

    implementer.table = nullptr;
    g_push_calls = 0;
    lua_getglobal(L, "nwscript");
    lua_getfield(L, -1, "call");
    lua_remove(L, -2);
    lua_pushliteral(L, "GetFacing");
    lua_pushnumber(L, 7);
    check(lua_pcall(L, 2, 1, 0) != 0 && g_push_calls == 0,
          "invalid context refuses before pushing the first routine argument");
    lua_settop(L, 0);
    lua_getglobal(L, "nwscript");
    lua_getfield(L, -1, "with_caller");
    lua_pushnumber(L, 7);
    lua_pushcfunction(L, call_void);
    check(lua_pcall(L, 2, 0, 0) != 0 && implementer.has_caller == 0 && implementer.caller_id == 0,
          "nwscript.with_caller refuses invalid context without writing caller state");
    lua_settop(L, 0);
    implementer.table = commands;
    check(invoke(L, call_void) == 0, "routine calls recover when the live table returns");

    lua_close(L);
    std::printf("kp_routinetest: %d failure(s)\n", g_failures);
    return g_failures ? 1 : 0;
}
