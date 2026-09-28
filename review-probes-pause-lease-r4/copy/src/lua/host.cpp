#include "lua/host.hpp"

#include <algorithm>
#include <cctype>
#include <filesystem>
#include <system_error>
#include <map>
#include <unordered_set>

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

// One spelling per file. The held set, the stamp map and the duplicate check
// all compare paths as strings, so "dir/./a.lua" and "dir/a.lua" must meet.
std::string normal_path(const std::string& p) {
    return fs::path(p).lexically_normal().string();
}

// A name kp.scripts accepts: a bare file stem, never a path. NUL is checked
// on its own: find_first_of with a C string stops at the terminator and can
// never match it, and a NUL would cut the path the OS sees short.
bool bare_name(const std::string& n) {
    if (n.empty() || n == "." || n == "..") return false;
    if (n.find('\0') != std::string::npos) return false;
    return n.find_first_of("/\\:") == std::string::npos && n.find("..") == std::string::npos;
}

#ifdef _WIN32
bool iequals(const std::string& a, const std::string& b) {
    if (a.size() != b.size()) return false;
    for (std::size_t i = 0; i < a.size(); ++i) {
        const auto x = static_cast<unsigned char>(a[i]), y = static_cast<unsigned char>(b[i]);
        if (std::tolower(x) != std::tolower(y)) return false;
    }
    return true;
}
#endif

// Script names are compared the way the platform looks files up.
bool same_name(const std::string& a, const std::string& b) {
#ifdef _WIN32
    return iequals(a, b);
#else
    return a == b;
#endif
}

// Two paths name one file. POSIX asks the filesystem (device and inode), which
// catches hard links, symlinks and case variants on a case-insensitive
// directory. On _WIN32 the libstdc++ equivalent() cannot be exercised here, so
// it is not trusted; the lookup rule there is case-insensitive, and that is
// what is compared.
bool same_file(const std::string& a, const std::string& b) {
    if (a == b) return true;
#ifdef _WIN32
    return iequals(a, b);
#else
    std::error_code ec;
    const bool eq = fs::equivalent(a, b, ec);
    return !ec && eq;
#endif
}

// `p` lies under `root`, compared by path component so "/s2" is not under
// "/s". Both are resolved first, so a symlink is judged by where it lands.
bool resolves_inside(const fs::path& root_in, const fs::path& p) {
    std::error_code ec;
    fs::path root = fs::weakly_canonical(root_in, ec);
    if (ec) return false;
    const fs::path target = fs::weakly_canonical(p, ec);
    if (ec) return false;
    if (root.filename().empty()) root = root.parent_path();
    auto r = root.begin();
    auto t = target.begin();
    for (; r != root.end(); ++r, ++t)
        if (t == target.end() || *r != *t) return false;
    return t != target.end();
}

// Sets a marker for the span of one lifecycle raise and restores it.
struct RaiseMark {
    const Script*& slot;
    const Script* saved;
    RaiseMark(const Script*& s, const Script* v) : slot(s), saved(s) { slot = v; }
    ~RaiseMark() { slot = saved; }
};

// Counts the host's own calls into Lua, so the synchronous lifecycle methods
// can refuse to run underneath one.
struct DepthGuard {
    unsigned& d;
    explicit DepthGuard(unsigned& depth) : d(depth) { ++d; }
    ~DepthGuard() { --d; }
};

constexpr std::size_t kResultsKept = 64;

const char* busy_error() {
    return "host busy: a script callback is running; lifecycle changes from Lua "
           "go through the deferred request queue";
}

}  // namespace

// ---------------------------------------------------------------- Script ----

Script::Script(std::string name, std::string path,
               const std::function<void(lua_State*)>* on_state_created,
               const std::function<void(lua_State*)>* on_state_closing)
    : name_(std::move(name)), path_(std::move(path)),
      on_state_created_(on_state_created), on_state_closing_(on_state_closing) {}

Script::~Script() {
    if (staged_L_) { close_state(staged_L_); staged_L_ = nullptr; staged_bound_.clear(); }
    unload();
}

// The one place a state this Script created is closed. Every close goes
// through here so on_state_closing runs exactly once per state, while the
// state is still whole.
void Script::close_state(lua_State* L) {
    if (!L) return;
    if (on_state_closing_ && *on_state_closing_) (*on_state_closing_)(L);
    lua_close(L);
}

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
    if (!stage(error)) return false;
    commit_staged();
    return true;
}

