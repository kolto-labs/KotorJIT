// Reviewer probes for Lua lifecycle L1+L2. Scratch only; not part of the repo.
// Each probe prints OBSERVE lines (facts) and a verdict tag the review cites.
#include <chrono>
#include <cstdio>
#include <cmath>
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
#include "lualib.h"
}

namespace fs = std::filesystem;
using namespace kp;

namespace {
fs::path g_root;
std::vector<std::string> g_notes;
int g_flag = 0;
unsigned g_created = 0, g_closed = 0;

events::EventContract ev(const char* n) { events::EventContract e; e.lua_name = n; return e; }
const events::EventContract kLoad = ev("OnScriptLoad"), kUnload = ev("OnScriptUnload"), kTick = ev("OnTick");

void sink(platform::LogLevel, const char*, void*) {}
int l_note(lua_State* L) { g_notes.emplace_back(luaL_checkstring(L, 1)); return 0; }
int l_setflag(lua_State* L) { g_flag = int(luaL_checkinteger(L, 1)); return 0; }
lua::Host* g_host = nullptr;
int l_nested(lua_State*) { g_host->dispatch(kTick, {}); return 0; }
int l_unbind(lua_State* L) { lua::Script::owner(L)->bind_callback(luaL_checkstring(L, 1), LUA_NOREF); return 0; }
int l_bind(lua_State* L) {
    const char* e = luaL_checkstring(L, 1);
    luaL_checktype(L, 2, LUA_TFUNCTION);
    lua_pushvalue(L, 2);
    lua::Script::owner(L)->bind_callback(e, luaL_ref(L, LUA_REGISTRYINDEX));
    return 0;
}
void created(lua_State* L) {
    ++g_created;
    lua_register(L, "note", l_note);
    lua_register(L, "setflag", l_setflag);
    lua_register(L, "bind", l_bind);
    lua_register(L, "unbind", l_unbind);
    lua_register(L, "nested_dispatch", l_nested);
    api::register_timers(L);
    api::scripts::register_all(L);
}
void closing(lua_State*) { ++g_closed; }

unsigned count(const std::string& n) { unsigned c = 0; for (auto& s : g_notes) if (s == n) ++c; return c; }

struct Case {
    fs::path dir; std::unique_ptr<lua::Host> host;
    explicit Case(const char* n, unsigned budget = 8) {
        dir = g_root / n; std::error_code ec; fs::remove_all(dir, ec); fs::create_directories(dir);
        g_notes.clear();
        lua::HostConfig c; c.script_dir = dir.string(); c.error_budget = budget;
        c.on_state_created = created; c.on_state_closing = closing;
        host = std::make_unique<lua::Host>(std::move(c));
        host->set_lifecycle(&kLoad, &kUnload, "k1", "probe");
        api::scripts::bind_host(host.get());
        g_host = host.get();
    }
    ~Case() { host.reset(); api::scripts::bind_host(nullptr); }
    fs::path p(const std::string& s) const { return dir / (s + ".lua"); }
    void write(const std::string& s, const std::string& body, bool bump = true) {
        std::error_code ec; const bool ex = fs::exists(p(s), ec);
        const auto before = ex ? fs::last_write_time(p(s), ec) : fs::file_time_type{};
        { std::ofstream(p(s), std::ios::binary) << body; }
        if (ex && bump) fs::last_write_time(p(s), before + std::chrono::seconds(2), ec);
    }
    void load_all() { std::vector<std::string> e; host->load_all(e); for (auto& x : e) std::printf("    load error: %s\n", x.c_str()); }
    unsigned poll(std::vector<std::string>* e = nullptr) { return host->reload_changed(e); }
    void tick() { host->dispatch(kTick, {}); }
};

const char* st(lua::ScriptState s) {
    switch (s) { case lua::ScriptState::Loaded: return "Loaded"; case lua::ScriptState::FailedToLoad: return "FailedToLoad";
    case lua::ScriptState::Quarantined: return "Quarantined"; case lua::ScriptState::Unloaded: return "Unloaded"; }
    return "?";
}
void show(Case& c, const char* name, const char* tag) {
    lua::Script* s = c.host->find(name);
    if (!s) { std::printf("  OBSERVE %s: %s absent\n", tag, name); return; }
    std::printf("  OBSERVE %s: %s state=%s gen=%llu timers=%zu L=%p last_error=%s\n", tag, name, st(s->state()),
                (unsigned long long)s->generation(), s->L() ? api::timers::pending(s->L()) : 0,
                (void*)s->L(), s->last_load_error().empty() ? "-" : "set");
}
std::string run_lua(lua_State* L, const char* code) {
    if (luaL_dostring(L, code) != 0) { std::string e = lua_tostring(L, -1); lua_pop(L, 1); return "ERR:" + e; }
    std::string r = lua_isnoneornil(L, -1) ? "nil" : (lua_tostring(L, -1) ? lua_tostring(L, -1) : luaL_typename(L, -1));
    lua_settop(L, 0); return r;
}

// P0: a staged chunk that synchronously re-enters Host::dispatch (in game:
// nwscript.call('ExecuteScript', ...) -> vm.run_script hook -> OnRunScript
// dispatch) reaches the OLD generation, still Loaded. Its bind/unbind then
// lands on the STAGED map because staging_chunk_ is true.
void p0_nested_dispatch_during_staging() {
    std::puts("P0 nested dispatch while a new generation is staging");
    for (int variant = 0; variant < 3; ++variant) {
        Case c(variant == 0 ? "p0bind" : variant == 1 ? "p0unbind" : "p0control");
        // Old generation: its OnTick mutates bindings.
        const char* old_body = variant == 0
            ? "function OnTick() bind('OnSave', function() note('old-onsave') end) end\n"
            : variant == 1 ? "function OnTick() unbind('OnSave') end\n"
                           : "function OnTick() note('old-tick-noop') end\n";
        c.write("a", old_body);
        c.load_all();
        // New generation: registers its own OnSave handler, makes a few refs,
        // then (like a top-level ExecuteScript) re-enters dispatch.
        c.write("a", "local keep = {}\nfor i=1,4 do keep[i] = {} end\n"
                     "bind('OnSave', function() note('new-onsave') end)\n"
                     "T = kp.registertimer(100000, function() note('new-timer') return true end, {tag='ud'})\n"
                     "nested_dispatch()\n");
        std::string err;
        const bool ok = c.host->reload_one("a", err);
        show(c, "a", variant == 0 ? "bind-variant" : variant == 1 ? "unbind-variant" : "control(no-op old OnTick)");
        std::printf("  OBSERVE nested dispatch reached old generation: old-tick-noop=%u\n", count("old-tick-noop"));
        lua::Script* s = c.host->find("a");
        std::printf("  OBSERVE reload ok=%d bound(OnSave)=%d\n", ok, s && s->bound("OnSave"));
        g_notes.clear();
        const events::EventContract save = ev("OnSave");
        const events::Outcome o = c.host->dispatch(save, {});
        std::printf("  OBSERVE OnSave after commit: called=%u errored=%u new-onsave=%u old-onsave=%u\n",
                    o.called, o.errored, count("new-onsave"), count("old-onsave"));
        if (s && !s->errors().empty()) std::printf("  OBSERVE error: %.160s\n", s->errors().back().message.c_str());
    }
}

// P1: R1 keeps timers (string and function) through a failed reload, and they keep firing.
void p1_failed_reload_keeps_timers() {
    std::puts("P1 failed reload keeps timers");
    api::timers::set_clock(0);
    Case c("p1");
    c.write("a", "function cb() note('str') return true end\n"
                 "kp.registertimer(10, 'cb')\n"
                 "kp.registertimer(10, function() note('fn') return true end)\n");
    c.load_all();
    show(c, "a", "before");
    const std::size_t total0 = api::timers::pending();
    for (const char* bad : {"this is not lua (\n",
                            "kp.registertimer(10, function() note('staged-fn') return true end)\n"
                            "kp.registertimer(10, 'cb')\nerror('late throw')\n"}) {
        c.write("a", bad);
        std::vector<std::string> errs; c.poll(&errs);
        show(c, "a", "after-bad");
        std::printf("  OBSERVE global pending before=%zu after=%zu (staged timers must not leak)\n", total0, api::timers::pending());
        g_notes.clear();
        static std::uint64_t now = 0; now += 1000;
        api::timers::pump(now, 1);
        std::printf("  OBSERVE fired str=%u fn=%u staged-fn=%u\n", count("str"), count("fn"), count("staged-fn"));
    }
}

// P2: ordering hazard. New chunk top level runs BEFORE old OnScriptUnload.
void p2_topLevel_vs_old_unload() {
    std::puts("P2 new top-level side effect vs old OnScriptUnload");
    Case c("p2");
    const char* body = "setflag(GEN)\nfunction OnScriptUnload() setflag(0) end\n";
    c.write("a", std::string("GEN=1\n") + body);
    c.load_all();
    std::printf("  OBSERVE after load flag=%d\n", g_flag);
    c.write("a", std::string("GEN=2\n") + body);
    c.poll();
    show(c, "a", "after-reload");
    std::printf("  OBSERVE after reload flag=%d (the new generation set 2 at top level; old unload reset it)\n", g_flag);
}

// P3: editor save that is not an atomic rename: delete-then-create across a poll.
void p3_delete_window() {
    std::puts("P3 delete window between polls (non-atomic save)");
    Case c("p3");
    c.write("a", "function OnScriptLoad() note('load') end\nfunction OnScriptUnload() note('unload') end\nx=1\n");
    c.load_all();
    c.tick();
    // Atomic rename first (the good case).
    { std::ofstream(c.dir / "a.lua.tmp") << "function OnScriptLoad() note('load') end\nx=2\n"; }
    fs::rename(c.dir / "a.lua.tmp", c.p("a"));
    std::error_code ec; fs::last_write_time(c.p("a"), fs::last_write_time(c.p("a")) + std::chrono::seconds(4), ec);
    c.poll();
    show(c, "a", "after-atomic-rename");
    // Now delete, poll, recreate with a SYNTAX ERROR, poll.
    fs::rename(c.p("a"), c.dir / "a.lua~");
    c.poll();
    show(c, "a", "after-poll-in-window");
    { std::ofstream(c.p("a")) << "this is ( not lua\n"; }
    c.poll();
    show(c, "a", "after-recreate-broken");
    // Explicit unload does not survive the window either.
    c.write("a", "x=3\n");
    c.poll();
    std::string err; c.host->unload_one("a", err);
    show(c, "a", "explicitly-unloaded");
    fs::rename(c.p("a"), c.dir / "a.lua~");
    c.poll();
    fs::rename(c.dir / "a.lua~", c.p("a"));
    c.poll();
    show(c, "a", "after-window-on-unloaded");
}

// P4: empty (truncated) file is a valid chunk.
void p4_truncate_window() {
    std::puts("P4 truncate-then-write: poll sees an empty file");
    Case c("p4");
    c.write("a", "bind('OnTick', function() note('tick') end)\n");
    c.load_all();
    c.write("a", "");
    c.poll();
    show(c, "a", "after-empty");
    g_notes.clear(); c.tick();
    std::printf("  OBSERVE handler after empty reload fired=%u\n", count("tick"));
}

// P5: mtime equality on this filesystem. Two writes back to back.
void p5_mtime_granularity() {
    std::puts("P5 mtime granularity, back-to-back writes, no explicit bump");
    Case c("p5");
    c.write("a", "v=1\n", false);
    c.load_all();
    unsigned same = 0, n = 200;
    for (unsigned i = 0; i < n; ++i) {
        const auto t0 = fs::last_write_time(c.p("a"));
        { std::ofstream(c.p("a"), std::ios::binary) << "v=" << (i + 2) << "\n"; }
        const auto t1 = fs::last_write_time(c.p("a"));
        if (t0 == t1) ++same;
    }
    std::printf("  OBSERVE %u/%u back-to-back rewrites left mtime unchanged\n", same, n);
    // Load-then-edit with no stat in between (the host stamps at load).
    unsigned missed = 0;
    for (unsigned i = 0; i < 50; ++i) {
        Case d("p5b");
        d.write("a", "v=1\n", false);
        d.load_all();
        { std::ofstream(d.p("a"), std::ios::binary) << "v=2\n"; }
        d.poll();
        lua::Script* s = d.host->find("a");
        if (s && s->generation() == 1) ++missed;
    }
    std::printf("  OBSERVE %u/50 immediate edits after load were missed by the poll\n", missed);
}

// P6: request storm / unbounded queue.
void p6_request_storm() {
    std::puts("P6 request storm");
    Case c("p6");
    c.write("a", "x=1\n");
    c.write("b", "N=0\nfunction OnScriptLoad() N=N+1 end\n");
    c.load_all();
    lua_State* L = c.host->find("a")->L();
    auto t0 = std::chrono::steady_clock::now();
    std::printf("  OBSERVE queue 20000 reloads: %s\n",
                run_lua(L, "for i=1,20000 do kp.scripts.reload('b') end return 'queued'").c_str());
    std::printf("  OBSERVE pending_requests=%zu\n", c.host->pending_requests());
    const unsigned ran = c.host->service_requests();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - t0).count();
    show(c, "b", "after-storm");
    std::printf("  OBSERVE one service_requests ran=%u in %lld ms (one game tick)\n", ran, (long long)ms);
    // Self-reload from OnScriptLoad: one reload per service, forever.
    c.write("s", "function OnScriptLoad() kp.scripts.reload(kp.scriptname()) end\n");
    c.poll();
    for (int i = 0; i < 5; ++i) c.host->service_requests();
    show(c, "s", "self-reload-after-5-services");
    std::printf("  OBSERVE pending after 5 services=%zu\n", c.host->pending_requests());
}

