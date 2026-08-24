#include "api/timers.hpp"

#include <algorithm>
#include <chrono>
#include <map>
#include <string>
#include <utility>
#include <vector>

#include "api/output.hpp"
#include "lua/host.hpp"
#include "platform/platform.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
}

namespace kp::api {

namespace {

struct Timer {
    std::uint64_t id = 0;
    lua_State*    L = nullptr;
    std::string   callback;
    std::uint64_t delay_ms = 0;
    std::uint64_t due_ms = 0;
    unsigned      call_count = 0;
    int           userdata_ref = LUA_NOREF;
};

// Ordered by id so a pump with several timers due at the same millisecond
// fires them in registration order. Deterministic ordering is not a nicety
// here: two timers due on the same frame that touch the same game state need a
// defined winner, and "whatever the container iterated" is not one.
std::map<std::uint64_t, Timer> g_timers;
std::uint64_t g_next_id = 1;

// The timer currently inside its callback. Single-threaded on purpose: pump()
// is called from the game's main loop, which is the only thread that runs Lua.
std::uint64_t g_firing_id = 0;
lua_State*    g_firing_state = nullptr;

unsigned g_budget = 8;   // matches HostConfig::error_budget

// The scheduler's clock. One value, written by pump() and read by
// registertimer, so a timer's due time is always expressed in the same units
// the pump compares it against.
std::uint64_t g_clock = 0;
bool          g_clock_set = false;

// A private registry key. Its address is the key, so a script cannot collide
// with it by writing to the registry.
const char kSentinelKey = 0;

// The finalised object that ties a state's timers to the state's lifetime.
// It holds the state it was installed on so the finaliser does not have to
// trust the lua_State it is called with -- during a normal collection that can
// be a coroutine, and dropping the coroutine's timers would drop nothing.
struct Sentinel {
    lua_State* owner;
};

int sentinel_gc(lua_State* L) {
    auto* s = static_cast<Sentinel*>(lua_touserdata(L, 1));
    if (s != nullptr && s->owner != nullptr) timers::forget_state(s->owner);
    return 0;
}

void install_sentinel(lua_State* L) {
    lua_pushlightuserdata(L, const_cast<char*>(&kSentinelKey));
    lua_rawget(L, LUA_REGISTRYINDEX);
    const bool already = !lua_isnil(L, -1);
    lua_pop(L, 1);
    if (already) return;

    lua_pushlightuserdata(L, const_cast<char*>(&kSentinelKey));
    auto* s = static_cast<Sentinel*>(lua_newuserdata(L, sizeof(Sentinel)));
    s->owner = L;

    lua_createtable(L, 0, 1);
    lua_pushcfunction(L, sentinel_gc);
    lua_setfield(L, -2, "__gc");
    lua_setmetatable(L, -2);

    lua_rawset(L, LUA_REGISTRYINDEX);
}

// Which state owns the timers for this one. Coroutines share a registry with
// the state that spawned them, so a timer registered from inside a coroutine
// belongs to the script, not to the coroutine -- which will usually be dead
// long before the timer fires.
lua_State* owner_state(lua_State* L) {
    lua_pushlightuserdata(L, const_cast<char*>(&kSentinelKey));
    lua_rawget(L, LUA_REGISTRYINDEX);
    auto* s = static_cast<Sentinel*>(lua_touserdata(L, -1));
    lua_pop(L, 1);
    return s != nullptr ? s->owner : L;
}

// Same handler as the host's dispatch loop uses. Without it a timer error is
// "attempt to call a nil value" with no line number, and the author has no way
// to tell which of their timers is broken.
int traceback_handler(lua_State* L) {
    const char* msg = lua_tostring(L, 1);
    luaL_traceback(L, L, msg != nullptr ? msg : "(non-string error)", 1);
    return 1;
}

void cancel_timer(std::uint64_t id) {
    auto it = g_timers.find(id);
    if (it == g_timers.end()) return;
    if (it->second.userdata_ref != LUA_NOREF)
        luaL_unref(it->second.L, LUA_REGISTRYINDEX, it->second.userdata_ref);
    g_timers.erase(it);
}

// A timer that throws is charged to its script's error budget under the
// callback's own name, so `n` failures of one timer quarantine the script on
// exactly the same rule as `n` failures of OnTick. The alternative is the
// failure mode the host exists to prevent: a broken timer that renews itself
// and prints the same traceback forever.
void report_error(lua_State* L, const std::string& callback,
                  const char* message, std::uint64_t game_tick) {
    const char* msg = message != nullptr ? message : "(no message)";
    platform::log(platform::LogLevel::Error, "timer '%s': %s", callback.c_str(), msg);
    if (lua::Script* s = lua::Script::owner(L); s != nullptr)
        s->record_error(callback, msg, game_tick, g_budget);
}

// Run one timer, if it is still there and still due. Returns whether a callback
// actually ran, which is what pump() counts.
bool fire_one(std::uint64_t id, std::uint64_t now, std::uint64_t game_tick) {
    auto it = g_timers.find(id);
    if (it == g_timers.end()) return false;      // an earlier callback cancelled it
    if (it->second.due_ms > now) return false;   // or rescheduled it past this pump

    lua_State* L = it->second.L;

    // A quarantined, unloaded or failed script keeps its timers until its state
    // closes, but does not run them. Phasor does the same, and the reason is
    // the same: quarantine that a timer can drive straight through is not
    // quarantine.
    if (lua::Script* s = lua::Script::owner(L);
        s != nullptr && s->state() != lua::ScriptState::Loaded) {
        return false;
    }

    const std::string  callback = it->second.callback;   // copied: the map is about
    const int          ud_ref   = it->second.userdata_ref;  // to be reachable from Lua
    const unsigned     count    = ++it->second.call_count;

    const int base = lua_gettop(L);
    lua_pushcfunction(L, traceback_handler);
    lua_getglobal(L, callback.c_str());
    if (!lua_isfunction(L, -1)) {
        lua_settop(L, base);
        // Phasor resolves the name at fire time too, so a typo is invisible
        // until the timer expires. Kept, because the alternative is refusing to
        // register a callback a script has not defined yet -- which is the
        // normal case when the chunk registers timers before defining them.
        report_error(L, callback, "callback is not a global function", game_tick);
        cancel_timer(id);
        return false;
    }

    lua_pushnumber(L, lua_Number(id));
    lua_pushnumber(L, lua_Number(count));
    if (ud_ref == LUA_NOREF) lua_pushnil(L);
    else                     lua_rawgeti(L, LUA_REGISTRYINDEX, ud_ref);

    g_firing_id = id;
    g_firing_state = L;
    const int rc = lua_pcall(L, 3, 1, base + 1);
    g_firing_id = 0;
    g_firing_state = nullptr;

    if (rc != 0) {
        const char* msg = lua_tostring(L, -1);
        report_error(L, callback, msg, game_tick);
        lua_settop(L, base);
        cancel_timer(id);
        return true;
    }

    // Renewal follows the same rule as an event result in src/lua/value.cpp:
    // a boolean is itself, a number is compared against 1. Returning 2 stops
    // the timer. Widening that would make the two places disagree about what
    // "true" means, which is worse than the surprise.
    bool renew = false;
    if (lua_isboolean(L, -1))     renew = lua_toboolean(L, -1) != 0;
    else if (lua_isnumber(L, -1)) renew = lua_tonumber(L, -1) == 1;
    lua_settop(L, base);

    auto again = g_timers.find(id);
    if (again == g_timers.end()) return true;
    if (renew) again->second.due_ms = now + again->second.delay_ms;
    else       cancel_timer(id);
    return true;
}

// ------------------------------------------------------------ lua surface ---

int l_registertimer(lua_State* L) {
    const int argc = lua_gettop(L);
    if (argc < 2)
        return luaL_error(L, "kotor.registertimer expects at least 2 arguments (got %d)", argc);
    if (argc > 3)
        return luaL_error(L, "kotor.registertimer expects at most 3 arguments (got %d)", argc);

    const lua_Number delay = luaL_checknumber(L, 1);
    if (!(delay >= 0))   // also rejects NaN, which would never come due
        return luaL_argerror(L, 1, "delay must be a non-negative number of milliseconds");
    if (lua_type(L, 2) != LUA_TSTRING)
        return luaL_argerror(L, 2, lua_pushfstring(L, "expected string, got %s",
                                                   luaL_typename(L, 2)));

    // Everything that can raise has raised by now, so nothing below leaks a
    // C++ object through a longjmp.
    const char* name  = lua_tostring(L, 2);
    lua_State*  owner = owner_state(L);

    // Exactly one userdata value, held as a registry reference so a table
    // survives until the timer fires. nil in the slot is the same as omitting
    // it, which is what makes registertimer(ms, name, maybe_nil) safe to write.
    int ref = LUA_NOREF;
    if (argc == 3 && !lua_isnil(L, 3)) {
        lua_pushvalue(L, 3);
        ref = luaL_ref(L, LUA_REGISTRYINDEX);
    }

    const std::uint64_t id = g_next_id++;
    Timer t;
    t.id = id;
    t.L = owner;
    t.callback = name;
    t.delay_ms = std::uint64_t(delay);
    t.due_ms = timers::clock() + t.delay_ms;
    t.userdata_ref = ref;
    g_timers.emplace(id, std::move(t));

    lua_pushnumber(L, lua_Number(id));
    return 1;
}

int l_removetimer(lua_State* L) {
    const int argc = lua_gettop(L);
    if (argc > 1)
        return luaL_error(L, "kotor.removetimer expects at most 1 argument (got %d)", argc);

    // Deliberately forgiving, matching Phasor: no argument, nil, a non-number,
    // an unknown id and another script's id are all ignored. Cancelling a timer
    // that has already fired is the normal case, not an error.
    if (argc == 0 || lua_isnil(L, 1) || !lua_isnumber(L, 1)) return 0;
    const lua_Number raw = lua_tonumber(L, 1);
    if (!(raw >= 0)) return 0;
    const auto id = std::uint64_t(raw);

    auto it = g_timers.find(id);
    if (it == g_timers.end() || it->second.L != owner_state(L)) return 0;

    // The one case that is an error rather than a no-op. Cancelling the timer
    // whose callback is on the stack would free the entry the fire path is
    // about to reschedule, and the script already has a way to say this:
    // return false.
    if (g_firing_id == id)
        return luaL_error(L, "attempt to remove timer %d within its own callback; "
                             "return false from the callback instead", int(id));

    cancel_timer(id);
    return 0;
}

}  // namespace

namespace timers {

std::uint64_t now_ms() {
    using namespace std::chrono;
    return std::uint64_t(
        duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count());
}

void set_clock(std::uint64_t now) { g_clock = now; g_clock_set = true; }

std::uint64_t clock() {
    if (!g_clock_set) set_clock(now_ms());
    return g_clock;
}

void set_error_budget(unsigned budget) { g_budget = budget; }

unsigned pump(std::uint64_t now, std::uint64_t game_tick) {
    set_clock(now);

    // Snapshot first. A callback may register timers, cancel timers, or get its
    // script quarantined, and none of that is allowed to invalidate the walk.
    // Newly registered timers land in the next pump, which also bounds a timer
    // that renews itself with a zero delay to one firing per frame.
    std::vector<std::pair<std::uint64_t, std::uint64_t>> due;   // (due_ms, id)
    for (const auto& entry : g_timers)
        if (entry.second.due_ms <= now) due.emplace_back(entry.second.due_ms, entry.first);
    std::sort(due.begin(), due.end());

    unsigned fired = 0;
    for (const auto& d : due)
        if (fire_one(d.second, now, game_tick)) ++fired;
    return fired;
}

void forget_state(lua_State* L) {
    for (auto it = g_timers.begin(); it != g_timers.end(); ) {
        if (it->second.L == L) it = g_timers.erase(it);
        else ++it;
    }
    if (g_firing_state == L) { g_firing_state = nullptr; g_firing_id = 0; }
}

std::size_t pending() { return g_timers.size(); }

std::size_t pending(lua_State* L) {
    std::size_t n = 0;
    for (const auto& entry : g_timers)
        if (entry.second.L == L) ++n;
    return n;
}

}  // namespace timers

void register_timers(lua_State* L) {
    install_sentinel(L);
    push_kotor_table(L);
    lua_pushcfunction(L, l_registertimer); lua_setfield(L, -2, "registertimer");
    lua_pushcfunction(L, l_removetimer);   lua_setfield(L, -2, "removetimer");
    lua_pop(L, 1);
}

}  // namespace kp::api
