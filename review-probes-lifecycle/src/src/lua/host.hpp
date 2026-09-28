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
#include <deque>
#include <filesystem>
#include <functional>
#include <map>
#include <memory>
#include <string>
#include <unordered_map>
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
    // `on_state_created` is borrowed from the owning Host's config and may be
    // null. It outlives every Script the Host holds.
    //
    // `on_state_closing` is borrowed the same way. It runs exactly once
    // immediately before every lua_close of a state this Script created, so a
    // caller can count creates and closes and expect them to match.
    Script(std::string name, std::string path,
           const std::function<void(lua_State*)>* on_state_created = nullptr,
           const std::function<void(lua_State*)>* on_state_closing = nullptr);
    ~Script();

    Script(const Script&) = delete;
    Script& operator=(const Script&) = delete;

    // Build a new generation and switch to it only if it works.
    //
    // The chunk is compiled and run in a FRESH lua_State. The running state,
    // if any, is closed only after that succeeds. A syntax error or a throwing
    // chunk leaves the previous generation running, with its handlers and
    // timers intact, and reports the error. With no previous generation the
    // script becomes FailedToLoad, as before.
    //
    // Host code that needs to raise OnScriptUnload between "the new chunk
    // worked" and "the old state closes" uses stage() and commit_staged()
    // directly. load() is stage() then commit_staged() with nothing between.
    bool load(std::string& error);
    bool stage(std::string& error);
    void commit_staged();
    bool staged() const { return staged_L_ != nullptr; }

    // Close the state and mark the script Unloaded, whatever it was before.
    void unload();

    const std::string& name() const { return name_; }
    const std::string& path() const { return path_; }
    ScriptState        state() const { return state_; }
    int                priority() const { return priority_; }
    lua_State*         L() const { return L_; }

    // Incremented on every successful load, so a caller can tell "reloaded"
    // from "never unloaded". 0 until the first successful load.
    std::uint64_t      generation() const { return generation_; }
    // The last load or reload error. Cleared by a successful load.
    const std::string& last_load_error() const { return last_load_error_; }

    // True when the script will handle this callback, either because it defined
    // a global of that name at load time or because it registered a handler
    // afterwards. Answered from sets and maps; no Lua call is made.
    bool defines(const std::string& callback) const {
        return defined_.count(callback) != 0 || bound_.count(callback) != 0;
    }

    // Bind a Lua function to an event at RUNTIME, taking ownership of a registry
    // reference to it.
    //
    // The load-time probe cannot see these. A script can register a handler
    // from inside another callback -- typically OnScriptLoad -- so the handler
    // does not exist as a global when the probe runs. Without this, every such
    // script loads cleanly and then receives nothing.
    //
    // Rebinding the same event replaces the previous handler and releases its
    // reference. Passing LUA_NOREF unbinds.
    void bind_callback(const std::string& event, int registry_ref);
    bool bound(const std::string& event) const { return bound_.count(event) != 0; }

    // Push the handler for `callback` onto the stack. Returns false and pushes
    // nothing when there is none.
    bool push_handler(const std::string& callback) const;

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
    void close_state(lua_State*);

    std::string name_, path_;
    lua_State*  L_ = nullptr;
    // A new generation between stage() and commit_staged(). While its chunk
    // runs (staging_chunk_), bind_callback() targets it: the chunk that
    // registers a handler at its top level is running in this state, not in
    // L_. After the chunk returns, the old generation's OnScriptUnload may
    // still run, and what IT binds or unbinds belongs to the old state.
    lua_State*  staged_L_ = nullptr;
    bool        staging_chunk_ = false;
    std::unordered_map<std::string, int> staged_bound_;
    std::uint64_t generation_ = 0;
    std::string last_load_error_;
    ScriptState state_ = ScriptState::Unloaded;
    int         priority_ = 0;
    std::unordered_set<std::string> defined_;
    std::unordered_map<std::string, int> bound_;   // event -> registry ref
    std::vector<ScriptError> errors_;
    const std::function<void(lua_State*)>* on_state_created_ = nullptr;
    const std::function<void(lua_State*)>* on_state_closing_ = nullptr;
};

struct HostConfig {
    std::string script_dir;
    unsigned    error_budget = 8;   // errors in one callback before quarantine
    bool        hot_reload = true;

    // Called on each freshly created lua_State, after the standard libraries
    // are open and before the script's own chunk runs.
    //
    // This exists so the host stays domain-free. Calling the game's API
    // registration from here directly would make src/lua/ depend on src/api/,
    // and this host is otherwise usable by anything that wants prioritised,
    // arbitrated Lua callbacks. The runtime installs the hook; the host never
    // learns what it does.
    std::function<void(lua_State*)> on_state_created;