// P7: odd names reaching Host::request through kp.scripts.
void p7_names() {
    std::puts("P7 names: NUL, dot-forms, case");
    Case c("p7");
    c.write("a", "x=1\n");
    { std::ofstream(c.dir / "notlua") << "note('ran notlua (no .lua extension)')\n"; }
    fs::create_directories(g_root / "outside");
    { std::ofstream(g_root / "outside" / "evil.lua") << "note('ran outside file')\n"; }
    fs::create_symlink(g_root / "outside" / "evil.lua", c.dir / "link.lua");
    c.load_all();
    lua_State* L = c.host->find("a")->L();
    std::printf("  OBSERVE symlink out of dir loaded by load_all: notes=%u state=%s path=%s\n",
                count("ran outside file"), c.host->find("link") ? st(c.host->find("link")->state()) : "absent",
                c.host->find("link") ? c.host->find("link")->path().c_str() : "-");
    const char* reqs[] = {"return kp.scripts.load('notlua\\0x')", "return kp.scripts.load('.hidden')",
                          "return kp.scripts.load('A')", "return kp.scripts.load('a.')",
                          "return kp.scripts.load(' a')"};
    std::vector<std::uint64_t> ids;
    for (const char* r : reqs) ids.push_back(std::uint64_t(std::stod(run_lua(L, r))));
    c.host->service_requests();
    for (std::size_t i = 0; i < ids.size(); ++i) {
        const lua::RequestResult* r = c.host->result(ids[i]);
        std::printf("  OBSERVE %s -> %s %s\n", reqs[i], r ? (r->status == lua::RequestStatus::Ok ? "OK" : "ERROR") : "nil",
                    r ? r->error.c_str() : "");
    }
    std::printf("  OBSERVE notlua ran=%u; scripts held=%zu\n", count("ran notlua (no .lua extension)"), c.host->scripts().size());
    for (auto& s : c.host->scripts()) {
        std::string n = s->name(); for (auto& ch : n) if (ch == 0) ch = '@';
        std::printf("    held name=[%s] path=[%s] state=%s\n", n.c_str(), s->path().c_str(), st(s->state()));
    }
}

