// Exercises the support module -- output, timers, strings -- without the game.
//
// Everything in this module is either a pure function over a string or a
// scheduler driven by a clock, so both are checkable offline. What is NOT
// checkable offline is where the text ends up: the console surface needs the
// console.do_console detour and the feedback surface needs the VM bound. This
// tool proves the routing decision instead -- that feedback finds the routine
// by name when it is there and falls back to the log when it is not -- by
// installing stand-in kotor.GetFirstPC and kotor.SendMessageToPC from Lua.
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

// The log sink the runtime would install. Here it prints to stdout so the log
// lines and the script's own print() land in one readable stream; in the game
// this is what appends to kotorphasor.log.
void tool_log_sink(platform::LogLevel level, const char* message, void*) {
    std::printf("  [log:%s] %s\n", platform::to_string(level), message);
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
    local once = kotor.registertimer(100, "on_once", { tag = "payload" })
    local rep  = kotor.registertimer(250, "on_repeat")
    local doomed = kotor.registertimer(300, "on_never")
    kotor.removetimer(doomed)
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
    kotor.removetimer()        -- no argument
    kotor.removetimer(nil)     -- nil
    kotor.removetimer(99999)   -- an id nobody owns
    kotor.removetimer(1)       -- id 1 is 10_timers' on_once, and stays alive
    print("  [20_remove_inside] four ignored removes: none, nil, unknown, another script's id")
    kotor.registertimer(150, "on_self")
end

function on_self(id, count)
    kotor.removetimer(id)
    print("  [20_remove_inside] THIS SHOULD NOT PRINT")
end
)LUA"},

{"30_throws.lua", R"LUA(
-- Four timers on one broken callback, against an error budget of 3.
function start()
    kotor.registertimer(100, "on_boom")
    kotor.registertimer(200, "on_boom")
    kotor.registertimer(300, "on_boom")
    kotor.registertimer(400, "on_boom")
end

function on_boom(id, count)
    error("deliberate failure")
end
)LUA"},

{"40_survives.lua", R"LUA(
-- Never comes due within the run. Here to show the state's timers go away when
-- the state closes, without anybody calling forget_state.
function start()
    kotor.registertimer(999000, "never_due")
end

function never_due() end
)LUA"},

{"50_output.lua", R"LUA(
-- The three output surfaces, and the routine lookup feedback does by name.
function start()
    kotor.log("log line, default level")
    kotor.log("two lines\nin one call", "warn")
    print(("  [50_output] console reached the console surface: %s")
          :format(tostring(kotor.console("console line"))))
    print(("  [50_output] feedback reached the engine: %s")
          :format(tostring(kotor.feedback("feedback with no routines registered"))))
end

-- Stand-ins for what src/api/routines.cpp will register. feedback looks the
-- name up at call time, so installing them after registration still works.
function install_fake_routines()
    kotor.GetFirstPC = function() return 1 end
    kotor.SendMessageToPC = function(pc, msg)
        print(("  [50_output] SendMessageToPC(%d, %q)"):format(pc, msg))
    end
    kotor.AurPostString = function(s, x, y, life)
        print(("  [50_output] AurPostString(%q, %d, %d, %.1f)"):format(s, x, y, life))
    end
end

function talk()
    print(("  [50_output] feedback reached the engine: %s")
          :format(tostring(kotor.feedback("hello from the routine path"))))
    print(("  [50_output] positioned feedback: %s")
          :format(tostring(kotor.feedback("top left", 0, 1, 2.5))))
end
)LUA"},
};

// Call a zero-argument global on one script's state, reporting rather than
// swallowing a failure. The runtime never does this -- it dispatches events --
// but the harness needs an entry point that runs after registration.
void call_entry(lua::Script& s, const char* fn, bool required) {
    lua_State* L = s.L();
    if (L == nullptr) return;
    const int base = lua_gettop(L);
    lua_getglobal(L, fn);
    if (!lua_isfunction(L, -1)) {
        lua_settop(L, base);
        if (required) std::printf("  [%s] has no %s()\n", s.name().c_str(), fn);
        return;
    }
    if (lua_pcall(L, 0, 0, 0) != 0)
        std::printf("  [%s] %s() failed: %s\n", s.name().c_str(), fn,
                    lua_tostring(L, -1) ? lua_tostring(L, -1) : "?");
    lua_settop(L, base);
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

    lua::Host host({scratch.string(), /*error_budget=*/3, /*hot_reload=*/false});
    std::vector<std::string> errors;
    const unsigned loaded = host.load_all(errors);
    for (const std::string& e : errors) std::printf("  load error: %s\n", e.c_str());
    std::printf("loaded %u script(s), error budget 3\n", loaded);

    // What the runtime does inside Script::load, before the chunk runs. Here it
    // happens after, so each script exposes start() rather than registering at
    // its top level.
    for (const auto& s : host.scripts()) api::register_support(s->L());
    std::printf("registered kotor.log/console/feedback, registertimer/removetimer, "
                "tokenizestring/tokenizecmdstring on %u state(s)\n", loaded);

    rule("output");
    std::printf("console is unbound, so console text goes to the log:\n");
    for (const auto& s : host.scripts()) call_entry(*s, "start", false);

    std::printf("\nnow with the console writer bound, as the do_console detour would:\n");
    api::bind_console(&tool_console_writer, nullptr);
    for (const auto& s : host.scripts())
        if (s->name() == "50_output") call_entry(*s, "start", false);

    std::printf("\nand with stand-in routines installed in the kotor table:\n");
    for (const auto& s : host.scripts())
        if (s->name() == "50_output") {
            call_entry(*s, "install_fake_routines", true);
            call_entry(*s, "talk", true);
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

    fs::remove_all(scratch, ec);
    return api::timers::pending() == 0 ? 0 : 1;
}
