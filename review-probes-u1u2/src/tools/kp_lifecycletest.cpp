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

void on_created(lua_State* L) {
    ++g_created;
    if (!g_open.insert(L).second) g_hook_error = true;
    lua_register(L, "note", l_note);
    lua_register(L, "bind", l_bind);
    lua_register(L, "unbind", l_unbind);
    lua_register(L, "request", l_request);
    lua_register(L, "sync_unload", l_sync_unload);
    lua_register(L, "sync_service", l_sync_service);
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
    void expect(bool c, const std::string& what) { if (!c) fails.push_back(what); }
    ~Result() {
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

void service_runs_snapshot_only() {
    Result r{"lifecycle.service_runs_snapshot_only"};
    Case c("snapshot");
    c.write("a", "function OnScriptLoad() request('reload', 'b') end\n");
    c.write("b", "x = 1\n");
    c.load_all();
    // load_all's OnScriptLoad already queued one reload of b.
    const std::size_t queued_at_boot = c.host->pending_requests();
    c.host->request(lua::LifecycleOp::Reload, "a");
    const unsigned first = c.host->service_requests();
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

    fs::remove_all(g_root, ec);
    std::printf("%u case(s), %u failed\n", g_cases, g_failures);
    return g_failures == 0 ? 0 : 1;
}
