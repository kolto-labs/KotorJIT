#include "api/timers.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
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
    std::string   callback;                  // global name, or a label for a function
    int           callback_ref = LUA_NOREF;  // registry ref to the function, if one was passed
    std::uint64_t delay_ms = 0;
    std::uint64_t due_ms = 0;
    std::uint64_t delay_ticks = 0;
    std::uint64_t due_tick = 0;
    bool          auto_repeat = false;
    bool          tick_based = false;
    bool          cancelled_in_cb = false;
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
std::uint64_t g_tick = 0;

// A private registry key. Its address is the key, so a script cannot collide
// with it by writing to the registry.
const char kSentinelKey = 0;

// The finalised object that ties a state's timers to the state's lifetime.
// It holds the state it was installed on so the finaliser does not have to
// trust the lua_State it is called with -- during a normal collection that can
// be a coroutine, and dropping the coroutine's timers would drop nothing.
//
// `closing` is set by the finaliser. lua_close runs every finaliser before it
// frees anything, and a script's own __gc can run AFTER this one and call
// kp.registertimer. Without the flag that timer would outlive the state and
// the next pump would dereference freed memory; with it, registration refuses.
struct Sentinel {
    lua_State* owner;
    bool       closing;
};

int sentinel_gc(lua_State* L) {
    auto* s = static_cast<Sentinel*>(lua_touserdata(L, 1));
    if (s == nullptr) return 0;
    s->closing = true;
    if (s->owner != nullptr) timers::forget_state(s->owner);
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
    s->closing = false;

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
Sentinel* sentinel_of(lua_State* L) {
    lua_pushlightuserdata(L, const_cast<char*>(&kSentinelKey));
    lua_rawget(L, LUA_REGISTRYINDEX);
    auto* s = static_cast<Sentinel*>(lua_touserdata(L, -1));
    lua_pop(L, 1);
    return s;
}

lua_State* owner_state(lua_State* L) {
    Sentinel* s = sentinel_of(L);
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

// Looks up a callback name, as a protected call. The lookup is ordinary
// global access, so a strict-globals __index on _G runs here and may raise;
// outside a pcall that error has nowhere to go but the panic handler, which
// ends the process.
int lookup_global(lua_State* L) {
    lua_getglobal(L, lua_tostring(L, 1));
    return 1;
}

// The only place a live timer's registry references are released, and the
// entry is erased in the same step, so each reference is released exactly once
// whichever way the timer ends: completion, removetimer, or a throw. A state
// that closes takes its references with it (forget_state erases without
// unref-ing, because the registry is being torn down).
void cancel_timer(std::uint64_t id) {
    auto it = g_timers.find(id);
    if (it == g_timers.end()) return;
    if (it->second.userdata_ref != LUA_NOREF)
        luaL_unref(it->second.L, LUA_REGISTRYINDEX, it->second.userdata_ref);
    if (it->second.callback_ref != LUA_NOREF)
        luaL_unref(it->second.L, LUA_REGISTRYINDEX, it->second.callback_ref);
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
    const bool ready = it->second.tick_based ? (it->second.due_tick <= game_tick)
                                             : (it->second.due_ms <= now);
    if (!ready) return false;   // or rescheduled it past this pump

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
    const int          fn_ref   = it->second.callback_ref;  // to be reachable from Lua
    const unsigned     count    = ++it->second.call_count;

    const int base = lua_gettop(L);
    lua_pushcfunction(L, traceback_handler);
    // A function value is pushed from its registry reference. Once it is on
    // the stack the call keeps it alive, whatever the callback does to its
    // own timer. A name is looked up now, as it always was, but inside a
    // protected call: _G's __index is script code and may raise.
    if (fn_ref != LUA_NOREF) {
        lua_rawgeti(L, LUA_REGISTRYINDEX, fn_ref);
    } else {
        lua_pushcfunction(L, lookup_global);
        lua_pushstring(L, callback.c_str());
        g_firing_id = id;              // removetimer(id) from __index raises,
        g_firing_state = L;            // as it would from the callback itself
        const int lrc = lua_pcall(L, 1, 1, base + 1);
        g_firing_id = 0;
        g_firing_state = nullptr;
        if (lrc != 0) {
            // Charged like a throw from the callback; the callback never ran,
            // so this is not counted as a firing.
            report_error(L, callback, lua_tostring(L, -1), game_tick);
            lua_settop(L, base);
            cancel_timer(id);
            return false;
        }
    }
    // __index may have registered or cancelled timers. Re-read the entry
    // rather than trust anything taken from it before the lookup.
    auto live = g_timers.find(id);
    if (live == g_timers.end()) { lua_settop(L, base); return false; }
    const int ud_ref = live->second.userdata_ref;
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
    if (again->second.cancelled_in_cb) {
        cancel_timer(id);
        return true;
    }
    if (!renew && again->second.auto_repeat && lua_isnoneornil(L, base + 1)) {
        renew = true;
    }
    if (renew) {
        if (again->second.tick_based)
            again->second.due_tick = game_tick + again->second.delay_ticks;
        else
            again->second.due_ms = now + again->second.delay_ms;
    } else {
        cancel_timer(id);
    }
    return true;
}

// ------------------------------------------------------------ lua surface ---

int l_registertimer(lua_State* L) {
    const int argc = lua_gettop(L);
    if (argc < 2)
        return luaL_error(L, "kp.registertimer expects at least 2 arguments (got %d)", argc);
    if (argc > 3)
        return luaL_error(L, "kp.registertimer expects at most 3 arguments (got %d)", argc);

    // Finite, and no more than 2^32 - 1 ms (about 49.7 days). NaN would never
    // come due; infinity and anything past 2^64 are undefined behaviour in the
    // conversion below and in practice fired at once. The cap keeps the cast
    // defined and clock() + delay far from overflow.
    const lua_Number delay = luaL_checknumber(L, 1);
    if (!std::isfinite(delay) || !(delay >= 0) || delay > lua_Number(timers::kMaxDelayMs))
        return luaL_argerror(L, 1, "delay must be a finite number of milliseconds "
                                   "from 0 to 4294967295");
    const int cb_type = lua_type(L, 2);
    if (cb_type != LUA_TSTRING && cb_type != LUA_TFUNCTION)
        return luaL_argerror(L, 2, lua_pushfstring(L, "expected string or function, got %s",
                                                   luaL_typename(L, 2)));
    if (Sentinel* s = sentinel_of(L); s != nullptr && s->closing)
        return luaL_error(L, "kp.registertimer: this script's state is closing");

    // A function is labelled by where it was defined. The label is what an
    // error is charged to, so every timer made from one closure definition
    // shares one error budget, exactly as every timer naming one global does.
    // Built before anything C++ is constructed: lua_pushfstring can raise.
    // A C function has no source line (every one is "[C]:-1"), so it is
    // labelled by its address instead: one C function, one budget.
    const char* name = nullptr;
    if (cb_type == LUA_TFUNCTION) {
        if (lua_iscfunction(L, 2)) {
            name = lua_pushfstring(L, "function [C] %p", lua_topointer(L, 2));
        } else {
            lua_Debug ar;
            lua_pushvalue(L, 2);             // ">S" pops the function it reads
            lua_getinfo(L, ">S", &ar);
            name = lua_pushfstring(L, "function %s:%d", ar.short_src, ar.linedefined);
        }
    } else {
        name = lua_tostring(L, 2);
    }

    // Argument checks are done. What can still raise is the two luaL_ref
    // calls below, and only on out-of-memory; if the second one does, the
    // first reference is held until the state closes. No C++ object with a
    // destructor exists until after them, so a longjmp here leaks nothing else.
    lua_State*  owner = owner_state(L);

    // Exactly one userdata value, held as a registry reference so a table
    // survives until the timer fires. nil in the slot is the same as omitting
    // it, which is what makes registertimer(ms, name, maybe_nil) safe to write.
    int ref = LUA_NOREF;
    if (argc == 3 && !lua_isnil(L, 3)) {
        lua_pushvalue(L, 3);
        ref = luaL_ref(L, LUA_REGISTRYINDEX);
    }
    int fn_ref = LUA_NOREF;
    if (cb_type == LUA_TFUNCTION) {
        lua_pushvalue(L, 2);
        fn_ref = luaL_ref(L, LUA_REGISTRYINDEX);
    }

    const std::uint64_t id = g_next_id++;
    Timer t;
    t.id = id;
    t.L = owner;
    t.callback = name;
    t.delay_ms = std::uint64_t(delay);
    t.due_ms = timers::clock() + t.delay_ms;
    t.userdata_ref = ref;
    t.callback_ref = fn_ref;
    g_timers.emplace(id, std::move(t));

    lua_pushnumber(L, lua_Number(id));
    return 1;
}

int l_removetimer(lua_State* L) {
    const int argc = lua_gettop(L);
    if (argc > 1)
        return luaL_error(L, "kp.removetimer expects at most 1 argument (got %d)", argc);

    // Deliberately forgiving, matching Phasor: no argument, nil, a non-number,
    // an unknown id and another script's id are all ignored. Cancelling a timer
    // that has already fired is the normal case, not an error.
    if (argc == 0 || lua_isnil(L, 1) || !lua_isnumber(L, 1)) return 0;
    const lua_Number raw = lua_tonumber(L, 1);
    if (!(raw >= 0) || !(raw < 18446744073709551616.0)) return 0;   // cast stays defined
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

int create_timer(lua_State* L, bool auto_repeat, bool tick_based, const char* fn_name) {
    const int argc = lua_gettop(L);
    if (argc < 2)
        return luaL_error(L, "%s expects at least 2 arguments (got %d)", fn_name, argc);
    if (argc > 3)
        return luaL_error(L, "%s expects at most 3 arguments (got %d)", fn_name, argc);

    const lua_Number delay = luaL_checknumber(L, 1);
    if (tick_based) {
        if (!std::isfinite(delay) || delay < 1.0 || std::floor(delay) != delay ||
            delay > lua_Number(timers::kMaxDelayMs))
            return luaL_argerror(L, 1, "ticks must be one or more");
    } else if (auto_repeat) {
        if (!std::isfinite(delay) || delay < 1.0 || delay > lua_Number(timers::kMaxDelayMs))
            return luaL_argerror(L, 1, "interval must be one or more");
    } else {
        if (!std::isfinite(delay) || !(delay >= 0) || delay > lua_Number(timers::kMaxDelayMs))
            return luaL_argerror(L, 1, "delay must be zero or more");
    }

    const int cb_type = lua_type(L, 2);
    if (cb_type != LUA_TSTRING && cb_type != LUA_TFUNCTION)
        return luaL_argerror(L, 2, lua_pushfstring(L, "expected string or function, got %s",
                                                   luaL_typename(L, 2)));
    if (Sentinel* s = sentinel_of(L); s != nullptr && s->closing)
        return luaL_error(L, "%s: this script's state is closing", fn_name);

    const char* name = nullptr;
    if (cb_type == LUA_TFUNCTION) {
        if (lua_iscfunction(L, 2)) {
            name = lua_pushfstring(L, "function [C] %p", lua_topointer(L, 2));
        } else {
            lua_Debug ar;
            lua_pushvalue(L, 2);
            lua_getinfo(L, ">S", &ar);
            name = lua_pushfstring(L, "function %s:%d", ar.short_src, ar.linedefined);
        }
    } else {
        name = lua_tostring(L, 2);
    }

    lua_State* owner = owner_state(L);
    int ref = LUA_NOREF;
    if (argc == 3 && !lua_isnil(L, 3)) {
        lua_pushvalue(L, 3);
        ref = luaL_ref(L, LUA_REGISTRYINDEX);
    }
    int fn_ref = LUA_NOREF;
    if (cb_type == LUA_TFUNCTION) {
        lua_pushvalue(L, 2);
        fn_ref = luaL_ref(L, LUA_REGISTRYINDEX);
    }

    const std::uint64_t id = g_next_id++;
    Timer t;
    t.id = id;
    t.L = owner;
    t.callback = name;
    t.callback_ref = fn_ref;
    t.userdata_ref = ref;
    t.auto_repeat = auto_repeat;
    t.tick_based = tick_based;
    if (tick_based) {
        t.delay_ticks = std::uint64_t(delay);
        t.due_tick = g_tick + t.delay_ticks;
    } else {
        t.delay_ms = std::uint64_t(delay);
        t.due_ms = timers::clock() + t.delay_ms;
    }
    g_timers.emplace(id, std::move(t));

    lua_pushnumber(L, lua_Number(id));
    return 1;
}

int l_timer_after(lua_State* L)       { return create_timer(L, false, false, "kp.timer.after"); }
int l_timer_every(lua_State* L)       { return create_timer(L, true,  false, "kp.timer.every"); }
int l_timer_after_ticks(lua_State* L) { return create_timer(L, false, true,  "kp.timer.after_ticks"); }

int l_timer_cancel(lua_State* L) {
    if (lua_gettop(L) == 0 || lua_isnil(L, 1) || !lua_isnumber(L, 1)) {
        lua_pushboolean(L, 0);
        return 1;
    }
    const lua_Number raw = lua_tonumber(L, 1);
    if (!(raw >= 0) || !(raw < 18446744073709551616.0)) {
        lua_pushboolean(L, 0);
        return 1;
    }
    const auto id = std::uint64_t(raw);
    auto it = g_timers.find(id);
    if (it == g_timers.end() || it->second.L != owner_state(L)) {
        lua_pushboolean(L, 0);
        return 1;
    }
    if (g_firing_id == id) {
        it->second.cancelled_in_cb = true;
        lua_pushboolean(L, 1);
        return 1;
    }
    cancel_timer(id);
    lua_pushboolean(L, 1);
    return 1;
}

int l_timer_list(lua_State* L) {
    lua_State* owner = owner_state(L);
    const std::uint64_t now = timers::clock();
    lua_newtable(L);
    int n = 0;
    for (const auto& entry : g_timers) {
        const Timer& t = entry.second;
        if (t.L != owner) continue;
        lua_createtable(L, 0, 4);
        lua_pushnumber(L, lua_Number(t.id));
        lua_setfield(L, -2, "id");
        const lua_Number due_in = t.tick_based
            ? lua_Number(t.due_tick > g_tick ? (t.due_tick - g_tick) : 0)
            : lua_Number(t.due_ms > now ? (t.due_ms - now) : 0);
        lua_pushnumber(L, due_in);
        lua_setfield(L, -2, "due_in_ms");
        lua_pushboolean(L, t.auto_repeat ? 1 : 0);
        lua_setfield(L, -2, "repeating");
        lua_pushinteger(L, int(t.call_count));
        lua_setfield(L, -2, "fired");
        lua_rawseti(L, -2, ++n);
    }
    return 1;
}

int l_timer_tick(lua_State* L) {
    lua_pushnumber(L, static_cast<lua_Number>(g_tick));
    return 1;
}

int l_timer_clock(lua_State* L) {
    lua_pushnumber(L, static_cast<lua_Number>(timers::clock()));
    return 1;
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

std::uint64_t tick() { return g_tick; }

void set_error_budget(unsigned budget) { g_budget = budget; }

unsigned pump(std::uint64_t now, std::uint64_t game_tick) {
    set_clock(now);
    g_tick = game_tick;

    // Snapshot first. A callback may register timers, cancel timers, or get its
    // script quarantined, and none of that is allowed to invalidate the walk.
    // Newly registered timers land in the next pump, which also bounds a timer
    // that renews itself with a zero delay to one firing per frame.
    std::vector<std::pair<std::uint64_t, std::uint64_t>> due;   // (due_key, id)
    for (const auto& entry : g_timers) {
        const Timer& t = entry.second;
        if (t.tick_based) {
            if (t.due_tick <= game_tick) due.emplace_back(t.due_tick, entry.first);
        } else {
            if (t.due_ms <= now) due.emplace_back(t.due_ms, entry.first);
        }
    }
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
    push_kp_table(L);
    lua_pushcfunction(L, l_registertimer); lua_setfield(L, -2, "registertimer");
    lua_pushcfunction(L, l_removetimer);   lua_setfield(L, -2, "removetimer");

    lua_getfield(L, -1, "timer");
    if (!lua_istable(L, -1)) {
        lua_pop(L, 1);
        lua_createtable(L, 0, 7);
        lua_pushvalue(L, -1);
        lua_setfield(L, -3, "timer");
    }
    lua_pushcfunction(L, l_timer_after);       lua_setfield(L, -2, "after");
    lua_pushcfunction(L, l_timer_every);       lua_setfield(L, -2, "every");
    lua_pushcfunction(L, l_timer_after_ticks); lua_setfield(L, -2, "after_ticks");
    lua_pushcfunction(L, l_timer_cancel);      lua_setfield(L, -2, "cancel");
    lua_pushcfunction(L, l_timer_list);        lua_setfield(L, -2, "list");
    lua_pushcfunction(L, l_timer_tick);        lua_setfield(L, -2, "tick");
    lua_pushcfunction(L, l_timer_clock);       lua_setfield(L, -2, "clock");
    lua_pop(L, 2);
}

}  // namespace kp::api
