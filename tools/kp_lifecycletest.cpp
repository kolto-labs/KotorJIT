// Host-only proof of the Lua script lifecycle: load, unload, reload, hot reload,
// deferred requests and the state-closing hook. No game, no runtime.
//
// Every case builds its own lua::Host over its own scratch directory, so a
// failure in one cannot leak state into the next. File mtimes are set
// explicitly rather than waited for: a sleep would make the edit-detection
// cases depend on the filesystem's timestamp granularity.
//
// Each case prints one PASS or FAIL line. The exit code is authoritative.
//
// Usage:
//   kp_lifecycletest [scratch-dir]

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <set>
#include <string>
#include <vector>

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

unsigned g_failures = 0;
unsigned g_cases = 0;

fs::path g_root;
lua::Host* g_host = nullptr;
std::vector<std::string> g_notes;
std::set<lua_State*> g_open;          // states created and not yet closed
unsigned g_created = 0, g_closed = 0;
bool g_hook_error = false;            // create/close pairing broken
std::string g_last_sync;              // what sync_unload() saw

events::EventContract make_event(const char* name) {
    events::EventContract ev;
    ev.lua_name = name;
    return ev;
}
const events::EventContract kLoadEv = make_event("OnScriptLoad");
const events::EventContract kUnloadEv = make_event("OnScriptUnload");
const events::EventContract kTickEv = make_event("OnTick");

void tool_log_sink(platform::LogLevel, const char*, void*) {}

// ---------------------------------------------------------- Lua helpers ----

int l_note(lua_State* L) {
    g_notes.emplace_back(luaL_checkstring(L, 1));
    return 0;
}

// bind(event, fn): what kp.events.register does, without the event-constant
// table. It goes through Script::owner and bind_callback exactly as compat.cpp.
int l_bind(lua_State* L) {
    const char* ev = luaL_checkstring(L, 1);
    luaL_checktype(L, 2, LUA_TFUNCTION);
    lua::Script* owner = lua::Script::owner(L);
    if (owner == nullptr) return luaL_error(L, "no owner");
    lua_pushvalue(L, 2);
    owner->bind_callback(ev, luaL_ref(L, LUA_REGISTRYINDEX));
    return 0;
}

// unbind(event): what kp.events.unregister does.
int l_unbind(lua_State* L) {
    const char* ev = luaL_checkstring(L, 1);
    if (lua::Script* owner = lua::Script::owner(L)) owner->bind_callback(ev, LUA_NOREF);
    return 0;
}

lua::LifecycleOp parse_op(lua_State* L, int idx) {
    const std::string op = luaL_checkstring(L, idx);
    if (op == "load") return lua::LifecycleOp::Load;
    if (op == "unload") return lua::LifecycleOp::Unload;
    return lua::LifecycleOp::Reload;
}

// request(op, name) -> id. Queues only.
int l_request(lua_State* L) {
    const lua::LifecycleOp op = parse_op(L, 1);
    const std::uint64_t id = g_host->request(op, luaL_checkstring(L, 2));
    lua_pushnumber(L, double(id));
    return 1;
}

// sync_unload(name): the thing Lua must never be able to do. Records the
// host's answer so the case can check it was refused.
int l_sync_unload(lua_State* L) {
    std::string err;
    const bool ok = g_host->unload_one(luaL_checkstring(L, 1), err);
    g_last_sync = ok ? "ok" : "refused:" + err;
    lua_pushboolean(L, ok);
    return 1;
}

int l_sync_service(lua_State* L) {
    lua_pushnumber(L, double(g_host->service_requests()));
    return 1;
}

int l_probe_result(lua_State* L);   // defined with service_runs_snapshot_only

// nested_tick(): re-enter Host::dispatch(OnTick) synchronously from Lua. In
// game this is a chunk's top-level nwscript.call('ExecuteScript', ...) whose
// vm.run_script hook raises OnRunScript before the call returns.
int l_nested_tick(lua_State*) {
    g_host->dispatch(kTickEv, {});
    return 0;
}

void on_created(lua_State* L) {
    ++g_created;
    if (!g_open.insert(L).second) g_hook_error = true;
    lua_register(L, "note", l_note);
    lua_register(L, "bind", l_bind);
    lua_register(L, "unbind", l_unbind);
    lua_register(L, "request", l_request);
    lua_register(L, "sync_unload", l_sync_unload);
    lua_register(L, "sync_service", l_sync_service);
    lua_register(L, "probe_result", l_probe_result);
    lua_register(L, "nested_tick", l_nested_tick);
    api::register_timers(L);
}

void on_closing(lua_State* L) {
    ++g_closed;
    // The state must still be usable here: the hook runs before lua_close.
    lua_pushnil(L);
    lua_pop(L, 1);
    if (g_open.erase(L) != 1) g_hook_error = true;
}

// ------------------------------------------------------------- fixtures ----

struct Case {
    fs::path dir;
    std::unique_ptr<lua::Host> host;

    explicit Case(const char* name, bool hot = true, unsigned budget = 8) {
        dir = g_root / name;
        std::error_code ec;
        fs::remove_all(dir, ec);
        fs::create_directories(dir);
        g_notes.clear();
        lua::HostConfig cfg;
        cfg.script_dir = dir.string();
        cfg.error_budget = budget;
        cfg.hot_reload = hot;
        cfg.on_state_created = on_created;
        cfg.on_state_closing = on_closing;
        host = std::make_unique<lua::Host>(std::move(cfg));
        host->set_lifecycle(&kLoadEv, &kUnloadEv, "k1", "test");
        g_host = host.get();
    }
    ~Case() { host.reset(); g_host = nullptr; }

    fs::path path(const char* script) const { return dir / (std::string(script) + ".lua"); }

    // Write a script body. The mtime is pushed forward past anything it had,
    // so a rewrite is always a visible edit whatever the filesystem's
    // timestamp granularity.
    void write(const char* script, const std::string& body) {
        const fs::path p = path(script);
        std::error_code ec;
        const bool existed = fs::exists(p, ec);
        const auto before = existed ? fs::last_write_time(p, ec) : fs::file_time_type{};
        { std::ofstream(p, std::ios::binary) << body; }
        if (existed) fs::last_write_time(p, before + std::chrono::seconds(2), ec);
    }