// P7b: duplicate refusal is lexical. An alias (symlink or hard link) created
// after boot and requested by its own stem runs the same file twice.
void p7b_alias_duplicate() {
    std::puts("P7b alias duplicate");
    Case c("p7b");
    c.write("a", "function OnTick() note('a-body-tick') end\n");
    c.load_all();
    fs::create_hard_link(c.p("a"), c.p("b"));
    lua_State* L = c.host->find("a")->L();
    const std::uint64_t id = std::uint64_t(std::stod(run_lua(L, "return kp.scripts.load('b')")));
    c.host->service_requests();
    const lua::RequestResult* r = c.host->result(id);
    std::printf("  OBSERVE load('b') hard link to a.lua -> %s; equivalent=%d\n",
                r && r->status == lua::RequestStatus::Ok ? "OK" : "ERROR", int(fs::equivalent(c.p("a"), c.p("b"))));
    g_notes.clear(); c.tick();
    std::printf("  OBSERVE one tick ran the same file body %u times\n", count("a-body-tick"));
}

// P8: result() numeric edge cases.
void p8_result_numbers() {
    std::puts("P8 kp.scripts.result numeric edges");
    Case c("p8");
    c.write("a", "x=1\n");
    c.write("b", "x=1\n");
    c.load_all();
    lua_State* L = c.host->find("a")->L();
    run_lua(L, "ID = kp.scripts.reload('b')");
    c.host->service_requests();
    for (const char* e : {"return type(kp.scripts.result(ID))", "return type(kp.scripts.result(ID + 0.5))",
                          "return type(kp.scripts.result(math.huge))", "return type(kp.scripts.result(0/0))",
                          "return type(kp.scripts.result(2^64))", "return type(kp.scripts.result(-1))"})
        std::printf("  OBSERVE %s -> %s\n", e, run_lua(L, e).c_str());
}

