// Exercises the support module -- output, timers, strings -- without the game.
//
// Everything in this module is either a pure function over a string or a
// scheduler driven by a clock, so both are checkable offline. What is NOT
// checkable offline is where the text ends up: the console surface needs the
// console.do_console detour and the feedback surface needs the VM bound. This
// tool proves the routing decision instead -- that feedback finds the routine
// by name when it is there and falls back to the log when it is not -- by
// installing a stand-in nwscript.call from Lua.
//
// The timer cases run against the real lua::Host, not a stub state, because the
// interesting behaviour is quarantine and quarantine belongs to Script.
//
// The scripts are written to a scratch directory at startup and removed at the
// end. luaL_loadfile needs files, and the repository's example scripts are not
// this tool's to add to.
//
// Usage:
//   kp_supporttest [scratch-dir]

#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

#include <sys/wait.h>
#include <unistd.h>

#include "api/output.hpp"
#include "api/strings.hpp"
#include "api/timers.hpp"
#include "lua/host.hpp"
#include "platform/platform.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
}

namespace fs = std::filesystem;
using namespace kp;

namespace {

unsigned g_failures = 0;

struct LogRecord {
    platform::LogLevel level;
    std::string message;
};

std::vector<LogRecord> g_log_records;

void check(bool condition, const char* what) {
    std::printf("  %-68s %s\n", what, condition ? "ok" : "FAIL");
    if (!condition) ++g_failures;
}

// The log sink the runtime would install. Here it prints to stdout so the log
// lines and the script's own print() land in one readable stream; in the game
// this is what appends to hyperstim.log.
void tool_log_sink(platform::LogLevel level, const char* message, void*) {
    g_log_records.push_back({level, message != nullptr ? message : ""});
    std::printf("  [log:%s] %s\n", platform::to_string(level), message);
}

void check_only_info_log(const char* expected, const char* what) {
    const bool exact = g_log_records.size() == 1
                    && g_log_records[0].level == platform::LogLevel::Info
                    && g_log_records[0].message == expected;
    if (!exact) {
        std::printf("    expected one info log '%s'; captured %zu record(s)\n",
                    expected, g_log_records.size());
        for (const LogRecord& record : g_log_records)
            std::printf("      [%s] %s\n", platform::to_string(record.level),
                        record.message.c_str());
    }
    check(exact, what);
}

// The console writer the console.do_console detour would supply.
void tool_console_writer(const char* line, void*) {
    std::printf("  [console] %s\n", line);
}

void rule(const char* title) {
    const std::size_t len = std::string(title).size();
    std::printf("\n=== %s %s\n", title, std::string(len < 60 ? 60 - len : 3, '=').c_str());
}

const char* state_name(lua::ScriptState s) {
    switch (s) {
    case lua::ScriptState::Loaded:       return "loaded";
    case lua::ScriptState::FailedToLoad: return "failed";
    case lua::ScriptState::Quarantined:  return "QUARANTINED";
    case lua::ScriptState::Unloaded:     return "unloaded";
    }
    return "?";
}

// ------------------------------------------------------------- tokenising ---

void show_tokens(const char* what, const std::vector<std::string>& tokens) {
    std::printf("  %-34s -> %zu:", what, tokens.size());
    for (const std::string& t : tokens) std::printf(" [%s]", t.c_str());
    std::printf("\n");
}

void tokenising_cases() {
    rule("strings");

    std::printf("tokenizestring(str, delims) -- empty fields dropped\n");
    show_tokens("(\"a,b,c\", \",\")",        api::tokenize("a,b,c", ","));
    show_tokens("(\"a,,b\", \",\")",         api::tokenize("a,,b", ","));
    show_tokens("(\",,a,,\", \",\")",        api::tokenize(",,a,,", ","));
    show_tokens("(\"a:b,c\", \",:\")",       api::tokenize("a:b,c", ",:"));
    show_tokens("(\"10.1.2.3/24\", \"/\")",  api::tokenize("10.1.2.3/24", "/"));
    show_tokens("(\"\", \",\")",             api::tokenize("", ","));
    show_tokens("(\",,,\", \",\")",          api::tokenize(",,,", ","));
    show_tokens("(\"abc\", \"\")",           api::tokenize("abc", ""));

    std::printf("\ntokenizecmdstring(line) -- quotes hold a token together\n");
    show_tokens("give \"plot armour\" 1",    api::tokenize_command("give \"plot armour\" 1"));
    show_tokens("  spaced   out  ",          api::tokenize_command("  spaced   out  "));
    show_tokens("say \"\" done",             api::tokenize_command("say \"\" done"));
    show_tokens("say \"a  b\" \"c\"",        api::tokenize_command("say \"a  b\" \"c\""));
    show_tokens("open \"unterminated",       api::tokenize_command("open \"unterminated"));
    show_tokens("say a\"b",                  api::tokenize_command("say a\"b"));
    show_tokens("(empty line)",              api::tokenize_command(""));
    show_tokens("tab\\tseparated",           api::tokenize_command("tab\tseparated"));
}

// ----------------------------------------------------------- the scripts ----

struct ScriptFile {
    const char* name;
    const char* body;
};

const ScriptFile kScripts[] = {
{"10_timers.lua", R"LUA(
-- Firing, userdata, renewal, and removal before the timer ever comes due.
function start()
    local once = kp.registertimer(100, "on_once", { tag = "payload" })
    local rep  = kp.registertimer(250, "on_repeat")
    local doomed = kp.registertimer(300, "on_never")
    kp.removetimer(doomed)
    print(("  [10_timers] ids once=%d repeat=%d removed=%d"):format(once, rep, doomed))
end

function on_once(id, count, data)
    print(("  [10_timers] on_once     count=%d data.tag=%s"):format(count, tostring(data.tag)))
    return false
end

function on_repeat(id, count)
    print(("  [10_timers] on_repeat   count=%d (renews while count < 3)"):format(count))
    return count < 3
end

function on_never(id, count)
    print("  [10_timers] on_never     THIS SHOULD NOT PRINT")
end
)LUA"},

{"20_remove_inside.lua", R"LUA(
-- Everything removetimer ignores, and the one case that raises.
function start()
    kp.removetimer()        -- no argument
    kp.removetimer(nil)     -- nil
    kp.removetimer(99999)   -- an id nobody owns
    kp.removetimer(1)       -- id 1 is 10_timers' on_once, and stays alive
    print("  [20_remove_inside] four ignored removes: none, nil, unknown, another script's id")
    kp.registertimer(150, "on_self")
end

function on_self(id, count)
    kp.removetimer(id)
    print("  [20_remove_inside] THIS SHOULD NOT PRINT")
end
)LUA"},

{"30_throws.lua", R"LUA(
-- Four timers on one broken callback, against an error budget of 3.
function start()
    kp.registertimer(100, "on_boom")
    kp.registertimer(200, "on_boom")
    kp.registertimer(300, "on_boom")
    kp.registertimer(400, "on_boom")
end

function on_boom(id, count)
    error("deliberate failure")
end
)LUA"},

{"40_survives.lua", R"LUA(
-- Never comes due within the run. Here to show the state's timers go away when
-- the state closes, without anybody calling forget_state.
function start()
    kp.registertimer(999000, "never_due")
end

function never_due() end
)LUA"},

{"50_output.lua", R"LUA(
-- The three output surfaces, and the routine lookup feedback does by name.
function start()
    kp.diagnostic("log line, default level")
    kp.diagnostic("two lines\nin one call", "warn")
    print(("  [50_output] console reached the console surface: %s")
          :format(tostring(kp.console("console line"))))
    print(("  [50_output] feedback reached the engine: %s")
          :format(tostring(kp.feedback("feedback with no routines registered"))))
end

-- Stand-ins for what src/api/routines.cpp will register. feedback looks the
-- name up at call time, so installing them after registration still works.
function install_fake_routines()
    output_calls = {}
    fail_routine = nil
    nwscript = { call = function(name, ...)
        local args = {...}
        output_calls[#output_calls + 1] = {
            name = name,
            argc = select("#", ...),
            args = args,
        }
        if name == fail_routine then
            error("forced " .. name .. " failure")
        end
        if name == "GetFirstPC" then return 17 end
        if name == "SendMessageToPC" then
            local pc, msg = ...
            print(("  [50_output] SendMessageToPC(%d, %q)"):format(pc, msg))
            return
        end
        if name == "AurPostString" then
            local s, x, y, life = ...
            print(("  [50_output] AurPostString(%q, %d, %d, %.1f)"):format(s, x, y, life))
            return
        end
        error("unexpected routine " .. tostring(name))
    end }
end

function talk()
    assert(kp.feedback("hello from the routine path") == true,
           "plain feedback did not reach nwscript.call")
    assert(kp.feedback("top left", 0, 1, 2.5) == true,
           "positioned feedback did not reach nwscript.call")

    assert(#output_calls == 3, "expected exactly three NWScript calls")
    assert(output_calls[1].name == "GetFirstPC" and output_calls[1].argc == 0,
           "plain feedback must resolve the player through GetFirstPC")
    assert(output_calls[2].name == "SendMessageToPC"
           and output_calls[2].argc == 2
           and output_calls[2].args[1] == 17
           and output_calls[2].args[2] == "hello from the routine path",
           "plain feedback must route its player and text through SendMessageToPC")
    assert(output_calls[3].name == "AurPostString"
           and output_calls[3].argc == 4
           and output_calls[3].args[1] == "top left"
           and output_calls[3].args[2] == 0
           and output_calls[3].args[3] == 1
           and output_calls[3].args[4] == 2.5,
           "positioned feedback must route text, coordinates, and lifetime through AurPostString")
end

local function feedback_with_forced_failure(routine, text, ...)
    output_calls = {}
    fail_routine = routine
    local reached = kp.feedback(text, ...)
    fail_routine = nil
    assert(reached == false, routine .. " failure must return false from kp.feedback")
end

function fail_get_first_pc()
    feedback_with_forced_failure("GetFirstPC", "fallback GetFirstPC")
end

function fail_send_message_to_pc()
    feedback_with_forced_failure("SendMessageToPC", "fallback SendMessageToPC")
end

function fail_aur_post_string()
    feedback_with_forced_failure("AurPostString", "fallback AurPostString", 4, 7, 1.25)
end

function fallback_without_bridge()
    assert(kp.feedback("feedback with no bridge") == false,
           "feedback without nwscript.call must report its log fallback")
end
)LUA"},
};

// Call a zero-argument global on one script's state, reporting rather than
// swallowing a failure. The runtime never does this -- it dispatches events --
// but the harness needs an entry point that runs after registration.
bool call_entry(lua::Script& s, const char* fn, bool required) {
    lua_State* L = s.L();
    if (L == nullptr) {
        if (required) {
            std::printf("  [%s] cannot call required %s(): state is closed\n",
                        s.name().c_str(), fn);
            ++g_failures;
        }
        return false;
    }
    const int base = lua_gettop(L);
    lua_getglobal(L, fn);
    if (!lua_isfunction(L, -1)) {
        lua_settop(L, base);
        if (required) {
            std::printf("  [%s] has no required %s()\n", s.name().c_str(), fn);
            ++g_failures;
        }
        return false;
    }
    if (lua_pcall(L, 0, 0, 0) != 0) {
        std::printf("  [%s] %s() failed: %s\n", s.name().c_str(), fn,
                    lua_tostring(L, -1) ? lua_tostring(L, -1) : "?");
        ++g_failures;
        lua_settop(L, base);
        return false;
    }
    lua_settop(L, base);
    return true;
}

void check_protected_feedback_error(lua::Script& script, const char* entry,
                                    const char* expected_log, const char* call_what,
                                    const char* log_what) {
    g_log_records.clear();
    check(call_entry(script, entry, true), call_what);
    check_only_info_log(expected_log, log_what);
}

// ------------------------------------------------- function-valued timers ---
//
// kp.registertimer(ms, fn [, data]). Run in a Host of their own, in a scratch
// subdirectory, after the string-timer flow above has finished: these cases
// assert on pending() and on error budgets, and sharing the 0..1000 pump with
// the scripts above would make every count depend on theirs.
//
// "Released" is observed, not assumed. Each probe closure captures a token
// table that is also a key in a weak table. While the timer holds its registry
// reference the token survives a full collection (the control); once the timer
// completes, is cancelled or throws, the next collection drops it.

const ScriptFile kFnScripts[] = {
{"60_fn.lua", R"LUA(
weak = setmetatable({}, { __mode = "k" })

local function probe(tag, body)
    local token = {}
    weak[token] = tag
    return function(...) local _ = token; return body(...) end
end

function live(tag)
    collectgarbage("collect"); collectgarbage("collect")
    for _, t in pairs(weak) do if t == tag then return true end end
    return false
end

-- A closure keeps its upvalue across firings and gets the same three
-- arguments a named callback gets.
function arm_fires()
    fires = { n = 0, ids = {}, counts = {} }
    local n = 0
    fires.id = kp.registertimer(100, function(id, count, data)
        n = n + 1
        fires.n = n
        fires.ids[#fires.ids + 1] = id
        fires.counts[#fires.counts + 1] = count
        fires.tag = data and data.tag
        return count < 3
    end, { tag = "fn-payload" })
end
function fires_ok()
    return fires.n == 3 and fires.ids[1] == fires.id and fires.ids[3] == fires.id
       and fires.counts[1] == 1 and fires.counts[3] == 3 and fires.tag == "fn-payload"
end

function arm_complete() kp.registertimer(100, probe("complete", function() return false end)) end
function arm_cancel()   cancel_id = kp.registertimer(999000, probe("cancel", function() end)) end
function do_cancel()    kp.removetimer(cancel_id) end

-- One throwing closure beside two healthy timers due on the same pump.
function arm_error()
    healthy = { fn = 0, named = 0 }
    kp.registertimer(100, probe("error", function() error("fn boom") end))
    kp.registertimer(100, function() healthy.fn = healthy.fn + 1 end)
    kp.registertimer(100, "named_healthy")
end
function named_healthy() healthy.named = healthy.named + 1 end
function healthy_ok() return healthy.fn == 1 and healthy.named == 1 end

-- Anything else in the callback slot is a type error at the call site.
function bad_callback_rejected()
    local ok, err = pcall(kp.registertimer, 100, 42)
    local ok2, err2 = pcall(kp.registertimer, 100, {})
    return not ok and tostring(err):find("string or function", 1, true) ~= nil
       and not ok2 and tostring(err2):find("string or function", 1, true) ~= nil
end

-- The string path, unchanged: late lookup by name, same arguments.
function arm_named()
    named = { n = 0 }
    kp.registertimer(100, "on_named", { tag = "named-payload" })
end
function on_named(id, count, data)
    named.n = count
    named.tag = data and data.tag
    return count < 2
end
function named_ok() return named.n == 2 and named.tag == "named-payload" end

-- The delay must be a finite number of milliseconds from 0 to 2^32 - 1.
-- Anything accepted by mistake is removed again so later counts stay exact.
function delay_bounds_ok()
    local bad = { math.huge, -math.huge, 0/0, -1, 1e30, 4294967296 }
    local all_rejected = true
    for _, d in ipairs(bad) do
        local ok, err = pcall(kp.registertimer, d, function() end)
        if ok then kp.removetimer(err); all_rejected = false
        elseif not tostring(err):find("delay must be", 1, true) then all_rejected = false end
    end
    local id0 = kp.registertimer(0, function() end)
    local idmax = kp.registertimer(4294967295, function() end)
    kp.removetimer(id0); kp.removetimer(idmax)
    -- removetimer stays forgiving for out-of-range ids.
    kp.removetimer(math.huge); kp.removetimer(1e30); kp.removetimer(0/0)
    return all_rejected and type(id0) == "number" and type(idmax) == "number"
end
)LUA"},

{"70_fn_throws.lua", R"LUA(
-- Four timers on one throwing closure against a budget of 3: the budget is
-- charged per callback, and one closure is one callback.
function start()
    local boom = function() error("closure failure") end
    for i = 1, 4 do kp.registertimer(100 * i, boom) end
end
)LUA"},

{"72_fn_clabels.lua", R"LUA(
-- Two different C functions as callbacks. Each throws when called with
-- (id, count, data). They are different callbacks, so they must not share
-- one error-budget label.
function start()
    kp.registertimer(100, error)
    kp.registertimer(100, setmetatable)
end
)LUA"},

{"90_fn_strict.lua", R"LUA(
-- A string timer naming an undefined global under the strict.lua pattern.
-- Only ever started in a forked child: before the fix the lookup ran outside
-- any protected call and the panic ended the process.
function start()
    kp.registertimer(0, "no_such_global")
    setmetatable(_G, { __index = function(_, k)
        error("strict: undefined global " .. tostring(k), 2)
    end })
end
)LUA"},

{"91_fn_strict_remove.lua", R"LUA(
-- _G's __index cancels the very timer whose name it is resolving. The lookup
-- runs as that timer's callback, so removetimer raises inside the protected
-- lookup instead of freeing the entry the fire path is still using.
function start()
    local id
    id = kp.registertimer(0, "missing_fn", { payload = true })
    setmetatable(_G, { __index = function(_, k)
        if k == "missing_fn" then kp.removetimer(id) end
        return nil
    end })
end
)LUA"},

{"80_fn_close.lua", R"LUA(
-- A finaliser that registers timers while the state is being closed. One proxy
-- is made by the chunk, before kp.registertimer and its sentinel exist; the
-- other is made afterwards, so both finaliser orders are exercised.
-- Each finaliser logs what registration answered, so the test can see which
-- side of the sentinel's finaliser it ran on.
local function finaliser(tag)
    return function()
        if not (kp and kp.registertimer) then return end
        local ok1, e1 = pcall(kp.registertimer, 50, function() end)
        local ok2, e2 = pcall(kp.registertimer, 50, "never_defined")
        kp.diagnostic(("[close] %s fn=%s name=%s %s"):format(
            tag, tostring(ok1), tostring(ok2), ok1 and "" or tostring(e1)))
    end
end

local early = newproxy(true)
getmetatable(early).__gc = finaliser("early")
keep_early = early

function start()
    kp.registertimer(100, function() closed_fired = true end)
    local late = newproxy(true)
    getmetatable(late).__gc = finaliser("late")
    keep_late = late
end
)LUA"},
};

// Evaluate a chunk in a script's state and return its first result as a
// boolean. A Lua error is a failure and is printed.
bool eval_bool(lua::Script& s, const char* chunk) {
    lua_State* L = s.L();
    if (L == nullptr) return false;
    const int base = lua_gettop(L);
    if (luaL_loadstring(L, chunk) != 0 || lua_pcall(L, 0, 1, 0) != 0) {
        std::printf("  [%s] %s: %s\n", s.name().c_str(), chunk,
                    lua_tostring(L, -1) ? lua_tostring(L, -1) : "?");
        lua_settop(L, base);
        return false;
    }
    const bool r = lua_toboolean(L, -1) != 0;
    lua_settop(L, base);
    return r;
}

lua::Script* find_script(lua::Host& host, const char* name) {
    for (const auto& s : host.scripts())
        if (s->name() == name) return s.get();
    return nullptr;
}

// Pump [from, to] in 50 ms steps. Returns the callbacks run.
unsigned pump_range(std::uint64_t from, std::uint64_t to) {
    unsigned n = 0;
    for (std::uint64_t t = from; t <= to; t += 50) n += api::timers::pump(t, t / 50);
    return n;
}

void function_timer_cases(const fs::path& scratch) {
    rule("function timers");

    const fs::path dir = scratch / "fn";
    std::error_code ec;
    fs::create_directories(dir, ec);
    for (const ScriptFile& sf : kFnScripts) {
        std::ofstream out(dir / sf.name, std::ios::binary);
        out << sf.body;
    }

    const std::size_t baseline = api::timers::pending();
    api::timers::set_clock(0);
    api::timers::set_error_budget(3);

    lua::Host host({dir.string(), /*error_budget=*/3, /*hot_reload=*/false, {}, {}});
    std::vector<std::string> errors;
    host.load_all(errors);
    for (const std::string& e : errors) std::printf("  load error: %s\n", e.c_str());
    for (const auto& s : host.scripts()) api::register_support(s->L());

    lua::Script* fn = find_script(host, "60_fn");
    lua::Script* throws = find_script(host, "70_fn_throws");
    lua::Script* closing = find_script(host, "80_fn_close");
    lua::Script* clabels = find_script(host, "72_fn_clabels");
    lua::Script* strict = find_script(host, "90_fn_strict");
    lua::Script* strict_rm = find_script(host, "91_fn_strict_remove");
    check(fn != nullptr && throws != nullptr && closing != nullptr && fn->L() != nullptr
          && clabels != nullptr && strict != nullptr && strict_rm != nullptr,
          "function-timer scripts loaded");
    if (fn == nullptr || throws == nullptr || closing == nullptr || fn->L() == nullptr
        || clabels == nullptr || strict == nullptr || strict_rm == nullptr) return;

    // timers.lookup_removes_self: __index calling removetimer on the timer it is
    // resolving. Forked for the same reason as the case below.
    {
        std::fflush(stdout);
        std::fflush(stderr);
        const pid_t pid = fork();
        if (pid == 0) {
            int bad = 0;
            const unsigned before = strict_rm->error_count();
            if (!call_entry(*strict_rm, "start", true)) bad |= 1;
            api::timers::pump(api::timers::clock() + 50, 1);
            if (strict_rm->error_count() != before + 1) bad |= 2;
            if (strict_rm->errors().empty()
                || strict_rm->errors().back().callback != "missing_fn"
                || strict_rm->errors().back().message.find("within its own callback")
                       == std::string::npos) bad |= 4;
            if (strict_rm->state() != lua::ScriptState::Loaded) bad |= 8;
            if (strict_rm->L() == nullptr || api::timers::pending(strict_rm->L()) != 0) bad |= 16;
            std::printf("    [child] survived the pump, mask=%d\n", bad);
            std::fflush(stdout);
            std::fflush(stderr);
            _exit(bad == 0 ? 0 : 3);
        }
        int status = 0;
        const bool waited = pid > 0 && waitpid(pid, &status, 0) == pid;
        std::printf("    child: exited=%d status=%d signalled=%d\n",
                    waited && WIFEXITED(status), waited && WIFEXITED(status) ? WEXITSTATUS(status) : -1,
                    waited && WIFSIGNALED(status));
        check(waited && WIFEXITED(status) && WEXITSTATUS(status) == 0,
              "timers.lookup_removes_self: raises in lookup, reported, cancelled");
    }

    // timers.string_lookup_protected: a string timer whose global lookup raises
    // (a strict _G) must be an isolated, reported timer error. Before the fix
    // it was an unprotected error: LuaJIT's panic handler, then exit. Run in a
    // forked child so a panic fails this check instead of ending the tool.
    {
        std::fflush(stdout);
        std::fflush(stderr);
        const pid_t pid = fork();
        if (pid == 0) {
            int bad = 0;
            const unsigned before = strict->error_count();
            g_log_records.clear();
            if (!call_entry(*strict, "start", true)) bad |= 1;
            api::timers::pump(api::timers::clock() + 50, 1);
            if (strict->error_count() != before + 1) bad |= 2;
            if (strict->errors().empty() || strict->errors().back().callback != "no_such_global"
                || strict->errors().back().message.find("strict: undefined global no_such_global")
                       == std::string::npos) bad |= 4;
            if (strict->state() != lua::ScriptState::Loaded) bad |= 8;
            if (strict->L() == nullptr || api::timers::pending(strict->L()) != 0) bad |= 16;
            if (!strict->errors().empty())
                std::printf("    [child] recorded [%s] %s\n",
                            strict->errors().back().callback.c_str(),
                            strict->errors().back().message.substr(
                                0, strict->errors().back().message.find('\n')).c_str());
            std::printf("    [child] survived the pump, mask=%d\n", bad);
            std::fflush(stdout);
            std::fflush(stderr);
            _exit(bad == 0 ? 0 : 3);
        }
        int status = 0;
        const bool waited = pid > 0 && waitpid(pid, &status, 0) == pid;
        std::printf("    child: exited=%d status=%d signalled=%d\n",
                    waited && WIFEXITED(status), waited && WIFEXITED(status) ? WEXITSTATUS(status) : -1,
                    waited && WIFSIGNALED(status));
        check(waited && WIFEXITED(status) && WEXITSTATUS(status) == 0,
              "timers.string_lookup_protected: strict _G error isolated, reported");
    }

    // timers.delay_bounds
    check(eval_bool(*fn, "return delay_bounds_ok()"),
          "timers.delay_bounds: inf/nan/negative/huge rejected, 0 and 2^32-1 ok");
    check(api::timers::pending(fn->L()) == 0, "timers.delay_bounds: nothing left scheduled");

    // timers.c_function_labels: two C callbacks get two budgets.
    check(call_entry(*clabels, "start", true), "timers.c_function_labels: registers two");
    pump_range(0, 200);
    {
        const auto& errs = clabels->errors();
        const bool two = errs.size() == 2;
        for (const auto& e : errs) std::printf("    C callback label: %s\n", e.callback.c_str());
        check(two && errs[0].callback.rfind("function [C]", 0) == 0
                  && errs[1].callback.rfind("function [C]", 0) == 0
                  && errs[0].callback != errs[1].callback
                  && clabels->state() == lua::ScriptState::Loaded,
              "timers.c_function_labels: distinct labels per C function");
    }
    api::timers::set_clock(0);

    // timers.bad_callback_rejected
    check(eval_bool(*fn, "return bad_callback_rejected()"),
          "timers.bad_callback_rejected: number/table callback raises");
    check(api::timers::pending(fn->L()) == 0, "timers.bad_callback_rejected: nothing scheduled");

    // timers.function_callback_fires
    check(call_entry(*fn, "arm_fires", true), "timers.function_callback_fires: registers");
    pump_range(0, 1000);
    check(eval_bool(*fn, "return fires_ok()"),
          "timers.function_callback_fires: 3 firings, id/count/data, upvalue kept");
    check(api::timers::pending(fn->L()) == 0,
          "timers.function_callback_fires: stops when it returns false");

    // timers.string_callback_unchanged
    api::timers::set_clock(2000);
    check(call_entry(*fn, "arm_named", true), "timers.string_callback_unchanged: registers");
    pump_range(2000, 3000);
    check(eval_bool(*fn, "return named_ok()"),
          "timers.string_callback_unchanged: late lookup, count, data");
    check(api::timers::pending(fn->L()) == 0, "timers.string_callback_unchanged: stops");

    // timers.function_ref_released_on_complete
    api::timers::set_clock(4000);
    check(call_entry(*fn, "arm_complete", true), "timers.function_ref_released_on_complete: registers");
    check(eval_bool(*fn, "return live('complete')"),
          "timers.function_ref_released_on_complete: control, held while pending");
    pump_range(4000, 4200);
    check(!eval_bool(*fn, "return live('complete')"),
          "timers.function_ref_released_on_complete: collected after completion");

    // timers.function_ref_released_on_cancel
    check(call_entry(*fn, "arm_cancel", true), "timers.function_ref_released_on_cancel: registers");
    check(eval_bool(*fn, "return live('cancel')"),
          "timers.function_ref_released_on_cancel: control, held while pending");
    check(call_entry(*fn, "do_cancel", true), "timers.function_ref_released_on_cancel: removetimer");
    check(!eval_bool(*fn, "return live('cancel')") && api::timers::pending(fn->L()) == 0,
          "timers.function_ref_released_on_cancel: collected after removetimer");

    // timers.function_ref_released_on_error (and the error stays isolated)
    api::timers::set_clock(5000);
    check(call_entry(*fn, "arm_error", true), "timers.function_ref_released_on_error: registers");
    check(eval_bool(*fn, "return live('error')"),
          "timers.function_ref_released_on_error: control, held while pending");
    const unsigned errors_before = fn->error_count();
    pump_range(5000, 5200);
    check(!eval_bool(*fn, "return live('error')"),
          "timers.function_ref_released_on_error: collected after the throw");
    check(fn->error_count() == errors_before + 1 && fn->state() == lua::ScriptState::Loaded,
          "timers.function_error_isolated: one error recorded, script still loaded");
    check(!fn->errors().empty() && fn->errors().back().callback.rfind("function", 0) == 0
          && fn->errors().back().message.find("fn boom") != std::string::npos,
          "timers.function_error_isolated: error names a function callback and its message");
    if (!fn->errors().empty())
        std::printf("    recorded callback label: %s\n", fn->errors().back().callback.c_str());
    check(eval_bool(*fn, "return healthy_ok()"),
          "timers.function_error_isolated: healthy timers on the same pump still ran");
    check(api::timers::pending(fn->L()) == 0,
          "timers.function_error_isolated: the throwing timer is cancelled");

    // timers.function_ref_released_once: a reference released twice goes onto
    // the registry's free list twice, and two later luaL_ref calls then return
    // the same slot. After completion, cancel and error above, fresh refs must
    // all be distinct.
    {
        lua_State* L = fn->L();
        std::vector<int> refs;
        for (int i = 0; i < 32; ++i) {
            lua_newtable(L);
            refs.push_back(luaL_ref(L, LUA_REGISTRYINDEX));
        }
        bool distinct = true;
        for (std::size_t i = 0; i < refs.size(); ++i)
            for (std::size_t j = i + 1; j < refs.size(); ++j)
                if (refs[i] == refs[j]) distinct = false;
        for (int r : refs) luaL_unref(L, LUA_REGISTRYINDEX, r);
        check(distinct, "timers.function_ref_released_once: no registry slot freed twice");
    }

    // timers.function_error_budget: one closure is one callback for the budget.
    api::timers::set_clock(6000);
    check(call_entry(*throws, "start", true), "timers.function_error_budget: registers four");
    pump_range(6000, 6500);
    check(throws->state() == lua::ScriptState::Quarantined && throws->error_count() == 3,
          "timers.function_error_budget: quarantined after 3, fourth never ran");

    // timers.function_ref_released_on_state_close
    api::timers::set_clock(7000);
    check(call_entry(*closing, "start", true), "timers.function_ref_released_on_state_close: registers");
    lua_State* closed_L = closing->L();
    check(api::timers::pending(closed_L) == 1,
          "timers.function_ref_released_on_state_close: one timer pending before close");
    g_log_records.clear();
    closing->unload();
    // Which finalisers ran on which side of the sentinel. Registration before
    // it succeeds and is then dropped by forget_state; after it, it raises.
    bool saw_before = false, saw_after = false;
    for (const LogRecord& r : g_log_records) {
        if (r.message.find("[close]") == std::string::npos) continue;
        if (r.message.find("fn=true name=true") != std::string::npos) saw_before = true;
        if (r.message.find("fn=false name=false") != std::string::npos
            && r.message.find("closing") != std::string::npos) saw_after = true;
    }
    check(saw_after,
          "timers.function_ref_released_on_state_close: a finaliser after the sentinel is refused");
    check(saw_before,
          "timers.function_ref_released_on_state_close: a finaliser before the sentinel also ran");
    check(api::timers::pending(closed_L) == 0,
          "timers.function_ref_released_on_state_close: none left, including finaliser registrations");
    check(pump_range(7000, 7500) == 0,
          "timers.function_ref_released_on_state_close: a later pump runs nothing of the closed state");

    host.unload_all();
    check(api::timers::pending() == baseline, "function timers: pending back to baseline");
}

}  // namespace

int main(int argc, char** argv) {
    platform::set_log_sink(&tool_log_sink, nullptr);

    // No machine path in this file. The scratch directory is the platform's
    // temp directory unless the caller names one.
    const fs::path scratch = argc > 1 ? fs::path(argv[1])
                                      : fs::temp_directory_path() / "kp_supporttest";
    std::error_code ec;
    fs::remove_all(scratch, ec);
    fs::create_directories(scratch, ec);
    if (ec) { std::fprintf(stderr, "cannot create %s\n", scratch.string().c_str()); return 2; }

    for (const ScriptFile& sf : kScripts) {
        std::ofstream out(scratch / sf.name, std::ios::binary);
        out << sf.body;
    }
    std::printf("scratch scripts written to %s\n", scratch.string().c_str());

    tokenising_cases();

    // ---------------------------------------------------------------------
    rule("host");

    // The clock is set before anything registers, so registertimer and pump
    // agree on what "now" means. In the game the runtime leaves both on
    // timers::now_ms().
    api::timers::set_clock(0);
    api::timers::set_error_budget(3);

    lua::Host host({scratch.string(), /*error_budget=*/3, /*hot_reload=*/false, {}, {}});
    std::vector<std::string> errors;
    const unsigned loaded = host.load_all(errors);
    for (const std::string& e : errors) std::printf("  load error: %s\n", e.c_str());
    std::printf("loaded %u script(s), error budget 3\n", loaded);

    // What the runtime does inside Script::load, before the chunk runs. Here it
    // happens after, so each script exposes start() rather than registering at
    // its top level.
    for (const auto& s : host.scripts()) api::register_support(s->L());
    std::printf("registered kp.diagnostic/console/feedback, registertimer/removetimer, "
                "tokenizestring/tokenizecmdstring on %u state(s)\n", loaded);

    rule("output");
    std::printf("console is unbound, so console text goes to the log:\n");
    for (const auto& s : host.scripts()) call_entry(*s, "start", false);

    for (const auto& s : host.scripts())
        if (s->name() == "50_output")
            check(call_entry(*s, "fallback_without_bridge", true),
                  "feedback without nwscript.call explicitly reports fallback");

    std::printf("\nnow with the console writer bound, as the do_console detour would:\n");
    api::bind_console(&tool_console_writer, nullptr);
    for (const auto& s : host.scripts())
        if (s->name() == "50_output") call_entry(*s, "start", false);

    std::printf("\nand with a stand-in nwscript.call bridge installed:\n");
    for (const auto& s : host.scripts())
        if (s->name() == "50_output") {
            check(call_entry(*s, "install_fake_routines", true),
                  "stand-in nwscript.call installs without Lua errors");
            check(call_entry(*s, "talk", true),
                  "feedback routes exact routine names and arguments through nwscript.call");
            check_protected_feedback_error(
                *s, "fail_get_first_pc", "[feedback] fallback GetFirstPC",
                "GetFirstPC bridge error is protected and returns false",
                "GetFirstPC bridge error emits its exact fallback log");
            check_protected_feedback_error(
                *s, "fail_send_message_to_pc", "[feedback] fallback SendMessageToPC",
                "SendMessageToPC bridge error is protected and returns false",
                "SendMessageToPC bridge error emits its exact fallback log");
            check_protected_feedback_error(
                *s, "fail_aur_post_string", "[feedback] fallback AurPostString",
                "AurPostString bridge error is protected and returns false",
                "AurPostString bridge error emits its exact fallback log");
        }

    // ---------------------------------------------------------------------
    rule("timers");
    std::printf("pending after registration: %zu\n", api::timers::pending());
    std::printf("driving pump() from t=0 to t=1000 in 50 ms steps\n");

    unsigned total = 0;
    for (std::uint64_t t = 0; t <= 1000; t += 50) {
        const unsigned fired = api::timers::pump(t, /*game_tick=*/t / 50);
        total += fired;
        if (fired != 0) std::printf("  t=%3llu fired %u\n", (unsigned long long)t, fired);
    }
    std::printf("total callbacks run: %u, still pending: %zu\n", total, api::timers::pending());

    // ---------------------------------------------------------------------
    rule("quarantine");
    for (const auto& s : host.scripts()) {
        if (s->errors().empty() && s->state() == lua::ScriptState::Loaded) continue;
        std::printf("  %-18s %-12s errors=%u pending timers=%zu\n",
                    s->name().c_str(), state_name(s->state()), s->error_count(),
                    s->L() != nullptr ? api::timers::pending(s->L()) : 0);
        for (const auto& e : s->errors()) {
            std::string first = e.message.substr(0, e.message.find('\n'));
            std::printf("      [%s] %s\n", e.callback.c_str(), first.c_str());
        }
    }
    std::printf("  30_throws had four timers on a callback that always throws.\n"
                "  Three errors reached the budget, so the fourth never ran.\n");

    // ---------------------------------------------------------------------
    rule("state lifetime");
    std::printf("pending before unload_all: %zu\n", api::timers::pending());
    host.unload_all();
    std::printf("pending after  unload_all: %zu\n", api::timers::pending());
    std::printf("  Nothing called forget_state. Each state carries a finalised\n"
                "  sentinel, so lua_close drops that state's timers on the way out.\n");

    function_timer_cases(scratch);

    fs::remove_all(scratch, ec);
    check(api::timers::pending() == 0, "all timers are gone after state teardown");
    return g_failures == 0 ? 0 : 1;
}