    unsigned load_all() {
        std::vector<std::string> errors;
        const unsigned n = host->load_all(errors);
        for (const auto& e : errors) std::printf("    load error: %s\n", e.c_str());
        return n;
    }

    unsigned poll(std::vector<std::string>* errors = nullptr) {
        return host->reload_changed(errors);
    }

    void tick() { host->dispatch(kTickEv, {}); }
};

unsigned count_note(const std::string& n) {
    unsigned c = 0;
    for (const auto& s : g_notes) if (s == n) ++c;
    return c;
}

int index_of(const std::string& n) {
    for (std::size_t i = 0; i < g_notes.size(); ++i) if (g_notes[i] == n) return int(i);
    return -1;
}

double lua_global_number(lua::Script* s, const char* name) {
    if (s == nullptr || s->L() == nullptr) return -1;
    lua_getglobal(s->L(), name);
    const double v = lua_tonumber(s->L(), -1);
    lua_pop(s->L(), 1);
    return v;
}

struct Result {
    explicit Result(const char* n) : name(n) {}
    const char* name;
    std::vector<std::string> fails;
    bool skipped = false;   // the scenario cannot be built here; not counted
    void expect(bool c, const std::string& what) { if (!c) fails.push_back(what); }
    ~Result() {
        if (skipped) return;
        ++g_cases;
        if (fails.empty()) { std::printf("PASS %s\n", name); return; }
        ++g_failures;
        std::printf("FAIL %s\n", name);
        for (const auto& f : fails) std::printf("     - %s\n", f.c_str());
    }
};

// ---------------------------------------------------------------- cases ----

void unload_one_raises_OnScriptUnload_once() {
    Result r{"lifecycle.unload_one_raises_OnScriptUnload_once"};
    {
        Case c("unload_once");
        c.write("a", "function OnScriptUnload() note('a:unload') end\n");
        r.expect(c.load_all() == 1, "a loads");
        std::string err;
        r.expect(c.host->unload_one("a", err), "unload_one(a) succeeds: " + err);
        lua::Script* a = c.host->find("a");
        r.expect(a && a->state() == lua::ScriptState::Unloaded, "a is Unloaded");
        r.expect(a && a->L() == nullptr, "a's state is closed");
        r.expect(!c.host->unload_one("a", err), "second unload_one(a) is refused");
        r.expect(count_note("a:unload") == 1, "OnScriptUnload ran once before teardown");
    }
    r.expect(count_note("a:unload") == 1, "host teardown does not raise it again");
}

void unload_one_drops_timers() {
    Result r{"lifecycle.unload_one_drops_timers"};
    Case c("unload_timers");
    c.write("a", "function cb() return true end\nkp.registertimer(1000, 'cb')\n");
    c.load_all();
    lua::Script* a = c.host->find("a");
    r.expect(a && a->L() && api::timers::pending(a->L()) == 1, "a holds one timer");
    const std::size_t before = api::timers::pending();
    std::string err;
    r.expect(c.host->unload_one("a", err), "unload_one(a): " + err);
    r.expect(api::timers::pending() + 1 == before, "the timer is gone");
}

void unload_one_drops_bound_handlers() {
    Result r{"lifecycle.unload_one_drops_bound_handlers"};
    Case c("unload_handlers");
    c.write("a", "bind('OnTick', function() note('a:tick') end)\n");
    c.load_all();
    c.tick();
    r.expect(count_note("a:tick") == 1, "bound OnTick fires while loaded");
    std::string err;
    r.expect(c.host->unload_one("a", err), "unload_one(a): " + err);
    lua::Script* a = c.host->find("a");
    r.expect(a && !a->bound("OnTick"), "binding dropped");
    c.tick();
    r.expect(count_note("a:tick") == 1, "OnTick no longer reaches a");
}

void reload_one_increments_generation_and_rebinds() {
    Result r{"lifecycle.reload_one_increments_generation_and_rebinds"};
    Case c("reload_gen");
    c.write("a", "bind('OnTick', function() note('v1:tick') end)\n"
                 "function OnScriptUnload() note('v1:unload') end\n");
    c.load_all();
    lua::Script* a = c.host->find("a");
    r.expect(a && a->generation() == 1, "generation 1 after first load");
    c.write("a", "note('v2:chunk')\n"
                 "bind('OnTick', function() note('v2:tick') end)\n"
                 "function OnScriptLoad() note('v2:load') end\n");
    std::string err;
    r.expect(c.host->reload_one("a", err), "reload_one(a): " + err);
    a = c.host->find("a");
    r.expect(a && a->generation() == 2, "generation 2 after reload");
    r.expect(count_note("v1:unload") == 1 && count_note("v2:load") == 1,
             "old OnScriptUnload and new OnScriptLoad each ran once");
    r.expect(index_of("v1:unload") < index_of("v2:load"), "unload of old precedes load of new");
    // R1 ordering: the new chunk runs before the old generation is told.
    r.expect(index_of("v2:chunk") < index_of("v1:unload"),
             "new chunk body runs before old OnScriptUnload (compile-before-close)");
    c.tick();
    r.expect(count_note("v2:tick") == 1 && count_note("v1:tick") == 0,
             "top-level binding from the new chunk is live, old one is gone");
}

// The old generation's OnScriptUnload runs after the new chunk has been staged.
// Anything it binds or unbinds must land on the OLD state, not on the new
// generation that is waiting to be committed.
void old_unload_cannot_touch_new_bindings() {
    Result r{"lifecycle.old_unload_cannot_touch_new_bindings"};
    Case c("old_unload_unbind");
    const char* body = "bind('OnTick', function() note('tick') end)\n"
                       "function OnScriptUnload() unbind('OnTick') end\n";
    c.write("a", body);
    c.load_all();
    c.write("a", std::string(body) + "-- edited\n");
    std::string err;
    r.expect(c.host->reload_one("a", err), "reload_one(a): " + err);
    lua::Script* a = c.host->find("a");
    r.expect(a && a->bound("OnTick"), "new generation keeps its top-level OnTick binding");
    c.tick();
    r.expect(count_note("tick") == 1, "OnTick reaches the new generation");
}