bool Script::stage(std::string& error) {
    // A leftover staged state means a caller staged and never committed.
    if (staged_L_) { close_state(staged_L_); staged_L_ = nullptr; staged_bound_.clear(); }
    staging_chunk_ = false;

    // Failure leaves a running generation exactly as it was. Only a script
    // with nothing running becomes FailedToLoad.
    auto fail = [&](std::string msg) {
        error = std::move(msg);
        last_load_error_ = error;
        if (!L_) state_ = ScriptState::FailedToLoad;
        return false;
    };

    lua_State* N = luaL_newstate();
    if (!N) return fail("out of memory creating lua state");
    luaL_openlibs(N);

    // debug.getmetatable and debug.setmetatable bypass a protected __metatable
    // field, which is the only thing stopping a script from replacing the
    // metatable on a userdata handle and hijacking every field access through
    // it. Nothing legitimate here needs them, so they go before any script
    // chunk runs. The rest of the debug library stays: tracebacks come from it.
    lua_getglobal(N, "debug");
    if (lua_istable(N, -1)) {
        lua_pushnil(N); lua_setfield(N, -2, "getmetatable");
        lua_pushnil(N); lua_setfield(N, -2, "setmetatable");
        lua_pushnil(N); lua_setfield(N, -2, "getregistry");
    }
    lua_pop(N, 1);

    // Let host functions find us again from a bare lua_State.
    lua_pushlightuserdata(N, const_cast<char*>(&kOwnerKey));
    lua_pushlightuserdata(N, this);
    lua_rawset(N, LUA_REGISTRYINDEX);

    // Until the chunk returns, bind_callback() lands in the new state.
    staged_L_ = N;
    staging_chunk_ = true;
    if (on_state_created_ && *on_state_created_) (*on_state_created_)(N);

    auto discard = [&](const char* fallback) {
        staging_chunk_ = false;
        std::string msg = lua_tostring(N, -1) ? lua_tostring(N, -1) : fallback;
        staged_bound_.clear();          // refs die with the state
        staged_L_ = nullptr;
        close_state(N);
        return fail(std::move(msg));
    };

    if (luaL_loadfile(N, path_.c_str()) != 0) return discard("load failed");

    lua_pushcfunction(N, traceback_handler);
    lua_insert(N, -2);
    if (lua_pcall(N, 0, 0, -2) != 0) return discard("chunk failed");
    lua_pop(N, 1);  // traceback handler
    staging_chunk_ = false;
    return true;
}

void Script::commit_staged() {
    if (!staged_L_) return;
    // The old generation goes first, through the closing hook. Its bindings
    // are refs in its own registry, so they go with it.
    release_state();

    L_ = staged_L_;
    staged_L_ = nullptr;
    bound_ = std::move(staged_bound_);
    staged_bound_.clear();

    // Dispatch order must not depend on how the filesystem happened to list
    // files, so a script says where it wants to sit. Absent, it sits at 0 and
    // ties break on filename.
    lua_getglobal(L_, "priority");
    priority_ = lua_isnumber(L_, -1) ? int(lua_tonumber(L_, -1)) : 0;
    lua_pop(L_, 1);

    probe_callbacks(Host::known_callbacks());
    errors_.clear();
    last_load_error_.clear();
    state_ = ScriptState::Loaded;
    ++generation_;
}

void Script::bind_callback(const std::string& event, int ref) {
    // While a new generation is being staged, the only Lua running is its
    // chunk, so a registration belongs to it -- not to the old state, whose
    // registry the ref index does not refer to.
    lua_State* L = staging_chunk_ ? staged_L_ : L_;
    auto& map = staging_chunk_ ? staged_bound_ : bound_;
    if (!L) return;
    auto it = map.find(event);
    if (it != map.end()) {
        luaL_unref(L, LUA_REGISTRYINDEX, it->second);
        map.erase(it);
    }
    if (ref != LUA_NOREF && ref != LUA_REFNIL) map[event] = ref;
}

bool Script::push_handler(const std::string& callback) const {
    if (!L_) return false;
    // A runtime binding wins over a same-named global, because a script that
    // registered one asked for it explicitly and the global may be the stub it
    // registered FROM.
    auto it = bound_.find(callback);
    if (it != bound_.end()) {
        lua_rawgeti(L_, LUA_REGISTRYINDEX, it->second);
        if (lua_isfunction(L_, -1)) return true;
        lua_pop(L_, 1);
        return false;
    }
    if (defined_.count(callback) == 0) return false;
    lua_getglobal(L_, callback.c_str());
    if (lua_isfunction(L_, -1)) return true;
    lua_pop(L_, 1);
    return false;
}

