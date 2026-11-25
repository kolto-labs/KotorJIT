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

// File identity the way the platform's own filesystem reports it: st_dev
// plus st_ino on POSIX, the NTFS volume serial plus the 64-bit file index on
// _WIN32 (dwVolumeSerialNumber, nFileIndexHigh/Low from
// GetFileInformationByHandle -- the identity a hard link and its original
// share, and the identity a delete-then-recreate does NOT share, whatever
// the two files' path strings or mtimes happen to say). `ok` is false when
// the platform could not be asked -- the file could not be opened right now,
// or (POSIX) stat failed -- and every caller treats that as "cannot verify",
// never as "must be a different file": a same_file() built on a silent path
// or case-insensitive string compare is exactly the bug this replaces.
struct FileIdentity {
    bool ok = false;
#ifdef _WIN32
    unsigned long volume_serial = 0;
    unsigned long index_high = 0;
    unsigned long index_low = 0;
#else
    std::uint64_t dev = 0;
    std::uint64_t ino = 0;
#endif
    bool operator==(const FileIdentity& o) const {
        if (!ok || !o.ok) return false;
#ifdef _WIN32
        return volume_serial == o.volume_serial && index_high == o.index_high &&
               index_low == o.index_low;
#else
        return dev == o.dev && ino == o.ino;
#endif
    }
    bool operator!=(const FileIdentity& o) const { return !(*this == o); }
};

