#include "api/output.hpp"

#include <string>
#include <string_view>
#include <vector>

#include "api/strings.hpp"
#include "api/timers.hpp"
#include "platform/platform.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
}

namespace kp::api {

namespace {

ConsoleWriter g_console = nullptr;
void*         g_console_user = nullptr;

// Where AurPostString goes when the caller did not say. Taken from
// data/hostapi.toml, which declares x=0, y=0, life=5.0 for the same routine, so
// this is a data-sourced default rather than a guess. The units are still the
// engine's own and unverifiable without the game running.
constexpr int    kDefaultX = 0;
constexpr int    kDefaultY = 0;
constexpr double kDefaultLife = 5.0;

// Split a message the way Phasor's ProcessedString pop does: on '\n', into
// independent messages. A trailing newline does not produce a trailing empty
// message, because "line\n" is one line everywhere else in the world.
//
// '\r' is dropped at the end of a segment so a script that built its text with
// CRLF does not put a stray control character on the console.
std::vector<std::string> split_lines(const char* text) {
    std::vector<std::string> lines;
    std::string current;
    for (const char* p = text; *p != '\0'; ++p) {
        if (*p == '\n') {
            if (!current.empty() && current.back() == '\r') current.pop_back();
            lines.push_back(current);
            current.clear();
            continue;
        }
        current.push_back(*p);
    }
    if (!current.empty()) {
        if (current.back() == '\r') current.pop_back();
        lines.push_back(current);
    }
    if (lines.empty()) lines.emplace_back();   // an empty message is still a message
    return lines;
}

// Fetch kotor.<name> and leave it on the stack. False, with nothing left
// behind, when the name is absent or is not callable.
//
// By name and at call time. The routines bridge registers into the same table
// and the two modules have no registration order between them, so a cached
// lookup would degrade to log-only in the real runtime while still passing
// every test that registers output first.
bool push_routine(lua_State* L, const char* name) {
    lua_getglobal(L, "kotor");
    if (!lua_istable(L, -1)) { lua_pop(L, 1); return false; }
    lua_getfield(L, -1, name);
    lua_remove(L, -2);
    if (lua_isfunction(L, -1)) return true;
    lua_pop(L, 1);
    return false;
}

// GetFirstPC (routine 548). SendMessageToPC needs a recipient and there is
// exactly one, but the object id is the engine's to hand out.
bool first_pc(lua_State* L, lua_Number& out) {
    if (!push_routine(L, "GetFirstPC")) return false;
    if (lua_pcall(L, 0, 1, 0) != 0) { lua_pop(L, 1); return false; }
    if (!lua_isnumber(L, -1)) { lua_pop(L, 1); return false; }
    out = lua_tonumber(L, -1);
    lua_pop(L, 1);
    return true;
}

// Routine 374 SendMessageToPC(object oPlayer, string szMessage).
bool send_to_pc(lua_State* L, const std::string& line) {
    lua_Number pc = 0;
    if (!first_pc(L, pc)) return false;
    if (!push_routine(L, "SendMessageToPC")) return false;
    lua_pushnumber(L, pc);
    lua_pushlstring(L, line.c_str(), line.size());
    // pcall, not call: a routine that raises here would otherwise escape a
    // diagnostic function, and losing the message to the log is better than
    // turning a print into a script error.
    if (lua_pcall(L, 2, 0, 0) != 0) { lua_pop(L, 1); return false; }
    return true;
}

// Routine 582 AurPostString(string sString, int nX, int nY, float fLife).
bool aur_post(lua_State* L, const std::string& line, int x, int y, double life) {
    if (!push_routine(L, "AurPostString")) return false;
    lua_pushlstring(L, line.c_str(), line.size());
    lua_pushnumber(L, lua_Number(x));
    lua_pushnumber(L, lua_Number(y));
    lua_pushnumber(L, lua_Number(life));
    if (lua_pcall(L, 4, 0, 0) != 0) { lua_pop(L, 1); return false; }
    return true;
}

platform::LogLevel level_from(lua_State* L, int index) {
    const char* name = luaL_optstring(L, index, "info");
    const std::string_view level(name);
    if (level == "debug") return platform::LogLevel::Debug;
    if (level == "info")  return platform::LogLevel::Info;
    if (level == "warn")  return platform::LogLevel::Warn;
    if (level == "error") return platform::LogLevel::Error;
    luaL_argerror(L, index, "expected one of debug, info, warn, error");
    return platform::LogLevel::Info;   // not reached; luaL_argerror does not return
}

// kotor.log(text [, level]) -> nothing
//
// Always available, including before hooks are installed and after they are
// removed. This is the surface a script can rely on when nothing else works.
int l_log(lua_State* L) {
    const char* text = luaL_checkstring(L, 1);
    if (lua_gettop(L) > 2) return luaL_error(L, "kotor.log expects at most 2 arguments (got %d)",
                                             lua_gettop(L));
    const platform::LogLevel level = level_from(L, 2);
    for (const std::string& line : split_lines(text))
        platform::log(level, "%s", line.c_str());
    return 0;
}

// kotor.console(text) -> boolean
//
// True when the console surface took it, false when it went to the log
// instead. Phasor's output functions return nothing; a script here can tell
// whether its reply actually reached the player, which is worth the deviation
// on a runtime where the console is a detour that may not be installed yet.
int l_console(lua_State* L) {
    const char* text = luaL_checkstring(L, 1);
    if (lua_gettop(L) > 1) return luaL_error(L, "kotor.console expects at most 1 argument (got %d)",
                                             lua_gettop(L));
    console_write(text);
    lua_pushboolean(L, console_bound() ? 1 : 0);
    return 1;
}

// kotor.feedback(text [, x, y, life]) -> boolean
//
// Without a position this is routine 374 SendMessageToPC, which the mapping
// rates high confidence and which is the closest true equivalent of any Phasor
// messaging call. With a position it is routine 582 AurPostString, because a
// caller asking for a screen position should get the routine that takes one.
int l_feedback(lua_State* L) {
    const char* text = luaL_checkstring(L, 1);
    const int   argc = lua_gettop(L);
    if (argc != 1 && argc != 3 && argc != 4)
        return luaL_error(L, "kotor.feedback expects 1, 3 or 4 arguments (got %d)", argc);

    const bool   positioned = argc >= 3;
    const int    x    = positioned ? int(luaL_checknumber(L, 2)) : kDefaultX;
    const int    y    = positioned ? int(luaL_checknumber(L, 3)) : kDefaultY;
    const double life = argc >= 4 ? double(luaL_checknumber(L, 4)) : kDefaultLife;

    const std::vector<std::string> lines = split_lines(text);
    const int base = lua_gettop(L);

    bool reached = true;
    for (const std::string& line : lines) {
        const bool sent = positioned ? aur_post(L, line, x, y, life)
                                     : send_to_pc(L, line);
        if (!sent) {
            reached = false;
            platform::log(platform::LogLevel::Info, "[feedback] %s", line.c_str());
        }
    }

    // The engine helpers restore their own stack, but a pcall failure path is
    // exactly where an off-by-one would hide. Restoring here as well costs
    // nothing and makes the invariant local to this function.
    lua_settop(L, base);
    lua_pushboolean(L, reached ? 1 : 0);
    return 1;
}

}  // namespace

// ---------------------------------------------------------------- shared ----

void push_kotor_table(lua_State* L) {
    lua_getglobal(L, "kotor");
    if (lua_istable(L, -1)) return;
    lua_pop(L, 1);
    lua_newtable(L);
    lua_pushvalue(L, -1);
    lua_setglobal(L, "kotor");
}

// ---------------------------------------------------------------- console ---

void bind_console(ConsoleWriter writer, void* user) {
    g_console = writer;
    g_console_user = user;
}

void unbind_console() {
    g_console = nullptr;
    g_console_user = nullptr;
}

bool console_bound() { return g_console != nullptr; }

void console_write(const char* text) {
    if (text == nullptr) return;
    for (const std::string& line : split_lines(text)) {
        if (g_console != nullptr) g_console(line.c_str(), g_console_user);
        else platform::log(platform::LogLevel::Info, "[console] %s", line.c_str());
    }
}

// --------------------------------------------------------------- register ---

void register_output(lua_State* L) {
    push_kotor_table(L);
    lua_pushcfunction(L, l_log);      lua_setfield(L, -2, "log");
    lua_pushcfunction(L, l_console);  lua_setfield(L, -2, "console");
    lua_pushcfunction(L, l_feedback); lua_setfield(L, -2, "feedback");
    lua_pop(L, 1);
}

void register_support(lua_State* L) {
    register_output(L);
    register_timers(L);
    register_strings(L);
}

}  // namespace kp::api
