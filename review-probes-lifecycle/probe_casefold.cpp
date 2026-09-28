// I2 on a case-insensitive directory (casefolded tmpfs), the Linux stand-in for
// Windows/Wine file lookup. Scratch only.
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

#include "api/scripts_lua.hpp"
#include "api/timers.hpp"
#include "events/contract.hpp"
#include "lua/host.hpp"
#include "lua/value.hpp"
#include "platform/platform.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
}

namespace fs = std::filesystem;
using namespace kp;
namespace {
unsigned g_ticks = 0;
int l_tick(lua_State*) { ++g_ticks; return 0; }
void created(lua_State* L) { lua_register(L, "count_tick", l_tick); api::register_timers(L); api::scripts::register_all(L); }
void sink(platform::LogLevel, const char*, void*) {}
events::EventContract ev(const char* n) { events::EventContract e; e.lua_name = n; return e; }
const events::EventContract kLoad = ev("OnScriptLoad"), kUnload = ev("OnScriptUnload"), kTick = ev("OnTick");

void list(lua::Host& h, const char* tag) {
    std::printf("  OBSERVE %s: %zu script(s):", tag, h.scripts().size());
    for (auto& s : h.scripts()) std::printf(" [%s %s]", s->name().c_str(), fs::path(s->path()).filename().string().c_str());
    std::printf("\n");
}
}  // namespace

int main(int, char** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    platform::set_log_sink(&sink, nullptr);
    const fs::path dir = argv[1];
    { std::ofstream(dir / "10_cover.lua") << "function OnTick() count_tick() end\n"; }
    std::printf("  OBSERVE casefold lookup: exists(10_COVER.lua)=%d\n", int(fs::exists(dir / "10_COVER.lua")));
    lua::HostConfig c; c.script_dir = dir.string(); c.on_state_created = created;
    lua::Host h(std::move(c));
    h.set_lifecycle(&kLoad, &kUnload, "k1", "casefold");
    api::scripts::bind_host(&h);
    std::vector<std::string> errs; h.load_all(errs);
    list(h, "after load_all");

    // A: case variant of a held script.
    const auto a = h.request(lua::LifecycleOp::Load, "10_COVER");
    // B: a new file requested by a different case, then the hot-reload poll.
    { std::ofstream(dir / "newfile.lua") << "function OnTick() count_tick() end\n"; }
    const auto b = h.request(lua::LifecycleOp::Load, "NEWFILE");
    h.service_requests();
    for (auto id : {a, b}) {
        const lua::RequestResult* r = h.result(id);
        std::printf("  OBSERVE request %s -> %s %s\n", r->name.c_str(),
                    r->status == lua::RequestStatus::Ok ? "OK" : "ERROR", r->error.c_str());
    }
    list(h, "after service");
    h.reload_changed();
    list(h, "after hot-reload poll");
    g_ticks = 0; h.dispatch(kTick, {});
    std::printf("  OBSERVE one OnTick ran %u handler bodies from 2 files on disk\n", g_ticks);
    api::scripts::bind_host(nullptr);
    return 0;
}
