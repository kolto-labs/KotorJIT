// Offline contract against production registrations; no game or VM required.
#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <functional>
#include <iterator>
#include <string>
#include <thread>
#include <unistd.h>

#include "api/compat.hpp"
#include "api/enginestruct.hpp"
#include "api/entity.hpp"
#include "api/memory.hpp"
#include "api/output.hpp"
#include "api/vector.hpp"
#include "api/motion.hpp"
#include "api/scripts_lua.hpp"
#include "api/routines.hpp"
#include "api/structs.hpp"
#include "events/table.hpp"
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
void install_native(lua_State* L, bool reverse = false) {
    kp::api::open_engine_structs(L);
    if (reverse) kp::api::compat::install(L, "/offline/game");
    kp::api::memory::register_all(L);
    kp::api::structs::register_all(L);
    kp::api::entity::register_all(L);
    kp::api::register_support(L);
    kp::api::register_vector(L);
    kp::api::motion::register_all(L);
    kp::api::scripts::register_all(L);
    kp::runtime::register_director(L);
    if (!reverse) kp::api::compat::install(L, "/offline/game");
}
void install(lua_State* L, bool reverse = false) {
    kp::api::register_all(L);
    install_native(L, reverse);
}

}

int main(int argc, char**) {
    check(kp::api::select_game(argc > 1 ? kp::api::Game::K2 : kp::api::Game::K1),
          "select catalog before registration");

    if (argc == 1) {
        // The production latch is distinct from the engine_gate unit probe:
        // it must begin empty, bind only the first server-main-loop caller,
        // refuse a worker, never relatch from that worker, and reset cleanly.
        kp::runtime::reset_engine_thread();
        check(!kp::runtime::engine_thread_latched() && !kp::runtime::on_engine_thread(),
              "engine latch starts unbound");
        kp::runtime::latch_engine_thread();
        check(kp::runtime::engine_thread_latched() && kp::runtime::on_engine_thread(),
              "engine latch binds current thread");
        bool worker_owner = true;
        std::thread worker([&] {
            worker_owner = kp::runtime::on_engine_thread();
            kp::runtime::latch_engine_thread();
        });
        worker.join();
        check(!worker_owner, "worker does not own server latch");
        check(kp::runtime::on_engine_thread(), "main thread remains server owner");
        kp::runtime::reset_engine_thread();
    check(!kp::runtime::engine_thread_latched() && !kp::runtime::on_engine_thread(),
          "engine latch resets");

    // Simultaneous server contenders still elect exactly one owner. Repeated
    // calls from the losing thread cannot replace that owner.
    for (unsigned round = 0; round < 8; ++round) {
        std::atomic<unsigned> ready{0}, winners{0};
        std::atomic<bool> go{false}, stable{true};
        auto contend = [&] {
            ready.fetch_add(1);
            while (!go.load()) std::this_thread::yield();
            kp::runtime::latch_engine_thread();
            const bool owner = kp::runtime::on_engine_thread();
            if (owner) winners.fetch_add(1);
            for (unsigned attempt = 0; attempt < 16; ++attempt) {
                kp::runtime::latch_engine_thread();
                if (kp::runtime::on_engine_thread() != owner) stable.store(false);
            }
        };
        std::thread first(contend), second(contend);
        while (ready.load() != 2) std::this_thread::yield();
        go.store(true);
        first.join(); second.join();
        check(winners.load() == 1 && stable.load(), "concurrent latch has one stable owner");
        check(!kp::runtime::on_engine_thread(), "nonparticipant never owns concurrent latch");
        kp::runtime::reset_engine_thread();
    }
    }

    // events::dispatchable is the source of truth kp.events.register leans on
    // to refuse a handler that can never fire. Pin it against the exact 14
    // names docs/user/api-status.md documents as "Dead names" -- every one of
    // them has outer_event_id == -1 in the generated table and none of them
    // is a name any hook body looks up directly (see kDirectDispatchNames in
    // src/events/table.cpp). Same table for K1 and K2, so this runs once.
    {
        static const char* kExpectedDead[] = {
            "OnCreatureHeartbeat", "OnCreatureSpawn", "OnCreatureDamaged",
            "OnCreatureDeath", "OnCreatureEndCombatRound", "OnCreatureEndDialogue",
            "OnPlaceableEndDialogue", "OnTriggerTrapTriggered", "OnTriggerHeartbeat",
            "OnCreatureStateScript", "OnAreaTransitionFail", "OnItemUse",
            "OnClientRequestedScript", "OnDialogConditional",
        };
        std::size_t found = 0;
        for (const auto& ev : kp::events::table()) {
            const bool expected_dead =
                std::find_if(std::begin(kExpectedDead), std::end(kExpectedDead),
                             [&](const char* n) { return ev.lua_name == n; }) !=
                std::end(kExpectedDead);
            const std::string msg = "events::dispatchable(" + ev.lua_name +
                                    ") disagrees with api-status.md Dead names";
            check(kp::events::dispatchable(ev) == !expected_dead, msg.c_str());
            if (expected_dead) ++found;
        }
        check(found == std::size(kExpectedDead),
              "every documented dead name is present in the generated table");
    }
    for (bool bridge : {false, true}) {
        lua_State* isolated = luaL_newstate();
        if (!isolated) return 1;
        luaL_openlibs(isolated);
        if (bridge) kp::api::register_all(isolated);
        else install_native(isolated);
        lua_getglobal(isolated, bridge ? "kp" : "nwscript");
        check(lua_isnil(isolated, -1), "isolated registration creates only its owned root");
        lua_pop(isolated, 1);
        check(lua_gettop(isolated) == 0, "isolated registration balances stack");
        lua_close(isolated);
    }
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
                    assert((k == 'call' or k == 'with_caller' or k == 'last_trace')
                           and type(v) == 'function', 'engine export: ' .. k)
                end
                assert(type(nwscript.call) == 'function')
                assert(type(nwscript.with_caller) == 'function' and type(nwscript.last_trace) == 'function')
                assert(kp['as'] == nil and kp['last_routine_trace'] == nil and kp['log'] == nil)
                assert(kp.GetFirstPC == nil and kp.log_msg == nil and kp.read_byte == nil)
                for _,path in ipairs({'mem.readbyte', 'obj.get', 'struct.at',
                    'print', 'diagnostic', 'console', 'feedback', 'registertimer',
                    'removetimer', 'tokenizestring', 'tokenizecmdstring',
                    'harness.state', 'events.register', 'events.unregister',
                    'speed', 'time'}) do
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
                kp.print('namespace contract'); kp.diagnostic('host log is distinct from routine log')
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

        // OnCreatureDamaged is a real script slot (ScriptDamaged) but no hook
        // body raises it -- its contract has outer_event_id == -1 and it is
        // not one of the names RunScript/console/save/load/tick look up
        // directly. Registration must say so rather than pretend the handler
        // is armed. OnDialogConditional shares OnCreatureDamaged's dead
        // vm.run_script site and its arg shape ("arg1 CExoString*", same as
        // the live OnRunScript) -- it is dead too, which is why dispatchable()
        // cannot be a hook_site or arg-source heuristic.
        run(L, "assert(kp.events.register(kp.events.OnCreatureDamaged, function() end) == false)");
        run(L, "assert(kp.events.register(kp.events.OnDialogConditional, function() end) == false)");

        // A live EventHandler-routed event (find_by_site on hook_site +
        // outer_event_id, no script_event_type) still registers.
        run(L, "assert(kp.events.register(kp.events.OnCreatureAttacked, function() end) == true)");
        run(L, "assert(kp.events.unregister(kp.events.OnCreatureAttacked))");

        // A live SIGNAL_EVENT-routed event (find_by_site also matching on
        // script_event_type) still registers.
        run(L, "assert(kp.events.register(kp.events.OnModuleHeartbeat, function() end) == true)");
        run(L, "assert(kp.events.unregister(kp.events.OnModuleHeartbeat))");
    }
    std::printf("namespace contract: %d failure(s)\n", failures);
    return failures ? 1 : 0;
}
