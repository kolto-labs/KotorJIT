// Host-only proof of kp.scripts, kp.scriptname and kp.scriptdir. No game.
//
// Scripts are real files in a scratch directory run by the real lua::Host, with
// the module installed through on_state_created exactly where the runtime will
// install it. The console state is a bare lua_State with no owning Script,
// which is what the F12 console gets.
//
// Each case prints one PASS or FAIL line. The exit code is authoritative.
//
// Usage:
//   kp_scriptsapitest [scratch-dir]

#include <cctype>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <memory>
#include <sstream>
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

#ifndef KP_REPO
#define KP_REPO "."
#endif

namespace fs = std::filesystem;
using namespace kp;

namespace {

unsigned g_failures = 0, g_cases = 0;
fs::path g_root;
std::vector<std::string> g_notes;

events::EventContract make_event(const char* name) {
    events::EventContract ev;
    ev.lua_name = name;
    return ev;
}
const events::EventContract kLoadEv = make_event("OnScriptLoad");
const events::EventContract kUnloadEv = make_event("OnScriptUnload");
const events::EventContract kTickEv = make_event("OnTick");

void tool_log_sink(platform::LogLevel, const char*, void*) {}

int l_note(lua_State* L) { g_notes.emplace_back(luaL_checkstring(L, 1)); return 0; }

int l_bind(lua_State* L) {
    const char* ev = luaL_checkstring(L, 1);
    luaL_checktype(L, 2, LUA_TFUNCTION);
    lua::Script* owner = lua::Script::owner(L);
    if (!owner) return luaL_error(L, "no owner");
    lua_pushvalue(L, 2);
    owner->bind_callback(ev, luaL_ref(L, LUA_REGISTRYINDEX));
    return 0;
}

void on_created(lua_State* L) {
    lua_register(L, "note", l_note);
    lua_register(L, "bind", l_bind);
    api::register_timers(L);
    api::scripts::register_all(L);
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

struct Case {
    fs::path dir;
    std::unique_ptr<lua::Host> host;
    explicit Case(const char* name) {
        dir = g_root / name;
        std::error_code ec;
        fs::remove_all(dir, ec);
        fs::create_directories(dir);
        g_notes.clear();
        lua::HostConfig cfg;
        cfg.script_dir = dir.string();
        cfg.hot_reload = false;
        cfg.on_state_created = on_created;
        host = std::make_unique<lua::Host>(std::move(cfg));
        host->set_lifecycle(&kLoadEv, &kUnloadEv, "k1", "test");
        api::scripts::bind_host(host.get());
    }
    ~Case() {
        if (host) host->unload_all();
        api::scripts::bind_host(nullptr);
        host.reset();
    }
    void write(const char* n, const std::string& body) {
        std::ofstream(dir / (std::string(n) + ".lua"), std::ios::binary) << body;
    }
    void load_all() {
        std::vector<std::string> errors;
        host->load_all(errors);
        for (const auto& e : errors) std::printf("    load error: %s\n", e.c_str());
    }
    void tick() { host->dispatch(kTickEv, {}); }
};

// Run `code` in `L` under pcall. Returns "" on success, else the error text.
// Results are left in the global `out`.
std::string run(lua_State* L, const std::string& code) {
    if (L == nullptr) return "no state (script did not load)";
    if (luaL_loadstring(L, code.c_str()) != 0 || lua_pcall(L, 0, 0, 0) != 0) {
        std::string e = lua_tostring(L, -1) ? lua_tostring(L, -1) : "?";
        lua_pop(L, 1);
        return e;
    }
    return "";
}

std::string global_string(lua_State* L, const char* name) {
    if (L == nullptr) return "<no state>";
    lua_getglobal(L, name);
    std::string v = lua_isstring(L, -1) ? lua_tostring(L, -1) : std::string("<") + luaL_typename(L, -1) + ">";
    lua_pop(L, 1);
    return v;
}

unsigned count_note(const std::string& n) {
    unsigned c = 0;
    for (const auto& s : g_notes) if (s == n) ++c;
    return c;
}

// A bare state, the way the F12 console builds one: no owning Script.
struct ConsoleState {
    lua_State* L = luaL_newstate();
    ConsoleState() { luaL_openlibs(L); api::scripts::register_all(L); }
    ~ConsoleState() { lua_close(L); }
};

// ---------------------------------------------------------------- cases ----

void list_shape() {
    Result r{"scripts_api.list_shape"};
    Case c("list");
    c.write("a", "priority = 5\nfunction cb() return true end\nkp.registertimer(1000, 'cb')\n");
    c.write("b", "x = 1\n");
    c.load_all();
    lua_State* L = c.host->find("a")->L();
    const std::string err = run(L,
        "local t = kp.scripts.list()\n"
        "local byname = {}\n"
        "for i, e in ipairs(t) do byname[e.name] = e end\n"
        "local a = byname.a\n"
        "out = table.concat({#t, a.name, tostring(a.path:match('a%.lua$') ~= nil), a.state,\n"
        "  a.generation, a.priority, a.errors, a.timers, tostring(a.last_error),\n"
        "  byname.b.timers}, '|')\n");
    r.expect(err.empty(), "list() ran: " + err);
    r.expect(global_string(L, "out") == "2|a|true|loaded|1|5|0|1|nil|0",
             "list() fields: " + global_string(L, "out"));
}

void unload_request_then_service() {
    Result r{"scripts_api.unload_request_then_service"};
    Case c("unload_req");
    c.write("a", "function OnScriptUnload() local n = #kp.scripts.list(); note('a:unload:' .. n) end\n");
    c.write("b", "x = 1\n");
    c.load_all();
    lua_State* L = c.host->find("b")->L();
    std::string err = run(L, "id = kp.scripts.unload('a')\nfirst = kp.scripts.result(id)\n");
    r.expect(err.empty(), "unload() ran: " + err);
    r.expect(global_string(L, "first") == "pending", "result before service is 'pending': " + global_string(L, "first"));
    r.expect(c.host->find("a")->state() == lua::ScriptState::Loaded, "a still loaded before service");
    c.host->service_requests();
    r.expect(c.host->find("a")->state() == lua::ScriptState::Unloaded, "a unloaded after service");
    r.expect(count_note("a:unload:2") == 1, "OnScriptUnload sees bound list once");
    err = run(L, "local res = kp.scripts.result(id)\n"
                 "out = table.concat({tostring(res.ok), tostring(res.error), res.generation, res.name, res.op}, '|')\n"
                 "for _, e in ipairs(kp.scripts.list()) do if e.name == 'a' then st = e.state; tm = e.timers end end\n");
    r.expect(err.empty(), "result() ran: " + err);
    r.expect(global_string(L, "out") == "true|nil|1|a|unload", "result after service: " + global_string(L, "out"));
    r.expect(global_string(L, "st") == "unloaded" && global_string(L, "tm") == "0", "list shows a unloaded, 0 timers");
    err = run(L, "id2 = kp.scripts.load('a')\n");
    c.host->service_requests();
    run(L, "local res = kp.scripts.result(id2); out2 = tostring(res.ok) .. '|' .. res.generation\n");
    r.expect(global_string(L, "out2") == "true|2", "load brings a back as generation 2: " + global_string(L, "out2"));
}

void self_unload_from_callback_safe() {
    Result r{"scripts_api.self_unload_from_callback_safe"};
    api::timers::set_clock(0);
    Case c("self_unload");
    c.write("a", "bind('OnTick', function()\n"
                 "  kp.scripts.unload(kp.scriptname())\n"
                 "  note('tick-finished:' .. kp.scriptname())\n"
                 "end)\n");
    c.write("b", "function cb()\n"
                 "  kp.scripts.reload(kp.scriptname())\n"
                 "  note('timer-finished')\n"
                 "  return false\n"
                 "end\n"
                 "kp.registertimer(10, 'cb')\n");
    c.load_all();
    c.tick();
    api::timers::pump(100, 1);
    r.expect(count_note("tick-finished:a") == 1, "a's callback ran to the end after asking to unload itself");
    r.expect(count_note("timer-finished") == 1, "b's timer ran to the end after asking to reload itself");
    r.expect(c.host->find("a")->L() != nullptr && c.host->find("b")->generation() == 1,
             "nothing closed inside a callback");
    r.expect(c.host->service_requests() == 2, "service ran both requests");
    r.expect(c.host->find("a")->state() == lua::ScriptState::Unloaded, "a unloaded");
    r.expect(c.host->find("b")->generation() == 2, "b reloaded");
}

void console_state_has_no_scriptname() {
    Result r{"scripts_api.console_state_has_no_scriptname"};
    Case c("console");
    c.write("a", "x = 1\n");
    c.load_all();
    ConsoleState con;
    const std::string err = run(con.L, "n = tostring(kp.scriptname())\nd = kp.scriptdir()\n"
                                       "id = kp.scripts.unload('a')\nres = kp.scripts.result(id)\n");
    r.expect(err.empty(), "console calls ran: " + err);
    r.expect(global_string(con.L, "n") == "nil", "scriptname() is nil in the console: " + global_string(con.L, "n"));
    r.expect(global_string(con.L, "d") == c.dir.string(), "scriptdir() is the host dir: " + global_string(con.L, "d"));
    r.expect(global_string(con.L, "res") == "pending", "console request is pending");
    c.host->service_requests();
    r.expect(c.host->find("a")->state() == lua::ScriptState::Unloaded, "console request serviced");
}

void scriptname_and_scriptdir_in_a_script() {
    Result r{"scripts_api.scriptname_and_scriptdir_in_a_script"};
    Case c("names");
    c.write("20_named", "chunk_name = kp.scriptname()\nchunk_dir = kp.scriptdir()\n");
    c.load_all();
    lua_State* L = c.host->find("20_named")->L();
    r.expect(global_string(L, "chunk_name") == "20_named", "scriptname() at chunk top level: " + global_string(L, "chunk_name"));
    r.expect(global_string(L, "chunk_dir") == c.dir.string(), "scriptdir() at chunk top level");
}

bool all_lower(const std::string& k) {
    for (char ch : k) if (std::isupper(static_cast<unsigned char>(ch))) return false;
    return !k.empty();
}

void no_pascalcase_keys() {
    Result r{"scripts_api.no_pascalcase_keys"};
    Case c("keys");
    c.write("a", "x = 1\n");
    c.load_all();
    // Queue one request and service it, so result() has a table to enumerate.
    const std::uint64_t id = c.host->request(lua::LifecycleOp::Reload, "a");
    c.host->service_requests();
    lua_State* L = c.host->find("a")->L();
    const std::string err = run(L,
        "keys = {}\n"
        "for k in pairs(kp.scripts) do keys[#keys+1] = k end\n"
        "for k in pairs(kp.scripts.list()[1]) do keys[#keys+1] = k end\n"
        "for k in pairs(kp.scripts.result(" + std::to_string(id) + ")) do keys[#keys+1] = k end\n"
        "keys_joined = table.concat(keys, ',')\n");
    r.expect(err.empty(), "enumeration ran: " + err);
    const std::string keys = global_string(L, "keys_joined");
    std::stringstream ss(keys);
    std::string k;
    bool ok = !keys.empty() && keys[0] != '<';
    while (std::getline(ss, k, ',')) if (!all_lower(k)) ok = false;
    r.expect(ok, "every key is lowercase: " + keys);
    for (const char* want : {"list", "load", "unload", "reload", "result"})
        r.expect(("," + keys + ",").find(std::string(",") + want + ",") != std::string::npos,
                 std::string("kp.scripts.") + want + " exists");
}

void bad_args_error_not_crash() {
    Result r{"scripts_api.bad_args_error_not_crash"};
    Case c("badargs");
    c.write("a", "x = 1\n");
    c.load_all();
    lua_State* L = c.host->find("a")->L();
    for (const char* code : {"kp.scripts.load()", "kp.scripts.unload(nil)", "kp.scripts.reload({})",
                             "kp.scripts.load(42)", "kp.scripts.result('x')", "kp.scripts.result()"}) {
        const std::string err = run(L, code);
        r.expect(!err.empty(), std::string(code) + " raises a Lua error");
    }
    r.expect(run(L, "u = kp.scripts.result(987654)\n").empty() && global_string(L, "u") == "<nil>",
             "result() of an unknown id is nil");
    r.expect(c.host->pending_requests() == 0, "no bad call queued anything");
    r.expect(c.host->find("a")->state() == lua::ScriptState::Loaded, "a still fine");
}

void unbound_host() {
    Result r{"scripts_api.unbound_host"};
    api::scripts::bind_host(nullptr);
    ConsoleState con;
    r.expect(!run(con.L, "kp.scripts.list()").empty(), "list() with no host is a Lua error");
    r.expect(!run(con.L, "kp.scripts.load('a')").empty(), "load() with no host is a Lua error");
    r.expect(run(con.L, "d = kp.scriptdir()").empty() && global_string(con.L, "d").empty(),
             "scriptdir() with no host is the empty string");
}

void names_are_not_nwscript_names() {
    Result r{"scripts_api.names_are_not_nwscript_names"};
    // Every quoted token in the routine tables, compared case-insensitively.
    // That covers routine names, parameter names and constant defaults.
    const char* ours[] = {"scripts", "scriptname", "scriptdir",
                          "list", "load", "unload", "reload", "result"};
    unsigned files = 0;
    for (const char* game : {"k1", "k2"}) {
        std::ifstream in(fs::path(KP_REPO) / "data" / "routines" / (std::string(game) + ".json"));
        if (!in) continue;
        ++files;
        std::string text((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
        for (char& ch : text) ch = char(std::tolower(static_cast<unsigned char>(ch)));
        for (const char* n : ours) {
            const std::string quoted = std::string("\"") + n + "\"";
            r.expect(text.find(quoted) == std::string::npos,
                     std::string(n) + " appears in data/routines/" + game + ".json");
        }
    }
    r.expect(files == 2, "both routine tables were read from " KP_REPO "/data/routines");
}


// M6. result() answers nil for any id that is not a positive integer it could
// have issued: no cast of an out-of-range double, and ID + 0.5 is not ID.
void result_rejects_bad_ids() {
    Result r{"scripts_api.result_rejects_bad_ids"};
    Case c("result_ids");
    c.write("a", "x = 1\n");
    c.write("b", "x = 1\n");
    c.load_all();
    lua_State* L = c.host->find("a")->L();
    r.expect(run(L, "ID = kp.scripts.reload('b')\n").empty(), "queued a reload");
    c.host->service_requests();
    r.expect(run(L, "ok = type(kp.scripts.result(ID))\n").empty() && global_string(L, "ok") == "table",
             "the issued id answers a table");
    for (const char* e : {"ID + 0.5", "math.huge", "-math.huge", "0/0", "2^64", "2^53 + 2", "-1", "0"}) {
        const std::string code = std::string("t = type(kp.scripts.result(") + e + "))\n";
        const std::string err = run(L, code);
        r.expect(err.empty() && global_string(L, "t") == "nil",
                 std::string("result(") + e + ") is nil, got " + (err.empty() ? global_string(L, "t") : err));
    }
}

}  // namespace

int main(int argc, char** argv) {
    platform::set_log_sink(&tool_log_sink, nullptr);
    g_root = argc > 1 ? fs::path(argv[1]) : fs::temp_directory_path() / "kp_scriptsapitest";
    std::error_code ec;
    fs::remove_all(g_root, ec);
    fs::create_directories(g_root, ec);
    if (ec) { std::fprintf(stderr, "cannot create %s\n", g_root.string().c_str()); return 2; }

    list_shape();
    unload_request_then_service();
    self_unload_from_callback_safe();
    console_state_has_no_scriptname();
    scriptname_and_scriptdir_in_a_script();
    no_pascalcase_keys();
    bad_args_error_not_crash();
    unbound_host();
    names_are_not_nwscript_names();
    result_rejects_bad_ids();

    fs::remove_all(g_root, ec);
    std::printf("%u case(s), %u failed\n", g_cases, g_failures);
    return g_failures == 0 ? 0 : 1;
}