// P9: queued requests survive load_all (console `lua reload`) and act on the new set.
void p9_queue_survives_load_all() {
    std::puts("P9 queue across load_all");
    Case c("p9");
    c.write("a", "x=1\n");
    c.load_all();
    c.host->request(lua::LifecycleOp::Unload, "a");
    c.load_all();   // console `lua reload`
    show(c, "a", "after-load_all");
    std::printf("  OBSERVE pending after load_all=%zu\n", c.host->pending_requests());
    c.host->service_requests();
    show(c, "a", "after-service");
}

// P10: unload of self from own OnScriptUnload and OnScriptLoad; unload of another during dispatch.
void p10_reentrancy() {
    std::puts("P10 reentrancy");
    Case c("p10", 1);
    c.write("a", "function OnTick() kp.scripts.unload('b'); note('a-tick') end\n");
    c.write("b", "function OnTick() note('b-tick') end\nfunction OnScriptUnload() kp.scripts.load('b'); note('b-unload') end\n");
    c.load_all();
    c.tick();
    std::printf("  OBSERVE same tick: a-tick=%u b-tick=%u (b still ran this tick)\n", count("a-tick"), count("b-tick"));
    c.host->service_requests();
    show(c, "b", "after-service-1");
    c.host->service_requests();
    show(c, "b", "after-service-2 (b re-loaded itself from its own OnScriptUnload)");
    // Timer quarantines its own script, and asks for its own reload in the same callback.
    api::timers::set_clock(0);
    c.write("q", "kp.registertimer(1, function() kp.scripts.reload('q'); error('boom') end)\n"
                 "kp.registertimer(1, function() error('boom2') end)\n");
    c.poll();
    api::timers::pump(10, 1);
    show(c, "q", "after-timer-quarantine");
    c.tick();   // dispatch sweeps quarantined state
    show(c, "q", "after-dispatch-sweep");
    c.host->service_requests();
    show(c, "q", "after-service");
}