// What the hot-reload poll remembers about a held script's file, taken the
// moment it was (re)loaded (see Host::stamp). reload_changed's poll compares
// all four fields against what is on disk now, in this order: identity
// first (an identity change -- including one side becoming unverifiable --
// is always a change, full stop); then size and mtime, the cheap fields that
// already caught an ordinary edit; and only when identity, size and mtime
// all still agree with what is on disk does it fall back to `hash`, a
// bounded content digest, and only when that agreement is itself suspect
// (the file was seen missing since this stamp, or its mtime is close enough
// to "now" that the filesystem clock may not have had room to move). An
// untouched script's poll never reads its content: hash is checked, not
// recomputed, unless the identity/size/mtime triad alone could not settle
// the question.
struct FileStamp {
    FileIdentity id;
    std::uintmax_t size = 0;
    std::filesystem::file_time_type mtime{};
    std::uint64_t hash = 0;
    bool hash_valid = false;
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
    // True only while the new generation's chunk is running inside stage().
    // Host::dispatch and the lifecycle raises skip the script for exactly this
    // span (see Host::dispatch). It is narrower than staged(): the old
    // generation's OnScriptUnload runs after the chunk returns and before
    // commit_staged(), and it must still be delivered.
    bool staging_chunk() const { return staging_chunk_; }

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
    void collect_callbacks(std::unordered_set<std::string>& out) const {
        out.insert(defined_.begin(), defined_.end());
        for (const auto& kv : bound_) out.insert(kv.first);
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
    //
    // load_all and unload_all discard every request still queued: each
    // one's result becomes an error ("discarded: the script host reloaded"),
    // so a request made against the old set never acts on the new one.
    // Requests the new scripts make from their OnScriptLoad are kept.
    //
    // A .lua entry that is a symlink resolving outside the script directory
    // is not loaded and is reported in `errors`. The check is by path
    // component, not string prefix. It is not a security boundary: scripts
    // have io, os and kp.mem. It stops an accidental link from running a
    // file nobody put in the scripts folder.
    unsigned load_all(std::vector<std::string>& errors);
    // Load one file. Refuses a path or script name that is already held;
    // use reload_one for that. load_one is kept as the older spelling.
    //
    // "Held" is by file identity, not spelling: on POSIX a path that is the
    // same file (fs::equivalent: device and inode) as a held script is
    // refused, which covers hard links, in-directory symlinks and case
    // variants on a case-insensitive directory. On _WIN32 the comparison is
    // case-insensitive on the path and the name instead; hard-link aliases
    // are not detected there. load_path itself does not apply the symlink
    // containment rule below: a C++ caller may load any path it names.
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

    // Deferred lifecycle requests. request() never touches a state.
    //
    // Load of a name the host does not hold is resolved against the real
    // directory listing, never by building a path and opening it: the name
    // must be the stem of a listed .lua file (exact; case-insensitive on
    // _WIN32; on POSIX also any listed file that is the same file as
    // <script_dir>/<name>.lua). The script is then held under the on-disk
    // spelling. A name holding NUL, a slash or backslash, ':' or ".." is refused.
    //
    // Bounds, so a script cannot bury the tick in lifecycle work:
    //   * a request identical (op and name) to one still queued returns that
    //     request's id instead of queueing again;
    //   * at most kMaxQueued requests wait; beyond that a request fails at
    //     once with "request queue full";
    //   * a script cannot schedule its own load or reload from its own
    //     OnScriptLoad, or from the OnScriptUnload that a reload raises: that
    //     would reload it on every service forever. The request fails at once.
    // A failed-at-once request still has an id and a result.
    std::uint64_t request(LifecycleOp op, std::string name);
    // Run at most kMaxPerService of the requests queued before this call, in
    // arrival order. Leftovers stay at the front of the queue. Requests queued
    // while it runs (from OnScriptLoad or OnScriptUnload) go behind them and
    // wait for a later call. Returns how many ran; 0 and does nothing while a
    // Lua callback is running.
    unsigned      service_requests();
    // nullptr for an id this host never issued or has aged out.
    const RequestResult* result(std::uint64_t id) const;

    static constexpr std::size_t kMaxQueued = 64;
    static constexpr unsigned    kMaxPerService = 16;
    // A held script's file must be missing on this many consecutive polls
    // before the poll treats it as deleted. See reload_changed.
    static constexpr unsigned    kMissingPollsToDrop = 2;
    std::size_t   pending_requests() const { return queue_.size(); }

    const std::string& script_dir() const { return cfg_.script_dir; }
    unsigned           error_budget() const { return cfg_.error_budget; }

    // True while the host is inside a Lua call it made: dispatch, a lifecycle
    // raise, or a chunk running during load.
    bool busy() const { return depth_ != 0; }

    // Reload scripts whose file changed. Safe to call from the tick hook.
    // Failed reloads are appended to `errors` when it is not null.
    //
    // Editor saves are not atomic, so the poll is deliberately slow to act:
    //   * a held file must be absent on kMissingPollsToDrop consecutive polls
    //     before its script is dropped. One absent poll changes nothing: the
    //     running generation, an explicit Unloaded state and R1 all survive a
    //     rename-away-then-write save that a poll lands inside;
    //   * a file of size 0 is taken to be mid-write. It neither reloads a held
    //     script nor loads a new one, and it is not stamped, so the next poll
    //     looks again. To stop a script, unload it or delete the file.
    // Residual: a half-written file that is non-empty and happens to compile
    // loads as a partial generation; the writer's final write changes mtime
    // and the next poll replaces it. If the filesystem's mtime granularity is
    // coarser than the gap between the partial and final write, that final
    // write is missed until the next edit. A half-written file that does not
    // compile is covered by R1 (the running generation stays).
    //
    // A new file that is the same file as a held script (alias, case variant)
    // or a symlink escaping the directory is skipped without an error, so the
    // poll does not log it every time.
    unsigned reload_changed(std::vector<std::string>* errors = nullptr);

    // Raise OnScriptLoad / OnScriptUnload on the single script that needs them.
    // Boot enables this after the first Load so register_callback bindings
    // survive a hot reload. Pointers may be null; then the raises are no-ops.
    void set_lifecycle(const events::EventContract* load,
                       const events::EventContract* unload,
                       std::string game, std::string build);

    // The dispatch rule lives here. See events/contract.hpp for the statement
    // of it; this is the implementation, and the two must not drift.
    //
    // A script whose next generation's chunk is running (Script::
    // staging_chunk) is skipped, as it was before hot reload staged: then the
    // script was Unloaded while its chunk ran. A chunk can re-enter dispatch
    // synchronously (top-level ExecuteScript raising OnRunScript), and the
    // old generation's handler would otherwise run with bind_callback aimed
    // at the staged generation's map.
    events::Outcome dispatch(const events::EventContract&,
                             const std::vector<class Value>& args);

    // Scripts in dispatch order: priority descending, then filename.
    const std::vector<std::unique_ptr<Script>>& scripts() const { return scripts_; }

    // Distinct event names currently handled by at least one Loaded script
    // (global functions + runtime kp.on bindings).
    std::unordered_set<std::string> subscribed_events() const;
    bool has_subscriber(std::string_view callback) const;
    static std::uint64_t subscription_revision();
    static void set_subscription_notify(void (*fn)());

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
    void finish(RequestResult&&);
    void discard_queue(const char* why);
    Script* find_request(const std::string& name) const;
    // Script* on a file-identity match (Same), else nullptr (Different or
    // Unknown). When `unknown` is given, it is set true when at least one
    // held script's identity could not be compared against `path` -- the
    // caller decides what "cannot verify" means for it: do_load_path treats
    // it as a typed refusal (see there); the poll's alias skip and the
    // request resolver treat it the same as a match, so a script whose
    // identity is briefly unreadable is neither double-loaded nor logged as
    // an error every poll.
    Script* held_same_file(const std::string& path, bool* unknown = nullptr) const;
    std::string resolve_script_file(const std::string& name) const;
    std::unique_ptr<Script> make_script(const std::string& path);
    void stamp(const std::string& path);
    void raise_load(Script&);
    void raise_unload(Script&);
    void dispatch_one(Script&, const events::EventContract&,
                      const std::vector<class Value>& args);
    // Every .lua regular file in the script directory, sorted, excluding
    // symlinks that resolve outside it (appended to `refused` when given).
    std::vector<std::string> list_script_paths(std::vector<std::string>* refused = nullptr) const;

    HostConfig cfg_;
    std::vector<std::unique_ptr<Script>> scripts_;
    std::map<std::string, FileStamp> stamps_;
    std::map<std::string, unsigned> missing_;   // path -> consecutive absent polls
    // Paths the poll saw absent at least once since their last content
    // check. Set when a poll's missing-count is bumped; cleared only once a
    // check on the reappeared file actually runs (never on the poll that
    // merely notices the file exists again) -- so a hash read that fails
    // (e.g. a sharing violation mid-write) leaves the flag standing and the
    // next poll tries again, rather than silently trusting a stamp taken
    // before the file went away.
    std::unordered_set<std::string> needs_content_check_;
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
    // The script whose OnScriptLoad, or reload-raised OnScriptUnload, is
    // running. request() refuses a load or reload of it (see request()).
    const Script* raising_self_ = nullptr;
};

}  // namespace kp::lua