    // Called exactly once immediately before every lua_close: unload, reload,
    // quarantine release, unload_all, and a new generation that failed to load.
    // Symmetric with on_state_created. Appended last so positional aggregate
    // initialisers written before it still compile.
    std::function<void(lua_State*)> on_state_closing;
};

// A lifecycle change a script or the console asked for. These are always
// deferred: request() only queues, and service_requests() runs them from the
// tick, outside every Lua callback. Closing a state synchronously from inside
// its own callback or timer would free the stack that is still running.
enum class LifecycleOp { Load, Unload, Reload };
enum class RequestStatus { Pending, Ok, Error };

struct RequestResult {
    std::uint64_t id = 0;
    LifecycleOp   op = LifecycleOp::Load;
    std::string   name;
    RequestStatus status = RequestStatus::Pending;
    std::string   error;
    std::uint64_t generation = 0;   // the script's generation after the op
};

class Host {
public:
    explicit Host(HostConfig);
    ~Host();

    // Load every .lua in the script directory. Returns how many loaded; scripts
    // that fail are reported through errors() and do not stop the others.
    unsigned load_all(std::vector<std::string>& errors);
    // Load one file. Refuses a path or script name that is already held;
    // use reload_one for that. load_one is kept as the older spelling.
    bool     load_path(const std::string& path, std::string& error);
    bool     load_one(const std::string& path, std::string& error);
    void     unload_all();

    // Per-script operations by name (the file stem). Synchronous, so they are
    // for C++ callers outside dispatch only; each refuses while a Lua callback
    // is running. Lua goes through request().
    //
    //   unload_one: raise OnScriptUnload, close the state, keep the entry as
    //               Unloaded. Hot reload leaves an unloaded script alone.
    //   reload_one: build a new generation (see Script::load); works on a
    //               Loaded, Unloaded, FailedToLoad or Quarantined script.
    bool     unload_one(const std::string& name, std::string& error);
    bool     reload_one(const std::string& name, std::string& error);

    Script*  find(const std::string& name) const;

    // Deferred lifecycle requests. request() never touches a state. Load of a
    // name the host does not hold looks for <script_dir>/<name>.lua.
    std::uint64_t request(LifecycleOp op, std::string name);
    // Run the requests queued before this call. Requests queued while it runs
    // (from OnScriptLoad or OnScriptUnload) wait for the next call. Returns how
    // many ran; 0 and does nothing while a Lua callback is running.
    unsigned      service_requests();
    // nullptr for an id this host never issued or has aged out.
    const RequestResult* result(std::uint64_t id) const;
    std::size_t   pending_requests() const { return queue_.size(); }

    const std::string& script_dir() const { return cfg_.script_dir; }

    // True while the host is inside a Lua call it made: dispatch, a lifecycle
    // raise, or a chunk running during load.
    bool busy() const { return depth_ != 0; }

    // Reload scripts whose file changed. Safe to call from the tick hook.
    // Failed reloads are appended to `errors` when it is not null.
    unsigned reload_changed(std::vector<std::string>* errors = nullptr);

    // Raise OnScriptLoad / OnScriptUnload on the single script that needs them.
    // Boot enables this after the first Load so register_callback bindings
    // survive a hot reload. Pointers may be null; then the raises are no-ops.
    void set_lifecycle(const events::EventContract* load,
                       const events::EventContract* unload,
                       std::string game, std::string build);

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
    bool do_load_path(const std::string& path, std::string& error);
    bool do_reload(Script&, std::string& error);
    void do_unload(Script&);
    void run_request(RequestResult&);
    std::unique_ptr<Script> make_script(const std::string& path);
    void stamp(const std::string& path);
    void raise_load(Script&);
    void raise_unload(Script&);
    void dispatch_one(Script&, const events::EventContract&,
                      const std::vector<class Value>& args);
    std::vector<std::string> list_script_paths() const;

    HostConfig cfg_;
    std::vector<std::unique_ptr<Script>> scripts_;
    std::map<std::string, std::filesystem::file_time_type> stamps_;
    std::uint64_t tick_ = 0;
    unsigned depth_ = 0;
    std::uint64_t next_request_ = 1;
    std::deque<RequestResult> queue_;   // pending, in arrival order
    std::deque<RequestResult> inflight_;   // the batch service_requests is running
    std::deque<RequestResult> done_;    // finished, oldest first, capped
    const events::EventContract* load_event_ = nullptr;
    const events::EventContract* unload_event_ = nullptr;
    std::string game_;
    std::string build_;
    bool lifecycle_ = false;
};

}  // namespace kp::lua