void deleted_file_unloads_on_poll() {
    Result r{"lifecycle.deleted_file_unloads_on_poll"};
    Case c("deleted");
    c.write("a", "function OnScriptUnload() note('a:unload') end\n");
    c.write("b", "x = 1\n");
    c.load_all();
    fs::remove(c.path("a"));
    // Absence has to be seen on two consecutive polls (round 2, M1).
    c.poll();
    r.expect(c.host->find("a") != nullptr && count_note("a:unload") == 0,
             "one poll of absence is not yet a delete");
    c.poll();
    r.expect(c.host->find("a") == nullptr, "a is gone from the host");
    r.expect(count_note("a:unload") == 1, "a got OnScriptUnload once");
    r.expect(c.host->find("b") && c.host->find("b")->generation() == 1, "b untouched");
    c.poll();
    r.expect(count_note("a:unload") == 1, "a second poll does nothing more");
}

void new_file_loads_on_poll() {
    Result r{"lifecycle.new_file_loads_on_poll"};
    Case c("newfile");
    c.write("a", "x = 1\n");
    c.load_all();
    c.write("b", "function OnScriptLoad() note('b:load') end\n");
    c.poll();
    lua::Script* b = c.host->find("b");
    r.expect(b && b->state() == lua::ScriptState::Loaded && b->generation() == 1, "b loaded, gen 1");
    r.expect(count_note("b:load") == 1, "b got OnScriptLoad");
    r.expect(c.host->find("a")->generation() == 1, "a not reloaded");
    c.poll();
    r.expect(c.host->find("b")->generation() == 1, "b not reloaded by an idle poll");
    r.expect(c.host->scripts().size() == 2, "no duplicate entry for b");
}

void edit_inside_first_window_detected() {
    Result r{"lifecycle.edit_inside_first_window_detected"};
    Case c("firstwindow");
    c.write("a", "v = 1\n");
    c.load_all();
    // No poll between load and edit: this is the edit the lazy stamp missed.
    c.write("a", "v = 2\n");
    const unsigned n = c.poll();
    lua::Script* a = c.host->find("a");
    r.expect(n >= 1, "poll reports a reload");
    r.expect(a && a->generation() == 2, "a is on generation 2");
    r.expect(lua_global_number(a, "v") == 2, "a runs the edited body");
}

void duplicate_load_refused() {
    Result r{"lifecycle.duplicate_load_refused"};
    Case c("duplicate");
    c.write("a", "x = 1\n");
    c.load_all();
    std::string err;
    r.expect(!c.host->load_path(c.path("a").string(), err), "load_path of a held path refused");
    r.expect(err.find("already") != std::string::npos, "error says already loaded: " + err);
    err.clear();
    r.expect(!c.host->load_one(c.path("a").string(), err), "load_one of a held path refused");
    err.clear();
    const std::string dotted = (c.dir / "." / "a.lua").string();
    r.expect(!c.host->load_path(dotted, err), "an equivalent spelling of the path is refused");
    r.expect(c.host->scripts().size() == 1, "still one script");
    r.expect(c.host->find("a")->generation() == 1, "a was not reloaded by the refusal");
}

void failed_reload_keeps_running_generation() {
    Result r{"lifecycle.failed_reload_keeps_running_generation"};
    Case c("failkeep");
    c.write("a", "bind('OnTick', function() note('v1:tick') end)\n"
                 "function OnScriptUnload() note('v1:unload') end\n");
    c.load_all();
    lua_State* oldL = c.host->find("a")->L();

    for (const char* bad : {"this is not lua (\n", "error('boom at top level')\n"}) {
        c.write("a", bad);
        std::vector<std::string> errors;
        c.poll(&errors);
        lua::Script* a = c.host->find("a");
        const std::string tag = std::string(" [") + (bad[0] == 't' ? "syntax" : "runtime") + "]";
        r.expect(!errors.empty(), "the failure is reported" + tag);
        r.expect(a && a->state() == lua::ScriptState::Loaded, "a is still Loaded" + tag);
        r.expect(a && a->L() == oldL, "a still runs the same state" + tag);
        r.expect(a && a->generation() == 1, "generation unchanged" + tag);
        r.expect(a && !a->last_load_error().empty(), "last_load_error is kept" + tag);
        r.expect(count_note("v1:unload") == 0, "old generation was not told to unload" + tag);
        g_notes.clear();
        c.tick();
        r.expect(count_note("v1:tick") == 1, "old handler still fires" + tag);
        // The stamp moved forward, so an idle poll does not retry and re-log.
        errors.clear();
        c.poll(&errors);
        r.expect(errors.empty(), "an idle poll does not retry the broken file" + tag);
    }

    c.write("a", "bind('OnTick', function() note('v2:tick') end)\n");
    c.poll();
    lua::Script* a = c.host->find("a");
    r.expect(a && a->generation() == 2 && a->last_load_error().empty(), "fixing the file reloads it");
}

void failed_first_load_is_failed() {
    Result r{"lifecycle.failed_first_load_is_FailedToLoad"};
    Case c("failfirst");
    c.write("a", "this is not lua (\n");
    r.expect(c.load_all() == 0, "a does not load");
    lua::Script* a = c.host->find("a");
    r.expect(a && a->state() == lua::ScriptState::FailedToLoad, "a is FailedToLoad");
    r.expect(a && a->L() == nullptr && a->generation() == 0, "no state, generation 0");
    c.write("a", "x = 1\n");
    c.poll();
    a = c.host->find("a");
    r.expect(a && a->state() == lua::ScriptState::Loaded && a->generation() == 1,
             "an edit to a FailedToLoad script loads it");
}

void quarantine_then_edit_recovers() {
    Result r{"lifecycle.quarantine_then_edit_recovers"};
    Case c("quarantine", true, 2);
    c.write("a", "function OnTick() error('always') end\n");
    c.load_all();
    c.tick();
    c.tick();
    lua::Script* a = c.host->find("a");
    r.expect(a && a->state() == lua::ScriptState::Quarantined && a->L() == nullptr, "a quarantined");
    c.write("a", "function OnTick() note('fixed') end\n");
    c.poll();
    a = c.host->find("a");
    r.expect(a && a->state() == lua::ScriptState::Loaded && a->generation() == 2, "edit brings a back");
    r.expect(a && a->error_count() == 0, "error history cleared");
    c.tick();
    r.expect(count_note("fixed") == 1, "fixed handler runs");
}

