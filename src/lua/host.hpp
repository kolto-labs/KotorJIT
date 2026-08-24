// The Lua host: loading scripts, calling them, and surviving their mistakes.
//
// Each script gets its own lua_State. They share no globals, so one script
// cannot clobber another's variables by accident, and a host function can always
// tell which script called it by looking itself up in that state's registry.
//
// Three properties the rest of the runtime depends on:
//
//   * A script error never reaches game code. Every call goes through
//     lua_pcall, and a script that keeps failing is unloaded rather than left to
//     log the same traceback on every frame.
//   * Callbacks a script does not define cost a set lookup, not a Lua call. We
//     probe once at load and remember. Without this, a per-tick event would
//     charge every script for a callback none of them wrote.
//   * Dispatch order is declared, not incidental. A script sets `priority`;
//     ties break on filename. Nothing depends on directory iteration order.
#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <unordered_set>
#include <vector>

#include "events/contract.hpp"

struct lua_State;

namespace kp::lua {

// Why a script is not currently running.
enum class ScriptState {
    Loaded,
    FailedToLoad,   // syntax error, or the chunk itself threw
    Quarantined,    // exceeded the error budget while running
    Unloaded,
};

struct ScriptError {
    std::string callback;
    std::string message;    // includes a traceback where Lua gave us one
    std::uint64_t at_tick = 0;
};

class Script {
public:
    Script(std::string name, std::string path);
    ~Script();

    Script(const Script&) = delete;
    Script& operator=(const Script&) = delete;

    bool load(std::string& error);
    void unload();

    const std::string& name() const { return name_; }
    const std::string& path() const { return path_; }
    ScriptState        state() const { return state_; }
    int                priority() const { return priority_; }
    lua_State*         L() const { return L_; }

    // True when the script defined this callback. Answered from the set built
    // at load time; no Lua call is made.
    bool defines(const std::string& callback) const {
        return defined_.count(callback) != 0;
    }

    // Errors seen so far, and the budget before quarantine. Quarantine exists
    // because the alternative -- what the design we are following actually
    // shipped -- is a script failing in a per-tick callback and printing a
    // traceback forever.
    unsigned error_count() const { return errors_.size(); }
    const std::vector<ScriptError>& errors() const { return errors_; }
    void record_error(const std::string& callback, const std::string& msg,
                      std::uint64_t tick, unsigned budget);

    // Close the lua_State without changing state_. Quarantine is decided while
    // the script's own stack is being unwound, so the close has to happen after
    // dispatch finishes rather than at the moment of the decision.
    void release_state();

    // Recover the owning Script from a lua_State, for host functions.
    static Script* owner(lua_State*);

private:
    void probe_callbacks(const std::vector<std::string>& known);

    std::string name_, path_;
    lua_State*  L_ = nullptr;
    ScriptState state_ = ScriptState::Unloaded;
    int         priority_ = 0;
    std::unordered_set<std::string> defined_;
    std::vector<ScriptError> errors_;
};

struct HostConfig {
    std::string script_dir;
    unsigned    error_budget = 8;   // errors in one callback before quarantine
    bool        hot_reload = true;
};

class Host {
public:
    explicit Host(HostConfig);
    ~Host();

    // Load every .lua in the script directory. Returns how many loaded; scripts
    // that fail are reported through errors() and do not stop the others.
    unsigned load_all(std::vector<std::string>& errors);
    bool     load_one(const std::string& path, std::string& error);
    void     unload_all();

    // Reload scripts whose file changed. Safe to call from the tick hook.
    unsigned reload_changed();

    // The dispatch rule lives here. See events/contract.hpp for the statement
    // of it; this is the implementation, and the two must not drift.
    events::Outcome dispatch(const events::EventContract&,
                             const std::vector<class Value>& args);

    // Scripts in dispatch order: priority descending, then filename.
    const std::vector<std::unique_ptr<Script>>& scripts() const { return scripts_; }

    // Every callback name the runtime can raise. This is generated from the
    // event table and is the single source for both dispatch and the
    // undefined-callback probe -- a name in one but not the other is the bug
    // class this arrangement is designed to make impossible.
    static const std::vector<std::string>& known_callbacks();

    std::uint64_t tick() const { return tick_; }
    void          advance_tick() { ++tick_; }

private:
    void sort_scripts();

    HostConfig cfg_;
    std::vector<std::unique_ptr<Script>> scripts_;
    std::uint64_t tick_ = 0;
};

}  // namespace kp::lua