void Script::release_state() {
    // The refs live in this state's registry, so closing it releases them; we
    // just drop the map so a reload does not carry stale indices forward.
    bound_.clear();
    if (L_) { lua_State* L = L_; L_ = nullptr; close_state(L); }
    defined_.clear();
}

void Script::unload() {
    release_state();
    state_ = ScriptState::Unloaded;
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

void Host::set_lifecycle(const events::EventContract* load,
                         const events::EventContract* unload,
                         std::string game, std::string build) {
    load_event_ = load;
    unload_event_ = unload;
    game_ = std::move(game);
    build_ = std::move(build);
    lifecycle_ = true;
}

void Host::raise_load(Script& s) {
    if (!lifecycle_ || load_event_ == nullptr || s.state() != ScriptState::Loaded) return;
    const std::vector<Value> args = {
        Value::str(game_),
        Value::str(build_),
    };
    RaiseMark mark(raising_self_, &s);   // no self-reload from OnScriptLoad
    dispatch_one(s, *load_event_, args);
}

void Host::raise_unload(Script& s) {
    if (!lifecycle_ || unload_event_ == nullptr || !s.L()) return;
    dispatch_one(s, *unload_event_, {});
}

void Host::dispatch_one(Script& s, const events::EventContract& ev,
                        const std::vector<Value>& args) {
    if (!s.L() || s.staging_chunk() || !s.defines(ev.lua_name)) return;

    DepthGuard guard(depth_);
    lua_State* L = s.L();
    const int base = lua_gettop(L);
    lua_pushcfunction(L, traceback_handler);
    if (!s.push_handler(ev.lua_name)) { lua_settop(L, base); return; }
    for (const auto& a : args) a.push(L);
    lua_pushboolean(L, true);
    if (lua_pcall(L, int(args.size()) + 1, int(ev.results.size()), base + 1) != 0) {
        const char* msg = lua_tostring(L, -1);
        s.record_error(ev.lua_name, msg ? msg : "(no message)", tick_, cfg_.error_budget);
    }
    lua_settop(L, base);
    if (s.state() == ScriptState::Quarantined && s.L()) s.release_state();
}

std::vector<std::string> Host::list_script_paths(std::vector<std::string>* refused) const {
    std::vector<std::string> paths;
    std::error_code ec;
    if (cfg_.script_dir.empty() || !fs::is_directory(cfg_.script_dir, ec)) return paths;
    for (const auto& e : fs::directory_iterator(cfg_.script_dir, ec)) {
        if (e.path().extension() != ".lua") continue;
        std::error_code eec;
        if (!e.is_regular_file(eec)) continue;   // follows symlinks
        if (e.is_symlink(eec) && !resolves_inside(cfg_.script_dir, e.path())) {
            if (refused)
                refused->push_back(e.path().filename().string() +
                                   ": symlink resolves outside the script directory; not loaded");
            continue;
        }
        paths.push_back(normal_path(e.path().string()));
    }
    std::sort(paths.begin(), paths.end());
    return paths;
}

std::unique_ptr<Script> Host::make_script(const std::string& path) {
    return std::make_unique<Script>(fs::path(path).stem().string(), path,
                                    &cfg_.on_state_created, &cfg_.on_state_closing);
}

// Recorded BEFORE the file is read. Stamping afterwards would miss an edit
// that lands between the read and the stamp -- the same hole as the lazy stamp
// this replaces. A failed load is stamped too, so editing a broken script is
// seen and a broken file is not retried on every poll.
void Host::stamp(const std::string& path) {
    std::error_code ec;
    const auto t = fs::last_write_time(path, ec);
    if (!ec) stamps_[path] = t;
}

Script* Host::find(const std::string& name) const {
    for (const auto& sp : scripts_)
        if (sp->name() == name) return sp.get();
    return nullptr;
}

// A request's name, looked up the way the platform looks up files.
Script* Host::find_request(const std::string& name) const {
    if (Script* s = find(name)) return s;
    for (const auto& sp : scripts_)
        if (same_name(sp->name(), name)) return sp.get();
    return nullptr;
}

Script* Host::held_same_file(const std::string& path) const {
    for (const auto& sp : scripts_)
        if (same_file(sp->path(), path)) return sp.get();
    return nullptr;
}

// The listed .lua file a request name means, in its on-disk spelling, or ""
// when there is none. Built from the directory listing rather than by opening
// <dir>/<name>.lua, so the name can only select something load_all would load.
std::string Host::resolve_script_file(const std::string& name) const {
    const std::vector<std::string> listed = list_script_paths();
    for (const auto& p : listed)
        if (fs::path(p).stem().string() == name) return p;
    for (const auto& p : listed)
        if (same_name(fs::path(p).stem().string(), name)) return p;
#ifndef _WIN32
    // A case-insensitive directory on POSIX (casefold): the asked-for
    // spelling opens a listed file under another spelling.
    const std::string asked = normal_path((fs::path(cfg_.script_dir) / (name + ".lua")).string());
    std::error_code ec;
    if (fs::is_regular_file(asked, ec))
        for (const auto& p : listed)
            if (same_file(p, asked)) return p;
#endif
    return {};
}

bool Host::load_path(const std::string& path, std::string& error) {
    if (busy()) { error = busy_error(); return false; }
    return do_load_path(path, error);
}

bool Host::load_one(const std::string& path, std::string& error) {
    return load_path(path, error);
}

bool Host::do_load_path(const std::string& raw, std::string& error) {
    const std::string path = normal_path(raw);
    const std::string name = fs::path(path).stem().string();
    for (const auto& sp : scripts_) {
        if (same_file(sp->path(), path) || same_name(sp->name(), name)) {
            error = "already loaded as '" + sp->name() + "' (" + sp->path() +
                    "); use reload";
            return false;
        }
    }
    auto s = make_script(path);
    stamp(path);
    bool ok;
    {
        DepthGuard guard(depth_);   // the chunk runs here
        ok = s->load(error);
    }
    Script* raw_s = s.get();
    scripts_.push_back(std::move(s));
    sort_scripts();
    if (ok) raise_load(*raw_s);
    return ok;
}

// A new generation replaces the old one only once it has loaded. The order is
// fixed: new chunk runs, old gets OnScriptUnload, old state closes, new gets
// OnScriptLoad. A failure anywhere before the close leaves the old running.
//
// Hazard that follows from the order (review M7): the new chunk's TOP LEVEL
// runs before the old generation's OnScriptUnload. Native state the top level
// sets and the old OnScriptUnload undoes ends up undone. Scripts should do
// native setup in OnScriptLoad, which runs after the old generation is gone.
// While the chunk runs the old generation receives no events (dispatch skips
// a script whose chunk is staging); its timers are not paused, but the timer
// pump runs from the tick, not from inside a chunk.
bool Host::do_reload(Script& s, std::string& error) {
    stamp(s.path());
    bool ok;
    {
        DepthGuard guard(depth_);
        ok = s.stage(error);
    }
    if (!ok) return false;
    {
        // The old generation hears it is going; it may not queue its own
        // reload from here, or every reload would schedule the next.
        RaiseMark mark(raising_self_, &s);
        raise_unload(s);    // may quarantine and close the old state; fine
    }
    s.commit_staged();
    sort_scripts();         // priority may have changed
    raise_load(s);
    return true;
}

void Host::do_unload(Script& s) {
    raise_unload(s);
    s.unload();
}

bool Host::unload_one(const std::string& name, std::string& error) {
    if (busy()) { error = busy_error(); return false; }
    Script* s = find(name);
    if (!s) { error = "no script named '" + name + "'"; return false; }
    if (s->state() == ScriptState::Unloaded) { error = "'" + name + "' is not loaded"; return false; }
    do_unload(*s);
    return true;
}

bool Host::reload_one(const std::string& name, std::string& error) {
    if (busy()) { error = busy_error(); return false; }
    Script* s = find(name);
    if (!s) { error = "no script named '" + name + "'"; return false; }
    return do_reload(*s, error);
}

std::uint64_t Host::request(LifecycleOp op, std::string name) {
    // Coalesce: asking again for something still queued changes nothing.
    // Only the queue is searched; a request already running is a new ask.
    for (const auto& q : queue_)
        if (q.op == op && q.name == name) return q.id;

    RequestResult r;
    r.id = next_request_++;
    r.op = op;
    r.name = std::move(name);
    const std::uint64_t id = r.id;
    if (raising_self_ != nullptr && op != LifecycleOp::Unload &&
        same_name(raising_self_->name(), r.name)) {
        r.status = RequestStatus::Error;
        r.error = "'" + r.name + "' cannot load or reload itself from its own OnScriptLoad "
                  "or reload OnScriptUnload; it would reload on every service";
        finish(std::move(r));
        return id;
    }
    if (queue_.size() >= kMaxQueued) {
        r.status = RequestStatus::Error;
        r.error = "request queue full (" + std::to_string(kMaxQueued) + " pending)";
        finish(std::move(r));
        return id;
    }
    queue_.push_back(std::move(r));
    return id;
}

void Host::finish(RequestResult&& r) {
    done_.push_back(std::move(r));
    while (done_.size() > kResultsKept) done_.pop_front();
}

void Host::discard_queue(const char* why) {
    while (!queue_.empty()) {
        RequestResult r = std::move(queue_.front());
        queue_.pop_front();
        r.status = RequestStatus::Error;
        r.error = why;
        finish(std::move(r));
    }
}

void Host::run_request(RequestResult& r) {
    std::string err;
    bool ok = false;
    Script* target = nullptr;
    if (!bare_name(r.name)) {
        err = "'" + r.name + "' is not a script name";
        r.status = RequestStatus::Error;
        r.error = err;
        return;
    }
    target = find_request(r.name);
    std::string path;
    if (target == nullptr && r.op == LifecycleOp::Load) {
        path = resolve_script_file(r.name);
        // The listed file may already be held under its own spelling (a case
        // variant on a case-insensitive directory, or an alias).
        if (!path.empty()) target = held_same_file(path);
    }
    if (target != nullptr) {
        Script& s = *target;
        switch (r.op) {
        case LifecycleOp::Unload:
            if (s.state() == ScriptState::Unloaded) err = "'" + s.name() + "' is not loaded";
            else { do_unload(s); ok = true; }
            break;
        case LifecycleOp::Load:
            if (s.state() == ScriptState::Loaded) {
                err = "'" + r.name + "' is already loaded" +
                      (s.name() == r.name ? std::string() : " as '" + s.name() + "'") + "; use reload";
                break;
            }
            ok = do_reload(s, err);
            break;
        case LifecycleOp::Reload:
            ok = do_reload(s, err);
            break;
        }
    } else if (r.op == LifecycleOp::Load) {
        if (path.empty()) {
            err = "no script file " + (fs::path(cfg_.script_dir) / (r.name + ".lua")).string();
        } else {
            ok = do_load_path(path, err);
            target = find(fs::path(path).stem().string());
        }
    } else {
        err = "no script named '" + r.name + "'";
    }
    r.status = ok ? RequestStatus::Ok : RequestStatus::Error;
    r.error = ok ? std::string() : err;
    if (target != nullptr) r.generation = target->generation();
}

unsigned Host::service_requests() {
    if (busy() || !inflight_.empty()) return 0;   // no re-entry mid-batch
    // Snapshot of at most kMaxPerService from the front. A request made while
    // these run -- from OnScriptLoad or OnScriptUnload -- goes behind the
    // leftovers and waits for a later call, so this loop always ends.
    //
    // The batch stays a member while it runs, so result() still answers
    // "pending" for a request whose own OnScriptLoad asks about it.
    while (!queue_.empty() && inflight_.size() < kMaxPerService) {
        inflight_.push_back(std::move(queue_.front()));
        queue_.pop_front();
    }
    unsigned ran = 0;
    while (!inflight_.empty()) {
        run_request(inflight_.front());
        ++ran;
        RequestResult r = std::move(inflight_.front());
        inflight_.pop_front();
        finish(std::move(r));
    }
    return ran;
}

const RequestResult* Host::result(std::uint64_t id) const {
    for (const auto& r : inflight_) if (r.id == id) return &r;
    for (const auto& r : queue_) if (r.id == id) return &r;
    for (const auto& r : done_) if (r.id == id) return &r;
    return nullptr;
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
    const std::vector<std::string> paths = list_script_paths(&errors);

    unsigned loaded = 0;
    for (const auto& p : paths) {
        std::string err;
        if (do_load_path(p, err)) ++loaded;
        else errors.push_back(fs::path(p).filename().string() + ": " + err);
    }
    return loaded;
}

void Host::unload_all() {
    for (auto& sp : scripts_) raise_unload(*sp);
    scripts_.clear();
    stamps_.clear();
    missing_.clear();
    // After the raises, so what an OnScriptUnload queued goes too; before
    // load_all loads, so what a new OnScriptLoad queues is kept.
    discard_queue("discarded: the script host reloaded");
}

events::Outcome Host::dispatch(const events::EventContract& ev,
                               const std::vector<Value>& args) {
    events::Outcome out;
    DepthGuard guard(depth_);

    // `relevant` tells a script whether its return value can still matter. It
    // starts true and flips once someone claims. It is advisory: a later script
    // still runs, and its return is discarded whether or not it checks.
    bool relevant = true;

    for (const auto& sp : scripts_) {
        Script& s = *sp;
        if (s.state() != ScriptState::Loaded) continue;
        if (s.staging_chunk()) continue;         // see host.hpp: dispatch
        if (!s.defines(ev.lua_name)) continue;   // set lookup, no Lua call

        lua_State* L = s.L();
        const int base = lua_gettop(L);

        lua_pushcfunction(L, traceback_handler);
        if (!s.push_handler(ev.lua_name)) { lua_settop(L, base); continue; }
        for (const auto& a : args) a.push(L);
        lua_pushboolean(L, relevant);            // trailing argument

        const int nargs = int(args.size()) + 1;
        const int nres  = int(ev.results.size());
        ++out.called;

        if (lua_pcall(L, nargs, nres, base + 1) != 0) {
            const char* msg = lua_tostring(L, -1);
            s.record_error(ev.lua_name, msg ? msg : "(no message)",
                           tick_, cfg_.error_budget);
            ++out.errored;
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
        } else {
            // Someone already claimed. Still record whether this script had an
            // answer, so the totals reconcile and a reader can see how many
            // scripts were overruled rather than silent.
            std::vector<Value> discarded;
            if (convert_tuple(L, base + 2, ev.results, discarded)) ++out.ignored;
            else ++out.abstained;
        }
        lua_settop(L, base);
    }

    // Now that no script's stack is in use, release anything that hit its error
    // budget during this dispatch. Deferring to here is what makes it safe to
    // quarantine a script from inside its own failing call.
    for (auto& sp : scripts_)
        if (sp->state() == ScriptState::Quarantined && sp->L()) {
            raise_unload(*sp);
            sp->release_state();
        }

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

unsigned Host::reload_changed(std::vector<std::string>* errors) {
    if (!cfg_.hot_reload || busy()) return 0;

    unsigned changed = 0;
    std::unordered_set<std::string> held;
    for (const auto& sp : scripts_) held.insert(sp->path());

    for (const auto& path : list_script_paths()) {
        if (held.count(path)) continue;
        if (held_same_file(path) != nullptr) continue;   // alias or case variant
        std::error_code sec;
        if (fs::file_size(path, sec) == 0 || sec) continue;   // mid-write; next poll
        std::string err;
        if (do_load_path(path, err)) ++changed;
        else if (errors) errors->push_back(fs::path(path).filename().string() + ": " + err);
    }

    // Walk a snapshot of the scripts: reloading re-sorts scripts_, and a
    // deleted file removes its entry.
    std::vector<Script*> walk;
    for (const auto& sp : scripts_) walk.push_back(sp.get());

    std::vector<Script*> gone;
    for (Script* sp : walk) {
        std::error_code ec;
        const bool exists = fs::exists(sp->path(), ec);
        if (!ec && !exists) {
            // One absent poll can be an editor mid-save (rename away, write
            // new). Only a second consecutive one is a delete.
            if (++missing_[sp->path()] >= kMissingPollsToDrop) gone.push_back(sp);
            continue;
        }
        if (ec) continue;           // unreadable right now; not proof it is gone
        missing_.erase(sp->path());

        // An explicit unload sticks until someone asks for a load.
        if (sp->state() == ScriptState::Unloaded) continue;

        const auto t = fs::last_write_time(sp->path(), ec);
        if (ec) continue;
        auto it = stamps_.find(sp->path());
        if (it != stamps_.end() && it->second == t) continue;
        // Size 0 is a truncate-then-write caught between the two. Not
        // stamped, so the next poll sees the finished file as an edit.
        if (fs::file_size(sp->path(), ec) == 0 || ec) continue;

        // Reloading clears the error history too, so fixing a script is enough
        // to bring it out of quarantine without restarting the game. A failed
        // reload keeps the running generation (see do_reload).
        std::string err;
        if (do_reload(*sp, err)) ++changed;
        else if (errors) errors->push_back(sp->name() + ": " + err);
    }

    for (Script* sp : gone) {
        raise_unload(*sp);
        stamps_.erase(sp->path());
        missing_.erase(sp->path());
        scripts_.erase(std::remove_if(scripts_.begin(), scripts_.end(),
                                      [sp](const auto& p) { return p.get() == sp; }),
                       scripts_.end());
        ++changed;
    }
    return changed;
}

}  // namespace kp::lua