void state_closing_hook_once_per_close() {
    Result r{"lifecycle.state_closing_hook_once_per_close"};
    const unsigned c0 = g_created, k0 = g_closed;
    g_hook_error = false;
    {
        Case c("closing", true, 1);
        c.write("a", "x = 1\n");
        c.write("b", "function OnTick() error('x') end\n");
        c.load_all();                                       // 2 creates
        std::string err;
        c.write("a", "x = 2\n");
        c.host->reload_one("a", err);                       // +1 create, +1 close
        c.write("a", "not lua (\n");
        c.host->reload_one("a", err);                       // +1 create, +1 close (discarded)
        c.tick();                                           // b quarantined: +1 close
        c.host->unload_one("a", err);                       // +1 close
        c.write("b", "x = 3\n");
        c.host->reload_one("b", err);                       // +1 create
        r.expect(g_created - c0 == 5, "5 states created, saw " + std::to_string(g_created - c0));
        r.expect(g_closed - k0 == 4, "4 states closed so far, saw " + std::to_string(g_closed - k0));
    }                                                       // unload_all: +1 close
    r.expect(g_created - c0 == g_closed - k0, "every created state was closed exactly once");
    r.expect(!g_hook_error, "each close matched an open state, and no state closed twice");
    r.expect(g_open.empty(), "no state left open");
}

void request_from_own_callback_deferred() {
    Result r{"lifecycle.request_from_own_callback_deferred"};
    Case c("req_callback");
    c.write("a", "bind('OnTick', function()\n"
                 "  req_id = request('unload', 'a')\n"
                 "  note('after-request')\n"
                 "end)\n"
                 "function OnScriptUnload() note('a:unload') end\n");
    c.load_all();
    c.tick();
    lua::Script* a = c.host->find("a");
    r.expect(count_note("after-request") == 1, "callback kept running after request()");
    r.expect(a && a->state() == lua::ScriptState::Loaded && a->L() != nullptr,
             "a is still loaded after dispatch returns");
    const std::uint64_t id = std::uint64_t(lua_global_number(a, "req_id"));
    const lua::RequestResult* res = c.host->result(id);
    r.expect(id != 0 && res && res->status == lua::RequestStatus::Pending, "request is pending");
    r.expect(c.host->pending_requests() == 1, "one request queued");
    r.expect(c.host->service_requests() == 1, "service runs it");
    a = c.host->find("a");
    r.expect(a && a->state() == lua::ScriptState::Unloaded, "a unloaded by service");
    res = c.host->result(id);
    r.expect(res && res->status == lua::RequestStatus::Ok, "result is ok");
    r.expect(count_note("a:unload") == 1, "OnScriptUnload once");
}

void request_from_timer_deferred() {
    Result r{"lifecycle.request_from_timer_deferred"};
    api::timers::set_clock(0);
    Case c("req_timer");
    c.write("a", "function cb() req_id = request('reload', 'a'); note('timer'); return false end\n"
                 "kp.registertimer(10, 'cb')\n");
    c.load_all();
    api::timers::pump(100, 1);
    lua::Script* a = c.host->find("a");
    r.expect(count_note("timer") == 1, "timer fired");
    r.expect(a && a->generation() == 1 && a->L() != nullptr, "no reload happened inside the timer");
    const std::uint64_t id = std::uint64_t(lua_global_number(a, "req_id"));
    r.expect(c.host->service_requests() == 1, "service runs it");
    a = c.host->find("a");
    r.expect(a && a->generation() == 2, "reloaded at service time");
    const lua::RequestResult* res = c.host->result(id);
    r.expect(res && res->status == lua::RequestStatus::Ok && res->generation == 2,
             "result ok with generation 2");
}

void unknown_name_result_error() {
    Result r{"lifecycle.unknown_name_result_error"};
    Case c("unknown");
    c.write("a", "x = 1\n");
    c.load_all();
    const std::uint64_t u = c.host->request(lua::LifecycleOp::Unload, "nope");
    const std::uint64_t l = c.host->request(lua::LifecycleOp::Load, "../escape");
    const std::uint64_t e = c.host->request(lua::LifecycleOp::Reload, "");
    c.host->service_requests();
    const lua::RequestResult* ru = c.host->result(u);
    const lua::RequestResult* rl = c.host->result(l);
    const lua::RequestResult* re = c.host->result(e);
    r.expect(ru && ru->status == lua::RequestStatus::Error &&
             ru->error.find("nope") != std::string::npos, "unload of unknown name is an error");
    r.expect(rl && rl->status == lua::RequestStatus::Error, "load of a path-like name is an error");
    r.expect(re && re->status == lua::RequestStatus::Error, "empty name is an error");
    r.expect(c.host->result(999999) == nullptr, "an id never issued has no result");
    r.expect(c.host->scripts().size() == 1, "nothing was added");
}

void priority_resort_after_reload() {
    Result r{"lifecycle.priority_resort_after_reload"};
    Case c("priority");
    c.write("a", "x = 1\n");
    c.write("b", "x = 1\n");
    c.load_all();
    r.expect(c.host->scripts()[0]->name() == "a", "a first at equal priority");
    c.write("b", "priority = 10\n");
    std::string err;
    c.host->reload_one("b", err);
    r.expect(c.host->scripts()[0]->name() == "b", "b first after reload_one raises its priority");
    c.write("b", "priority = -5\n");
    c.poll();
    r.expect(c.host->scripts()[0]->name() == "a", "a first after a hot reload lowers b");
}

void explicit_unload_survives_poll() {
    Result r{"lifecycle.explicit_unload_survives_poll"};
    Case c("unload_sticks");
    c.write("a", "x = 1\n");
    c.load_all();
    std::string err;
    c.host->unload_one("a", err);
    c.write("a", "x = 2\n");
    c.poll();
    lua::Script* a = c.host->find("a");
    r.expect(a && a->state() == lua::ScriptState::Unloaded && a->generation() == 1,
             "hot reload leaves an explicitly unloaded script alone");
    const std::uint64_t id = c.host->request(lua::LifecycleOp::Load, "a");
    c.host->service_requests();
    a = c.host->find("a");
    r.expect(a && a->state() == lua::ScriptState::Loaded && a->generation() == 2,
             "load request brings it back as generation 2");
    r.expect(c.host->result(id) && c.host->result(id)->status == lua::RequestStatus::Ok, "load ok");
    const std::uint64_t again = c.host->request(lua::LifecycleOp::Load, "a");
    c.host->service_requests();
    r.expect(c.host->result(again) && c.host->result(again)->status == lua::RequestStatus::Error,
             "load of a loaded script is an error");
    c.host->unload_one("a", err);
    fs::remove(c.path("a"));
    c.poll();
    c.poll();
    r.expect(c.host->find("a") == nullptr, "an unloaded script whose file is deleted is dropped");
}

