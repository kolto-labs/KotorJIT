// Offline contract against production registrations; no game or VM required.
#include <cstdio>
#include <cstring>
#include <fstream>
#include <functional>
#include <string>
#include <unistd.h>

#include "api/compat.hpp"
#include "api/enginestruct.hpp"
#include "api/entity.hpp"
#include "api/memory.hpp"
#include "api/output.hpp"
#include "api/routines.hpp"
#include "api/structs.hpp"
#include "lua/host.hpp"
#include "runtime/internal.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}

namespace {
int failures = 0;
void check(bool ok, const char* message) {
    if (!ok) { ++failures; std::fprintf(stderr, "FAIL: %s\n", message); }
}
bool run(lua_State* L, const char* code) {
    if (luaL_dostring(L, code) == 0) return true;
    check(false, lua_tostring(L, -1));
    lua_pop(L, 1);
    return false;
}
void install(lua_State* L, bool reverse = false) {
    kp::api::open_engine_structs(L);
    kp::api::register_all(L);
    if (reverse) kp::api::compat::install(L, "/offline/game");
    kp::api::memory::register_all(L);
    kp::api::structs::register_all(L);
    kp::api::entity::register_all(L);
    kp::api::register_support(L);
    kp::runtime::register_director(L);
    if (!reverse) kp::api::compat::install(L, "/offline/game");
}
}

int main(int argc, char**) {
    check(kp::api::select_game(argc > 1 ? kp::api::Game::K2 : kp::api::Game::K1),
          "select catalog before registration");
    for (bool reverse : {false, true}) {
        lua_State* L = luaL_newstate();
        if (!L) return 1;
        luaL_openlibs(L);
        // Capture the complete standard global surface, including Lua print.
        run(L, R"lua(
            local before = {}
            for k,v in pairs(_G) do before[k] = v end
            kp = { marker = 42, mem = {}, obj = {}, struct = {}, events = {}, harness = {} }
            local root, mem, obj, struct = kp, kp.mem, kp.obj, kp.struct
            local events, harness = kp.events, kp.harness
            return function()
                for k,v in pairs(before) do
                    assert(_G[k] == v, 'replaced standard global: ' .. k)
                end
                for k in pairs(_G) do
                    assert(before[k] ~= nil or k == 'kp' or k == 'nwscript',
                           'unexpected host global: ' .. k)
                end
                assert(kotor == nil and log == nil and log_msg == nil)
                assert(cb == nil and _G.events == nil and register_callback == nil)
                assert(kp == root and kp.marker == 42)
                assert(kp.mem == mem and kp.obj == obj and kp.struct == struct)
                assert(kp.events == events and kp.harness == harness)
                for k,v in pairs(nwscript) do
                    assert(k == 'call' and type(v) == 'function', 'engine export: ' .. k)
                end
                assert(type(nwscript.call) == 'function')
                assert(kp.GetFirstPC == nil and kp.log_msg == nil and kp.read_byte == nil)
                for _,path in ipairs({'mem.readbyte', 'obj.get', 'struct.at',
                    'print', 'log', 'console', 'feedback', 'registertimer',
                    'removetimer', 'tokenizestring', 'tokenizecmdstring',
                    'harness.state', 'events.register', 'events.unregister',
                    'as', 'last_routine_trace', 'speed', 'time'}) do
                    local v = kp
                    for name in path:gmatch('[^.]+') do v = v[name] end
                    assert(type(v) == 'function', 'missing kp.' .. path)
                end
                assert(type(kp.events.OnTick) == 'number')
                assert(kp.host == 'KotorPhasor' and kp.serverapp == 'KotorPhasor')
                assert(kp.game == 'KOTOR' and kp.api_version == 2)
                assert(type(kp.version) == 'string' and kp.gamedir() == '/offline/game')
                assert(kp.tokenizestring('a,b', ',')[2] == 'b')
                assert(kp.struct.allow_unverified_writes() == false)
                kp.print('namespace contract'); kp.log('host log is distinct from routine log')
            end
        )lua");
        const int contract = luaL_ref(L, LUA_REGISTRYINDEX);
        install(L, reverse);
        install(L, reverse); // Re-registration must preserve every shared table.
        for (const auto& routine : kp::api::table()) {
            lua_getglobal(L, routine.name);
            check(lua_isnil(L, -1), routine.name);
            lua_pop(L, 1);
            for (const char* root : {"nwscript", "kp"}) {
                // kp.log is native output; routine 74 remains nwscript.call("log", x).
                if (std::strcmp(root, "kp") == 0 && std::strcmp(routine.name, "log") == 0)
                    continue;
                lua_getglobal(L, root);
                lua_getfield(L, -1, routine.name);
                check(lua_isnil(L, -1), routine.name);
                lua_pop(L, 2);
            }
        }
        lua_rawgeti(L, LUA_REGISTRYINDEX, contract);
        if (lua_pcall(L, 0, 0, 0) != 0) {
            check(false, lua_tostring(L, -1)); lua_pop(L, 1);
        }
        check(lua_gettop(L) == 0, "registration and contract leave a balanced stack");
        lua_close(L);
    }

    char path[] = "/tmp/kp-namespace-XXXXXX";
    const int fd = mkstemp(path);
    if (fd < 0) return 1;
    close(fd);
    {
        std::ofstream fixture(path);
        fixture << R"lua(
            priority = 7 -- script-owned loader metadata is still accepted
            function OnTick() return 'legacy' end
            assert(kp.events.register(kp.events.OnTick, function() return 'explicit' end))
        )lua";
    }
    const std::function<void(lua_State*)> init = [](lua_State* L) { install(L); };
    kp::lua::Script script("namespace", path, &init);
    std::string error;
    const bool loaded = script.load(error);
    unlink(path);
    check(loaded, error.c_str());
    if (loaded) {
        check(script.priority() == 7, "script-owned priority is preserved");
        lua_State* L = script.L();
        check(script.push_handler("OnTick"), "explicit event binding is discoverable");
        check(lua_pcall(L, 0, 1, 0) == 0, "explicit handler executes");
        check(std::string(lua_tostring(L, -1)) == "explicit", "explicit handler wins");
        lua_pop(L, 1);
        run(L, "assert(kp.events.unregister(kp.events.OnTick))");
        check(script.push_handler("OnTick"), "legacy global handler remains discoverable");
        check(lua_pcall(L, 0, 1, 0) == 0, "legacy handler executes");
        check(std::string(lua_tostring(L, -1)) == "legacy", "unregister restores global fallback");
        lua_pop(L, 1);
        run(L, "local ok,err = pcall(kp.events.register, -1, function() end); "
               "assert(not ok and err:find('kp.events.On', 1, true))");
    }
    std::printf("namespace contract: %d failure(s)\n", failures);
    return failures ? 1 : 0;
}