// P11: host teardown with OnScriptUnload calling kp.scripts while bound / unbound.
void p11_teardown() {
    std::puts("P11 teardown order");
    {
        Case c("p11");
        c.write("a", "function OnScriptUnload() local ok, e = pcall(kp.scripts.list); note(ok and 'list-ok' or ('list-err:' .. tostring(e))) end\n");
        c.load_all();
        api::scripts::bind_host(nullptr);   // integration: unbind BEFORE host_.reset()
        c.host.reset();
    }
    for (auto& n : g_notes) std::printf("  OBSERVE %s\n", n.c_str());
}
}  // namespace

int main(int argc, char** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    platform::set_log_sink(&sink, nullptr);
    g_root = argc > 1 ? fs::path(argv[1]) : fs::temp_directory_path() / "kp_probe_lifecycle";
    std::error_code ec; fs::remove_all(g_root, ec); fs::create_directories(g_root);
    p0_nested_dispatch_during_staging();
    p1_failed_reload_keeps_timers();
    p2_topLevel_vs_old_unload();
    p3_delete_window();
    p4_truncate_window();
    p5_mtime_granularity();
    p6_request_storm();
    p7_names();
    p7b_alias_duplicate();
    p8_result_numbers();
    p9_queue_survives_load_all();
    p10_reentrancy();
    p11_teardown();
    std::printf("created=%u closed=%u (must match)\n", g_created, g_closed);
    return 0;
}