void load_request_for_new_file() {
    Result r{"lifecycle.load_request_for_new_file"};
    Case c("load_new", /*hot=*/false);
    c.write("a", "x = 1\n");
    c.load_all();
    c.write("b", "function OnScriptLoad() note('b:load') end\n");
    const std::uint64_t id = c.host->request(lua::LifecycleOp::Load, "b");
    r.expect(c.host->find("b") == nullptr, "nothing happens before service");
    c.host->service_requests();
    lua::Script* b = c.host->find("b");
    r.expect(b && b->state() == lua::ScriptState::Loaded, "b loaded by request");
    r.expect(c.host->result(id) && c.host->result(id)->generation == 1, "result carries generation 1");
    r.expect(count_note("b:load") == 1, "b got OnScriptLoad");
}

// What result() says about the request that is running right now.
std::string g_inflight_seen;
int l_probe_result(lua_State* L) {
    const lua::RequestResult* r = g_host->result(std::uint64_t(luaL_checknumber(L, 1)));
    g_inflight_seen = r == nullptr ? "nil"
                    : r->status == lua::RequestStatus::Pending ? "pending" : "done";
    return 0;
}

void service_runs_snapshot_only() {
    Result r{"lifecycle.service_runs_snapshot_only"};
    Case c("snapshot");
    c.write("a", "function OnScriptLoad() request('reload', 'b'); if inflight then probe_result(inflight) end end\n");
    c.write("b", "x = 1\n");
    c.load_all();
    // load_all's OnScriptLoad already queued one reload of b.
    const std::size_t queued_at_boot = c.host->pending_requests();
    const std::uint64_t mine = c.host->request(lua::LifecycleOp::Reload, "a");
    // The next generation of a reads `inflight` at load and asks about it.
    c.write("a", "inflight = " + std::to_string(mine) + "\n"
                 "function OnScriptLoad() request('reload', 'b'); probe_result(inflight) end\n");
    g_inflight_seen.clear();
    const unsigned first = c.host->service_requests();
    r.expect(g_inflight_seen == "pending",
             "a request being serviced reads as pending, not unknown: " + g_inflight_seen);
    r.expect(first == queued_at_boot + 1, "service ran only what was queued before it started");
    r.expect(c.host->pending_requests() == 1, "the request a's OnScriptLoad made waits");
    c.host->service_requests();
    r.expect(c.host->pending_requests() == 0, "the next service drains it");
}

void sync_refused_while_dispatching() {
    Result r{"lifecycle.sync_refused_while_dispatching"};
    Case c("sync_refused");
    c.write("a", "function OnTick() sync_unload('a'); served = sync_service(); note('still-here') end\n");
    c.load_all();
    c.host->request(lua::LifecycleOp::Reload, "a");
    g_last_sync.clear();
    c.tick();
    lua::Script* a = c.host->find("a");
    r.expect(g_last_sync.rfind("refused:", 0) == 0, "unload_one from inside a callback is refused: " + g_last_sync);
    r.expect(count_note("still-here") == 1, "the callback finished");
    r.expect(lua_global_number(a, "served") == 0, "service_requests from inside a callback runs nothing");
    r.expect(a && a->state() == lua::ScriptState::Loaded && a->generation() == 1, "a untouched");
    r.expect(c.host->pending_requests() == 1, "the queued request is still there");
    r.expect(!c.host->busy(), "host not busy after dispatch");
}

// ------------------------------------------------------- round 2 cases ----

// I1 (review probe P0). The new chunk's top level re-enters dispatch. The old
// generation is still Loaded, but it must not run while its successor's chunk
// runs: a bind or unbind from it would land in the staged generation's map.
void nested_dispatch_during_staging_skips_old() {
    Result r{"lifecycle.nested_dispatch_during_staging_skips_old"};
    const events::EventContract save = make_event("OnSave");
    const char* variants[][2] = {
        {"bind", "function OnTick() note('old:tick'); bind('OnSave', function() note('old:save') end) end\n"},
        {"unbind", "function OnTick() note('old:tick'); unbind('OnSave') end\n"},
        {"noop", "function OnTick() note('old:tick') end\n"},
    };
    for (const auto& v : variants) {
        const std::string tag = std::string(" [") + v[0] + "]";
        Case c((std::string("nested_") + v[0]).c_str());
        c.write("a", v[1]);
        c.load_all();
        c.write("a", "local keep = {}\nfor i = 1, 4 do keep[i] = {} end\n"
                     "bind('OnSave', function() note('new:save') end)\n"
                     "nested_tick()\n");
        std::string err;
        r.expect(c.host->reload_one("a", err), "reload_one(a)" + tag + ": " + err);
        r.expect(count_note("old:tick") == 0,
                 "the old generation got no event while the new chunk ran" + tag);
        lua::Script* a = c.host->find("a");
        r.expect(a && a->generation() == 2 && a->bound("OnSave"),
                 "the new generation holds its own OnSave binding" + tag);
        g_notes.clear();
        const events::Outcome o = c.host->dispatch(save, {});
        r.expect(o.called == 1 && count_note("new:save") == 1 && count_note("old:save") == 0,
                 "OnSave reaches the new handler, called=" + std::to_string(o.called) + tag);
    }
}

// I2. Duplicate refusal is by file identity. A hard link to a held script is
// the same file under another name; requesting it by its own stem must not run
// the body twice, and the poll must not log it as an error every time.
void alias_of_held_script_refused() {
    Result r{"lifecycle.alias_of_held_script_refused"};
    Case c("alias");
    c.write("a", "function OnTick() note('a:tick') end\n");
    c.load_all();
    std::error_code ec;
    fs::create_hard_link(c.path("a"), c.path("b"), ec);
    if (ec) { std::printf("NOTE  %s: no hard links here (%s); case not run\n", r.name, ec.message().c_str()); r.skipped = true; return; }
    const std::uint64_t id = c.host->request(lua::LifecycleOp::Load, "b");
    c.host->service_requests();
    const lua::RequestResult* res = c.host->result(id);
    r.expect(res && res->status == lua::RequestStatus::Error, "load of an alias of a held file is an error");
    std::vector<std::string> errors;
    c.poll(&errors);
    c.poll(&errors);
    r.expect(errors.empty(), "the poll skips the alias quietly (" + std::to_string(errors.size()) + " errors)");
    r.expect(c.host->scripts().size() == 1, "one script held, saw " + std::to_string(c.host->scripts().size()));
    c.tick();
    r.expect(count_note("a:tick") == 1, "one tick runs the body once, saw " + std::to_string(count_note("a:tick")));
}

