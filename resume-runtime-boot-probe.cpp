#include "runtime/runtime.hpp"
#include "runtime/internal.hpp"
#include "lua/host.hpp"
#include "api/scripts_lua.hpp"
extern "C" {
#include <lua.h>
#include <lauxlib.h>
}
#include <cassert>
#include <filesystem>
#include <fstream>
#include <cstdio>
#include <unistd.h>
// Explicit instantiation grants this private test access to the real boot seam;
// no production header or implementation is replaced or stubbed.
struct BootTag {
    using type = bool (kp::runtime::Runtime::*)(const kp::runtime::Config&);
    friend type access(BootTag);
};
template<class Tag, typename Tag::type Member> struct PrivateAccess {
    friend typename Tag::type access(Tag) { return Member; }
};
template struct PrivateAccess<BootTag, &kp::runtime::Runtime::boot_scripts>;
static int unload_calls = 0;
static kp::lua::Host* expected_host = nullptr;
static int record_unload(lua_State*) {
    assert(kp::api::scripts::bound_host() == expected_host);
    ++unload_calls;
    return 0;
}
int main(int argc, char**) {
    char temp[] = "/tmp/kp-runtime-boot-XXXXXX";
    assert(mkdtemp(temp));
    const std::filesystem::path dir(temp);
    std::ofstream(dir / "probe.lua") << R"lua(
assert(type(kp.scripts.list()) == 'table')
assert(type(kp.vec) == 'function')
local v = kp.vec(1,2,3)
assert(v.x == 1 and v.y == 2 and v.z == 3)
assert(type(kp.motion.capabilities) == 'function')
assert(type(kp.motion.capabilities()) == 'table')
assert(type(kp.camera) == 'table')
assert(kp.events.register(kp.events.OnScriptUnload, function()
    assert(type(kp.scripts.list()) == 'table')
    record_unload()
end))
boot_checked = true
)lua";
    auto& runtime = kp::runtime::Runtime::instance();
    kp::runtime::Config cfg;
    cfg.game_dir = temp;
    cfg.script_dir = temp;
    cfg.hot_reload = false;
    assert((runtime.*access(BootTag{}))(cfg));
    expected_host = runtime.host();
    assert(expected_host && kp::api::scripts::bound_host() == expected_host);
    assert(expected_host->scripts().size() == 1);
    lua_State* L = expected_host->scripts()[0]->L();
    assert(L);
    lua_getglobal(L, "boot_checked");
    assert(lua_toboolean(L, -1));
    lua_pop(L, 1);
    lua_register(L, "record_unload", record_unload);
    if (argc > 1) {
        // A native host-test ELF cannot match any supported game profile.
        // Seed the partial Host via the real boot seam, then exercise actual
        // failed-start cleanup on the refused host executable.
        cfg.log_path = (dir / "runtime.log").string();
        assert(!runtime.start(cfg));
        assert(runtime.phase() == kp::runtime::Phase::Failed);
    } else {
        runtime.stop();
    }
    assert(unload_calls == 1);
    assert(kp::api::scripts::bound_host() == nullptr);
    assert(runtime.host() == nullptr);
    assert(!kp::runtime::live());
    std::filesystem::remove_all(dir);
    std::puts(argc > 1
        ? "PASS actual Runtime failed-start cleanup of seeded Host, unload callback, cleared binding"
        : "PASS actual Runtime boot initializer, initial kp.scripts, unload callback, cleared host binding");
}
