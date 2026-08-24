#include "lua/host.hpp"

#include <algorithm>
#include <filesystem>
#include <map>

#include "lua/value.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}

namespace fs = std::filesystem;

namespace kp::lua {

namespace {

// A private registry key. Its address is the key, so nothing a script can write
// will collide with it.
const char kOwnerKey = 0;

// Push a message handler that decorates an error with a traceback. Without one,
// lua_pcall returns just "attempt to index a nil value" and the script author
// has no idea which line produced it.
int traceback_handler(lua_State* L) {
    const char* msg = lua_tostring(L, 1);
    luaL_traceback(L, L, msg ? msg : "(non-string error)", 1);
    return 1;
}

}  // namespace

// ---------------------------------------------------------------- Script ----

Script::Script(std::string name, std::string path)
    : name_(std::move(name)), path_(std::move(path)) {}

Script::~Script() { unload(); }

Script* Script::owner(lua_State* L) {
    lua_pushlightuserdata(L, const_cast<char*>(&kOwnerKey));
    lua_rawget(L, LUA_REGISTRYINDEX);
    auto* s = static_cast<Script*>(lua_touserdata(L, -1));
    lua_pop(L, 1);
    return s;
}

void Script::probe_callbacks(const std::vector<std::string>& known) {
    defined_.clear();
    for (const auto& cb : known) {
        lua_getglobal(L_, cb.c_str());
        if (lua_isfunction(L_, -1)) defined_.insert(cb);
        lua_pop(L_, 1);
    }
}

bool Script::load(std::string& error) {
    unload();

    L_ = luaL_newstate();
    if (!L_) { error = "out of memory creating lua state"; state_ = ScriptState::FailedToLoad; return false; }
    luaL_openlibs(L_);

    // Let host functions find us again from a bare lua_State.
    lua_pushlightuserdata(L_, const_cast<char*>(&kOwnerKey));
    lua_pushlightuserdata(L_, this);
    lua_rawset(L_, LUA_REGISTRYINDEX);

    if (luaL_loadfile(L_, path_.c_str()) != 0) {
        error = lua_tostring(L_, -1) ? lua_tostring(L_, -1) : "load failed";
        lua_close(L_); L_ = nullptr;
        state_ = ScriptState::FailedToLoad;
        return false;
    }

    lua_pushcfunction(L_, traceback_handler);
    lua_insert(L_, -2);
    if (lua_pcall(L_, 0, 0, -2) != 0) {
        error = lua_tostring(L_, -1) ? lua_tostring(L_, -1) : "chunk failed";
        lua_close(L_); L_ = nullptr;
        state_ = ScriptState::FailedToLoad;
        return false;
    }
    lua_pop(L_, 1);  // traceback handler

    // Dispatch order must not depend on how the filesystem happened to list
    // files, so a script says where it wants to sit. Absent, it sits at 0 and
    // ties break on filename.
    lua_getglobal(L_, "priority");
    priority_ = lua_isnumber(L_, -1) ? int(lua_tonumber(L_, -1)) : 0;
    lua_pop(L_, 1);

    probe_callbacks(Host::known_callbacks());
    errors_.clear();
    state_ = ScriptState::Loaded;
    return true;
}

void Script::release_state() {
    if (L_) { lua_close(L_); L_ = nullptr; }
    defined_.clear();
}

void Script::unload() {
    release_state();
    if (state_ == ScriptState::Loaded) state_ = ScriptState::Unloaded;
}

void Script::record_error(const std::string& callback, const std::string& msg,
                          std::uint64_t tick, unsigned budget) {
    errors_.push_back({callback, msg, tick});

    // Count failures in THIS callback, not overall. A script that misbehaves in
    // one rare event should not be killed by a slow accumulation across
    // unrelated ones, but a script failing every frame in a tick callback must
    // be stopped -- otherwise it prints the same traceback forever, which is
    // exactly the failure mode this design exists to avoid.
    const auto n = std::count_if(errors_.begin(), errors_.end(),
                                 [&](const ScriptError& e) { return e.callback == callback; });
    if (n >= static_cast<long>(budget)) {
        // Mark only. This is called from inside dispatch, with the failing
        // script's own lua_State still on the stack being unwound -- closing it
        // here leaves dispatch cleaning up a freed state. The Host closes
        // quarantined states once the dispatch loop has finished.
        state_ = ScriptState::Quarantined;
    }
}

// ------------------------------------------------------------------ Host ----

Host::Host(HostConfig cfg) : cfg_(std::move(cfg)) {}
Host::~Host() { unload_all(); }

const std::vector<std::string>& Host::known_callbacks() {
    // Generated from the event table at build time. Dispatch and the
    // undefined-callback probe both read this one list; a name present in one
    // and missing from the other is the bug this arrangement rules out.
    static const std::vector<std::string> kCallbacks = {
#include "generated/callbacks.inc"
    };
    return kCallbacks;
}

void Host::sort_scripts() {
    std::stable_sort(scripts_.begin(), scripts_.end(),
                     [](const auto& a, const auto& b) {
                         if (a->priority() != b->priority())
                             return a->priority() > b->priority();
                         return a->name() < b->name();
                     });
}

bool Host::load_one(const std::string& path, std::string& error) {
    auto s = std::make_unique<Script>(fs::path(path).stem().string(), path);
    if (!s->load(error)) return false;
    scripts_.push_back(std::move(s));
    sort_scripts();
    return true;
}

unsigned Host::load_all(std::vector<std::string>& errors) {
    unload_all();
    if (cfg_.script_dir.empty() || !fs::is_directory(cfg_.script_dir)) {
        errors.push_back("script directory not found: " + cfg_.script_dir);
        return 0;
    }

    // Collect and sort paths first. Directory iteration order is not defined,
    // and load order affects nothing else only because we sort afterwards --
    // doing it here as well keeps error reporting stable between runs.
    std::vector<std::string> paths;
    for (const auto& e : fs::directory_iterator(cfg_.script_dir))
        if (e.is_regular_file() && e.path().extension() == ".lua")
            paths.push_back(e.path().string());
    std::sort(paths.begin(), paths.end());

    unsigned loaded = 0;
    for (const auto& p : paths) {
        std::string err;
        if (load_one(p, err)) ++loaded;
        else errors.push_back(fs::path(p).filename().string() + ": " + err);
    }
    return loaded;
}

void Host::unload_all() { scripts_.clear(); }

events::Outcome Host::dispatch(const events::EventContract& ev,
                               const std::vector<Value>& args) {
    events::Outcome out;

    // `relevant` tells a script whether its return value can still matter. It
    // starts true and flips once someone claims. It is advisory: a later script
    // still runs, and its return is discarded whether or not it checks.
    bool relevant = true;

    for (const auto& sp : scripts_) {
        Script& s = *sp;
        if (s.state() != ScriptState::Loaded) continue;
        if (!s.defines(ev.lua_name)) continue;   // set lookup, no Lua call

        lua_State* L = s.L();
        const int base = lua_gettop(L);

        lua_pushcfunction(L, traceback_handler);
        lua_getglobal(L, ev.lua_name.c_str());
        for (const auto& a : args) a.push(L);
        lua_pushboolean(L, relevant);            // trailing argument

        const int nargs = int(args.size()) + 1;
        const int nres  = int(ev.results.size());
        ++out.called;

        if (lua_pcall(L, nargs, nres, base + 1) != 0) {
            const char* msg = lua_tostring(L, -1);
            s.record_error(ev.lua_name, msg ? msg : "(no message)",
                           tick_, cfg_.error_budget);
            lua_settop(L, base);
            continue;                            // other scripts still run
        }

        if (!out.claimed) {
            std::vector<Value> results;
            if (convert_tuple(L, base + 2, ev.results, results)) {
                // First usable answer wins. Later scripts still get called;
                // their answers are discarded.
                out.claimed = true;
                out.claimed_by = s.name();
                if (!results.empty()) {
                    std::visit([&out](auto&& v) {
                        using T = std::decay_t<decltype(v)>;
                        if constexpr (std::is_same_v<T, bool>)             out.bool_result = v;
                        else if constexpr (std::is_same_v<T, std::int64_t>) out.int_result = v;
                        else if constexpr (std::is_same_v<T, double>)       out.int_result = std::int64_t(v);
                        else if constexpr (std::is_same_v<T, std::uint32_t>) out.int_result = v;
                        else if constexpr (std::is_same_v<T, std::string>)  out.string_result = v;
                    }, results.front().storage());
                }
                relevant = false;
            } else {
                ++out.abstained;
            }
        }
        lua_settop(L, base);
    }

    // Now that no script's stack is in use, release anything that hit its error
    // budget during this dispatch. Deferring to here is what makes it safe to
    // quarantine a script from inside its own failing call.
    for (auto& sp : scripts_)
        if (sp->state() == ScriptState::Quarantined && sp->L())
            sp->release_state();

    // Nobody answered, so the event falls back to its declared default.
    if (!out.claimed) {
        switch (ev.fallback) {
        case events::Fallback::True:     out.bool_result = true;  break;
        case events::Fallback::False:    out.bool_result = false; break;
        case events::Fallback::Identity: break;  // caller keeps its input
        case events::Fallback::None:     break;
        }
    }
    return out;
}

unsigned Host::reload_changed() {
    if (!cfg_.hot_reload) return 0;
    static std::map<std::string, fs::file_time_type> stamps;

    unsigned reloaded = 0;
    for (auto& sp : scripts_) {
        std::error_code ec;
        const auto t = fs::last_write_time(sp->path(), ec);
        if (ec) continue;
        auto it = stamps.find(sp->path());
        if (it == stamps.end()) { stamps[sp->path()] = t; continue; }
        if (it->second == t) continue;
        it->second = t;

        // Reloading clears the error history too, so fixing a script is enough
        // to bring it out of quarantine without restarting the game.
        std::string err;
        if (sp->load(err)) ++reloaded;
    }
    if (reloaded) sort_scripts();   // priority may have changed
    return reloaded;
}

}  // namespace kp::lua