// I2 on a case-insensitive directory (review casefold probe). Needs
// KP_CASEFOLD_DIR to name an empty case-insensitive directory; on a
// case-sensitive filesystem the case cannot be built and is not counted.
void case_variant_request_refused() {
    const char* dir_env = std::getenv("KP_CASEFOLD_DIR");
    if (dir_env == nullptr || *dir_env == '\0') {
        std::printf("NOTE  lifecycle.case_variant_request_refused: KP_CASEFOLD_DIR unset; case not run\n");
        return;
    }
    Result r{"lifecycle.case_variant_request_refused"};
    const fs::path dir = dir_env;
    { std::ofstream(dir / "10_cover.lua") << "function OnTick() note('cover') end\n"; }
    if (!fs::exists(dir / "10_COVER.lua")) {
        r.expect(false, "KP_CASEFOLD_DIR is not case-insensitive");
        return;
    }
    lua::HostConfig cfg;
    cfg.script_dir = dir.string();
    cfg.on_state_created = on_created;
    cfg.on_state_closing = on_closing;
    lua::Host h(std::move(cfg));
    h.set_lifecycle(&kLoadEv, &kUnloadEv, "k1", "casefold");
    g_host = &h;
    g_notes.clear();
    std::vector<std::string> errs;
    h.load_all(errs);
    const std::uint64_t a = h.request(lua::LifecycleOp::Load, "10_COVER");
    { std::ofstream(dir / "newfile.lua") << "function OnTick() note('newfile') end\n"; }
    const std::uint64_t b = h.request(lua::LifecycleOp::Load, "NEWFILE");
    h.service_requests();
    const lua::RequestResult* ra = h.result(a);
    const lua::RequestResult* rb = h.result(b);
    r.expect(ra && ra->status == lua::RequestStatus::Error, "load of a case variant of a held script is an error");
    r.expect(rb && rb->status == lua::RequestStatus::Ok, "load of a new file by another case works");
    r.expect(h.find("newfile") != nullptr, "the new script is held under its on-disk spelling");
    std::vector<std::string> poll_errs;
    h.reload_changed(&poll_errs);
    r.expect(poll_errs.empty(), "the poll adds nothing and logs nothing");
    r.expect(h.scripts().size() == 2, "2 files on disk, " + std::to_string(h.scripts().size()) + " held");
    h.dispatch(kTickEv, {});
    r.expect(count_note("cover") == 1 && count_note("newfile") == 1,
             "one tick runs each file once, saw " + std::to_string(g_notes.size()) + " bodies");
    g_host = nullptr;
}

// M1. A non-atomic save (rename away, then write) seen by one poll must not
// drop the script, lose R1, or undo an explicit unload.
void delete_window_keeps_script() {
    Result r{"lifecycle.delete_window_keeps_script"};
    Case c("delete_window");
    c.write("a", "bind('OnTick', function() note('v1:tick') end)\n"
                 "function OnScriptUnload() note('v1:unload') end\n");
    c.load_all();
    lua_State* oldL = c.host->find("a")->L();
    fs::rename(c.path("a"), c.dir / "a.lua~");
    c.poll();
    lua::Script* a = c.host->find("a");
    r.expect(a && a->state() == lua::ScriptState::Loaded && a->L() == oldL,
             "one poll inside the window keeps a running");
    r.expect(count_note("v1:unload") == 0, "no OnScriptUnload inside the window");
    { std::ofstream(c.path("a"), std::ios::binary) << "this is ( not lua\n"; }
    std::error_code ec;
    fs::last_write_time(c.path("a"), fs::last_write_time(c.dir / "a.lua~") + std::chrono::seconds(4), ec);
    fs::remove(c.dir / "a.lua~");
    c.poll();
    a = c.host->find("a");
    r.expect(a && a->state() == lua::ScriptState::Loaded && a->L() == oldL && a->generation() == 1,
             "a broken rewrite after the window keeps the running generation (R1)");
    c.tick();
    r.expect(count_note("v1:tick") == 1, "the old handler still fires");

    std::string err;
    c.write("a", "x = 3\n");
    c.poll();
    r.expect(c.host->unload_one("a", err), "unload_one(a): " + err);
    fs::rename(c.path("a"), c.dir / "a.lua~");
    c.poll();
    fs::rename(c.dir / "a.lua~", c.path("a"));
    c.poll();
    a = c.host->find("a");
    r.expect(a && a->state() == lua::ScriptState::Unloaded, "an explicit unload survives the window");
}

// W2 (round 3, ported from the reviewer's probe_r2.cpp sub-case A). A
// held file is deleted, observed absent on exactly one poll (inside
// kMissingPollsToDrop's grace window, so R1 still applies), then recreated
// with a DIFFERENT body forced to the SAME mtime the original stamp
// recorded. On a coarse filesystem clock (measured 17/20 collisions under
// Wine for writes 150ms apart; forced here to 100% so the case is
// deterministic on any filesystem) an mtime-only poll cannot see this as a
// change and keeps running the deleted generation's content forever. v1 and
// v2 are the same length so a size-only check cannot catch it either --
// only file identity (this is a new file, not the old one still open) or a
// content hash proves it changed.
void delete_then_recreate_same_mtime_promotes_generation() {
    Result r{"lifecycle.delete_then_recreate_same_mtime_promotes_generation"};
    Case c("recreate_a");
    const std::string v1 = "function OnScriptUnload() note('a:unload') end\n"
                           "function OnTick() note('a:v1') end\n";
    const std::string v2 = "function OnScriptUnload() note('a:unload') end\n"
                           "function OnTick() note('a:v2') end\n";
    if (v1.size() != v2.size()) { r.expect(false, "test fixture bug: v1/v2 length mismatch"); return; }
    c.write("a", v1);
    c.load_all();
    std::error_code ec;
    const auto t0 = fs::last_write_time(c.path("a"), ec);
    fs::remove(c.path("a"));
    c.poll();   // one absent poll: inside the grace window, nothing happens yet
    lua::Script* a = c.host->find("a");
    r.expect(a != nullptr && a->generation() == 1, "one absent poll keeps the script (M1 grace window)");
    { std::ofstream(c.path("a"), std::ios::binary) << v2; }
    fs::last_write_time(c.path("a"), t0, ec);   // force the exact same mtime as before the delete
    r.expect(!ec, "forcing mtime on the recreated file: " + ec.message());
    c.poll();
    a = c.host->find("a");
    r.expect(a != nullptr && a->generation() == 2,
             "the recreated file is a new generation, gen=" + std::to_string(a ? a->generation() : 0));
    r.expect(count_note("a:unload") == 1, "the deleted generation's OnScriptUnload fired once");
    c.tick();
    r.expect(count_note("a:v2") == 1 && count_note("a:v1") == 0,
             "the new body runs, not the stale one (v1=" + std::to_string(count_note("a:v1")) +
             " v2=" + std::to_string(count_note("a:v2")) + ")");
}

// W2 variant b (round 3). Same recipe, but the delete and the recreate both
// land BETWEEN two polls, so the file is never observed missing at all --
// missing_[] never increments, so any fix that only re-checks identity on a
// missing-then-present transition would not fire here. This is the case
// that needs the racy-mtime content check: identity, size and mtime can all
// coincide with the old stamp (a filesystem is free to reuse an inode
// quickly after a delete) when the recreate happens close enough in time to
// the original write that the clock has not visibly moved.
void delete_and_recreate_between_polls_promotes_generation() {
    Result r{"lifecycle.delete_and_recreate_between_polls_promotes_generation"};
    Case c("recreate_b");
    const std::string v1 = "function OnScriptUnload() note('b:unload') end\n"
                           "function OnTick() note('b:v1') end\n";
    const std::string v2 = "function OnScriptUnload() note('b:unload') end\n"
                           "function OnTick() note('b:v2') end\n";
    if (v1.size() != v2.size()) { r.expect(false, "test fixture bug: v1/v2 length mismatch"); return; }
    c.write("a", v1);
    c.load_all();
    std::error_code ec;
    const auto t0 = fs::last_write_time(c.path("a"), ec);
    fs::remove(c.path("a"));
    { std::ofstream(c.path("a"), std::ios::binary) << v2; }
    fs::last_write_time(c.path("a"), t0, ec);
    r.expect(!ec, "forcing mtime on the recreated file: " + ec.message());
    c.poll();   // the only poll: sees the file present throughout, never missing
    lua::Script* a = c.host->find("a");
    r.expect(a != nullptr && a->generation() == 2,
             "a single poll still promotes the new generation, gen=" +
             std::to_string(a ? a->generation() : 0));
    r.expect(count_note("b:unload") == 1, "the deleted generation's OnScriptUnload fired once");
    c.tick();
    r.expect(count_note("b:v2") == 1 && count_note("b:v1") == 0,
             "the new body runs, not the stale one (v1=" + std::to_string(count_note("b:v1")) +
             " v2=" + std::to_string(count_note("b:v2")) + ")");
}

// M2. A truncated file mid-write is not a new generation.
void empty_file_not_reloaded() {
    Result r{"lifecycle.empty_file_not_reloaded"};
    Case c("empty_file");
    c.write("a", "bind('OnTick', function() note('tick') end)\n");
    c.load_all();
    c.write("a", "");
    c.poll();
    lua::Script* a = c.host->find("a");
    r.expect(a && a->generation() == 1, "an empty file does not replace generation 1");
    c.tick();
    r.expect(count_note("tick") == 1, "the handler still fires");
    c.write("a", "bind('OnTick', function() note('tick2') end)\n");
    c.poll();
    a = c.host->find("a");
    r.expect(a && a->generation() == 2, "the finished write reloads");
    c.write("z", "");
    c.poll();
    r.expect(c.host->find("z") == nullptr, "an empty new file is not loaded yet");
}

// M3. Identical pending requests coalesce, the queue is bounded, one service
// does bounded work, and a script cannot reload itself from OnScriptLoad.
void request_queue_coalesced_and_bounded() {
    Result r{"lifecycle.request_queue_coalesced_and_bounded"};
    Case c("queue_bound");
    c.write("b", "x = 1\n");
    c.write("s", "function OnScriptLoad() self_id = request('reload', 's') end\n");
    c.load_all();
    const std::uint64_t first = c.host->request(lua::LifecycleOp::Reload, "b");
    std::uint64_t last = first;
    for (int i = 0; i < 1000; ++i) last = c.host->request(lua::LifecycleOp::Reload, "b");
    r.expect(last == first, "a repeat of a pending request returns its id");
    r.expect(c.host->pending_requests() == 1, "1000 reloads of b coalesce to 1, saw " +
             std::to_string(c.host->pending_requests()));
    c.host->service_requests();
    r.expect(c.host->find("b")->generation() == 2, "b reloaded once");

    lua::Script* s = c.host->find("s");
    const std::uint64_t self_id = std::uint64_t(lua_global_number(s, "self_id"));
    const lua::RequestResult* sr = c.host->result(self_id);
    r.expect(sr && sr->status == lua::RequestStatus::Error, "a self-reload from OnScriptLoad is refused");
    for (int i = 0; i < 5; ++i) c.host->service_requests();
    r.expect(c.host->find("s")->generation() == 1, "s does not reload every service, gen=" +
             std::to_string(c.host->find("s")->generation()));

    std::vector<std::uint64_t> ids;
    for (int i = 0; i < 100; ++i)
        ids.push_back(c.host->request(lua::LifecycleOp::Unload, "n" + std::to_string(i)));
    r.expect(c.host->pending_requests() == 64, "the queue holds at most 64, saw " +
             std::to_string(c.host->pending_requests()));
    const lua::RequestResult* over = c.host->result(ids.back());
    r.expect(over && over->status == lua::RequestStatus::Error, "an overflowing request fails at once");
    const unsigned ran = c.host->service_requests();
    r.expect(ran == 16, "one service runs at most 16, ran " + std::to_string(ran));
    r.expect(c.host->pending_requests() == 48, "the rest wait, saw " + std::to_string(c.host->pending_requests()));
    const std::uint64_t late = c.host->request(lua::LifecycleOp::Unload, "late");
    c.host->service_requests();
    r.expect(c.host->result(ids[16]) && c.host->result(ids[16])->status != lua::RequestStatus::Pending,
             "leftovers run before requests made after them");
    r.expect(c.host->result(late) && c.host->result(late)->status == lua::RequestStatus::Pending,
             "a later request still waits its turn");
}

// M4. A NUL byte is not a script name, even when a file matches the prefix.
void nul_name_refused() {
    Result r{"lifecycle.nul_name_refused"};
    Case c("nul_name");
    c.write("a", "x = 1\n");
    { std::ofstream(c.dir / "notlua") << "note('ran notlua')\n"; }
    c.load_all();
    const std::uint64_t id = c.host->request(lua::LifecycleOp::Load, std::string("notlua\0x", 8));
    c.host->service_requests();
    const lua::RequestResult* res = c.host->result(id);
    r.expect(res && res->status == lua::RequestStatus::Error, "load('notlua\\0x') is an error");
    r.expect(count_note("ran notlua") == 0, "the file without .lua did not run");
    r.expect(c.host->scripts().size() == 1, "nothing was added");
}

// M5. Requests queued before a host-wide reload do not act on the new set.
void queued_requests_discarded_by_load_all() {
    Result r{"lifecycle.queued_requests_discarded_by_load_all"};
    Case c("queue_reload");
    c.write("a", "x = 1\n");
    c.load_all();
    const std::uint64_t id = c.host->request(lua::LifecycleOp::Unload, "a");
    c.load_all();
    r.expect(c.host->pending_requests() == 0, "load_all emptied the queue");
    const lua::RequestResult* res = c.host->result(id);
    r.expect(res && res->status == lua::RequestStatus::Error, "the old request reads as an error, not nil");
    c.host->service_requests();
    lua::Script* a = c.host->find("a");
    r.expect(a && a->state() == lua::ScriptState::Loaded, "the reloaded a is still loaded");
}

// M9. A symlink in the scripts dir may point inside it, not outside it.
void symlink_outside_dir_refused() {
    Result r{"lifecycle.symlink_outside_dir_refused"};
    Case c("symlinks");
    const fs::path outside = g_root / "symlinks_outside";
    std::error_code ec;
    fs::remove_all(outside, ec);
    fs::create_directories(outside);
    fs::create_directories(c.dir / "sub");
    { std::ofstream(outside / "evil.lua") << "note('outside')\n"; }
    { std::ofstream(c.dir / "sub" / "inner.lua") << "note('inside')\n"; }
    // A sibling whose name starts with the script dir's name must not pass a
    // prefix check.
    const fs::path sibling = fs::path(c.dir.string() + "2");
    fs::remove_all(sibling, ec);
    fs::create_directories(sibling);
    { std::ofstream(sibling / "twin.lua") << "note('sibling')\n"; }
    fs::create_symlink(outside / "evil.lua", c.path("link"), ec);
    if (ec) { std::printf("NOTE  %s: no symlinks here (%s); case not run\n", r.name, ec.message().c_str()); r.skipped = true; return; }
    fs::create_symlink(c.dir / "sub" / "inner.lua", c.path("inner"), ec);
    fs::create_symlink(sibling / "twin.lua", c.path("twin"), ec);
    std::vector<std::string> errors;
    c.host->load_all(errors);
    r.expect(count_note("outside") == 0 && c.host->find("link") == nullptr, "the escaping symlink is not loaded");
    r.expect(count_note("sibling") == 0 && c.host->find("twin") == nullptr, "a prefix-sibling symlink is not loaded");
    r.expect(count_note("inside") == 1 && c.host->find("inner") != nullptr, "a symlink inside the dir loads");
    r.expect(errors.size() == 2, "both refusals are reported, saw " + std::to_string(errors.size()));
    const std::uint64_t id = c.host->request(lua::LifecycleOp::Load, "link");
    c.host->service_requests();
    r.expect(c.host->result(id) && c.host->result(id)->status == lua::RequestStatus::Error,
             "a load request for the escaping symlink is an error");
    fs::remove_all(sibling, ec);
    fs::remove_all(outside, ec);
}

}  // namespace

int main(int argc, char** argv) {
    platform::set_log_sink(&tool_log_sink, nullptr);
    g_root = argc > 1 ? fs::path(argv[1]) : fs::temp_directory_path() / "kp_lifecycletest";
    std::error_code ec;
    fs::remove_all(g_root, ec);
    fs::create_directories(g_root, ec);
    if (ec) { std::fprintf(stderr, "cannot create %s\n", g_root.string().c_str()); return 2; }
    api::timers::set_clock(0);

    unload_one_raises_OnScriptUnload_once();
    unload_one_drops_timers();
    unload_one_drops_bound_handlers();
    reload_one_increments_generation_and_rebinds();
    old_unload_cannot_touch_new_bindings();
    deleted_file_unloads_on_poll();
    new_file_loads_on_poll();
    edit_inside_first_window_detected();
    duplicate_load_refused();
    failed_reload_keeps_running_generation();
    failed_first_load_is_failed();
    quarantine_then_edit_recovers();
    state_closing_hook_once_per_close();
    request_from_own_callback_deferred();
    request_from_timer_deferred();
    unknown_name_result_error();
    priority_resort_after_reload();
    explicit_unload_survives_poll();
    load_request_for_new_file();
    service_runs_snapshot_only();
    sync_refused_while_dispatching();
    nested_dispatch_during_staging_skips_old();
    alias_of_held_script_refused();
    case_variant_request_refused();
    delete_window_keeps_script();
    delete_then_recreate_same_mtime_promotes_generation();
    delete_and_recreate_between_polls_promotes_generation();
    empty_file_not_reloaded();
    request_queue_coalesced_and_bounded();
    nul_name_refused();
    queued_requests_discarded_by_load_all();
    symlink_outside_dir_refused();

    fs::remove_all(g_root, ec);
    std::printf("%u case(s), %u failed\n", g_cases, g_failures);
    return g_failures == 0 ? 0 : 1;
}
